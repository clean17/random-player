import aiohttp
import json
import re, os, sys, time, itertools
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit
from typing import List, Dict, Any, Optional, Set, Tuple
from playwright.async_api import async_playwright
import subprocess
import shutil
import asyncio
import requests
from datetime import datetime

today = datetime.now().strftime("%Y%m%d")
month = datetime.now().strftime("%y%m")
month_dir = f"logs/i/{month}"
os.makedirs(month_dir, exist_ok=True)
filename = f"{month_dir}/scrap_ig_{today}.log"

# sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from config.config import settings

COS_DIR = settings['COS_DIR']
IMAGE_DIR2 = settings['IMAGE_DIR2']
BASE_SAVE_DIR = IMAGE_DIR2
# BASE_SAVE_DIR = r"D:\temp"

# ======== 설정 ========
USER_DATA_DIR = str(Path("./ig_profile-14").resolve())  # 세션 저장 (2회차부터 자동 로그인)  # fx014 // dlsdn317!
# USER_DATA_DIR = str(Path("./ig_profile-1").resolve())  # fx015
# USER_DATA_DIR = str(Path("./ig_profile-16").resolve())  # fx016.. 사용하지마_법무부_
HEADLESS = False

USERNAME = settings['SCRAP_USERNAME']   # 인스타 로그인 계정
# USERNAME = 'fkaus014'
PASSWORD = settings['SCRAP_PASSWORD']   # 비밀번호
# PASSWORD = 'dlsdn317!'

# USERNAME = ""   # 인스타 로그인 계정
# PASSWORD = ""   # 비밀번호

# 스크롤/속도
SCROLL_PAUSE = 1.8
MAX_SCROLLS = 30001
DELAY_2_SECOND = 2
DELAY_10_SECOND = 10
DELAY_1_MINUTE = 60 * 1
DELAY_3_MINUTE = 60 * 3
DELAY_10_MINUTE = 60 * 10
ALREADY_COLLECTED_COUNT = 40

# ── CDN/응답 필터 설정: 리전/세그먼트 버전 다양성 대응 ─────────────────────────────────────────
CDN_HOST_RE   = re.compile(r"^https://scontent-[a-z0-9\-]+\.cdninstagram\.com/") # scontent-ssn1-1 등
CDN_PATH_ALLOW= re.compile(r"/o1/|/v/t(?!51\.|39\.|89\.)\d")  # 이미지 경로(t51/t39/t89) 제외한 비디오 CDN
MIN_GOOD_VIDEO_BYTES = 50_000         # 50KB 이상만 후보 (짧은 캐러셀 영상 대응)

# 동시 다운로드 제한
MAX_CONCURRENCY = 4
# 팔로우
ACCOUNTS = [

]
# ACCOUNTS = ["fkaus014"]  # 스크랩 대상 계정 배열


ERROR_LINKS: Dict[str, List[str]] = {}  # account -> [failed links]
ERROR_LINKS_FILE = "logs/i/error_links.json"


def load_error_links() -> Dict[str, List[str]]:
    if not os.path.exists(ERROR_LINKS_FILE):
        return {}
    try:
        with open(ERROR_LINKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        total = sum(len(v) for v in data.values())
        if total:
            # print(f"[INFO] 이전 에러 링크 로드: {total}개 ({list(data.keys())})")
            print(f"[INFO] 이전 에러 링크 로드: {total}개")
        return data
    except Exception as e:
        print(f"[WARN] error_links 로드 실패: {e}")
        return {}


def save_error_links(data: Dict[str, List[str]]) -> None:
    try:
        os.makedirs(os.path.dirname(ERROR_LINKS_FILE), exist_ok=True)
        with open(ERROR_LINKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] error_links 저장 실패: {e}")


def append_error_link(account: str, link: str) -> None:
    ERROR_LINKS.setdefault(account, []).append(link)
    save_error_links(ERROR_LINKS)






# ======== 유틸 ========
def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "_", name)

def ensure_dirs(base: str, account: str) -> Dict[str, str]:
    base_acc = os.path.join(base, account)
    img_dir = os.path.join(base_acc, "images")
    reel_dir = os.path.join(base_acc, "reels")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(reel_dir, exist_ok=True)
    return {"base": base_acc, "images": img_dir, "reels": reel_dir}

def guess_ext_from_url_or_type(url: str, content_type: Optional[str]) -> str:
    if content_type:
        if "image/" in content_type:
            return ".jpg" if "jpeg" in content_type else f".{content_type.split('/')[1].split(';')[0]}"
        if "video/" in content_type:
            return ".mp4"
    # fallback to URL path
    path = urlparse(url).path
    ext = os.path.splitext(path)[1]
    if ext:
        return ext.split("?")[0]
    # ultimate fallback
    if "/video" in url:
        return ".mp4"
    return ".jpg"

def is_post_or_reel(url: str) -> bool:
    try:
        path = url.split("?")[0]
        return "/p/" in path or "/reel/" in path
    except Exception:
        return False

def is_media_response(resp) -> bool:
    try:
        ct = (resp.headers or {}).get("content-type", "")
        return ("image" in ct or "video" in ct) and not resp.url.startswith("blob:")
    except Exception:
        return False

# --- helper: ffprobe로 비디오 길이(초) 가져오기 ---
def get_video_duration_sec(path: str):
    """
    ffprobe(FFmpeg) 필요. 성공 시 길이(초) float, 실패 시 None 반환.
    """
    if shutil.which("ffprobe") is None:
        # ffprobe 미설치
        return None
    try:
        # duration만 깔끔하게 출력
        # 참고: 일부 파일은 format.duration 대신 stream.duration이 필요할 수 있어 단순 출력 사용
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path
            ],
            capture_output=True, text=True, timeout=10
        )
        out = (res.stdout or "").strip()
        if not out:
            return None
        return float(out)
    except Exception:
        return None

def shortcode_to_mediaid(shortcode: str) -> str:
    """Instagram 릴스 shortcode → 숫자 media ID 변환"""
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    n = 0
    for c in shortcode:
        n = n * 64 + alphabet.index(c)
    return str(n)

def canonical_cdn_key(u: str) -> str:
    """
    쿼리스트링은 무시하고, host+path만 키로 사용 (동일 리소스 중복 제거).
    예: https://scontent-.../o1/v/t2/abc.mp4?efg=... -> scontent-.../o1/v/t2/abc.mp4
    """
    p = urlsplit(u)
    return f"{p.netloc}{p.path}"

