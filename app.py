import os
import random
import configparser
import time
import subprocess
from flask import Flask, jsonify, render_template, send_file, redirect, url_for, request, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta

app = Flask(__name__)

# Read configuration from config.ini
config = configparser.ConfigParser()
with open('config.ini', 'r', encoding='utf-8') as configfile:
    config.read_file(configfile)
VIDEO_DIRECTORY1 = config['directories']['video_directory']
VIDEO_DIRECTORY2 = config['directories']['video_directory2']
VIDEO_DIRECTORY3 = config['directories']['video_directory3']
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

@app.route('/ffmpeg')
@login_required
def ffmpeg():
    return render_template('ffmpeg.html')

@app.route('/run_batch', methods=['POST'])
def run_batch():
    keyword = request.form.get('keyword')
    clipboard_content = request.form.get('clipboard_content')
    print(keyword)
    print(clipboard_content)
    if keyword and clipboard_content:
        command = f'f:\\m\\ff.bat {keyword} "{clipboard_content}"'
        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8')
            flash(f'Command executed: {result.stdout}', 'success')
        except subprocess.CalledProcessError as e:
            flash(f'Error executing command: {e}', 'danger')
        except UnicodeDecodeError as e:
            flash(f'Encoding error: {e}', 'danger')
        except IndexError as e:
            flash(f'Index error: {e}', 'danger')
    else:
        flash('Keyword and clipboard content are required', 'warning')
    return redirect(url_for('home'))

@app.route('/')
@login_required
def home():
    return render_template('directory_select.html')

@app.route('/select_directory', methods=['POST'])
@login_required
def select_directory():
    directory = request.form.get('directory')
    return redirect(url_for('video_player', directory=directory))

@app.route('/video_player/<directory>')
@login_required
def video_player(directory):
    return render_template('index.html', directory=directory)

@app.before_request
def check_lockout():
    if 'lockout_time' in session and session['lockout_time']:
        if datetime.now() >= session['lockout_time']:
            session.pop('lockout_time', None)
            session['attempts'] = 0

@app.route('/videos', methods=['GET'])
@login_required
def get_videos():
    directory = request.args.get('directory')
    if directory == '1':
        video_directory = VIDEO_DIRECTORY1
    elif directory == '2':
        video_directory = VIDEO_DIRECTORY2
    else :
        video_directory = VIDEO_DIRECTORY3
    videos = []
    for root, dirs, files in os.walk(video_directory):
        for file in files:
            if file.endswith(('.mp4', '.avi', '.mkv')):
                rel_dir = os.path.relpath(root, video_directory)
                rel_file = os.path.join(rel_dir, file)
                videos.append(rel_file)

    random.seed(time.time())
    random.shuffle(videos)
    return jsonify(videos)

@app.route('/video/<path:filename>', methods=['GET'])
@login_required
def get_video(filename):
    directory = request.args.get('directory')
    if directory == '1':
        video_directory = VIDEO_DIRECTORY1
    elif directory == '2':
        video_directory = VIDEO_DIRECTORY2
    else :
        video_directory = VIDEO_DIRECTORY3

    return send_file(os.path.join(video_directory, filename))

@app.route('/delete/<path:filename>', methods=['DELETE'])
@login_required
def delete_video(filename):
    directory = request.args.get('directory')
    if directory == '1':
        video_directory = VIDEO_DIRECTORY1
    elif directory == '2':
        video_directory = VIDEO_DIRECTORY2
    else :
        video_directory = VIDEO_DIRECTORY3

    file_path = os.path.join(video_directory, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return '', 204
    return '', 404

if __name__ == '__main__':
#     app.run(debug=True, host='0.0.0.0', port=8090)
    app.run(debug=False, host='0.0.0.0', port=443, ssl_context=('cert.pem', 'key.pem'))