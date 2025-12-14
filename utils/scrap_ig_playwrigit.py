import aiohttp
import re, os, sys, time, itertools
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit
from typing import List, Dict, Any, Optional, Set, Tuple
from playwright.async_api import async_playwright
import subprocess
import shutil
import asyncio
import requests
import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config.config import settings

IMAGE_DIR2 = settings['IMAGE_DIR2']
# print(IMAGE_DIR2)
BASE_SAVE_DIR = IMAGE_DIR2
# BASE_SAVE_DIR = r"D:\temp"

# ======== 설정 ========
USER_DATA_DIR = str(Path("./ig_profile-0").resolve())  # 세션 저장 (2회차부터 자동 로그인)  # fx014
USER_DATA_DIR = str(Path("./ig_profile-1").resolve())  # fx015
# USER_DATA_DIR = str(Path("./ig_profile-2").resolve())  # fx016
HEADLESS = False

USERNAME = settings['SCRAP_USERNAME']   # 인스타 로그인 계정
PASSWORD = settings['SCRAP_PASSWORD']   # 비밀번호

# USERNAME = ""   # 인스타 로그인 계정
# PASSWORD = ""   # 비밀번호

# 스크롤/속도
SCROLL_PAUSE = 1.8
MAX_SCROLLS = 30001
DELAY_SECOND = 2.0
DELAY_MINUTE = 60 * 5
ALREADY_COLLECTED_COUNT = 50

ACCOUNTS = [

]
# ACCOUNTS = ["fkaus014"]  # 스크랩 대상 계정 배열

TEST_LINKS = [

]






# ── CDN/응답 필터 설정: 리전/세그먼트 버전 다양성 대응 ─────────────────────────────────────────
CDN_HOST_RE   = re.compile(r"^https://scontent-[a-z0-9\-]+\.cdninstagram\.com/") # scontent-ssn1-1 등
CDN_PATH_ALLOW= re.compile(r"/o1/")   # # /o1/ 경로 포함 (t2, t16 등 세부 버전은 다양), 필요 시 |/o0/ 등 추가
MIN_GOOD_VIDEO_BYTES = 500_000        # 0.5MB 이상만 후보


# 동시 다운로드 제한
MAX_CONCURRENCY = 4

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
    login_user = page.locator("input[name='username']")
    login_pass = page.locator("input[name='password']")
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
    await page.wait_for_selector("main", timeout=15000)


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


async def collect_post_links(page, max_scrolls=MAX_SCROLLS, pause=SCROLL_PAUSE) -> List[str]:
    """프로필 페이지에서 스크롤하며 /p/, /reel/ 링크 수집 (상대경로 → 절대경로)"""
    links = []
    post_links: Set[str] = set()
    # stable_rounds = 0
    # last_count = 0
    already_collected_count = 0
    await page.wait_for_selector("main", timeout=20000)
    await asyncio.sleep(4)

    last_height = await page.evaluate("document.body.scrollHeight")

    for _ in range(max_scrolls):
        anchors = await page.locator('a[href*="/p/"], a[href*="/reel/"]').element_handles()
        if len(anchors) == 0:
            print('  ★★★★★★★★★★★★★★★★★★★★★★★ Account is not valid ★★★★★★★★★★★★★★★★★★★★★★★ ')
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
                if already_collected_count > ALREADY_COLLECTED_COUNT:
                    rev_links = links[::-1]   # slicing, 원본 보존
                    return rev_links

                url = "https://chickchick.shop/func/scrap-posts?urls="+origin_href
                res = requests.get(url)
                data = res.json()
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
UL_SEL   = "section main > div:nth-of-type(1) > div:nth-of-type(1) div[role='presentation'] ul"
LI_SEL   = UL_SEL + " > li"
IMG_SEL  = UL_SEL + " > li img"
FALLBACK_IMG  = "section main > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) img"
NEXT_BTN_SEL  = (
    "section main > div:nth-of-type(1) > div:nth-of-type(1) "
    "button[aria-label*='다음'], :has(button:has-text('다음')), "
    "button[aria-label*='Next'], :has(button:has-text('Next'))"
)

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

async def extract_imgs_src_only(page, post_url: str, seen: Set[str]) -> None:
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

    # 2) 캐러셀
    if ul_found and IMG_SEL and NEXT_BTN_SEL:
        async def collect_from_main() -> None:
            for u in await collect_max_images(IMG_SEL):
                if u:
                    seen.add(u)

        await collect_from_main()

        # "다음" 클릭 반복 (클릭 전 수집 → 클릭 → 잠깐 대기)
        for _ in range(20):
            next_btn = page.locator(NEXT_BTN_SEL).first
            if not await next_btn.count():
                break

            # 클릭 전 수집(현재 화면)
            await collect_from_main()

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

    return final_urls