def extract_account_and_type(url):
    # URL 파싱
    parsed = urlparse(url)
    # print(parsed)
    # ParseResult(scheme='https', netloc='www.instagram.com', path='/fkaus014/p/DO27U_DDw63/')

    # 1) 기본 도메인 (https://www.instagram.com)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # 2) path 부분 나누기
    parts = [p for p in parsed.path.split("/") if p]  # 빈 문자열 제거
    # parts = ['fkaus014', 'p', 'DO27U_DDw63']

    # username = parts[0]  # fkaus014
    # post_type = parts[1] # p
    # post_id   = parts[2] # DO27U_DDw63

    post_type = parts[0] # p
    post_id   = parts[1] # DO27U_DDw63

    return {
        "type": post_type
    }

# ======== 브라우저 조작 ========
async def ensure_login(page):
    await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
    await asyncio.sleep(4)
    # 로그인 폼 보이면 로그인
    login_user = page.locator("input[name='username'], input[name='email']")
    login_pass = page.locator("input[name='password'], input[name='pass']")
    if await login_user.count() and await login_pass.count():
        await login_user.fill(USERNAME)
        await login_pass.fill(PASSWORD)
        await login_pass.press("Enter")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(10)
        # 팝업 닫기
        for txt in ["나중에 하기", "Not Now"]:
            btn = page.locator(f"button:has-text('{txt}')")
            if await btn.count():
                await btn.click()
                await asyncio.sleep(1)

async def go_to_profile(page, handle: str):
    url = f"https://www.instagram.com/{handle.strip('/')}/"
    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_selector("main", timeout=30000)


POST_PREFIXES = {"p", "reel", "tv", "stories"}  # IGTV 포함(필요 없으면 제거)

def normalize_ig_post_url(url: str) -> str:
    """
    https://www.instagram.com/<user>/p/<code>  -> https://www.instagram.com/p/<code>
    https://www.instagram.com/<user>/reel/<code> -> https://www.instagram.com/reel/<code>
    이미 /p/, /reel/, /tv/ 로 시작하면 그대로 유지.
    쿼리/프래그먼트 보존, 상대경로도 허용.
    """
    base = "https://www.instagram.com"
    s = urlsplit(urljoin(base, url))  # 상대경로 대비
    parts = [seg for seg in s.path.split("/") if seg]  # ["user","p","CODE"]

    if len(parts) >= 2 and parts[0] not in POST_PREFIXES and parts[1] in POST_PREFIXES:
        # 첫 세그먼트가 유저명이고, 그 다음이 p/reel/tv 인 전형적 패턴 → 유저명 제거
        parts = parts[1:]

    new_path = "/" + "/".join(parts) if parts else "/"
    return urlunsplit((s.scheme, s.netloc, new_path, s.query, s.fragment))


async def collect_post_links(page, max_scrolls=MAX_SCROLLS, pause=SCROLL_PAUSE, target_url: Optional[str] = None) -> List[str]:
    """프로필 페이지에서 스크롤하며 /p/, /reel/ 링크 수집 (상대경로 → 절대경로)
    target_url을 주면, 스크롤 도중 해당 게시물을 만나는 순간 더 스크롤하지 않고 즉시 반환한다."""
    links = []
    post_links: Set[str] = set()
    # stable_rounds = 0
    # last_count = 0
    already_collected_count = 0
    target_norm = normalize_ig_post_url(target_url) if target_url else None
    await page.wait_for_selector("main", timeout=20000)
    # await asyncio.sleep(5)

    # 처음에만 게시물 링크가 뜰 때까지 최대 10초 기다림
    try:
        await page.wait_for_selector('a[href*="/p/"], a[href*="/reel/"]', timeout=10_000)
    except:
        pass

    last_height = await page.evaluate("document.body.scrollHeight")

    for _ in range(max_scrolls):
        anchors = await page.locator('a[href*="/p/"], a[href*="/reel/"]').element_handles()
        if len(anchors) == 0:
            print('[ERROR-1] ★★★★★★★★★★★★★★★★★★★★★★★ Account is not valid ★★★★★★★★★★★★★★★★★★★★★★★ ')
        for a in anchors:
            href = await a.get_attribute("href")
            if not href:
                continue

            # 절대경로화
            if href.startswith("/"):
                # href: /계정/p/postId/
                parseResult = urlparse(normalize_ig_post_url(href))
                origin_href = parseResult.path

                href = urljoin("https://www.instagram.com", href)

            # acount 세그먼트 제거
            # href = normalize_ig_post_url(href)

            if is_post_or_reel(href):
                if target_norm and normalize_ig_post_url(href) == target_norm:
                    print(f"[INFO] 목표 URL 도달, 스크롤 중단: {href}")
                    rev_links = links[::-1]   # slicing, 원본 보존
                    return rev_links

                if already_collected_count > ALREADY_COLLECTED_COUNT:
                    rev_links = links[::-1]   # slicing, 원본 보존
                    return rev_links

                url = "https://chickchick.kr/func/scrap-posts?urls="+origin_href
                res = requests.get(url)
                try:
                    res = requests.get(url, timeout=5)
                    data = res.json()
                except (requests.exceptions.RequestException, ValueError) as e:
                    # 서버 무응답/타임아웃/JSON 파싱 실패 - 지금까지 모은 링크를 날리지 않고
                    # 이 링크는 '미등록'으로 간주해 계속 진행한다 (예전엔 여기서 return [] 하여 전체 수집이 사라졌음)
                    print(f"[WARN] https://chickchick.kr 확인 실패({type(e).__name__}), 미등록으로 간주하고 계속: {origin_href}")
                    data = {"result": False}
                if data["result"]: # 등록되어 있음
                    already_collected_count += 1
                    continue

                if href not in post_links:
                    post_links.add(href)
                    links.append(href)

        await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        await asyncio.sleep(pause)

        # 새로운 콘텐츠 로딩됐는지 확인
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            # 더 이상 늘어나지 않으면 종료
            break
        last_height = new_height

        # await page.evaluate("window.scrollBy(0, Math.max(400, window.innerHeight*0.9));")
        # try:
        #     await page.wait_for_load_state("networkidle", timeout=3000) # 스크롤 후 대기(최대)
        # except:
        #     pass
        # await asyncio.sleep(pause)
        #
        # if len(post_links) == last_count:
        #     stable_rounds += 1
        #     if stable_rounds >= 3:
        #         break
        # else:
        #     stable_rounds = 0
        #     last_count = len(post_links)

    # return sorted(post_links)
    # links.reverse() # 역순으로 뒤집기
    # return links

    rev_links = links[::-1]   # slicing, 원본 보존
    return rev_links

