import os
from datetime import datetime, timedelta
import signal
import sys
from flask import Flask, session, request, jsonify, send_file, abort
from flask_login import LoginManager
import logging
from auth import auth, User, users
from config import load_config, settings
from ffmpeg_handle import m_ffmpeg
from main import main
from video import video
from waitress import serve

app = Flask(__name__)
app.config.update(load_config())
app.register_blueprint(main, url_prefix='/')
app.register_blueprint(auth, url_prefix='/auth')
app.register_blueprint(video, url_prefix='/video')
app.register_blueprint(m_ffmpeg, url_prefix='/ffmpeg')
app.secret_key = app.config['SECRET_KEY']

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@app.before_request
def handle_server_restart():
    if 'lockout_time' in session and session['lockout_time']:
        if datetime.now() >= session['lockout_time']:
            session.pop('lockout_time', None)
            session['attempts'] = 0
    if check_server_restarted():
        session.clear()
   # load_tasks_from_json_file()

@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(user_id)
    return None

# 서버 종료 시 파일에 작업 저장
# @app.teardown_appcontext
# def teardown_appcontext_func(exception=None):
#     save_tasks_to_json_file()

def check_server_restarted():
    restart_flag = 'server_status.txt'
    if not os.path.exists(restart_flag):
        with open(restart_flag, 'w') as f:
            f.write('restarted')
        return True
    return False

def signal_handler(sig, frame):
    print("Exiting server...")
    os.system('taskkill /f /im python.exe')
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    # app.run(debug=True, host='0.0.0.0', port=8090)
    # app.run(debug=True, host='0.0.0.0', port=443, ssl_context=('cert.pem', 'key.pem'))

    # Create a logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Create a file handler for logging
    file_handler = logging.FileHandler('app.log', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    # Create a console handler for logging
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)

    # Create a logging format
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add the handlers to the logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    serve(app, host='0.0.0.0', port=8090) ## ssl > nginx 에 적용