def looks_like_good_video(resp):
    """좋은(완전) mp4 응답만 통과: 200 OK, video/*, CDN host, /o1/, 충분한 content-length, content-range 없음"""
    try:
        if resp.status != 200:
            return False
        # content-type
        ct = (resp.headers or {}).get("content-type", "")
        if "video" not in ct:
            return False
        # 조각 스트리밍 제외
        hdrs = {k.lower(): v for k, v in (resp.headers or {}).items()}
        if "content-range" in hdrs:
            return False
        # CDN host + 경로 규칙
        if not (CDN_HOST_RE.match(resp.url) and CDN_PATH_ALLOW.search(resp.url)):
            return False
        # 크기(있으면 체크)
        clen = hdrs.get("content-length")
        if clen and clen.isdigit() and int(clen) < MIN_GOOD_VIDEO_BYTES:
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
            # await asyncio.sleep(0.5)
            await asyncio.sleep(0.7)
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

    # 네트워크 응답에서 '좋은' 비디오만 즉시 선별 저장
    def on_response(resp):
        if looks_like_good_video(resp):
            good_video_urls.add(resp.url)
    page.on("response", on_response)

    await page.goto(url, wait_until="domcontentloaded")
    await asyncio.sleep(DELAY_SECOND) # 시간 조정

    # 이미지 수집 (도우미 사용)
    seen = set()
    images: List[str] = await extract_imgs_src_only(page, url, seen)

    # 비디오 수집: 보이게/재생 유도 → '좋은' 응답 대기
    await force_play_video_if_possible(page)

    # 잠시 재시도하며 응답 모으기(총 ~6초)
    for _ in range(4):
        if good_video_urls:
            break
        await asyncio.sleep(0.75) # 시간 조정

    # 보조: DOM의 <video src>도 수집(있을 수 있음) → CDN 필터 적용
    vids = page.locator("section main > div:nth-of-type(1) video")
    n_vid = await vids.count()
    dom_video_srcs = []
    for i in range(n_vid):
        vsrc = await vids.nth(i).get_attribute("src")
        if vsrc and vsrc.startswith("http"):
            dom_video_srcs.append(vsrc)

    # DOM/네트워크 합치고, 최종적으로 CDN 규칙으로 필터
    candidates = set(dom_video_srcs) | good_video_urls
    # video_cdn = sorted(u for u in candidates if CDN_HOST_RE.match(u) and CDN_PATH_ALLOW.search(u))
    unique = {}
    for u in candidates:
        if CDN_HOST_RE.match(u) and CDN_PATH_ALLOW.search(u):
            k = canonical_cdn_key(u)
            # 먼저 본(가장 '좋아 보이는') 원본 URL을 보존
            unique.setdefault(k, u)
    video_cdn = sorted(unique.values())

    return {
        "post_url": url,
        "images": images,        # 항상 채움(있으면)
        "videos": [],            # 사용하지 않으므로 빈 리스트 유지
        "video_cdn": video_cdn,  # 항상 채움(있으면)
    }

# async def extract_media_from_post(page, url: str) -> Dict[str, Any]:
#     """개별 포스트/릴스 페이지에서 이미지/영상 URL 추출."""
#     collected_network: Set[str] = set()
#
#     def on_response(resp):
#         # blob: 제외, 이미지/비디오 응답만 수집
#         ct = (resp.headers or {}).get("content-type", "")
#         if ("image" in ct or "video" in ct) and not resp.url.startswith("blob:"):
#             collected_network.add(resp.url)
#
#     page.on("response", on_response)
#
#     await page.goto(url, wait_until="domcontentloaded")
#     await asyncio.sleep(2.5)
#
#     # DOM 기반 수집
#     images: List[str] = await extract_imgs_src_only(page, url)   # ← 반드시 await
#     videos: List[str] = []
#     imgs = page.locator("article img")                      # ← 캐러셀 루프에서 사용할 locator
#     vids = page.locator("article video")
#
#     # 비디오(src)
#     n_vid = await vids.count()
#     for i in range(n_vid):
#         vsrc = await vids.nth(i).get_attribute("src")
#         if vsrc and vsrc.startswith("http"):
#             videos.append(vsrc)
#
#     # 캐러셀 '다음' 클릭 시도 (최대 5회)
#     for _ in range(5):
#         next_btn = page.locator("button[aria-label*='Next'], button:has-text('Next')")
#         if not await next_btn.count():
#             break
#         try:
#             await next_btn.click()
#             await asyncio.sleep(1.5)
#
#             # 새로 로드된 이미지/비디오 다시 수집
#             n_img = await imgs.count()
#             for i in range(n_img):
#                 src = await imgs.nth(i).get_attribute("src")
#                 if src and src.startswith("http"):
#                     images.append(src)
#
#             n_vid = await vids.count()
#             for i in range(n_vid):
#                 vsrc = await vids.nth(i).get_attribute("src")
#                 if vsrc and vsrc.startswith("http"):
#                     videos.append(vsrc)
#         except Exception:
#             break
#
#     # 중복 제거
#     images = list(dict.fromkeys(images))
#     videos = list(dict.fromkeys(videos))
#
#     return {
#         "post_url": url,
#         "images": images,
#         "videos": videos,
#         "video_cdn": filtered_video_cdn,
#     }


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

