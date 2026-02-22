import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from config.config import settings
from playwright.async_api import async_playwright
from urllib.parse import urljoin
from PIL import Image
from io import BytesIO
import uuid, os, requests
import json
import asyncio
import datetime

today = datetime.datetime.now().strftime("%Y%m%d")
filename = f"logs/scrap_ai_{today}.log"
log_file = open(filename, "w", encoding="utf-8")
sys.stdout = log_file
sys.stderr = log_file
# print("이건 파일로 감")
# raise Exception("에러도 파일로 감")

# 게시글 목록 페이지 URL 템플릿
url_template = settings['CRAWL_URL']
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
        else:
            # print(f"Skipped {img_url}, width: {img.width}px")
            pass
    except Exception as e:
        print(f"Failed to download {img_url}: {e}")

def save_image_with_uuid(img_name, img_url, save_dir):
    name, ext = os.path.splitext(img_name)
    unique_img_name = f"{name}{ext}"
    save_path = os.path.join(save_dir, unique_img_name)
    download_image(img_url, save_path)

def save_video_with_uuid(video_name: str, video_url: str, save_dir: str):
    ext = os.path.splitext(video_name)[1] or ".mp4"
    new_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(save_dir, new_name)

    resp = requests.get(video_url, stream=True, timeout=60)
    resp.raise_for_status()

    with open(save_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

async def async_auto_scroll_page(page):
    await page.evaluate("""
        async () => {
            return new Promise((resolve) => {
                let totalHeight = 0;
                const distance = 200; // px 단위로 조금씩 내리기
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


async def async_crawl_images_from_page(page_num):

    async with async_playwright() as p:
        # browser = await p.chromium.launch(headless=False)
        browser = await p.chromium.launch(
            headless=False,
            args=["--window-size=10,10"],
        )
        # browser = p.chromium.launch(headless=True) # 운영
        # page = await browser.new_page()

        context = await browser.new_context(viewport={"width": 10, "height": 10})
        page = await context.new_page()

        page_url = url_template.format(page_num)
        # print('url', page_url)
        await page.goto(page_url, timeout=15000)
        await page.wait_for_timeout(4000)
        await page.reload()
        await page.wait_for_timeout(4000)

        # 게시글 링크 추출
        links = await page.eval_on_selector_all(
            "a.vrow.column:not(.notice)",
            "els => els.map(e => e.getAttribute('href'))"
        )

        post_links = [url_host + link for link in links if link and link.startswith("/")]
        # print(f"Page {page_num} post links:", post_links)


        for i, post_url in enumerate(post_links, start=1):
            try:
                print(f"[{i}/{len(post_links)}] ************************** post_url: {post_url}")
                current_url = post_url.split('?')[0]
                account = current_url.split('/')[-2]

                # 수집한 적이 있는지 확인
                url = "https://chickchick.kr/func/scrap-posts?urls="+current_url
                res = requests.get(url)
                data = res.json()
                # print(data)
                if data["result"]: # 등록되어 있음
                    print(f"##### Done: page {page_num} #####")
                    sys.exit(0)  # 여기서 프로그램 전체가 종료됨


                await page.goto(post_url, timeout=15000)

                # ✅ 천천히 자동 스크롤
                await async_auto_scroll_page(page)

                # ✅ <p><a><img></a></p> 구조에서 img 태그의 src 추출
                srcs = await page.eval_on_selector_all(
                    "div.article-body div.fr-view.article-content p a > img",
                    "els => els.map(img => img.getAttribute('src'))"
                )

                img_urls = [
                    ('https:' + src if src and src.startswith('//') else src)
                    for src in srcs
                    if src and ("ac.namu.la" in src or "ac-p1.namu.la" in src)
                ]

                video_srcs = await page.eval_on_selector_all(
                    "div.article-body div.fr-view.article-content p span > video",
                    "els => els.map(video => video.getAttribute('src'))"
                )

                video_urls = [
                    ('https:' + src if src and src.startswith('//') else src)
                    for src in video_srcs
                    if src and ("ac.namu.la" in src or "ac-p1.namu.la" in src)
                ]

                count = 0
                for img_url in img_urls:
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = urljoin(url_host, img_url)

                    img_name = os.path.basename(img_url.split('?')[0])
                    save_image_with_uuid(img_name, img_url, IMAGE_DIR)
                    count = count + 1

                for video_url in video_urls:
                    if video_url.startswith('//'):
                        video_url = 'https:' + video_url
                    elif video_url.startswith('/'):
                        video_url = urljoin(url_host, video_url)

                    video_name = os.path.basename(video_url.split('?')[0])
                    save_video_with_uuid(video_name, video_url, IMAGE_DIR)
                    count = count + 1
                print(f'download success : {count}')

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
                    # logging.warning(f"progress-update 요청 실패: {e}")
                    print(f"progress-update 요청 실패-ai: {e}")
                    pass  # 오류

            except Exception as e:
                print(f"Error in {post_url}: {e}")

        # await browser.close()


async def async_crawl_ai():
    for page_num in range(1, 21):
        print(f"##### Start: page {page_num} #####")
        await async_crawl_images_from_page(page_num)

    log_file.close()

def run_scrap_ai_job():
    # 이벤트 루프는 “스레드당 1개”가 원칙
    asyncio.run(async_crawl_ai())

# 그냥 호출(async_crawl_ai())하면 코루틴 객체만 리턴, 코드가 실행되지 않음
asyncio.run(async_crawl_ai())

'''
비동기 함수(코루틴, asyncio) 안에서 아래 코드 사용하면 ?

with sync_playwright() as p:
    → Sync API(동기 API)를 호출하면
    → Playwright 내부적으로 이미 asyncio 이벤트 루프가 돌고 있는데, 또다시 블로킹 코드(Sync API)를 쓰면 안 됨
    (Python의 asyncio 시스템은 비동기/동기 코드가 충돌하지 않도록 엄격하게 막고 있음)
    
따라서 비동기 함수 안에서는 Playwright의 Async API를 써야 함 >> sync_playwright > async_playwright
'''