# 컨테이너: section > main > div:first-child > div:first-child > div[role="presentation"] > ul > li > img
"""
UL_SEL   = "section main > div:nth-of-type(1) > div:nth-of-type(1) div[role='presentation'] ul"
LI_SEL   = UL_SEL + " > li"
IMG_SEL  = UL_SEL + " > li img"
FALLBACK_IMG  = "section main > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) img"
NEXT_BTN_SEL  = (
    "section main > div:nth-of-type(1) > div:nth-of-type(1) "
    "button[aria-label*='다음'], :has(button:has-text('다음')), "
    "button[aria-label*='Next'], :has(button:has-text('Next'))"
)
"""

# 공통 루트
ROOT_MAIN   = "section main > div:nth-of-type(1) > div:nth-of-type(1)"
ROOT_DIALOG = "div[role='dialog']"

async def _resolve_root(page) -> Tuple[Optional[str], Optional[str]]:
    """메인 루트 우선, 없으면 다이얼로그 루트 선택. (root_css, kind) 반환"""
    try:
        await page.wait_for_selector(ROOT_MAIN, timeout=2500)
        if await page.locator(ROOT_MAIN).count():
            return ROOT_MAIN, "main"
    except Exception:
        pass
    try:
        await page.wait_for_selector(ROOT_DIALOG, timeout=4000)
        if await page.locator(ROOT_DIALOG).count():
            return ROOT_DIALOG, "dialog"
    except Exception:
        pass
    return None, None

def _under(root: str, rel: str) -> str:
    """루트 아래 상대 셀렉터를 절대 셀렉터로"""
    if not rel:
        return root
    return f"{root} {rel}".strip()

def _sel(root: str, kind: str, rel_main: str, rel_dialog: Optional[str] = None) -> str:
    """루트 종류에 따라 알맞은 상대 셀렉터를 선택"""
    rel = rel_main if kind == "main" else (rel_dialog if rel_dialog is not None else rel_main)
    return _under(root, rel)

async def extract_imgs_src_only(page, post_url: str, seen: Set[str]) -> Tuple[List[str], List[str]]:
    root, kind = await _resolve_root(page)

    # 루트/종류에 맞춰 모든 셀렉터 구성
    if root:
        # 캐러셀 UL/LI/IMG
        UL_SEL  = _sel(root, kind, "div[role='presentation'] ul")
        IMG_SEL = _sel(root, kind, "div[role='presentation'] ul > li img")

        # 다음 버튼 (버튼 "자체"만 선택)
        NEXT_BTN_SEL = ", ".join([
            _sel(root, kind, "button[aria-label*='다음']"),
            _sel(root, kind, "button:has-text('다음')"),
            _sel(root, kind, "button[aria-label*='Next']"),
            _sel(root, kind, "button:has-text('Next')"),
        ])

        # fallback IMG (루트 기준)
        FALLBACK_IMG = _sel(root, kind,
                            rel_main="> div:nth-of-type(1) > div:nth-of-type(1) img",
                            rel_dialog="img")
    else:
        UL_SEL = IMG_SEL = NEXT_BTN_SEL = None
        # 루트를 못 찾으면 둘 다 커버
        FALLBACK_IMG = (
            "section main > div:nth-of-type(1) > div:nth-of-type(1) "
            "> div:nth-of-type(1) > div:nth-of-type(1) img, "
            "div[role='dialog'] img"
        )

    # 1) UL 대기 (있으면 캐러셀 모드, 없으면 fallback)
    ul_found = False
    if UL_SEL:
        try:
            await page.wait_for_selector(UL_SEL, timeout=5000)
            ul_found = True
        except Exception:
            ul_found = False

    # 공통: 이미지 한 번에 최대 해상도만 수집
    async def collect_max_images(selector: str) -> List[str]:
        try:
            n = await page.locator(selector).count()
            if n > 0:
                await page.locator(selector).nth(n - 1).scroll_into_view_if_needed()
        except Exception:
            pass

        urls: List[str] = await page.evaluate(
            """
            (sel) => {
              const pickLargestFromSrcset = (img) => {
                const ss = img.getAttribute('srcset');
                if (!ss) return null;
                const items = ss.split(',').map(s => s.trim()).map(entry => {
                  const [u, d] = entry.split(/\\s+/);
                  let w = 0;
                  if (d && d.endsWith('w')) {
                    const n = parseInt(d.slice(0, -1), 10);
                    if (!isNaN(n)) w = n;
                  }
                  return { url: u, w };
                }).filter(it => it.url);
                if (!items.length) return null;
                items.sort((a,b)=>b.w-a.w);
                return items[0].url;
              };

              const preferAttrs = (img) => {
                const cand = [
                  'data-src-large','data-src-2x','data-large','data-original',
                  'data-srcset','data-fullsrc','data-full','data-url'
                ];
                for (const a of cand) {
                  const v = img.getAttribute(a);
                  if (v) return v;
                }
                return null;
              };

              const imgs = Array.from(document.querySelectorAll(sel));
              return imgs.map(img =>
                pickLargestFromSrcset(img) ||
                preferAttrs(img) ||
                img.currentSrc ||
                img.getAttribute('src')
              ).filter(Boolean);
            }
            """,
            selector
        )
        return urls

    async def collect_video_srcs(selector: str) -> List[str]:
        urls = await page.evaluate(
            """
            (sel) => {
              const vids = Array.from(document.querySelectorAll(sel));
              const out = [];
    
              for (const v of vids) {
                let src = v.getAttribute('src') || v.currentSrc;
                if (!src) {
                  const source = v.querySelector('source');
                  if (source) {
                    src = source.getAttribute('src');
                  }
                }
                if (src) out.push(src);
              }
    
              return out;
            }
            """,
            selector
        )
        return urls

    good_video_urls: Set[str] = set()

    # 네트워크 응답에서 '좋은' 비디오만 즉시 선별 저장 (페이지에서 발생하는 모든 네트워크 응답(response)을 “이벤트로” 받아서 검사하는 패턴)
    def on_response(resp):
        if looks_like_good_video(resp):
            good_video_urls.add(resp.url)

    # 2) 캐러셀
    if ul_found and IMG_SEL and NEXT_BTN_SEL:
        VIDEO_SEL = _sel(root, kind, "div[role='presentation'] ul > li video")
        async def collect_from_main() -> None:
            for u in await collect_max_images(IMG_SEL):
                if u:
                    seen.add(u)

            for v in await collect_video_srcs(VIDEO_SEL):
                if v:
                    good_video_urls.add(v)

        await collect_from_main()
        page.on("response", on_response)


        # "다음" 클릭 반복 (클릭 전 수집 → 클릭 → 잠깐 대기)
        for _ in range(20):
            next_btn = page.locator(NEXT_BTN_SEL).first
            if not await next_btn.count():
                break

            # 클릭 전 수집(현재 화면)
            await collect_from_main()
            page.on("response", on_response)

            # 클릭
            try:
                await next_btn.click(timeout=1000)
            except Exception:
                try:
                    await next_btn.click(timeout=1000, force=True)
                except Exception:
                    break

            # await asyncio.sleep(0.5) # 시간 조정
            await asyncio.sleep(0.7) # 시간 조정

        # 마지막 한 번 더
        await collect_from_main()
        page.on("response", on_response)

    # 3) Fallback
    if await page.locator(FALLBACK_IMG).count():
        for u in await collect_max_images(FALLBACK_IMG):
            if u:
                seen.add(u)

    # ===== 4) (선택) 추가 중복 축소: 사이즈 파라미터 무시 키로 병합 =====
    # 같은 사진인데 ?w=, ?h=, =s2048 등만 다른 경우를 더 줄이고 싶다면 사용
    import re
    def norm(u: str) -> str:
        # 아주 보수적으로 몇 가지 사이즈 토큰만 제거
        #  - Google 계열: "=s1234" 꼬리 토큰
        u2 = re.sub(r'(=s\d+)(?=$)', '', u)
        #  - 흔한 width/height 쿼리파라미터 제거 (다른 토큰 보존)
        u2 = re.sub(r'([?&])(w|width|h|height|size|s)=\d+(?=(&|$))', r'\1', u2, flags=re.I)
        u2 = re.sub(r'[?&]+$', '', u2)
        return u2

    best_by_key = {}
    for u in seen:
        key = norm(u)
        # 같은 키면 더 긴(대체로 고해상도) URL을 보존하는 간단 규칙
        if key not in best_by_key or len(u) > len(best_by_key[key]):
            best_by_key[key] = u

    final_urls = list(best_by_key.values())

    # 로그
    # print(f"\n=== {post_url} ===")
    # for i, u in enumerate(final_urls, 1):
    #     print(f"[IMG {i}] {u}")

    return final_urls, list(good_video_urls)


