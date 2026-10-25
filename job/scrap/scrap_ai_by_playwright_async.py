import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from config.config import settings
from utils.image_thumbs import ensure_thumb
from playwright.async_api import async_playwright
from urllib.parse import urljoin, urlparse, parse_qs
from PIL import Image
from io import BytesIO
import uuid, os, requests
import json
import asyncio
import base64
import time
from datetime import datetime

def ts():
    return datetime.now().strftime("[INFO] [%Y/%m/%d %H:%M:%S]")

today = datetime.now().strftime("%Y%m%d")
month = datetime.now().strftime("%y%m")
month_dir = f"logs/a/{month}"
os.makedirs(month_dir, exist_ok=True)
filename = f"{month_dir}/scrap_ai_{today}.log"
log_file = open(filename, "a", encoding="utf-8")
sys.stdout = log_file
sys.stderr = log_file
# print("이건 파일로 감")
# raise Exception("에러도 파일로 감")

# 게시글 목록 페이지 URL 템플릿 (아래 목록 순서대로 게시판을 하나씩 끝까지 진행)
BOARD_URL_TEMPLATES = [
    settings['CRAWL_URL'],   # 기존 설정값 (aireal)
    # settings['CRAWL_URL2'],  # aibansil
    "https://arca.live/b/aibansil?mode=best&p={}",
]
url_host = settings['CRAWL_HOST']
IMAGE_DIR = settings['IMAGE_DIR']
# IMAGE_DIR = 'D:\\temp_img_dir'

# 이미지 저장 경로 설정
os.makedirs(IMAGE_DIR, exist_ok=True)




# 기존 다운로드 함수 그대로 사용
def download_image(img_url, save_path):
    try:
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = urljoin(url_host, img_url)

        img_data = requests.get(img_url).content
        img = Image.open(BytesIO(img_data))
        if img.width >= 700:
            with open(save_path, 'wb') as handler:
                handler.write(img_data)
            # print(f"Downloaded {img_url} to {save_path}")
            # print(f"{save_path}")
            ensure_thumb(save_path, IMAGE_DIR)   # 저장 직후 썸네일 — 실패해도 예외 없이 'fail' 만 돌려준다
            return True
        else:
            # print(f"Skipped {img_url}, width: {img.width}px")
            return False
    except Exception as e:
        print(f"Failed to download {img_url}: {e}")
        return False

def save_image_with_uuid(img_name, img_url, save_dir):
    name, ext = os.path.splitext(img_name)
    unique_img_name = f"{name}{ext}"
    save_path = os.path.join(save_dir, unique_img_name)
    return download_image(img_url, save_path)

# 이미지·영상 호스트 — 예전 글은 namu.la, 2026-10 이후 글은 arca.live(ac.arca.live / ac-o.arca.live)
MEDIA_HOSTS = ("ac.namu.la", "ac-p1.namu.la", "arca.live")


def is_media_url(src):
    return bool(src) and any(host in src for host in MEDIA_HOSTS)


def to_absolute_url(src):
    if src.startswith('//'):
        return 'https:' + src
    if src.startswith('/'):
        return urljoin(url_host, src)
    return src


def media_candidates(pairs):
    """[[data-originalurl, src], ...] → 요소마다 시도할 주소 목록. 허용 호스트만, 중복 요소는 한 번만."""
    result = []
    seen = set()
    for pair in pairs:
        urls = [to_absolute_url(u) for u in dict.fromkeys(pair) if is_media_url(u)]
        if not urls:
            continue
        key = urls[0].split('?')[0]   # expires/key 만 다른 같은 파일
        if key in seen:
            continue
        seen.add(key)
        result.append(urls)
    return result

# 서명 URL(?expires=...&key=...)의 만료 여부를 먼저 확인 — 만료된 상태면 재시도해도 소용없으니
# 로그에 남겨서 "네트워크 문제였는지 vs 이미 만료돼서였는지"를 바로 구분할 수 있게 한다.
def _signed_url_expiry_info(url):
    try:
        qs = parse_qs(urlparse(url).query)
        expires = int(qs.get("expires", [None])[0])
    except (TypeError, ValueError, IndexError):
        return None
    remaining = expires - time.time()
    return expires, remaining

