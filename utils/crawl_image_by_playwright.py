import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config.config import settings
from playwright.sync_api import Playwright, sync_playwright
from urllib.parse import urljoin
from PIL import Image
from io import BytesIO
import uuid, os, requests

# 게시글 목록 페이지 URL 템플릿
url_template = settings['CRAWL_URL']
url_host = settings['CRAWL_HOST']
IMAGE_DIR = settings['IMAGE_DIR']


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
            print(f"{save_path}")
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

def auto_scroll_page(page):
    page.evaluate("""
        () => {
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


def crawl_images_from_page(page_num):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        page_url = url_template.format(page_num)
        print('url', page_url)
        page.goto(page_url, timeout=15000)
        page.wait_for_timeout(10000)  # 10초 대기 (ms 단위)

        # 게시글 링크 추출
        links = page.eval_on_selector_all(
            "a.vrow.column",
            "els => els.map(e => e.getAttribute('href'))"
        )

        post_links = [url_host + link for link in links if link and link.startswith("/")]
        # print(f"Page {page_num} post links:", post_links)

        # for post_url in post_links:
        for i, post_url in enumerate(post_links, start=1):
            try:
                print(f"[{i}/{len(post_links)}] ************************** post_url: {post_url}")
                page.goto(post_url, timeout=15000)

                # ✅ 천천히 자동 스크롤
                auto_scroll_page(page)

                # # ✅ <p><a><img></a></p> 구조에서 a 태그의 href 추출
                # hrefs = page.eval_on_selector_all(
                #     "div.article-body div.fr-view.article-content p a > img",
                #     "els => els.map(img => img.parentElement.getAttribute('href'))"
                # )
                #
                # # ac.namu.la 또는 ac-p1.namu.la 로 시작하는 원본 링크만 추출
                # img_urls = [href for href in hrefs if href and ("ac.namu.la" in href or "ac-p1.namu.la" in href)]

                # ✅ <p><a><img></a></p> 구조에서 img 태그의 src 추출
                srcs = page.eval_on_selector_all(
                    "div.article-body div.fr-view.article-content p a > img",
                    "els => els.map(img => img.getAttribute('src'))"
                )

                # ac.namu.la 또는 ac-p1.namu.la 로 시작하는 이미지 링크만 추출
                img_urls = [
                    ('https:' + src if src and src.startswith('//') else src)
                    for src in srcs
                    if src and ("ac.namu.la" in src or "ac-p1.namu.la" in src)
                ]

                for img_url in img_urls:
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    elif img_url.startswith('/'):
                        img_url = urljoin(url_host, img_url)

                    img_name = os.path.basename(img_url.split('?')[0])
                    save_image_with_uuid(img_name, img_url, IMAGE_DIR)

            except Exception as e:
                print(f"Error in {post_url}: {e}")

        browser.close()

# 실행
# 25.05.07
for page_num in range(1, 26):
    crawl_images_from_page(page_num)
    print(f"##### Done: page {page_num} #####")