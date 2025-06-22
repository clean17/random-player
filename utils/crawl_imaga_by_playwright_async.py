import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config.config import settings
from playwright.async_api import async_playwright
from urllib.parse import urljoin
from PIL import Image
from io import BytesIO
import uuid, os, requests
import json

# 게시글 목록 페이지 URL 템플릿
url_template = settings['CRAWL_URL']
url_host = settings['CRAWL_HOST']
IMAGE_DIR = settings['IMAGE_DIR']
is_first = True
save_url = None

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

async def async_auto_scroll_page(page):
    await page.evaluate("""
        async () => {
            await new Promise((resolve) => {
                let totalHeight = 0;
                const distance = 100;
                const timer = setInterval(() => {
                    window.scrollBy(0, distance);
                    totalHeight += distance;
                    if (totalHeight >= document.body.scrollHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 100);
            });
        }
    """)


async def async_crawl_images_from_page(page_num):
    global is_first
    global save_url

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        page_url = url_template.format(page_num)
        print('url', page_url)
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

        # 현재 스크립트 파일의 경로
        SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(SCRIPT_DIR, '..', 'data', 'data.json')
        file_path = os.path.normpath(file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for i, post_url in enumerate(post_links, start=1):
            try:
                print(f"[{i}/{len(post_links)}] ************************** post_url: {post_url}")
                current_url = post_url.split('?')[0]

                if is_first and page_num == 1:
                    save_url = current_url
                    is_first = False

                if data.get('ai_scheduler_uri') == current_url:
                    print(f"동일함! for문 중단  {data.get('ai_scheduler_uri')}")
                    data['ai_scheduler_uri'] = save_url
                    with open(file_path, "w", encoding="utf-8") as f: # 쓰기
                        json.dump(data, f, ensure_ascii=False, indent=2)
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

                count = 0
                for img_url in img_urls:
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = urljoin(url_host, img_url)

                    img_name = os.path.basename(img_url.split('?')[0])
                    save_image_with_uuid(img_name, img_url, IMAGE_DIR)
                    count += 1
                print(f'download success : {count}')

            except Exception as e:
                print(f"Error in {post_url}: {e}")

        await browser.close()


async def async_crawl_ai():
    for page_num in range(1, 21):
        print(f"##### Start: page {page_num} #####")
        await async_crawl_images_from_page(page_num)
        print(f"##### Done: page {page_num} #####")

# 그냥 호출(async_crawl_ai())하면 코루틴 객체만 리턴, 코드가 실행되지 않음
# asyncio.run(async_crawl_ai())

'''
비동기 함수(코루틴, asyncio) 안에서 아래 코드 사용하면 ?

with sync_playwright() as p:
    → Sync API(동기 API)를 호출하면
    → Playwright 내부적으로 이미 asyncio 이벤트 루프가 돌고 있는데, 또다시 블로킹 코드(Sync API)를 쓰면 안 됨
    (Python의 asyncio 시스템은 비동기/동기 코드가 충돌하지 않도록 엄격하게 막고 있음)
    
따라서 비동기 함수 안에서는 Playwright의 Async API를 써야 함 >> sync_playwright > async_playwright
'''