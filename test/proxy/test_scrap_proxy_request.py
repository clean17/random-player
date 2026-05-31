import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import quote, urljoin
from PIL import Image
from io import BytesIO
import uuid

import configparser
from pathlib import Path

config = configparser.ConfigParser()

cfg_path = Path(__file__).resolve().parent.parent / "config" / "config.ini"
read_files = config.read(cfg_path, encoding="utf-8")
print("sections  =", config.sections())    # 올라온 섹션 이름들

mud_vpn = config['urls']['mud_vpn']
encoded_username = quote(config['settings']['mudfish_username'])
encoded_password = quote(config['settings']['mudfish_password'])

# 프록시 설정 (미꾸라지 SOCKS5 프록시 서버 주소와 포트)
proxies = {
    'http': f'socks5h://{encoded_username}:{encoded_password}@{mud_vpn}',
    'https': f'socks5h://{encoded_username}:{encoded_password}@{mud_vpn}'
}

# 헤더 설정 (예시: 브라우저의 User-Agent)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
}


url = 'https://m.blog.naver.com/PostView.naver?blogId=mojjustice&logNo=224100395324'
try:
    response = requests.get(url, headers=headers, proxies=proxies, timeout=20)
    response.raise_for_status()  # HTTP 에러 자동 예외 발생

    soup = BeautifulSoup(response.content, 'html.parser')
    html_text = soup.prettify()

    # 저장 경로 설정
    save_path = "naver_post.html"
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(html_text)

    print(f"📁 HTML 저장 완료 → {save_path}")

except Exception as e:
    print("❌ 요청 또는 저장 중 오류:", e)