from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, make_response
from flask_login import UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from utils.wsgi_midleware import logger
from utils.jwt import create_access_token
from .rds import redis_client
import time
import pytz

from config.config import settings
from .repository.users.users import find_user_by_username, update_user_login_attempt, update_user_lockout_time

auth = Blueprint('auth', __name__)

SECOND_PASSWORD_SESSION_KEY = settings['SECOND_PASSWORD_SESSION_KEY']
SESSION_EXPIRATION_TIME = timedelta(minutes=30) # 세션 만료 시간
GUEST_SESSION_EXPIRATION_TIME = timedelta(minutes=30) # 세션 만료 시간
YOUR_SECRET_PASSWORD = settings['YOUR_SECRET_PASSWORD']


users = {
    settings['USERNAME']: {'password': settings['PASSWORD']},
    settings['GUEST_USERNAME']: {'password': settings['GUEST_PASSWORD']},
    settings['SUPER_USERNAME']: {'password': settings['SUPER_PASSWORD']},
}

class User(UserMixin):
    def __init__(self, username):
        self.id = username


def check_active_session():
    if current_user.is_authenticated and current_user.get_id() == settings['USERNAME']:
        key = f"user_session:{current_user.get_id()}"
        ttl = redis_client.ttl(key)

        if ttl <= 0:  # -2: 키없음, -1: TTL 없음
            return redirect(url_for('auth.logout'))
        else:
            redis_client.expire(key, SESSION_EXPIRATION_TIME)  # TTL 연장

# setex(name, time, value); name: 키, time: TTL, value: 값
def save_verified_time(username):
    redis_client.setex(
        f"second_password_verified:{username}",
        timedelta(minutes=10),
        datetime.now().isoformat()
    )

def get_verified_time(username):
    return redis_client.get(f"second_password_verified:{username}")



@auth.route('/api/token', methods=['POST'])
def issue_token():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if username in users and check_password_hash(users[username]['password'], password):
        token = create_access_token({"sub": username})
        return jsonify(access_token=token)

    return jsonify(error="Invalid credentials"), 401

@auth.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember = request.form.get('remember_username', False)

        # 현재 시간을 UTC로 설정
        kst = pytz.timezone('Asia/Seoul')
        now = datetime.now(kst)

        # data = request.get_json()
        # username = data.get('username')
        # password = data.get('password')

        # 로그인 검증
        fetch_user = find_user_by_username(username) # db 조회

        if fetch_user and check_password_hash(fetch_user.password, password):
        # if username in users and check_password_hash(users[username]['password'], password): # db 사용하지 않았을 때
        #     print(username, generate_password_hash(password))

            if fetch_user.lockout_time:
                lockout_time = fetch_user.lockout_time
                if isinstance(lockout_time, str):
                    dt = datetime.fromisoformat(lockout_time)
                elif isinstance(lockout_time, datetime):
                    dt = lockout_time
                elif lockout_time is None:
                    dt = None
                else:
                    raise ValueError(f"Unexpected type: {type(lockout_time)}")

                lockout_time = dt.replace(tzinfo=kst)
                if now < lockout_time:
                    # flash('Too many login attempts. Try again later')
                    print('Too many login attempts. Try again later')
                    return redirect(url_for('auth.lockout'))  # 로그인 제한 페이지로 리다이렉트


            user = User(username)
            login_user(user)
            update_user_login_attempt(username, 0)
            session['attempts'] = 0
            session['lockout_time'] = None

            # GUEST_USERNAME 사용자라면
            if username == settings['GUEST_USERNAME']:
                session.permanent = False  # False; 브라우저 세션, 브라우저를 닫으면 세션 쿠키는 사라진다
                session["last_active"] = datetime.now().timestamp() # session["last_active"]

                if not current_user.is_authenticated:
                    return redirect(url_for('auth.logout'))
            else:
                session.permanent = True # True; PERMANENT_SESSION_LIFETIME 적용되도록 >> Flask의 기본 세션 만료 정책 (브라우저별 쿠키 기반, session_id), 브라우저를 꺼도 쿠키는 살아 있다
                key = f"user_session:{username}"
                redis_client.setex(key, SESSION_EXPIRATION_TIME, "active")

            logger.info(f"############################### login_username: {username} ###############################")

            session['principal'] = fetch_user
            resp = None
            if username == settings['GUEST_USERNAME']:
                resp = make_response(redirect('/func/chat'))
            else:
                resp = make_response(redirect('/'))
            if remember:
                resp.set_cookie('remember_username', username, max_age=60*60*24*30) # 30일
            else:
                resp.set_cookie('remember_username', '', expires=0)
            return resp

        # 로그인 실패
        else:
            logger.info(f"############################### login_fail: {username} ###############################")

            if fetch_user:
                update_user_login_attempt(username, (fetch_user.login_attempt or 0) + 1)

                if int(fetch_user.login_attempt or 0) >= 5:
                    update_user_lockout_time(username, (now + timedelta(days=1)).isoformat())
                    return redirect(url_for('auth.lockout'))  # 로그인 제한 페이지로 리다이렉트

            # 로그인 아이디가 정보가 없음
            else:
                if 'attempts' not in session:
                    session['attempts'] = 0
                    session['lockout_time'] = None

                session['attempts'] += 1

                # 로그인 실패가 5번이 되면 세션에 락아웃 타임 저장
                if session['attempts'] >= 5 and not session['lockout_time']:
                    session['lockout_time'] = (now + timedelta(days=1)).isoformat() # UTC 시간 저장

                # 세션에 락아웃이 걸렸을 경우
                if 'lockout_time' in session and session['lockout_time']: # 키 있는지 + 키의 값이 falsy가 아닌지
                    # 문자열을 datetime으로 변환
                    lockout_time = datetime.fromisoformat(session['lockout_time'])
                    if now < lockout_time:
                        return redirect(url_for('auth.lockout'))  # 로그인 제한 페이지로 리다이렉트
                    else:
                        # 차단 시간이 지났을 경우 초기화
                        session['attempts'] = 1
                        session['lockout_time'] = None

            flash('Invalid username or password')


    return render_template('login.html', version=int(time.time()))

