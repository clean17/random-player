from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash

from config import settings

auth = Blueprint('auth', __name__)

users = {
    settings['USERNAME']: {'password': settings['PASSWORD']},
    settings['GUEST_USERNAME']: {'password': settings['GUEST_PASSWORD']}
}

ALLOWED_USER_ID = settings['GUEST_USERNAME']  # GUEST_USERNAME 지정

class User(UserMixin):
    def __init__(self, username):
        self.id = username

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if 'attempts' not in session:
        session['attempts'] = 0
        session['lockout_time'] = None

    if session.get('lockout_time') and datetime.now() < session['lockout_time']:
        flash('Too many login attempts. Try again later.')
        return render_template('login.html')

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if session['attempts'] >= 5:
            if datetime.now() < session['lockout_time']:
                flash('Too many login attempts. Try again later.')
                return render_template('login.html')
            else:
                session['attempts'] = 0
                session['lockout_time'] = None

        if username in users and check_password_hash(users[username]['password'], password):
            user = User(username)
            login_user(user)
            session['attempts'] = 0

            # GUEST_USERNAME 사용자라면 특정 페이지로 이동
            if username == settings['GUEST_USERNAME']:
                return redirect(url_for('image.trip_image_list'))

            return redirect(url_for('main.home'))
        else:
            session['attempts'] += 1
            flash('Invalid username or password')
            if session['attempts'] >= 5:
                session['lockout_time'] = datetime.now() + timedelta(days=1)

    return render_template('login.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))