import requests
import json

from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()  # .env 파일을 현재 환경변수로 로드

today = datetime.today().strftime('%Y%m%d')

# 일별잔고수익률
def fn_ka01690(token, data, cont_yn='N', next_key=''):
    # 1. 요청할 API URL
    #host = 'https://mockapi.kiwoom.com' # 모의투자
    host = 'https://api.kiwoom.com' # 실전투자
    endpoint = '/api/dostk/acnt'
    url =  host + endpoint

    # 2. header 데이터
    headers = {
        'Content-Type': 'application/json;charset=UTF-8', # 컨텐츠타입
        'authorization': f'Bearer {token}', # 접근토큰
        'cont-yn': cont_yn, # 연속조회여부
        'next-key': next_key, # 연속조회키
        'api-id': 'ka01690', # TR명
    }

    # 3. http POST 요청
    response = requests.post(url, headers=headers, json=data)

    # 4. 응답 상태 코드와 데이터 출력
    print('Code:', response.status_code)
    print('Header:', json.dumps({key: response.headers.get(key) for key in ['next-key', 'cont-yn', 'api-id']}, indent=4, ensure_ascii=False))
    print('Body:', json.dumps(response.json(), indent=4, ensure_ascii=False))  # JSON 응답을 파싱하여 출력

# 실행 구간
if __name__ == '__main__':
    # 1. 토큰 설정
    MY_ACCESS_TOKEN = os.environ.get('MY_ACCESS_TOKEN') # 접근토큰

    # 2. 요청 데이터
    params = {
        'qry_dt': today, # 조회일자
    }

    # 3. API 실행
    fn_ka01690(token=MY_ACCESS_TOKEN, data=params)

# next-key, cont-yn 값이 있을 경우
# fn_ka01690(token=MY_ACCESS_TOKEN, data=params, cont_yn='Y', next_key='nextkey..')