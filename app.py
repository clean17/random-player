import os
import configparser
import os
import random
import signal
import subprocess
import time
from datetime import datetime, timedelta

from flask import Flask, render_template, send_file, redirect, url_for, request, flash, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from task_manager import TaskManager

app = Flask(__name__)

##################### Read configuration from config.ini ######################
config = configparser.ConfigParser()
with open('config.ini', 'r', encoding='utf-8') as configfile:
    config.read_file(configfile)
VIDEO_DIRECTORY1 = config['directories']['video_directory']
VIDEO_DIRECTORY2 = config['directories']['video_directory2']
VIDEO_DIRECTORY3 = config['directories']['video_directory3']
SECRET_KEY = config['settings']['secret_key']
USERNAME = config['settings']['username']
PASSWORD = generate_password_hash(config['settings']['password'])
ffmpeg_script_path = config['paths']['ffmpeg_script_path']
work_directory = config['paths']['work_directory']

app.secret_key = SECRET_KEY
################################################################################

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

users = {
    USERNAME: {'password': PASSWORD},
}

class User(UserMixin):
    def __init__(self, username):
        self.id = username

################################################################################
@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id)
    return None

task_manager = TaskManager(work_directory)

def check_server_restarted():
    restart_flag = 'server_status.txt'
    if not os.path.exists(restart_flag):
        # 파일이 없으면 서버가 재시작된 것으로 간주하고 파일을 생성
        with open(restart_flag, 'w') as f:
            f.write('restarted')
        return True
    return False
@app.before_request
def handle_server_restart():
    if check_server_restarted():
        session.clear()

@app.before_request
def check_lockout():
    if 'lockout_time' in session and session['lockout_time']:
        if datetime.now() >= session['lockout_time']:
            session.pop('lockout_time', None)
            session['attempts'] = 0

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
    session['visits'] = session.get('visits', 0) + 1
    return render_template('directory_select.html')

@app.route('/ffmpeg')
@login_required
def ffmpeg():
    return render_template('ffmpeg.html')

@app.route('/select_directory', methods=['POST'])
@login_required
def select_directory():
    directory = request.form.get('directory')
    return redirect(url_for('video_player', directory=directory))

@app.route('/video_player/<directory>')
@login_required
def video_player(directory):
    return render_template('video.html', directory=directory)

@app.route('/videos', methods=['GET'])
@login_required
def get_videos():
    directory = request.args.get('directory')
    if directory == '1':
        video_directory = VIDEO_DIRECTORY1
    elif directory == '2':
        video_directory = VIDEO_DIRECTORY2
    else:
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
    else:
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
    else:
        video_directory = VIDEO_DIRECTORY3

    file_path = os.path.join(video_directory, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return '', 204
    return '', 404

@app.route('/run_batch', methods=['POST'])
@login_required
def run_batch():
    keyword = request.form.get('keyword')
    clipboard_content = request.form.get('clipboard_content').replace('\r\n', '\n')
    print(clipboard_content)
    if keyword and clipboard_content:
        command = f'{ffmpeg_script_path} {keyword} "{clipboard_content}"'
        try:
            print("Executing command:", command)
            pid = task_manager.start_task(command, keyword)
            flash(f'Command executed with PID: {pid}', 'success')
        except subprocess.CalledProcessError as e:
            flash(f'Error executing command: {e}', 'danger')
        except UnicodeDecodeError as e:
            flash(f'Encoding error: {e}', 'danger')
        except IndexError as e:
            flash(f'Index error: {e}', 'danger')
    else:
        flash('Keyword and clipboard content are required', 'warning')
    return redirect(url_for('home'))

@app.route('/check_status')
@login_required
def check_status():
    tasks = task_manager.get_running_tasks()
    print(tasks)
    return render_template('check_status.html', tasks=tasks)

@app.route('/task_status')
@login_required
def task_status():
    tasks = task_manager.get_running_tasks()
    task_status = [{'pid': task['process'].pid, 'running': task['process'].poll() is None, 'keyword': task['info']['keyword'], 'thumbnail': task['info'].get('thumbnail')} for task in tasks]
    return jsonify(task_status)

@app.route('/kill_task/<int:pid>', methods=['POST'])
@login_required
def kill_task(pid):
    try:
        os.kill(pid, signal.SIGTERM)
        return redirect(url_for('check_status'))
    except Exception as e:
        return str(e)


if __name__ == '__main__':
#     app.run(debug=True, host='0.0.0.0', port=8090)
    app.run(debug=True, host='0.0.0.0', port=443, ssl_context=('cert.pem', 'key.pem'))