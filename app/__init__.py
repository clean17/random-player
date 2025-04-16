import os
from datetime import datetime, timezone
from flask import Flask, session, send_file, render_template_string, jsonify, request, redirect, url_for, send_from_directory, abort
from flask_login import LoginManager, current_user, logout_user
from .auth import auth, User, users
from config.config import load_config
from .ffmpeg_handle import m_ffmpeg # ffmpeg_handle.py에서 m_ffmpeg 블루프린트를 import
from .main import main
from .video import video
from .image import image_bp, environment
from .function import func, socketio
from .upload import upload
import fnmatch
from datetime import datetime, timedelta
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix
import uuid
from config.config import settings


ALLOWED_PATHS = [
    '/favicon.ico',       # nginx 서버리스
    '/service-worker.js', # nginx 서버리스
    '/image/images*',
    '/image/pages',
    '/image/move-image*',
    '/upload*',
    '/func/download-zip*',
    '/video/temp-video*',
    '/func/chat*',
    '/func/memo*',
]

# 파일 읽기
def load_blocked_ips(filepath='data/blocked_ips.txt'):
    blocked = {}
    try:
        with open(filepath, 'r') as f:
            for line in f:
                ip, until_str = line.strip().split(',')
                until = datetime.strptime(until_str, "%Y-%m-%d %H:%M:%S")
                blocked[ip] = until
    except FileNotFoundError:
        pass  # 파일 없으면 빈 딕셔너리로 시작
    return blocked

# 파일 저장
def save_blocked_ip(ip, until, filepath='data/blocked_ips.txt'):
    with open(filepath, 'a') as f:
        f.write(f"{ip},{until.strftime('%Y-%m-%d %H:%M:%S')}\n")

# block 만료 처리
def clean_expired_blocked_ips():
    now = datetime.now()
    expired = [ip for ip, until in BLOCKED_IPS.items() if until < now]
    for ip in expired:
        del BLOCKED_IPS[ip]

# 차단된 IP: {ip: block_until_time}
BLOCKED_IPS = load_blocked_ips()

# IP 기록: {ip: [404_count, last_404_time]}
IP_404_COUNTS = {}


# 설정값
BLOCK_THRESHOLD = 5
BLOCK_DURATION = timedelta(days=365)
# SESSION_EXPIRATION_TIME = timedelta(minutes=1) # 세션 만료 시간
SESSION_EXPIRATION_TIME = timedelta(seconds=5) # 세션 만료 시간

