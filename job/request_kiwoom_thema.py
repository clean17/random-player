import requests
import json

from dotenv import load_dotenv, set_key, find_dotenv
import os

dotenv_path = find_dotenv(usecwd=True) or ".env"
load_dotenv(dotenv_path=dotenv_path)
# load_dotenv()  # .env 파일을 현재 환경변수로 로드

MY_ACCESS_TOKEN = os.environ.get('MY_ACCESS_TOKEN')


# 테마그룹별요청
def fn_ka90001(token, data, cont_yn='N', next_key=''):
    # 1. 요청할 API URL
    #host = 'https://mockapi.kiwoom.com' # 모의투자
    host = 'https://api.kiwoom.com' # 실전투자
    endpoint = '/api/dostk/thme'
    url =  host + endpoint

    # 2. header 데이터
    headers = {
        'Content-Type': 'application/json;charset=UTF-8', # 컨텐츠타입
        'authorization': f'Bearer {token}', # 접근토큰
        'cont-yn': cont_yn, # 연속조회여부
        'next-key': next_key, # 연속조회키
        'api-id': 'ka90001', # TR명
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
    # MY_ACCESS_TOKEN = '사용자 AccessToken' # 접근토큰
    MY_ACCESS_TOKEN = os.environ.get('MY_ACCESS_TOKEN')

    # 2. 요청 데이터
    params = {
        'qry_tp': '2', # 검색구분 0:전체검색, 1:테마검색, 2:종목검색
        'stk_cd': '005930', # 종목코드 검색하려는 종목코드
        'date_tp': '10', # 날짜구분 n일전 (1일 ~ 99일 날짜입력)
        'thema_nm': '', # 테마명 검색하려는 테마명
        'flu_pl_amt_tp': '1', # 등락수익구분 1:상위기간수익률, 2:하위기간수익률, 3:상위등락률, 4:하위등락률
        'stex_tp': '1', # 거래소구분 1:KRX, 2:NXT 3.통합
    }

    # 3. API 실행
    fn_ka90001(token=MY_ACCESS_TOKEN, data=params)

# next-key, cont-yn 값이 있을 경우
# fn_ka90001(token=MY_ACCESS_TOKEN, data=params, cont_yn='Y', next_key='nextkey..')