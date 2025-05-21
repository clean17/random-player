from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from utils.wsgi_midleware import logger
from utils.jwt import create_access_token
from .rds import redis_client

from config.config import settings
from .repository.users.users import find_user_by_login_id

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
        datetime.utcnow().isoformat()
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
    if 'attempts' not in session:
        session['attempts'] = 0
        session['lockout_time'] = None

    # 현재 시간을 UTC로 설정
    now = datetime.now(timezone.utc)

    # 로그인 시도 제한을 초과했을 경우
    if 'lockout_time' in session and session['lockout_time']:
        # 문자열을 datetime으로 변환
        lockout_time = datetime.fromisoformat(session['lockout_time'])
        if now < lockout_time:
            flash('Too many login attempts. Try again later.')
            # return render_template('login.html')
            return redirect(url_for('auth.lockout'))  # 로그인 제한 페이지로 리다이렉트

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        # data = request.get_json()
        # username = data.get('username')
        # password = data.get('password')

        if session['attempts'] >= 5:
            lockout_time = datetime.fromisoformat(session['lockout_time'])
            if now < lockout_time:
                flash('Too many login attempts. Try again later.')
                # return render_template('login.html')
                return redirect(url_for('auth.lockout'))
            else:
                session['attempts'] = 0
                session['lockout_time'] = None

        # print('attempt_username', username)
        logger.info(f"############################### login_username: {username} ###############################")

        # 로그인 검증
        fetch_user = find_user_by_login_id(username) # db 조회
        if fetch_user and check_password_hash(fetch_user.password, password):
        # if username in users and check_password_hash(users[username]['password'], password):
        #     print(username, generate_password_hash(password))

            user = User(username)
            login_user(user)
            session['attempts'] = 0

            # GUEST_USERNAME 사용자라면
            if username == settings['GUEST_USERNAME']:
                session.permanent = False  # False; 브라우저 세션, 브라우저를 닫으면 세션 쿠키는 사라진다
                session["last_active"] = datetime.utcnow().timestamp() # session["last_active"]

                if not current_user.is_authenticated:
                    return redirect(url_for('auth.logout'))
            else:
                session.permanent = True # True; PERMANENT_SESSION_LIFETIME 적용되도록 >> Flask의 기본 세션 만료 정책 (브라우저별 쿠키 기반, session_id), 브라우저를 꺼도 쿠키는 살아 있다
                key = f"user_session:{username}"
                redis_client.setex(key, SESSION_EXPIRATION_TIME, "active")

            return redirect(url_for('main.home'))
        # 로그인 실패
        else:
            session['attempts'] += 1
            flash('Invalid username or password')
            if session['attempts'] >= 5:
                # session['lockout_time'] = datetime.now() + timedelta(days=1)
                session['lockout_time'] = (now + timedelta(days=1)).isoformat()  # UTC 시간 저장

    return render_template('login.html')

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
            # session['second_password_verified_at'] = datetime.utcnow().isoformat()
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
            "verified_time": get_verified_time(current_user.get_id())
        });
    else:
        return jsonify({
            "success": "false",
            "verified_time": "null"
        });

@auth.route("/update-session-time")
@login_required
def update_session_time():
    # session['second_password_verified_at'] = datetime.utcnow().isoformat()
    save_verified_time(current_user.get_id()) # redis 동기화
    return "update-session-time"

'''
Flask의 세션은 기본적으로 비영속적(non-permanent)
>> 브라우저를 닫으면 세션이 사라진다

session.permanent = False (기본값)	브라우저 꺼지면 세션 소멸 (세션 쿠키)
session.permanent = True 를 통해 세션을 영구적으로 설정, app.permanent_session_lifetime 만큼 유지됨

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=10)  # 10분 비활동 시 만료
app.config['SESSION_REFRESH_EACH_REQUEST'] = True  # 매 요청마다 세션 갱신 (원하지 않으면 False)
'''
