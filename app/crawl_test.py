import requests
from bs4 import BeautifulSoup
import os
import time

from config import settings

# 게시글 목록 페이지 URL 템플릿
url_template = settings['CRAWL_URL']
url_host = settings['CRAWL_HOST']

# 이미지 저장 경로 설정
save_dir = "images"
os.makedirs(save_dir, exist_ok=True)

def download_image(img_url, save_path):
    try:
        img_data = requests.get(img_url).content
        with open(save_path, 'wb') as handler:
            handler.write(img_data)
    except Exception as e:
        print(f"Failed to download {img_url}: {e}")

def crawl_images_from_page(page_num):
    url = url_template.format(page_num)
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # 페이지 소스를 출력하여 확인
    print(f"Page {page_num} HTML:\n", soup.prettify())

    post_links = [a['href'] for a in soup.select('a.vrow.column') if 'href' in a.attrs]

    # 추출된 링크를 출력하여 확인
    print(f"Page {page_num} post links: {post_links}")

    for post_link in post_links:
        post_url = f"{url_host}{post_link}"
        post_response = requests.get(post_url)
        post_soup = BeautifulSoup(post_response.content, 'html.parser')

        img_urls = [img['src'] for img in post_soup.select('img') if img['src'].startswith('http')]

        for img_url in img_urls:
            img_name = os.path.basename(img_url)
            save_path = os.path.join(save_dir, img_name)
            download_image(img_url, save_path)
            print(f"Downloaded {img_url} to {save_path}")

# 페이지 1부터 10까지 크롤링
for page_num in range(1, 11):
    crawl_images_from_page(page_num)
    time.sleep(1)  # 너무 빠르게 요청을 보내지 않도록 딜레이 추가
