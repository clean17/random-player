import os
from datetime import datetime, timezone
from flask import Flask, session, send_file, render_template_string, jsonify, request, redirect, url_for, send_from_directory
from flask_login import LoginManager, current_user
from .auth import auth, User, users
from config import load_config
from .ffmpeg_handle import m_ffmpeg # ffmpeg_handle.py에서 m_ffmpeg 블루프린트를 import
from .main import main
from .video import video
from .image import image_bp, environment
from .function import func, socketio
from .upload import upload
import fnmatch

ALLOWED_PATHS = [
    '/favicon.ico',       # nginx 서버리스
    '/service-worker.js', # nginx 서버리스
    '/image/images*',
    '/image/pages',
    '/image/move_image*',
    '/upload*',
    '/func/download-zip*',
    '/video/temp-video*',
    '/func/chat*',
    '/func/memo*',
]

BLOCKED_IPS = {'170.39.218.12'}

def create_app():
    app = Flask(__name__, static_folder='static')
    app.config.update(load_config())
    app.secret_key = app.config['SECRET_KEY']

    app.register_blueprint(main, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/auth')
    app.register_blueprint(video, url_prefix='/video')
    app.register_blueprint(m_ffmpeg, url_prefix='/ffmpeg')
    app.register_blueprint(image_bp, url_prefix='/image')
    app.register_blueprint(func, url_prefix='/func')
    app.register_blueprint(upload, url_prefix='/upload')
    app.jinja_env.globals.update(max=max, min=min)

    # Flask 앱에 WebSocket 기능을 추가
    socketio.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    # 서버 시작 시 호출 (순서대로 핸들러 호출, 하나라도 return 또는 abort() 시 다음 필터링 실행안됨)
    @app.before_request
    def block_ip():
        # 실 IP 추출 (프록시 뒤에 있을 경우)
        ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

        if ip in BLOCKED_IPS:
            abort(403)  # 차단된 IP는 접근 불가

    @app.before_request
    def handle_server_restart():
        if 'lockout_time' in session and session['lockout_time']:
            lockout_time = session['lockout_time']

            # lockout_time 값이 문자열인지 확인
            if isinstance(lockout_time, str):
                # 문자열을 datetime 객체로 변환
                lockout_time = datetime.fromisoformat(lockout_time)
            else:
                # 예상치 못한 데이터 타입이면 세션 초기화
                session.pop('lockout_time', None) # dict.pop(key[, default]) default: null일경우 기본값
                session['attempts'] = 0
                return

            # 현재 시간을 UTC로 설정
            now = datetime.now(timezone.utc)

            if now >= lockout_time:
                session.pop('lockout_time', None)  # lockout_time 제거
                session['attempts'] = 0

        if check_server_restarted():
            session.clear()

    @app.before_request
    def restrict_endpoints():
        if request.path == '/auth/logout':
            return

        if request.path == '/':
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

            # print('request.path', request.path)
            if not any(fnmatch.fnmatch(request.path, pattern) for pattern in ALLOWED_PATHS):
                return redirect(url_for('auth.logout'))

        # 다른 사용자는 제한하지 않음
        return

    @login_manager.user_loader
    def load_user(user_id):
        if user_id in users:
            return User(user_id)
        return None

    @app.route("/service-worker.js")
    def get_service_worker():
        return send_from_directory("static/js", "service-worker.js", mimetype="application/javascript")

    @app.route("/favicon.ico")
    def get_favicon():
        return send_from_directory("static", "favicon.ico", mimetype="application/javascript")

    def check_server_restarted():
        restart_flag = 'server_status.txt'
        if not os.path.exists(restart_flag):
            with open(restart_flag, 'w') as f:
                f.write('restarted')
            return True
        return False

    return app
