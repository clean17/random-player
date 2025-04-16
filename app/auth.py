from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash

from config.config import settings

auth = Blueprint('auth', __name__)

users = {
    settings['USERNAME']: {'password': settings['PASSWORD']},
    settings['GUEST_USERNAME']: {'password': settings['GUEST_PASSWORD']}
}

class User(UserMixin):
    def __init__(self, username):
        self.id = username

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

        if session['attempts'] >= 5:
            lockout_time = datetime.fromisoformat(session['lockout_time'])
            if now < lockout_time:
                flash('Too many login attempts. Try again later.')
                # return render_template('login.html')
                return redirect(url_for('auth.lockout'))
            else:
                session['attempts'] = 0
                session['lockout_time'] = None

        print('attempt_username', username)

        # 로그인 검증
        if username in users and check_password_hash(users[username]['password'], password):
            user = User(username)
            login_user(user)
            session['attempts'] = 0

            # GUEST_USERNAME 사용자라면
            # if username == settings['GUEST_USERNAME']:
            #     return redirect(url_for('image.image_list'))
            #     session.permanent = True  # PERMANENT_SESSION_LIFETIME 적용되도록
            #     if not current_user.is_authenticated:
            #         logout_user()
            #         return redirect(url_for('auth.login'))

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
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

'''
Flask의 세션은 기본적으로 비영속적(non-permanent)
>> 브라우저를 닫으면 세션이 사라진다

session.permanent = True 를 통해 세션을 영구적으로 설정

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=10)  # 10분 비활동 시 만료
app.config['SESSION_REFRESH_EACH_REQUEST'] = True  # 매 요청마다 세션 갱신 (원하지 않으면 False)
'''