def looks_like_good_video(resp):
    """좋은(완전) mp4 응답만 통과: 200 OK, video/*, CDN host, /o1/, 충분한 content-length, content-range 없음"""
    try:
        if resp.status != 200:
            return False
        # content-type
        ct = (resp.headers or {}).get("content-type", "")
        if "video" not in ct:
            return False
        hdrs = {k.lower(): v for k, v in (resp.headers or {}).items()}
        # 206 range 응답: byte 0부터 시작하는 첫 청크만 허용 (URL 자체는 유효한 CDN URL)
        cr = hdrs.get("content-range", "")
        if resp.status == 206:
            if not cr.lower().startswith("bytes 0-"):
                return False  # 중간 청크는 무시
        elif resp.status != 200:
            return False
        # CDN host + 경로 규칙
        if not (CDN_HOST_RE.match(resp.url) and CDN_PATH_ALLOW.search(resp.url)):
            return False
        # 크기: content-range의 전체 크기(bytes 0-x/TOTAL) 또는 content-length로 판단
        total = None
        if cr:
            try:
                total = int(cr.split("/")[-1])
            except Exception:
                pass
        if total is None:
            clen = hdrs.get("content-length")
            if clen and clen.isdigit():
                total = int(clen)
        if total is not None and total < MIN_GOOD_VIDEO_BYTES:
            return False
        return True
    except Exception:
        return False

async def force_play_video_if_possible(page):
    """비디오 보이게 하고 재생 유도 → 네트워크 트리거"""
    vid = page.locator("section main > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) video").first
    if await vid.count():
        try:
            await vid.scroll_into_view_if_needed()
        except:
            pass
    # 재생 버튼 클릭 시도
    try:
        play_btn = page.locator("button[aria-label*='Play'], button:has-text('Play')")
        if await play_btn.count():
            await play_btn.click()
            await asyncio.sleep(1)
    except:
        pass
    # JS로 강제 재생
    try:
        await page.evaluate("""
            (sel)=>{ const v=document.querySelector(sel);
                     if(v){ v.muted=true; v.play().catch(()=>{}); } }
        """, "article video")
    except:
        pass

