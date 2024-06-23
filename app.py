import os
import random
import configparser
import time
from flask import Flask, jsonify, render_template, send_file, redirect, url_for, request, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta

app = Flask(__name__)

# Read configuration from config.ini
config = configparser.ConfigParser()
with open('config.ini', 'r', encoding='utf-8') as configfile:
    config.read_file(configfile)
VIDEO_DIRECTORY = config['settings']['video_directory']
SECRET_KEY = config['settings']['secret_key']
USERNAME = config['settings']['username']
PASSWORD = generate_password_hash(config['settings']['password'])

app.secret_key = SECRET_KEY

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

users = {
    USERNAME: {'password': PASSWORD},
}

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

@app.route('/login', methods=['GET', 'POST'])
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
        if username in users and check_password_hash(users[username]['password'], password):
            user = User(username)
            login_user(user)
            session['attempts'] = 0
            return redirect(url_for('home'))
        else:
            session['attempts'] += 1
            flash('Invalid username or password')
            if session['attempts'] >= 5:
                session['lockout_time'] = datetime.now() + timedelta(days=1)
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    return render_template('index.html')

# @app.route('/reset_attempts')
# def reset_attempts():
#     session['attempts'] = 0
#     session.pop('lockout_time', None)
#     flash('Login attempts have been reset.')
#     return redirect(url_for('login'))

@app.before_request
def check_lockout():
    if session.get('lockout_time') and datetime.now() >= session['lockout_time']:
        session.pop('lockout_time', None)
        session['attempts'] = 0

@app.route('/videos', methods=['GET'])
def get_videos():
    videos = []
    for root, dirs, files in os.walk(VIDEO_DIRECTORY):
        for file in files:
            if file.endswith(('.mp4', '.avi', '.mkv')):
                # Store relative paths from VIDEO_DIRECTORY
                rel_dir = os.path.relpath(root, VIDEO_DIRECTORY)
                rel_file = os.path.join(rel_dir, file)
                videos.append(rel_file)
    random.seed(time.time())
    random.shuffle(videos)
    return jsonify(videos)

@app.route('/video/<path:filename>', methods=['GET'])
def get_video(filename):
    return send_file(os.path.join(VIDEO_DIRECTORY, filename))

@app.route('/delete/<path:filename>', methods=['DELETE'])
def delete_video(filename):
    file_path = os.path.join(VIDEO_DIRECTORY, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return '', 204
    return '', 404

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8090)