@auth.route('/lockout')
def lockout():
    return render_template('lockout.html')

@auth.route('/logout')
def logout():
    if current_user.is_authenticated:
        logger.info(f"############################### logout_username: {current_user.get_id()} ###############################")
    session[SECOND_PASSWORD_SESSION_KEY] = False
    session.clear()
    logout_user()
    # return redirect(url_for('auth.login'))
    return login()

@auth.route("/verify-password", methods=["GET", "POST"])
@login_required
def verify_password():
    if request.method == "POST":
        password = request.form.get("password")

        if password == YOUR_SECRET_PASSWORD:
            session[SECOND_PASSWORD_SESSION_KEY] = True # session.get(SECOND_PASSWORD_SESSION_KEY)
            # session['second_password_verified_at'] = datetime.now().isoformat()
            save_verified_time(current_user.get_id()) # redis 동기화

            next_page = request.args.get("next", "/func/memo")
            return redirect(next_page)
        else:
            return redirect(url_for("auth.logout"))

    return render_template("verify_password.html")

@auth.route("/check-verified", methods=["GET"])
@login_required
def check_verified():
    verified_time = get_verified_time(current_user.get_id())
    if verified_time:
        return jsonify({
            "success": "true",
            "verified_time": verified_time
        });
    else:
        return jsonify({
            "success": "false",
            "verified_time": "null"
        });

@auth.route("/update-session-time")
@login_required
def update_session_time():
    # session['second_password_verified_at'] = datetime.now().isoformat()
    save_verified_time(current_user.get_id()) # redis 동기화
    return jsonify({"update_session_time": "true"})

'''
Flask의 세션은 기본적으로 비영속적(non-permanent)
>> 브라우저를 닫으면 세션이 사라진다

session.permanent = False (기본값)	브라우저 꺼지면 세션 소멸 (세션 쿠키)
session.permanent = True 를 통해 세션을 영구적으로 설정, app.permanent_session_lifetime 만큼 유지됨

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=10)  # 10분 비활동 시 만료
app.config['SESSION_REFRESH_EACH_REQUEST'] = True  # 매 요청마다 세션 갱신 (원하지 않으면 False)
'''


@auth.route('/register')
def register():
    return jsonify({"succecss": True})

@auth.route('/forgot-password')
def forgot_password():
    return jsonify({"succecss": True})