# https://scontent-ssn1-1.cdninstagram.com/v/t51
async def extract_media_from_post(page, url: str):
    """
    어떤 URL이든(포스트/릴스) 이미지와 비디오를 동시에 수집.
    - images: DOM의 <img>에서 수집(+캐러셀 next)
    - video_cdn: 네트워크 응답에서 '좋은 mp4'만 즉시 선별(필요 시 DOM의 <video src>도 보조)
    """
    good_video_urls: Set[str] = set()

    # 네트워크 응답에서 '좋은' 비디오만 즉시 선별 저장 (페이지에서 발생하는 모든 네트워크 응답(response)을 “이벤트로” 받아서 검사하는 패턴)
    def on_response(resp):
        if looks_like_good_video(resp):
            good_video_urls.add(resp.url)
    page.on("response", on_response)

    await page.goto(url, wait_until="domcontentloaded")
    await asyncio.sleep(DELAY_2_SECOND)

    # 정적 HTML을 인터랙션 전에 미리 캡처 (인터랙션 후엔 동적 콘텐츠가 URL 토큰을 잘라낼 수 있음)
    _static_html: str = ""
    if "/reel/" in url:
        try:
            _static_html = await page.content()
        except Exception:
            pass

    # 페이지 상태 진단 — 릴스 페이지가 라이트 버전이면 SPA 재초기화 후 재진입
    if "/reel/" in url:
        try:
            diag = await page.evaluate("""
                () => ({
                    hasArticle: !!document.querySelector('article'),
                    videoCount: document.querySelectorAll('video').length,
                })
            """)
            if not diag.get("hasArticle") and diag.get("videoCount", 0) == 0:
                # SPA가 제대로 마운트되지 않음 → feed 경유 재진입 후 article 대기
                # print(f"[INFO] reel 라이트 버전 감지 → instagram.com 경유 재로드")
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                await asyncio.sleep(2)
                await page.goto(url, wait_until="domcontentloaded")
                # article이 마운트될 때까지 최대 8초 대기 (React SPA 렌더링 시간)
                try:
                    await page.wait_for_selector("article", timeout=8000)
                    print(f"[INFO] article 감지됨 → SPA 정상 마운트")
                except Exception:
                    await asyncio.sleep(DELAY_2_SECOND)
                _static_html = await page.content()
        except Exception:
            pass

    # 이미지 수집 (도우미 사용)
    seen = set()
    images, videos = await extract_imgs_src_only(page, url, seen)

    for v in videos:
        good_video_urls.add(v)

    # 비디오 수집: 보이게/재생 유도 → '좋은' 응답 대기
    await force_play_video_if_possible(page)

    # 릴스: 페이지의 모든 video 요소를 강제 재생 후 추가 대기
    if "/reel/" in url:
        try:
            vid_count = await page.evaluate("""
                () => {
                    const vids = Array.from(document.querySelectorAll('video'));
                    vids.forEach(v => { v.muted = true; v.play().catch(() => {}); });
                    return vids.length;
                }
            """)
            # print(f"[DEBUG] reel video 요소 {vid_count}개 발견, 강제 재생 시도")
        except Exception:
            pass

        # video 0개이면 실제 마우스 클릭으로 플레이어 초기화 (isTrusted=true 필요)
        if vid_count == 0:
            try:
                # main 요소 실제 위치에서 클릭 시도
                clicked = False
                try:
                    main_el = page.locator("main").first
                    if await main_el.count():
                        box = await main_el.bounding_box()
                        if box:
                            cx = box["x"] + box["width"] * 0.45
                            cy = box["y"] + box["height"] * 0.40
                            await page.mouse.click(cx, cy)
                            clicked = True
                except Exception:
                    pass
                if not clicked:
                    await page.mouse.click(640, 360)
                await asyncio.sleep(0.5)
                await page.keyboard.press("Space")
                await asyncio.sleep(4)  # video 로드 충분히 대기
                vid_count2 = await page.evaluate("document.querySelectorAll('video').length")
                # 스크린샷으로 페이지 상태 확인 (디버그용)
                try:
                    import tempfile as _tf, pathlib as _pl
                    ss_name = f"ig_reel_{url.rstrip('/').split('/')[-1]}.png"
                    ss_path = str(_pl.Path(_tf.gettempdir()) / ss_name)
                    await page.screenshot(path=ss_path, full_page=False)
                    # print(f"[DEBUG] 스크린샷 저장: {ss_path}")
                except Exception as _e:
                    print(f"[DEBUG] 스크린샷 실패: {_e}")
                if vid_count2 > 0:
                    print(f"[INFO] 인터랙션 후 video {vid_count2}개 감지 → 재생 유도")
                    await page.evaluate("""
                        () => { document.querySelectorAll('video').forEach(v => { v.muted = true; v.play().catch(() => {}); }); }
                    """)
                else:
                    # print(f"[INFO] 인터랙션 후에도 video 0개")
                    pass
            except Exception:
                pass

    # 캐러셀 포스트: 다음 슬라이드 버튼 클릭으로 모든 슬라이드 영상 CDN URL 수집
    if "/reel/" not in url:
        try:
            for _slide in range(20):  # 최대 20슬라이드
                btn = page.locator(
                    "button[aria-label='다음'], button[aria-label='Next'], "
                    "button[aria-label='next slide'], button[aria-label*='다음'], "
                    "button[aria-label*='Next']"
                ).first
                if not await btn.count():
                    break
                await btn.click()
                await asyncio.sleep(0.5)
                # 슬라이드 전환 후 video 강제 재생 → CDN 요청 유도
                try:
                    await page.evaluate("""
                        () => {
                            document.querySelectorAll('article video, main video, video').forEach(v => {
                                v.muted = true;
                                v.play().catch(() => {});
                            });
                        }
                    """)
                except Exception:
                    pass
                await asyncio.sleep(1.0)  # CDN 응답 대기
        except Exception:
            pass

    # 잠시 재시도하며 응답 모으기 (릴스는 더 오래 대기)
    wait_rounds = 8 if "/reel/" in url else 2
    for _ in range(wait_rounds):
        if good_video_urls:
            break
        await asyncio.sleep(0.5)

    # 보조: DOM의 <video src>도 수집(있을 수 있음) → CDN 필터 적용
    # page.evaluate()로 JS 즉시 실행 → locator 대기/타임아웃 없음
    try:
        dom_video_srcs: List[str] = await page.evaluate("""
            () => {
                const vids = Array.from(
                    document.querySelectorAll('section main > div:nth-of-type(1) video')
                );
                return vids.map(v => {
                    let src = v.getAttribute('src') || v.currentSrc || null;
                    if (!src || src.startsWith('blob:')) {
                        const s = v.querySelector('source');
                        if (s) src = s.getAttribute('src');
                    }
                    return src;
                }).filter(s => s && s.startsWith('http'));
            }
        """)
    except Exception as e:
        print(f"[ERROR-3-0] video src JS 추출 실패: {e}")
        dom_video_srcs = []

    # 릴스: 네트워크/DOM에서 못 잡았으면 모바일 API로 직접 영상 URL 요청
    if "/reel/" in url and not good_video_urls:
        try:
            shortcode = url.rstrip('/').split('/')[-1]
            media_id = shortcode_to_mediaid(shortcode)
            api_resp = await page.request.get(
                f"https://i.instagram.com/api/v1/media/{media_id}/info/",
                headers={
                    "X-IG-App-ID": "936619743392459",
                    "Accept": "application/json",
                    "Accept-Language": "ko-KR,ko;q=0.9",
                }
            )
            if api_resp.ok:
                data = await api_resp.json()
                items = data.get("items") or []
                for item in items:
                    for vv in (item.get("video_versions") or []):
                        vurl = vv.get("url", "")
                        if CDN_HOST_RE.match(vurl):
                            good_video_urls.add(vurl)
                if good_video_urls:
                    print(f"[INFO] 모바일 API에서 영상 URL {len(good_video_urls)}개 획득")
                else:
                    print(f"[DEBUG] 모바일 API 응답에 영상 URL 없음 (status={api_resp.status})")
            else:
                print(f"[DEBUG] 모바일 API {api_resp.status}: {shortcode}")
        except Exception as _e:
            print(f"[DEBUG] 모바일 API 실패: {_e}")

    # Fallback: 네트워크 인터셉터가 긴 토큰 URL을 잡지 못했을 때만 HTML 파싱
    # (good_video_urls 있으면 긴 토큰이 이미 확보된 것 → HTML의 잘린 토큰 추가 불필요)
    if not good_video_urls and (not dom_video_srcs or "/reel/" in url):
        try:
            # 릴스: 인터랙션 전 정적 HTML 사용 (인터랙션 후 동적 콘텐츠는 URL 토큰이 잘릴 수 있음)
            html = _static_html if _static_html else await page.content()
            # 1) CDN URL 직접 스캔
            raw_urls = re.findall(
                r'https:(?:/|\\/)(?:/|\\/)scontent-[a-z0-9\-]+\.cdninstagram\.com[^"\'<>\s]+',
                html
            )
            # 2) JSON video_url / playback_url 키 추출 (긴 토큰이 여기 있을 수 있음)
            for key_pat in (r'"video_url"\s*:\s*"([^"]+)"', r'"playback_url"\s*:\s*"([^"]+)"'):
                for m in re.finditer(key_pat, html):
                    u = m.group(1).replace('\\/', '/').replace('\\u0026', '&')
                    if CDN_HOST_RE.match(u):
                        raw_urls.append(u)
            seen_fallback: Set[str] = set()
            f1_urls: List[str] = []
            f2_urls: List[str] = []
            for u in raw_urls:
                u = u.replace('\\/', '/').replace('\\u0026', '&').rstrip('\\')
                if not any(x in u for x in ('.mp4', '/o1/v/', '/v/t2.', '/v/t50.')):
                    continue
                if u in seen_fallback:
                    continue
                seen_fallback.add(u)
                # f2는 adaptive streaming 세그먼트 → f1(직접다운로드) 없을 때만 사용
                if '/f2/' in u:
                    f2_urls.append(u)
                else:
                    f1_urls.append(u)
            # f1 우선, 없으면 f2도 시도 (일부 릴스는 f1 없음)
            fallback_order = f1_urls if f1_urls else f2_urls
            for u in fallback_order:
                dom_video_srcs.append(u)
            if seen_fallback:
                print(f"[INFO] HTML fallback 후보 {len(seen_fallback)}개 (f1={len(f1_urls)}, f2(스킵)={len(f2_urls)})")
        except Exception as e:
            print(f"[ERROR-3-0] HTML fallback 실패: {e}")

    # DOM/네트워크 합치고, 최종적으로 CDN 규칙으로 필터
    candidates = set(dom_video_srcs) | good_video_urls
    if not candidates and "/reel/" in url:
        print(f"[DEBUG] reel 캡처 0 — good_video_urls={len(good_video_urls)} dom_video_srcs={len(dom_video_srcs)}")
    unique = {}
    for u in candidates:
        if CDN_HOST_RE.match(u) and CDN_PATH_ALLOW.search(u):
            k = canonical_cdn_key(u)
            unique.setdefault(k, u)
        elif candidates:
            print(f"[DEBUG] CDN 필터 탈락: {u[:100]}")
    video_cdn = sorted(unique.values())

    return {
        "post_url": url,
        "images": images,        # 항상 채움(있으면)
        "videos": [],            # 사용하지 않으므로 빈 리스트 유지
        "video_cdn": video_cdn,  # 항상 채움(있으면)
    }