# ======== 다운로드 ========
async def download_one(session: aiohttp.ClientSession, url: str, save_dir: str, prefix: str="media") -> Optional[str]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
            if resp.status != 200:
                return None
            ct = resp.headers.get("Content-Type", "")
            ext = guess_ext_from_url_or_type(url, ct)

            ts = now_ms()
            seq = await next_seq()  # 타이브레이커
            fname = sanitize_filename(f"{prefix}_{ts:013d}_{seq:06d}{ext}")
            # fname = sanitize_filename(f"{prefix}_{int(time.time()*1000)}{ext}")
            path = os.path.join(save_dir, fname)
            data = await resp.read()
            with safe_open_exclusive(path) as f:
                f.write(data)
            # with open(path, "wb") as f:
            #     f.write(data)
            return path
    except FileExistsError:
        # 극히 드문 경합 대비 (다시 한 번 시퀀스 증가)
        seq = await next_seq()
        ts = now_ms()
        alt = os.path.join(save_dir, sanitize_filename(f"{prefix}_{ts:013d}_{seq:06d}{ext}"))
        with open(alt, "wb") as f:
            f.write(data)
        return alt
    except Exception:
        return None


async def download_media(images: List[str], videos: List[str], video_cdn: List[str], dirs: Dict[str, str], account: str):
    # 비디오는 video_cdn만 사용 (요구사항)
    video_sources = video_cdn if video_cdn else []

    # 중복 제거
    images = list(dict.fromkeys(images))
    video_sources = list(dict.fromkeys(video_sources))

    conn = aiohttp.TCPConnector(limit_per_host=MAX_CONCURRENCY, ssl=False)
    async with aiohttp.ClientSession(connector=conn) as session:
        tasks = []
        for i, url in enumerate(images, 1):
            tasks.append(download_one(session, url, dirs["images"], prefix=f"{account}_img"))
        for i, url in enumerate(video_sources, 1):
            tasks.append(download_one(session, url, dirs["reels"], prefix=f"{account}_reel"))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        ok_paths = [p for p in results if isinstance(p, str) and p]

        # 🔥 비디오 길이가 1초 미만이거나(0 포함) 길이 판독 실패(None)면 삭제
        deleted = []
        for p in ok_paths:
            try:
                if os.path.exists(p) and p.startswith(dirs["reels"]):
                    dur = get_video_duration_sec(p)  # None이면 판독 실패
                    # 규칙: dur is None(길이 불명) 또는 dur < 1.0 → 삭제
                    if dur is None or dur < 1.0:
                        os.remove(p)
                        deleted.append(p)
            except Exception as e:
                print(f"[WARN] 파일 삭제 실패: {p}, {e}")

        if deleted:
            print(f"[INFO] {len(deleted)}개의 짧은/길이불명 비디오 삭제됨 (<1s or unknown)")

        # 삭제되지 않은 경로만 반환
        return [p for p in ok_paths if p not in deleted]

def log_targets(context, tag=""):
    pages = context.pages
    bgs = context.background_pages
    sws = context.service_workers
    print(f"[DEBUG]{tag} pages={len(pages)} bg_pages={len(bgs)} service_workers={len(sws)}")
    for p in pages:
        try:
            print("  - page:", p.url)
        except Exception:
            pass


