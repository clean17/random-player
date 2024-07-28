import requests
from bs4 import BeautifulSoup
import os
import time
from urllib.parse import quote, urljoin
from config import settings

# 게시글 목록 페이지 URL 템플릿
url_template = settings['CRAWL_URL']
url_host = settings['CRAWL_HOST']

encoded_username = quote(settings['MUD_USERNAME'])
encoded_password = quote(settings['MUD_PASSWORD'])

# 프록시 설정 (미꾸라지 SOCKS5 프록시 서버 주소와 포트)
proxies = {
    'http': f'socks5://{encoded_username}:{encoded_password}@34.84.172.146:18081',
    'https': f'socks5://{encoded_username}:{encoded_password}@34.84.172.146:18081'
}

# 헤더 설정 (예시: 브라우저의 User-Agent)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# 이미지 저장 경로 설정
save_dir = "images"
os.makedirs(save_dir, exist_ok=True)

def download_image(img_url, save_path):
    try:
        img_data = requests.get(img_url, headers=headers, proxies=proxies).content
        with open(save_path, 'wb') as handler:
            handler.write(img_data)
    except Exception as e:
        print(f"Failed to download {img_url}: {e}")

def crawl_images_from_page(page_num):
    url = url_template.format(page_num)
    response = requests.get(url, headers=headers, proxies=proxies)
    soup = BeautifulSoup(response.content, 'html.parser')

    # 페이지 소스를 출력하여 확인
    # print(f"Page {page_num} HTML:\n", soup.prettify())

    post_links = [a['href'] for a in soup.select('a.vrow.column') if 'href' in a.attrs]

    # 추출된 링크를 출력하여 확인
    # print(f"Page {page_num} post links: {post_links}")

    for post_link in post_links:
        post_url = f"{url_host}{post_link}"
        post_response = requests.get(post_url, headers=headers, proxies=proxies)
        post_soup = BeautifulSoup(post_response.content, 'html.parser')

        # 'div.article-body > div.fr-view.article-content > p > img' 태그를 탐색하여 'src' 속성 값 추출
        img_urls = [img['src'] for img in post_soup.select('div.article-body div.fr-view.article-content p img')]

        for img_url in img_urls:
            # URL에 스킴이 없는 경우 'https:' 또는 절대 경로로 변환
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif img_url.startswith('/'):
                img_url = urljoin(url_host, img_url)
            img_name = os.path.basename(img_url.split('?')[0])  # 쿼리스트링 제거 후 파일명 추출
            save_path = os.path.join(save_dir, img_name)
            download_image(img_url, save_path)
            print(f"Downloaded {img_url} to {save_path}")

# 페이지 1부터 10까지 크롤링
for page_num in range(1, 2):
    crawl_images_from_page(page_num)
    time.sleep(10)  # 너무 빠르게 요청을 보내지 않도록 딜레이 추가