_seq = itertools.count()
_seq_lock = asyncio.Lock()

def now_ms() -> int:
    return int(time.time() * 1000)  # 사람 읽기 쉬운 벽시계 ms

async def next_seq() -> int:
    # 동일 ms 충돌 및 코루틴 동시성 대비
    async with _seq_lock:
        return next(_seq)

def safe_open_exclusive(path: str):
    # 존재 충돌 시 에러로 실패시키는 전용 오픈 (덮어쓰기 방지)
    return open(path, "xb")

class _Retry403(Exception):
    """aiohttp → page.request 재시도 신호"""
    pass

# ======== 다운로드 ========
async def download_one(session: aiohttp.ClientSession, url: str, save_dir: str, prefix: str="media", page=None) -> Optional[str]:
    data = None
    ext = ".bin"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status == 403 and page is not None:
                # 브라우저 세션으로 재시도 (서명 URL은 세션 바인딩)
                raise _Retry403()
            if resp.status not in (200, 206):
                print(f"[WARN] download_one HTTP {resp.status}: {url[:80]}")
                return None
            ct = resp.headers.get("Content-Type", "")
            ext = guess_ext_from_url_or_type(url, ct)
            data = await resp.read()
            if resp.status != 200 and ("/reel/" in url or any(x in url for x in ("/o1/v/", "/v/t2.", "/v/t50."))):
                # print(f"[INFO] download_one OK ({resp.status}): {url[:100]}")
                print(f"[INFO] download_one OK ({resp.status})")
    except _Retry403:
        try:
            pw_resp = await page.request.get(url, headers={
                "Referer": "https://www.instagram.com/",
                "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
                "Sec-Fetch-Dest": "video",
                "Sec-Fetch-Mode": "no-cors",
                "Sec-Fetch-Site": "cross-site",
            })
            if not pw_resp.ok:
                print(f"[WARN] download_one(pw) HTTP {pw_resp.status}: {url[:80]}")
                return None
            ct = pw_resp.headers.get("content-type", "")
            ext = guess_ext_from_url_or_type(url, ct)
            # print(f"[INFO] download_one(pw) OK: {url[:80]}")
            # print(f"[INFO] download_one(pw) OK")
            data = await pw_resp.body()
        except Exception as e:
            print(f"[WARN] download_one(pw) 실패 ({type(e).__name__}: {e}): {url[:80]}")
            return None
    except Exception as e:
        print(f"[WARN] download_one 실패 ({type(e).__name__}: {e}): {url[:80]}")
        return None

    if not data:
        return None
    try:
        ts = now_ms()
        seq = await next_seq()
        fname = sanitize_filename(f"{prefix}_{ts:013d}_{seq:06d}{ext}")
        path = os.path.join(save_dir, fname)
        try:
            with safe_open_exclusive(path) as f:
                f.write(data)
        except FileExistsError:
            seq = await next_seq()
            ts = now_ms()
            path = os.path.join(save_dir, sanitize_filename(f"{prefix}_{ts:013d}_{seq:06d}{ext}"))
            with open(path, "wb") as f:
                f.write(data)
        return path
    except Exception as e:
        print(f"[WARN] download_one 저장 실패 ({type(e).__name__}: {e}): {url[:80]}")
        return None