# ======== 메인 플로우 ========
async def handle_account(context, account: str):
    page = await context.new_page()
    await ensure_login(page)
    await go_to_profile(page, account)

    if account == 'test':
        # 디버깅
        links = TEST_LINKS
    else:
        # 링크 수집
        links = await collect_post_links(page)


    if len(links) > 5:
        print(f"[{account}] Collect Postlinks: {len(links)}")
    if len(links) > 300:
        await asyncio.sleep(60 * 30)  # 과도한 요청 방지

    # 저장 디렉토리 준비
    dirs = ensure_dirs(BASE_SAVE_DIR, account)

    all_saved = []
    check_saved = []
    cnt = 0
    for idx, link in enumerate(links, 1):
        today = datetime.datetime.today().strftime('%Y/%m/%d %H:%M:%S')
        # print(f"[{today}] [{account}] ({idx}/{len(links)}) {link}")
        print(f"[{account}] ({idx}/{len(links)}) {link}")

        parsed = urlparse(link)
        # ParseResult(scheme='https', netloc='www.instagram.com', path='/fkaus014/p/DO27U_DDw63/')
        qs_link = normalize_ig_post_url(parsed.path)
        parsed = urlparse(qs_link)

        cnt += 1
        # None, False, 0, '', [], {}, 모두 여기로 들어옴
        # if idx == 5: # 디버깅 테스트용
        #     break
        try:
            media = await extract_media_from_post(page, link)
            # print('media', media)
            # 이미지: 그대로 / 비디오: VIDEO_PREFIX만
            saved = await download_media(
                media["images"], media["videos"], media["video_cdn"], dirs, account
            )
            # print('saved', saved)
            all_saved.extend(saved or [])
            check_saved.extend(saved or [])
            if idx % 10 == 0:
                today = datetime.datetime.today().strftime('%Y/%m/%d %H:%M:%S')
                print(f"[{account}] [{today}] Interim check of number of saved files : {len(check_saved)}")
                check_saved = []
            link_segment = extract_account_and_type(normalize_ig_post_url(link))
            try:
                requests.post(
                    'https://chickchick.shop/func/scrap-posts',
                    json={
                        "account": str(account),
                        "post_urls": link,
                        "type": link_segment["type"],
                    },
                    # timeout=5
                    timeout=(3, 20)  # (connect_timeout=3초, read_timeout=20초)
                )
            except Exception as e:
                # logging.warning(f"progress-update 요청 실패: {e}")
                print(f"progress-update 요청 실패-1: {e}")
                pass  # 오류
            await asyncio.sleep(DELAY_SECOND)  # 과도한 요청 방지
            if cnt % 300 == 0:
                await asyncio.sleep(60 * 30)  # 과도한 요청 방지
            elif cnt % 100 == 0:
                await asyncio.sleep(DELAY_MINUTE)  # 과도한 요청 방지
        except Exception as e:
            print(f"  -> 에러: {e}")

    await page.close()
#     log_targets(context, tag=f" after {account}")

    if len(links) > 0:
        print(f"[{account}] Number of files saved: {len(all_saved)}")

    return len(links)

async def run_scrap():
    nowTime = datetime.datetime.today().strftime('%Y/%m/%d %H:%M:%S')
    print(f'        {nowTime}: running scrap ig')
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            USER_DATA_DIR,
            # headless=HEADLESS,  # 주석하면 브라우저 off
            # viewport={"width": 1920, "height": 1080},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )

        # 디버깅
        # await handle_account(context, 'test')

        for i, acc in enumerate(ACCOUNTS):
            today = datetime.datetime.today().strftime('%Y/%m/%d %H:%M:%S')
            print(f"\n=== [{today}] Start account processing: {acc} ({i+1}/{len(ACCOUNTS)}) ===")
            try:
                rs = await handle_account(context, acc)
            except Exception as e:
                print(f"[{acc}] Error in processing: {e}")
                continue

            if i < len(ACCOUNTS) - 1:
                if rs > 30:
                    await asyncio.sleep(DELAY_MINUTE) # 계정 간 쿨다운(선택): 과도한 접근 방지
                else:
                    await asyncio.sleep(30)

        await context.close()

def run_scrap_job():
    # 이벤트 루프는 “스레드당 1개”가 원칙
    asyncio.run(run_scrap())

if __name__ == "__main__":
    '''
    asyncio.run(run_scrap)      # ❌ 함수 자체를 넘김
    asyncio.run(run_scrap())    # ✅ 코루틴 객체를 넘김
    '''
    asyncio.run(run_scrap())
