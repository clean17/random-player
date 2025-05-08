import requests
from urllib.parse import quote
from config import settings

username = settings['MUD_USERNAME']
password = settings['MUD_PASSWORD']

encoded_username = quote(username)
encoded_password = quote(password)

# 프록시 설정
proxies = {
    'http': f'socks5://{encoded_username}:{encoded_password}@34.84.172.146:18081',
    'https': f'socks5://{encoded_username}:{encoded_password}@34.84.172.146:18081'
}

# 테스트 요청
try:
    response = requests.get('https://httpbin.org/ip', proxies=proxies)
    print(response.json())
except Exception as e:
    print(f"Error: {e}")