async def download_media(images: List[str], videos: List[str], video_cdn: List[str], dirs: Dict[str, str], account: str, cookies: Optional[List[Dict]] = None, page=None):
    # 비디오는 video_cdn만 사용 (요구사항)
    video_sources = video_cdn if video_cdn else []

    # 중복 제거
    images = list(dict.fromkeys(images))
    video_sources = list(dict.fromkeys(video_sources))

    conn = aiohttp.TCPConnector(limit_per_host=MAX_CONCURRENCY, ssl=False)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Referer": "https://www.instagram.com/",
    }
    if cookies:
        headers["Cookie"] = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    async with aiohttp.ClientSession(connector=conn, headers=headers) as session:
        tasks = []
        for i, url in enumerate(images, 1):
            tasks.append(download_one(session, url, dirs["images"], prefix=f"{account}_img", page=page))
        for i, url in enumerate(video_sources, 1):
            tasks.append(download_one(session, url, dirs["reels"], prefix=f"{account}_reel", page=page))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        ok_paths = [p for p in results if isinstance(p, str) and p]
        download_failed = len(tasks) - len(ok_paths)

        # 🔥 비디오 길이가 1초 미만이거나(0 포함) 길이 판독 실패(None)면 삭제
        deleted = []
        for p in ok_paths:
            try:
                if os.path.exists(p) and p.startswith(dirs["reels"]):
                    dur = get_video_duration_sec(p)  # None = ffprobe 미설치 또는 판독 실패
                    # ffprobe가 측정한 경우에만 1초 미만 삭제 (None이면 판단 불가 → 유지)
                    if dur is not None and dur < 1.0:
                        fsize = os.path.getsize(p) if os.path.exists(p) else 0
                        os.makedirs(COS_DIR, exist_ok=True)
                        dest = os.path.join(COS_DIR, os.path.basename(p))
                        os.rename(p, dest)
                        print(f"[INFO] 짧은 비디오 이동: {dur:.2f}s, {fsize//1024}KB — {os.path.basename(p)} → COS_DIR")
                        deleted.append(p)
            except Exception as e:
                print(f"[WARN] 파일 이동 실패: {p}, {e}")

        # if deleted:
        #     print(f"[INFO] {len(deleted)}개의 짧은/길이불명 비디오 삭제됨 (<1s or unknown)")

        final_paths = [p for p in ok_paths if p not in deleted]
        stats = {
            "attempted": len(tasks),
            "download_failed": download_failed,
            "deleted_short": len(deleted),
        }
        return final_paths, stats


# ======== 메인 플로우 ========
async def handle_account(page, account: str, preset_links: Optional[List[str]] = None, throttle: Optional[Dict] = None, target_url: Optional[str] = None):
    if throttle is None:
        throttle = {"processed": 0}

    await ensure_login(page)
    await go_to_profile(page, account)

    links = preset_links if preset_links is not None else await collect_post_links(page, target_url=target_url)

    if len(links) > 5:
        today = datetime.today().strftime('%Y/%m/%d %H:%M:%S')
        print(f"[INFO] [{today}] [{account}] Collect Postlinks: {len(links)}")

    # 저장 디렉토리 준비
    if len(links) > 0:
        dirs = ensure_dirs(BASE_SAVE_DIR, account)

    all_saved = []
    check_saved = []
    for idx, link in enumerate(links, 1):
        today = datetime.today().strftime('%Y/%m/%d %H:%M:%S')
        print(f"[INFO] [{today}] [{account}] ({idx}/{len(links)}) {link}")

        # parsed = urlparse(link)
        # # ParseResult(scheme='https', netloc='www.instagram.com', path='/fkaus014/p/DO27U_DDw63/')
        # qs_link = normalize_ig_post_url(parsed.path)
        # parsed = urlparse(qs_link)
        # print(f"[{account}] ({idx}/{len(links)}) {parsed.path}")

        # None, False, 0, '', [], {}, 모두 여기로 들어옴
        # if idx == 5: # 디버깅 테스트용
        #     break
        media = {
            "post_url": link,
            "images": [],
            "videos": [],
            "video_cdn": [],
        }
        for attempt in range(3):
            try:
                media = await extract_media_from_post(page, link)
                break
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2)
                else:
                    print(f"[ERROR-2] media 추출 실패-{attempt + 1}: {e}")
                    append_error_link(account, link)

            # print('media', media)
            # 이미지: 그대로 / 비디오: VIDEO_PREFIX만

        saved = None
        dl_stats = {}
        try:
            ig_cookies = await page.context.cookies()
            saved, dl_stats = await download_media(
                media.get("images", []), media.get("videos", []), media["video_cdn"], dirs, account, cookies=ig_cookies, page=page
            )
        except Exception as e:
            print(f"[ERROR-3] 다운로드 실패 {e}")
            append_error_link(account, link)

        today_log = datetime.today().strftime('%Y/%m/%d %H:%M:%S')
        img_cnt = len(media.get("images", []))
        vid_cnt = len(media.get("video_cdn", []))
        if not saved:
            if img_cnt == 0 and vid_cnt == 0:
                reason = "미디어 수집 0개"
            else:
                parts = []
                if dl_stats.get("download_failed"):
                    parts.append(f"다운로드실패={dl_stats['download_failed']}")
                    append_error_link(account, link)  # 다운로드 실패는 재시도 가치 있음
                if dl_stats.get("deleted_short"):
                    parts.append(f"짧은영상삭제={dl_stats['deleted_short']}")
                reason = ", ".join(parts) if parts else "원인불명"
            print(f"[WARN] [{today_log}] [{account}] ({idx}/{len(links)}) 저장 0개 (수집: img={img_cnt}, vid={vid_cnt} / {reason}) {link}")
        elif dl_stats.get("download_failed") or dl_stats.get("deleted_short"):
            parts = []
            if dl_stats.get("download_failed"):
                parts.append(f"다운로드실패={dl_stats['download_failed']}")
                append_error_link(account, link)
            if dl_stats.get("deleted_short"):
                parts.append(f"짧은영상삭제={dl_stats['deleted_short']}")
            print(f"[WARN] [{today_log}] [{account}] ({idx}/{len(links)}) 저장 {len(saved)}/{img_cnt+vid_cnt}개 ({', '.join(parts)}) {link}")
        all_saved.extend(saved or [])
        check_saved.extend(saved or [])
        if idx % 10 == 0:
            today = datetime.today().strftime('%Y/%m/%d %H:%M:%S')
            print(f"[INFO] [{today}] [{account}] Interim check of number of saved files: {len(check_saved)}")
            check_saved = []
        link_segment = extract_account_and_type(normalize_ig_post_url(link))

        payload = {
            "account": str(account),
            "post_urls": link,
            "type": link_segment["type"],
        }
        url = 'https://chickchick.kr/func/scrap-posts'

        for attempt in range(2):  # 총 2번 시도
            try:
                requests.post(
                    url,
                    json=payload,
                    timeout=(3, 20)
                )
                break
            except Exception as e:
                print(f"[WARN] progress-update 요청 실패-{attempt + 1}: {e}")
                if attempt < 1:  # 첫 실패면 10초 대기 후 재시도
                    time.sleep(10)
                else:  # 두 번째도 실패하면 그냥 무시
                    pass

        await asyncio.sleep(DELAY_2_SECOND)  # 과도한 요청 방지
        throttle["processed"] += 1
        if throttle["processed"] >= 300:
            today_t = datetime.today().strftime('%Y/%m/%d %H:%M:%S')
            print(f"[INFO] [{today_t}] 누적 처리 300개 도달 → 10분 대기 후 재개")
            throttle["processed"] = 0
            await asyncio.sleep(DELAY_10_MINUTE)
        elif idx % 100 == 0:
            await asyncio.sleep(DELAY_3_MINUTE)  # 과도한 요청 방지


    await page.close()

    if len(links) > 0:
        print(f"[INFO] [{today}] [{account}] Number of files saved: {len(all_saved)}")

    return len(links)

