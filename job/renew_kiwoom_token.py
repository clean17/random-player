import requests
import json

from dotenv import load_dotenv
import os

load_dotenv()  # .env 파일을 현재 환경변수로 로드

M_APP_KEY = os.environ.get('M_APP_KEY')
M_SECRET_KEY = os.environ.get('M_SECRET_KEY')

# 접근토큰 발급
def fn_au10001(data):
    # 1. 요청할 API URL
    #host = 'https://mockapi.kiwoom.com' # 모의투자
    host = 'https://api.kiwoom.com' # 실전투자
    endpoint = '/oauth2/token'
    url =  host + endpoint

    # 2. header 데이터
    headers = {
        'Content-Type': 'application/json;charset=UTF-8', # 컨텐츠타입
    }

    # 3. http POST 요청
    response = requests.post(url, headers=headers, json=data)

    # 4. 응답 상태 코드와 데이터 출력
    print('Code:', response.status_code)
    print('Header:', json.dumps({key: response.headers.get(key) for key in ['next-key', 'cont-yn', 'api-id']}, indent=4, ensure_ascii=False))
    body = json.dumps(response.json(), indent=4, ensure_ascii=False)
    data = json.loads(body)
    token = data["token"]
    print('Body:', body)  # JSON 응답을 파싱하여 출력
    print('Token:', token)

# 실행 구간
if __name__ == '__main__':
    # 1. 요청 데이터
    params = {
        'grant_type': 'client_credentials',  # grant_type
        'appkey': M_APP_KEY,  # 앱키
        'secretkey': M_SECRET_KEY,  # 시크릿키
    }

    # 2. API 실행
    fn_au10001(data=params)