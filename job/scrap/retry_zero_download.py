import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from config.config import settings
from playwright.async_api import async_playwright
from urllib.parse import urljoin
import uuid, requests
import asyncio
from datetime import datetime
import glob

url_host = settings['CRAWL_HOST']
IMAGE_DIR = settings['IMAGE_DIR']
os.makedirs(IMAGE_DIR, exist_ok=True)

def ts():
    return datetime.now().strftime("[INFO] [%Y/%m/%d %H:%M:%S]")


def collect_zero_urls(log_dir: str):
    """로그 파일에서 download success : 0 인 URL 목록 추출"""
    log_files = sorted(glob.glob(os.path.join(log_dir, "*.log")))
    zero_urls = []
    current_url = None

    for log_path in log_files:
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # URL 라인: [INFO] [...] [page X] (Y/Z) https://...
                if "[page" in line and "https://" in line:
                    current_url = "https://" + line.split("https://", 1)[1].strip()
                elif "download success : 0" in line and current_url:
                    zero_urls.append(current_url)
                    current_url = None
                elif "download success :" in line:
                    current_url = None

    seen = set()
    unique = []
    for u in zero_urls:
        base = u.split("?")[0]
        if base not in seen:
            seen.add(base)
            unique.append(u)
    return unique


def save_video_with_uuid(video_url: str, save_dir: str):
    ext = os.path.splitext(video_url.split("?")[0])[1] or ".mp4"
    new_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(save_dir, new_name)
    resp = requests.get(video_url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return save_path


async def auto_scroll(page):
    await page.evaluate("""
        async () => {
            return new Promise((resolve) => {
                let totalHeight = 0;
                const distance = 200;
                const timer = setInterval(() => {
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


async def retry_zero_downloads(post_urls):
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,
        args=["--window-size=10,10"],
    )
    context = await browser.new_context(viewport={"width": 10, "height": 10})
    page = await context.new_page()

    total = len(post_urls)
    for i, post_url in enumerate(post_urls, start=1):
        print(f"{ts()} ({i}/{total}) {post_url}", flush=True)
        try:
            await page.goto(post_url, timeout=15000)
            await auto_scroll(page)

            video_srcs = await page.eval_on_selector_all(
                "div.article-body div.fr-view.article-content p video",
                "els => els.map(v => v.getAttribute('src'))"
            )

            video_urls = [
                ("https:" + src if src and src.startswith("//") else src)
                for src in video_srcs
                if src and ("ac.namu.la" in src or "ac-p1.namu.la" in src)
            ]

            count = 0
            for video_url in video_urls:
                if video_url.startswith("//"):
                    video_url = "https:" + video_url
                elif video_url.startswith("/"):
                    video_url = urljoin(url_host, video_url)
                try:
                    path = save_video_with_uuid(video_url, IMAGE_DIR)
                    print(f"{ts()}   saved: {os.path.basename(path)}", flush=True)
                    count += 1
                except Exception as e:
                    print(f"{ts()}   video download failed: {e}", flush=True)

            print(f"{ts()} download success : {count}", flush=True)

        except Exception as e:
            print(f"{ts()} Error in {post_url}: {e}", flush=True)


def main():
    log_dir = "logs/a"
    month = datetime.now().strftime("%y%m")
    target_dir = os.path.join(log_dir, month)

    zero_urls = collect_zero_urls(target_dir)
    print(f"{ts()} 재시도 대상 URL: {len(zero_urls)}개", flush=True)
    if not zero_urls:
        print(f"{ts()} 대상 없음. 종료.", flush=True)
        os._exit(0)

    for u in zero_urls:
        print(f"  {u}", flush=True)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(retry_zero_downloads(zero_urls))
    finally:
        loop.close()
        os._exit(0)


if __name__ == "__main__":
    main()
