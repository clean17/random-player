import requests
from flask import Blueprint, Flask, render_template, request, jsonify, redirect
from config.config import settings

oauth = Blueprint('oauth', __name__)

THREADS_APP_ID = settings['THREADS_APP_ID']
THREADS_APP_SECRET = settings['THREADS_APP_SECRET']
FACEBOOK_APP_ID = settings['FACEBOOK_APP_ID']

@oauth.route('/policy', methods=['GET'])
def get_personal_information_processing_policy():
    return render_template('policy.html')
a
@oauth.route('/eliminate', methods=['GET'])
def eliminate():
    print('삭제 콜백')

@oauth.route('/remove', methods=['GET'])
def remove():
    print('제거 콜백')

@oauth.route('/callback', methods=['GET'])
def callback():
    print('콜백')
    code = request.args.get("code")
    if not code:
        return "No code received", 400
    print('code', code)

    # 코드 → 액세스 토큰 요청
    token_url = "https://graph.threads.net/oauth/access_token"
    params = {
        "client_id": THREADS_APP_ID,
        "client_secret": THREADS_APP_SECRET,
        "redirect_uri": "https://chickchick.shop/oauth/callback",
        "grant_type": "authorization_code",
        "code": code,
    }

    # response = requests.post(token_url, params=params)
    response = requests.post(token_url, data=params, timeout=15)
    token_data = response.json()
    if "access_token" not in token_data:
        return token_data, 400
    print('token_data', token_data)
    access_token = token_data.get("access_token")
    user_id = token_data.get("user_id")

    exchange_url = "https://graph.threads.net/access_token"
    exchange_params = {
        "grant_type": "th_exchange_token",
        "client_secret": THREADS_APP_SECRET,
        "access_token": access_token,
    }
    response = requests.get(exchange_url, params=exchange_params, timeout=15)
    long_term_token_data = response.json()
    # long_term_access_token = long_term_token_data.get("access_token")

    return long_term_token_data

@oauth.route("/deauthorize", methods=["POST"])
def deauthorize_callback():
    payload = request.form.get("signed_request")
    # user_id = decode_signed_request(payload)  # 앱 시크릿으로 검증

    # 해당 user_id 데이터 삭제
    # delete_user_data(user_id)

    return "", 200

# 페이스북 javascripts SDK 로그인 예제
@oauth.route('/', methods=['GET'])
def get_meta_oauth_page():
    return render_template('meta_oauth.html',  appId=FACEBOOK_APP_ID)









import hmac
import hashlib
import base64
import json


APP_SECRET = 'a81ad4c69277b75c4e3b4b361b28d4f5'  # Meta 앱 시크릿으로 교체하세요

def base64_url_decode(data):
    data += '=' * (-len(data) % 4)  # 패딩 추가
    return base64.urlsafe_b64decode(data.encode('utf-8'))

def parse_signed_request(signed_request, secret):
    try:
        encoded_sig, payload = signed_request.split('.', 1)

        sig = base64_url_decode(encoded_sig)
        data = json.loads(base64_url_decode(payload))

        expected_sig = hmac.new(
            secret.encode('utf-8'),
            msg=payload.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()

        if not hmac.compare_digest(sig, expected_sig):
            print('Signature mismatch')
            return None

        return data
    except Exception as e:
        print('Error parsing signed request:', e)
        return None

@oauth.route('/delete-callback', methods=['POST', 'GET'])
def delete_callback():
    signed_request = request.form.get('signed_request') or request.args.get('signed_request')
    if not signed_request:
        return jsonify({'error': 'Missing signed_request'}), 400

    data = parse_signed_request(signed_request, APP_SECRET)
    if not data:
        return jsonify({'error': 'Invalid signed_request'}), 400

    user_id = data.get('user_id')
    print(f"User {user_id} requested data deletion.")

    # 삭제 처리 로직 (DB에서 유저 데이터 제거 등)
    confirmation_code = 'abc123'  # 실제 구현 시 고유한 UUID 등으로 생성
    status_url = f'https://chickchick.shop/delete-status/{confirmation_code}'

    return jsonify({
        'url': status_url,
        'confirmation_code': confirmation_code
    })






@oauth.route('/<provider>')
def oauth_login(provider):
    return jsonify({"provider": provider})