# 브라우저 자체 JS 엔진의 fetch()로 받아온다. requests / page.request 둘 다 이 CDN의 영상 경로에서
# Cloudflare 챌린지(403)를 만나는데, 실제 페이지 렌더링과 동일한 네트워크 핑거프린트를 쓰는
# page.evaluate() 안의 fetch()만 통과되는 것을 확인함.
async def save_video_with_uuid(page, video_name: str, video_url: str, save_dir: str, max_attempts=3):
    ext = os.path.splitext(video_name)[1] or ".mp4"
    new_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(save_dir, new_name)

    fetch_script = """
        async (url) => {
            const res = await fetch(url);
            if (!res.ok) return { ok: false, status: res.status };
            const buf = await res.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let binary = '';
            const chunkSize = 0x8000; // 32KB씩 나눠서 문자열 변환 (콜스택 한도 회피)
            for (let i = 0; i < bytes.length; i += chunkSize) {
                binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
            }
            return { ok: true, base64: btoa(binary) };
        }
    """

    for attempt in range(1, max_attempts + 1):
        try:
            result = await page.evaluate(fetch_script, video_url)

            if not result.get("ok"):
                print(f"Failed to download {video_url}: HTTP {result.get('status')}")
                return False

            data = base64.b64decode(result["base64"])
            with open(save_path, "wb") as f:
                f.write(data)
            # 영상 프레임 추출은 ffmpeg 호출이라 이벤트 루프를 막지 않게 스레드로
            await asyncio.get_event_loop().run_in_executor(None, ensure_thumb, save_path, IMAGE_DIR)
            return True
        except Exception as e:
            expiry_info = _signed_url_expiry_info(video_url)
            if expiry_info and expiry_info[1] <= 0:
                print(f"Failed to download {video_url}: {e} (서명 URL 만료됨, {-expiry_info[1]:.0f}초 지남 — 재시도해도 소용없음)")
                return False
            if attempt < max_attempts:
                print(f"Failed to download {video_url}: {e} (재시도 {attempt}/{max_attempts})")
                await page.wait_for_timeout(1500)
                continue
            print(f"Failed to download {video_url}: {e} (재시도 {max_attempts}회 모두 실패)")
    return False

CLOUDFLARE_TITLE_MARKERS = ("Just a moment", "Attention Required")