def create_app():
    print("✅ create_app() called", uuid.uuid4())
    app = Flask(__name__, static_folder='static')
    app.config.update(load_config())
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 * 1024  # 50GB
    app.config['PERMANENT_SESSION_LIFETIME'] = SESSION_EXPIRATION_TIME
    app.config['SESSION_REFRESH_EACH_REQUEST'] = True  # 매 요청마다 세션 갱신 (원하지 않으면 False)
    app.secret_key = app.config['SECRET_KEY']

    app.register_blueprint(main, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/auth')
    app.register_blueprint(video, url_prefix='/video')
    app.register_blueprint(m_ffmpeg, url_prefix='/ffmpeg')
    app.register_blueprint(image_bp, url_prefix='/image')
    app.register_blueprint(func, url_prefix='/func')
    app.register_blueprint(upload, url_prefix='/upload')
    app.jinja_env.globals.update(max=max, min=min)

    # ProxyFix 미들웨어 적용 (리버스 프록시 뒤에서 올바르게 동작하도록)
    # Flask가 실제로 클라이언트 요청을 처리할 때, 리버스 프록시(Nginx, Apache) 뒤에 있으면 원래 클라이언트의 정보(프로토콜, 호스트 등)가 프록시의 정보로 덮어쓰여질 수 있다
    # ProxyFix는 프록시가 제공하는 HTTP 헤더(예: X-Forwarded-Proto, X-Forwarded-Host)를 읽어 원래 요청 정보를 복원한다
    # x_proto=1: X-Forwarded-Proto 헤더에 담긴 정보를 Flask가 요청이 HTTPS로 들어왔는지 인식하도록 한다
    # x_host=1: X-Forwarded-Host 헤더에 담긴 호스트 정보를 Flask가 올바른 도메인/호스트를 인식하도록 한다
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Flask 앱에 WebSocket 기능을 추가
    socketio.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    # 게스트 세션 로그아웃 강제
    @app.before_request
    def force_guest_auto_logout():
        # 게스트가 로그인한 경우
        if current_user.is_authenticated and current_user.get_id() == settings['GUEST_USERNAME']:
            now = datetime.utcnow()
            last_str = session.get('user_last_activity')

            last = datetime.fromisoformat(last_str) if isinstance(last_str, str) else now
            inactive_time = (now - last).total_seconds()

            if inactive_time > SESSION_EXPIRATION_TIME.total_seconds():
                logout_user()
                session.clear()
                return redirect(url_for('login'))

            session['user_last_activity'] = now.isoformat() # 세션 갱신

    # 서버 시작 시 호출 (순서대로 핸들러 호출, 하나라도 return 또는 abort() 시 다음 필터링 실행안됨)
    @app.before_request
    def before_request():
        # 실 IP 추출 (프록시 뒤에 있을 경우)
        ip = request.environ.get("HTTP_X_REAL_IP")
        # if ip == '127.0.0.1':
        #     ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
        # print(ip)

        # 차단된 경우 -> 시간 지난 건 해제
        if ip in BLOCKED_IPS:
            if datetime.now() >= BLOCKED_IPS[ip]:
                del BLOCKED_IPS[ip]  # 차단 해제
            else:
                return abort(403, description="접근이 차단된 IP입니다.")

        ###################### 세션 잠금 확인 ######################
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


        ###################### 엔드포인트 제한 ######################
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
            # GUEST_USERNAME 사용자가 /image/trip-images 경로가 아닌 경우만 제한
            # if not request.path.startswith('/image/trip-images'):
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

    @app.after_request
    def track_404(response):
        # ip = request.remote_addr
        ip = request.environ.get("HTTP_X_REAL_IP", request.environ.get("REMOTE_ADDR", "-")).strip()
        # 223.38 로 시작하고 나머지 변함

        # 404 응답이었으면 카운트 증가
        # if not current_user.is_authenticated and response.status_code == 404:
        #     count, _ = IP_404_COUNTS.get(ip, (0, datetime.now())) # 파라미터 2개로 각각의 값을 가져온다
        #     count += 1
        #     IP_404_COUNTS[ip] = (count, datetime.now())
        #
        #     # 5번 넘으면 차단
        #     if count >= BLOCK_THRESHOLD:
        #         until = datetime.now() + BLOCK_DURATION # value
        #         BLOCKED_IPS[ip] = until
        #         save_blocked_ip(ip, until)  # ✅ 파일에 추가 저장
        #         print(f"🚫 IP {ip} is blocked until {until}")
        #         del IP_404_COUNTS[ip]

        return response

    # @app.after_request
    def add_no_cache_headers(response):
        # Flask에서 모든 응답에 캐시 금지 헤더 추가
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

        # 특정 경로(/func/chat)에만 캐시 금지 예시
        # if request.path.startswith('/func/chat'):
        #     response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        #     response.headers["Pragma"] = "no-cache"
        #     response.headers["Expires"] = "0"
        # return response

    @app.errorhandler(RequestEntityTooLarge)
    def handle_413(e):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        print(f"### {current_time} - 🚫 413 RequestEntityTooLarge: 요청 크기 초과")
        return jsonify({'error': '업로드 파일이 너무 큽니다. 최대 30GB까지 허용됩니다.'}), 413

    # @app.route('/check-headers')
    def check_headers():
        return jsonify({
            "REMOTE_ADDR": request.environ.get("REMOTE_ADDR"),
            "HTTP_X_FORWARDED_FOR": request.environ.get("HTTP_X_FORWARDED_FOR"),
            "HTTP_X_REAL_IP": request.environ.get("HTTP_X_REAL_IP"),
            "HTTP_X_FORWARDED_PROTO": request.environ.get("HTTP_X_FORWARDED_PROTO"),
            "HTTP_HOST": request.environ.get("HTTP_HOST"),
            "request.remote_addr": request.remote_addr,
        })

    def check_server_restarted():
        restart_flag = 'data/server_status.txt'
        if not os.path.exists(restart_flag):
            with open(restart_flag, 'w') as f:
                f.write('restarted')
            return True
        return False

    return app
