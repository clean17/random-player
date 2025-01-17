import os
from datetime import datetime
from flask import Flask, session, send_file, render_template_string, jsonify, request, redirect, url_for
from flask_login import LoginManager, current_user
from .auth import auth, User, users
from config import load_config
from .ffmpeg_handle import m_ffmpeg # ffmpeg_handle.py에서 m_ffmpeg 블루프린트를 import
from .main import main
from .video import video
from .image import image_bp, environment
from .function import func
from .upload import upload
import fnmatch

ALLOWED_PATHS = [
    '/image/trip_images',
    '/image/temp_images',
    '/image/images/',
    '/main/',
    '/upload/',
    '/upload',
]

def create_app():
    app = Flask(__name__, static_folder='static')
    app.config.update(load_config())
    app.secret_key = app.config['SECRET_KEY']

    app.register_blueprint(main, url_prefix='/main')
    app.register_blueprint(auth, url_prefix='/auth')
    app.register_blueprint(video, url_prefix='/video')
    app.register_blueprint(m_ffmpeg, url_prefix='/ffmpeg')
    app.register_blueprint(image_bp, url_prefix='/image')
    app.register_blueprint(func, url_prefix='/func')
    app.register_blueprint(upload, url_prefix='/upload')
    app.jinja_env.globals.update(max=max, min=min)

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

    @app.before_request
    def restrict_endpoints():
        if request.path == '/auth/logout':
            return

        if request.path.startswith('/static'):
            return

        if not current_user.is_authenticated:
            return  # 로그인하지 않은 사용자는 검증하지 않음

        user_id = current_user.get_id()

        # GUEST_USERNAME 사용자에 대한 검증
        if user_id == app.config['GUEST_USERNAME']:
            # GUEST_USERNAME 사용자가 /image/trip_images 경로가 아닌 경우만 제한
            # if not request.path.startswith('/image/trip_images'):
            #     return redirect(url_for('auth.logout'))
                # return jsonify({"error": "Forbidden"}), 403

            print(request.path)
            if not any(fnmatch.fnmatch(request.path, pattern) for pattern in ALLOWED_PATHS):
                return redirect(url_for('auth.logout'))

        # 다른 사용자는 제한하지 않음
        return

    @login_manager.user_loader
    def load_user(user_id):
        if user_id in users:
            return User(user_id)
        return None

    @app.route('/logs')
    def view_logs():
        try:
            return send_file('logs/app.log', mimetype='text/plain')
        except Exception as e:
            return str(e)

    @app.route('/logs_html')
    def view_logs_html():
        try:
            with open('logs/app.log', 'r', encoding='utf-8') as log_file:
                log_content = log_file.read()
            log_html = '<br>'.join(log_content.split('\n'))
            return render_template_string('<pre>{{ logs }}</pre>', logs=log_html)
        except Exception as e:
            return str(e)

    def check_server_restarted():
        restart_flag = 'server_status.txt'
        if not os.path.exists(restart_flag):
            with open(restart_flag, 'w') as f:
                f.write('restarted')
            return True
        return False

    return app
