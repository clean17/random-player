"""
유저/비밀번호가 필요한 SOCKS5 프록시(34.84.172.146:18081)를 통해서 
https://httpbin.org/ip 에 요청을 보내서
실제로 프록시가 잘 동작하는지 테스트하는 스크립트
"""
import requests
from urllib.parse import quote

import os
import sys

# ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
# sys.path.append(ROOT_DIR)

from config.config import settings

username = settings['MUD_USERNAME']
password = settings['MUD_PASSWORD']

# URL 인코딩
encoded_username = quote(username)
encoded_password = quote(password)

# 프록시 설정 (socks5://username:password@host:port)
# socks5:// 는 프록시 서버를 지정하는 프로토콜
proxies = {
    'http': f'socks5://{encoded_username}:{encoded_password}@34.84.172.146:18081',
    'https': f'socks5://{encoded_username}:{encoded_password}@34.84.172.146:18081'
}

# 프록시를 경유한 테스트 요청
# httpbin.org/ip 는 이 요청이 보이는 클라이언트 IP 를 JSON으로 돌려주는 테스트용 API
try:
    response = requests.get('https://httpbin.org/ip', proxies=proxies)
    print(response.json())
except Exception as e:
    print(f"Error: {e}")

"""
venv 들어가서 모듈(패키지)를 실행
$ python -m test.test_vpn_socks5
{'origin': '34.84.172.146'}
"""