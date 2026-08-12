import requests
import json
import sys

from dotenv import load_dotenv, set_key, find_dotenv
import os

dotenv_path = find_dotenv(usecwd=True) or ".env"
load_dotenv(dotenv_path=dotenv_path)
# load_dotenv()  # .env 파일을 현재 환경변수로 로드

KIWOOM_APP_KEY = os.environ.get('KIWOOM_APP_KEY')
KIWOOM_SECRET_KEY = os.environ.get('KIWOOM_SECRET_KEY')
KIWOOM_MOCK_APP_KEY = os.environ.get('KIWOOM_MOCK_APP_KEY')
KIWOOM_MOCK_SECRET_KEY = os.environ.get('KIWOOM_MOCK_SECRET_KEY')

# 접근토큰 발급
# host / token_env_key를 지정하면 모의투자용 토큰도 동일 함수로 발급 가능 (기존 실전 호출부는 인자 생략 시 그대로 동작)
def fn_au10001(data, host='https://api.kiwoom.com', token_env_key='KIWOOM_ACCESS_TOKEN'):
    # 1. 요청할 API URL
    # host = 'https://mockapi.kiwoom.com' # 모의투자
    # host = 'https://api.kiwoom.com' # 실전투자
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
    print('Body:', body)  # 실패 시에도 실제 응답 내용을 먼저 볼 수 있도록 파싱 전에 출력

    if 'token' not in data:
        raise RuntimeError(f'토큰 발급 실패 (host={host}): {body}')
    token = data['token']
    print('Token:', token)

    # 5) 현재 프로세스 환경에도 반영 (즉시 사용 목적)
    os.environ[token_env_key] = token
    # 6) .env 파일에도 저장(없으면 추가, 있으면 값 업데이트)
    set_key(dotenv_path, token_env_key, token)

# 실행 구간
# 인자 없이 실행하면 실전(기존 동작 그대로) 갱신. --mock을 주면 모의투자 토큰을 갱신한다.
# 서버 프로세스의 KIWOOM_ENV와 무관하게 동작하도록 host/token_env_key/앱키를 명시적으로 고정한다 —
# 실전 잡과 모의 잡을 서로 다른 시각에 각각 스케줄해도(job/batch_process.py) 항상 의도한 대상만 갱신된다.
if __name__ == '__main__':
    is_mock = '--mock' in sys.argv

    if is_mock:
        params = {
            'grant_type': 'client_credentials',
            'appkey': KIWOOM_MOCK_APP_KEY,
            'secretkey': KIWOOM_MOCK_SECRET_KEY,
        }
        fn_au10001(data=params, host='https://mockapi.kiwoom.com', token_env_key='KIWOOM_MOCK_ACCESS_TOKEN')
    else:
        # 1. 요청 데이터
        params = {
            'grant_type': 'client_credentials',  # grant_type
            'appkey': KIWOOM_APP_KEY,  # 앱키
            'secretkey': KIWOOM_SECRET_KEY,  # 시크릿키
        }

        # 2. API 실행
        fn_au10001(data=params)