async def wait_for_cloudflare_clear(page, max_attempts=3, wait_ms=4000):
    """
    Cloudflare 봇 검증 페이지("Just a moment...")가 떠 있으면 몇 차례 대기+새로고침하며 풀리는지 확인.
    실제 콘텐츠 페이지로 넘어가면 True, max_attempts 안에 못 풀면 False.
    """
    for attempt in range(max_attempts):
        title = await page.title()
        if not any(marker in title for marker in CLOUDFLARE_TITLE_MARKERS):
            return True
        print(f"{ts()} Cloudflare 검증 대기 중... (시도 {attempt + 1}/{max_attempts})", flush=True)
        await page.wait_for_timeout(wait_ms)
        try:
            await page.reload(timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(wait_ms)

    title = await page.title()
    return not any(marker in title for marker in CLOUDFLARE_TITLE_MARKERS)


async def async_auto_scroll_page(page):
    await page.evaluate("""
        async () => {
            return new Promise((resolve) => {
                let totalHeight = 0;
                const distance = 160; // px 단위로 조금씩 내리기 (기존 200에서 20% 감속)
                const timer = setInterval(() => {
                    // id="comment"는 페이지 골격에 항상 존재하므로 "존재 여부"가 아니라
                    // 실제로 뷰포트 안으로 스크롤되어 들어왔는지로 판단해야 함
                    const commentEl = document.getElementById('comment');
                    if (commentEl && commentEl.getBoundingClientRect().top <= window.innerHeight) {
                        clearInterval(timer);
                        resolve();
                        return;
                    }

                    const scrollHeight = document.body.scrollHeight;
                    window.scrollBy(0, distance);
                    totalHeight += distance;
                    if (totalHeight >= scrollHeight - window.innerHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 120);
            });
        }
    """)


async def async_crawl_images_from_page(page_num, board_url_template):
    """
    이 함수가 True를 반환하면 이미 수집된 게시글에 도달했다는 뜻 —
    호출 쪽(async_crawl_ai)에서 현재 게시판 순회를 멈추고 다음 게시판으로 넘어간다.
    """
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,
        # 10x10처럼 비정상적으로 작은 창/뷰포트는 Cloudflare 봇 탐지에 걸려 콘텐츠 대신
        # "Just a moment..." 챌린지 페이지가 뜬다. 정상 크기를 유지하되 화면 밖으로 위치시켜 안 보이게 한다.
        args=[
            "--disable-blink-features=AutomationControlled",
            "--window-position=-3000,-3000",
            "--window-size=1280,800",
        ],
    )
    context = await browser.new_context(viewport={"width": 1280, "height": 800})
    page = await context.new_page()

    reached_existing = False

    try:
        page_url = board_url_template.format(page_num)
        await page.goto(page_url, timeout=15000)
        if not await wait_for_cloudflare_clear(page):
            print(f"{ts()} [page {page_num}] Cloudflare 검증을 통과하지 못해 목록을 가져오지 못함", flush=True)

        # 게시글 링크 추출
        links = await page.eval_on_selector_all(
            "a.vrow.column:not(.notice)",
            "els => els.map(e => e.getAttribute('href'))"
        )

        post_links = [url_host + link for link in links if link and link.startswith("/")]

        for i, post_url in enumerate(post_links, start=1):
            try:
                print(f"{ts()} [page {page_num}] ({i}/{len(post_links)}) {post_url}", flush=True)
                current_url = post_url.split('?')[0]
                account = current_url.split('/')[-2]

                # 수집한 적이 있는지 확인
                url = "https://chickchick.kr/func/scrap-posts?urls="+current_url
                res = requests.get(url)
                data = res.json()
                if data["result"]: # 등록되어 있음
                    print(f"{ts()} ##### Done: page {page_num} #####", flush=True)
                    log_file.flush()
                    reached_existing = True
                    break

                await page.goto(post_url, timeout=15000)

                if not await wait_for_cloudflare_clear(page):
                    print(f"{ts()} Cloudflare 검증을 통과하지 못해 건너뜀: {post_url}", flush=True)
                    continue

                # 천천히 자동 스크롤
                await async_auto_scroll_page(page)

                # <a><img></a> 구조에서 img 주소 추출 (<p>로 안 감싼 글도 있어 p 는 뺐다)
                # arca.live 글은 src 가 리사이즈본이고 원본(type=orig)은 data-originalurl 에 있다.
                # namu.la 글은 data-originalurl 이 없어 기존처럼 src 만 쓴다.
                # data-originalurl 의 expires 가 src 보다 이른(이미 만료된) 경우가 있어 [원본, src] 순으로 시도한다.
                img_pairs = await page.eval_on_selector_all(
                    "div.article-body div.fr-view.article-content a > img",
                    "els => els.map(img => [img.getAttribute('data-originalurl'), img.getAttribute('src')])"
                )
                # 영상: 예전 <p><span><video>, 2026-10 이후 <video class="video-autoplay"> — 감싸는 태그 무관하게 잡는다
                video_pairs = await page.eval_on_selector_all(
                    "div.article-body div.fr-view.article-content video",
                    "els => els.map(video => [video.getAttribute('data-originalurl'), video.getAttribute('src')])"
                )

                img_candidates = media_candidates(img_pairs)
                video_candidates = media_candidates(video_pairs)

                img_count = 0
                video_count = 0
                for urls in img_candidates:
                    img_name = os.path.basename(urls[0].split('?')[0])
                    # 폭 700px 미만·실패는 제외
                    if any(save_image_with_uuid(img_name, url, IMAGE_DIR) for url in urls):
                        img_count += 1

                for urls in video_candidates:
                    video_name = os.path.basename(urls[0].split('?')[0])
                    for url in urls:   # 원본 실패 시 src 로
                        if await save_video_with_uuid(page, video_name, url, IMAGE_DIR):
                            video_count += 1
                            break
                print(f"{ts()} download success : 이미지 {img_count}/{len(img_candidates)}, 영상 {video_count}/{len(video_candidates)}", flush=True)

                # 수집 후 url을 등록한다
                try:
                    requests.post(
                        'https://chickchick.kr/func/scrap-posts',
                        json={
                            "account": str(account),
                            "post_urls": current_url,
                            "type": 'ai',
                        },
                        timeout=(3, 20)  # (connect_timeout=3초, read_timeout=20초)
                    )
                except Exception as e:
                    print(f"progress-update 요청 실패-ai: {e}")
                    pass  # 오류

            except Exception as e:
                print(f"{ts()} Error in {post_url}: {e}", flush=True)
    finally:
        await browser.close()

    return reached_existing


async def async_crawl_ai():
    for board_index, board_url_template in enumerate(BOARD_URL_TEMPLATES, start=1):
        print(f"{ts()} ========== 게시판 {board_index}/{len(BOARD_URL_TEMPLATES)} 시작: {board_url_template} ==========", flush=True)
        for page_num in range(1, 21):
            print(f"{ts()} ##### Start: page {page_num} #####", flush=True)
            reached_existing = await async_crawl_images_from_page(page_num, board_url_template)
            if reached_existing:
                break

    log_file.close()

def run_scrap_ai_job():
    # 이벤트 루프는 “스레드당 1개”가 원칙
    asyncio.run(async_crawl_ai())

# 그냥 호출(async_crawl_ai())하면 코루틴 객체만 리턴, 코드가 실행되지 않음
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
try:
    loop.run_until_complete(async_crawl_ai())
finally:
    loop.close()
    log_file.flush()
    os._exit(0)  # anyio atexit 스레드 풀 경고 방지

'''
비동기 함수(코루틴, asyncio) 안에서 아래 코드 사용하면 ?

with sync_playwright() as p:
    → Sync API(동기 API)를 호출하면
    → Playwright 내부적으로 이미 asyncio 이벤트 루프가 돌고 있는데, 또다시 블로킹 코드(Sync API)를 쓰면 안 됨
    (Python의 asyncio 시스템은 비동기/동기 코드가 충돌하지 않도록 엄격하게 막고 있음)
    
따라서 비동기 함수 안에서는 Playwright의 Async API를 써야 함 >> sync_playwright > async_playwright
'''