async def run_scrap():
    global ERROR_LINKS
    ERROR_LINKS = load_error_links()

    account_length = len(ACCOUNTS)
    if account_length > 0:
        log_file = open(filename, "a", encoding="utf-8")   # w: 덮어쓰기, a: 이어쓰기
        sys.stdout = log_file
        sys.stderr = log_file
        # print("이건 파일로 감")
        # raise Exception("에러도 파일로 감")

        sys.stdout.reconfigure(line_buffering=True)
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            USER_DATA_DIR,
            # headless=HEADLESS,  # 주석하면 브라우저 off
            # viewport={"width": 1920, "height": 1080},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )


        throttle = {"processed": 0}  # 계정 간 누적 카운터 공유

        for i, acc in enumerate(ACCOUNTS):
            today = datetime.today().strftime('%Y/%m/%d %H:%M:%S')
            print(f"\n[INFO] [{today}] Start account processing: [{acc}] ({i+1}/{len(ACCOUNTS)})")

            try:
                page = await context.new_page()
            except Exception:
                context = await pw.chromium.launch_persistent_context(
                    USER_DATA_DIR,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                page = await context.new_page()

            try:
                # rs = await handle_account(page, acc, throttle=throttle, target_url='https://www.instagram.com/xx_jaehee_xx/p/C6XxuO7Psuu/')
                rs = await handle_account(page, acc, throttle=throttle)
            except Exception as e:
                print(f"[ERROR-4] [{acc}] Error in processing: {e}")
                continue

            if i < len(ACCOUNTS) - 1:
                if rs > 30:
                    today_c = datetime.today().strftime('%Y/%m/%d %H:%M:%S')
                    print(f"[INFO] [{today_c}] [{acc}] 계정 간 쿨다운 1분 대기")
                    await asyncio.sleep(DELAY_1_MINUTE)
                else:
                    await asyncio.sleep(DELAY_10_SECOND)

        # 재시도: 스냅샷 후 초기화 → 재시도 중 발생한 새 에러는 다시 파일에 누적
        pending = {acc: links for acc, links in ERROR_LINKS.items() if links}
        if pending:
            ERROR_LINKS.clear()
            save_error_links(ERROR_LINKS)

        for acc, err_links in pending.items():
            today = datetime.today().strftime('%Y/%m/%d %H:%M:%S')
            print(f"[INFO] [{today}] [{acc}] 에러 링크 재시도: {len(err_links)}개")
            try:
                page = await context.new_page()
            except Exception:
                context = await pw.chromium.launch_persistent_context(
                    USER_DATA_DIR,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                page = await context.new_page()
            try:
                await handle_account(page, acc, preset_links=err_links, throttle=throttle)
            except Exception as e:
                print(f"[ERROR-4] [{acc}] 에러 재시도 실패: {e}")

        # 재시도 후 남은 에러 파일 처리
        if ERROR_LINKS:
            save_error_links(ERROR_LINKS)
        else:
            try:
                os.remove(ERROR_LINKS_FILE)
            except FileNotFoundError:
                pass

        await context.close()

    if account_length > 0:
        log_file.close()

# def run_scrap_ig_job():
#     # 이벤트 루프는 “스레드당 1개”가 원칙
#     asyncio.run(run_scrap())

if __name__ == "__main__":
    '''
    asyncio.run(run_scrap)      # ❌ 함수 자체를 넘김
    asyncio.run(run_scrap())    # ✅ 코루틴 객체를 넘김
    '''
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_scrap())
    finally:
        loop.close()
        os._exit(0)  # anyio atexit 스레드 풀 경고 방지
