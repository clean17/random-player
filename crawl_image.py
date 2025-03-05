import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import quote, urljoin
from config import settings
from PIL import Image
from io import BytesIO
import uuid

# 게시글 목록 페이지 URL 템플릿
url_template = settings['CRAWL_URL']
url_host = settings['CRAWL_HOST']
mud_vpn = settings['MUD_VPN']
cookie = settings['COOKIE']
IMAGE_DIR = settings['IMAGE_DIR']

encoded_username = quote(settings['MUD_USERNAME'])
encoded_password = quote(settings['MUD_PASSWORD'])

# 프록시 설정 (미꾸라지 SOCKS5 프록시 서버 주소와 포트)
proxies = {
    'http': f'socks5://{encoded_username}:{encoded_password}@{mud_vpn}',
    'https': f'socks5://{encoded_username}:{encoded_password}@{mud_vpn}'
}

# 헤더 설정 (예시: 브라우저의 User-Agent)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Cookie': cookie
}

# 이미지 저장 경로 설정
os.makedirs(IMAGE_DIR, exist_ok=True)

def download_image(img_url, save_path):
    try:
        # URL에 스킴이 없는 경우 'https:' 추가
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            img_url = urljoin(url_host, img_url)

        # 이미지 다운로드
        img_data = requests.get(img_url, headers=headers, proxies=proxies).content

        # 이미지 크기 확인, 가로 700 이상
        img = Image.open(BytesIO(img_data))
        if img.width >= 700:
            with open(save_path, 'wb') as handler:
                handler.write(img_data)
            print(f"Downloaded {img_url} to {save_path}")
        else:
            print(f"Skipped {img_url} due to insufficient width: {img.width}px")
    except Exception as e:
        print(f"Failed to download {img_url}: {e}")


def save_image_with_uuid(img_name, img_url, save_dir):
    # 확장자 분리
    name, ext = os.path.splitext(img_name)
    # UUID 생성
    unique_img_name = f"{name}_{uuid.uuid4()}{ext}"
    # 저장 경로 생성
    save_path = os.path.join(save_dir, unique_img_name)
    # 이미지 다운로드
    download_image(img_url, save_path)

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
        # post_response = requests.get(post_url, headers=headers, proxies=proxies)

        try:
            post_response = requests.get(post_url, headers=headers, proxies=proxies)
            post_response.raise_for_status()  # Check for HTTP errors
        # Process the response
        except requests.exceptions.ProxyError as e:
            print("Proxy error:", e)
        except requests.exceptions.ConnectionError as e:
            print("Connection error:", e)
        except requests.exceptions.RequestException as e:
            print("An error occurred:", e)

        post_soup = BeautifulSoup(post_response.content, 'html.parser')

        # 'div.article-body > div.fr-view.article-content > p > img' 태그를 탐색하여 'src' 속성 값 추출
        img_urls = [img['src'] for img in post_soup.select('div.article-body div.fr-view.article-content p img') if img.get('src', '').startswith('//ac.namu.la')]

        for img_url in img_urls:
            # URL에 스킴이 없는 경우 'https:' 또는 절대 경로로 변환
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif img_url.startswith('/'):
                img_url = urljoin(url_host, img_url)
            img_name = os.path.basename(img_url.split('?')[0])  # 쿼리스트링 제거 후 파일명 추출

            # 중복된 파일명을 피하기 위해 고유 식별자 추가
            # save_image_with_uuid(img_name, img_url, save_dir)
            save_image_with_uuid(img_name, img_url, IMAGE_DIR)

# 페이지 1부터 10까지 크롤링 (1:11)
# 24.08.13 ~ 24.09.14
# 24.09.15 ~ 24.10.04
# 24.10.04 ~ 24.10.30
# 24.11.01 ~ 24.12.26
# 24.12.27 ~ 25.02.16
for page_num in range(1, 28):
    crawl_images_from_page(page_num)
    print(f' ##########################   page_num   ################################# : {page_num}')
