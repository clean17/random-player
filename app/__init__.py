import os
import time
import re
from datetime import datetime, timezone
from collections import defaultdict, deque
from flask import Flask, session, send_file, render_template, render_template_string, jsonify, request, redirect, url_for, send_from_directory, abort
from flask_login import LoginManager, current_user, logout_user, login_required
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity

# from job.batch_runner import create_scheduler
from .auth import auth, User, users, SESSION_EXPIRATION_TIME, GUEST_SESSION_EXPIRATION_TIME, SECOND_PASSWORD_SESSION_KEY, check_active_session, save_verified_time, get_verified_time
from config.config import load_config
from .ffmpeg_handle import m_ffmpeg # ffmpeg_handle.py에서 m_ffmpeg 블루프린트를 import
from .main import main
from .video import video
from .image import image_bp, environment
from .function import func, socketio
from .stock import stock
from .upload import upload
from .oauth import oauth
from .rds import rds
from .file import file_bp
from .admin import admin
from .api import api
from .post import posts
import fnmatch
from datetime import datetime, timedelta
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.middleware.proxy_fix import ProxyFix
import uuid
from config.config import settings
from redis import Redis
from flask_wtf.csrf import CSRFProtect
from urllib.parse import urlparse, urljoin

# 허용할 엔드포인트 경로 - 추가될수록 유지보수가 힘들어진다 > 블랙리스트로 전환 필요
ALLOWED_PATHS = [
    '/favicon.ico',       # nginx 서버리스
    '/service-worker.js', # nginx 서버리스
    '/image/images',
    '/image/pages',
    '/image/move-image',
    '/upload',
    '/video/temp-video', # 조회만 가능
    '/func/download-zip',
    '/func/chat',
    '/func/memo',
    '/func/video-call',
    '/func/last-read-chat-id',
    '/func/api/url-preview',
    # '/auth/verify-password', # auth는 세션 확인용 모두가 들어올 수 있음
    # '/auth/update-session-time',
    # '/auth/check-verified',
]

# 차단할 엔드포인트 경로
BLOCKED_PATHS = [
    "/image/delete-images", # 어디서 사용하는지 확인 필요
    "/image/shuffle/ref-images",
    # "/video/select-directory", # video는 화이트리스트 하나만 허용하니까 블랙리스트 추가할 필요 없음
    # "/video/video-player",
    "/video/video-player/1", "/video/video-player/2", "/video/video-player/3", "/video/video-player/4", "/video/video-player/5", "/video/video-player/7"
    # "/video/videos",
    # "/video/delete",
    # "/video/stream",
    "/ffmpeg",
    "/func/empty-trash-bin",
    # "/func/logs",
    "/func/buy/lotto-test",
    "/rds"
]

# 정규표현식 > 서브 경로까지 필터링
BLOCKED_PATTERNS = [
    r"^/admin.*",
    r"^/debug/.*",
    r"^/internal/api/.*"
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





BLOCKED_IPS = load_blocked_ips()                      # 차단된 IP: {ip: block_until_time}, 회사 IP: 106.101.2.102
ip_404_log = defaultdict(lambda: deque(maxlen=10))    # IP별 최근 404 기록 시간 저장 (deque로 sliding window)
IP_404_COUNTS = {}                                    # IP 기록: {ip: [404_count, last_404_time]}
BLOCK_THRESHOLD = 5                                   # 차단 설정 임계횟수
BLOCK_DURATION = timedelta(days=99999)                # 차단 기간
# BLOCKED_IP_PREFIXES = ['43', '3', '222', '139', '49', '66', '51', '34', '104', '124', '45', '167', '185', '64', '65', '162', '172', '170']
BLOCKED_IP_PREFIXES = ['222.239.104']

# csrf = CSRFProtect()

def get_client_ip(request):
    # 1. X-Real-IP (Nginx에서 주로 세팅, 프록시 뒤에 있을 경우)
    ip = request.environ.get("HTTP_X_REAL_IP")
    if ip:
        return ip

    # 2. X-Forwarded-For (여러 프록시 거칠 때, 제일 앞이 원본 IP)
    ip = request.headers.get("X-Forwarded-For")
    if ip:
        # 여러 IP가 있을 경우, 첫 번째(IP 체인의 가장 앞쪽)가 원래 클라이언트
        return ip.split(',')[0].strip()

    # 3. 그 외에는 Flask 기본값
    return request.remote_addr

def to_jpg(filename):
    return filename.rsplit('.', 1)[0] + '.jpg'

def format_hms(elapsed):
    h = int(elapsed // 3600)
    m = int((elapsed % 3600) // 60)
    # s = elapsed % 60
    s = int(elapsed % 60)
    # return f"{h}시간 {m}분 {s:.2f}초"
    return f"{h}시간 {m}분 {s}초"

def create_app():
    # scheduler = create_scheduler()
    # scheduler.start()

    print("✅ create_app() called", uuid.uuid4())
    app = Flask(__name__, static_folder='static')
    app.config.update(load_config())

    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 * 1024  # 50GB
    app.config['SESSION_REFRESH_EACH_REQUEST'] = True  # 매 요청마다 세션 갱신 (원하지 않으면 False)
    app.secret_key = app.config['SECRET_KEY'] # app.config.update(load_config()) 에서 키를 통해 가져온다
    # app.config['PERMANENT_SESSION_LIFETIME'] = SESSION_EXPIRATION_TIME # 전역 세션 만료 설정, Flask 공식 설정값 >>> 25.05.13 Redis로 TTL을 체크하기 위해 주석
    # app.permanent_session_lifetime = SESSION_EXPIRATION_TIME  # 기본 유효기간 설정 (기본값: timedelta(days=31), property 접근 방식; 위와 동일; 내부적으로 app.config['PERMANENT_SESSION_LIFETIME']를 읽고 쓴다

    # 세션을 Redis에 저장하도록 >>> Flask가 자동으로 Redis에 해당 세션을 JSON 직렬화하여 저장
    app.config['SESSION_TYPE'] = 'redis'
    app.config['SESSION_REDIS'] = Redis(host='localhost', port=6379)

    app.config["JWT_SECRET_KEY"] = app.config['SECRET_KEY'] # jwt 테스트 한다고 추가했음, 사용안함

    app.register_blueprint(main, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/auth')
    app.register_blueprint(api, url_prefix='/api')
    app.register_blueprint(video, url_prefix='/video')
    app.register_blueprint(m_ffmpeg, url_prefix='/ffmpeg')
    app.register_blueprint(image_bp, url_prefix='/image')
    app.register_blueprint(func, url_prefix='/func')
    app.register_blueprint(stock, url_prefix='/stocks')
    app.register_blueprint(upload, url_prefix='/upload')
    app.register_blueprint(oauth, url_prefix='/oauth')
    app.register_blueprint(rds, url_prefix='/rds')
    app.register_blueprint(file_bp, url_prefix='/file')
    app.register_blueprint(admin, url_prefix='/admin')
    app.register_blueprint(posts, url_prefix='/posts')
    app.jinja_env.globals.update(max=max, min=min)
    # Jinja2 탬플릿 캐시 x
    app.jinja_env.auto_reload = True
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    # Jinja2 커스텀 필터 등록
    app.jinja_env.filters['to_jpg'] = to_jpg


    # ProxyFix 미들웨어 적용 (리버스 프록시 뒤에서 올바르게 동작하도록)
    # Flask가 실제로 클라이언트 요청을 처리할 때, 리버스 프록시(Nginx, Apache) 뒤에 있으면 원래 클라이언트의 정보(프로토콜, 호스트 등)가 프록시의 정보로 덮어쓰여질 수 있다
    # ProxyFix는 프록시가 제공하는 HTTP 헤더(예: X-Forwarded-Proto, X-Forwarded-Host)를 읽어 원래 요청 정보를 복원한다
    # x_proto=1: X-Forwarded-Proto 헤더에 담긴 정보를 Flask가 요청이 HTTPS로 들어왔는지 인식하도록 한다
    # x_host=1: X-Forwarded-Host 헤더에 담긴 호스트 정보를 Flask가 올바른 도메인/호스트를 인식하도록 한다
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Flask 앱에 WebSocket 기능을 추가
    socketio.init_app(app)

    # jwt test
    jwt = JWTManager(app)

    # csrf.init_app(app)  # 앱에 CSRF 보호 적용

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'


    # 서버 시작 시 호출 (순서대로 핸들러 호출, 하나라도 return 또는 abort() 시 다음 필터링 실행안됨)
    @app.before_request
    def before_request():
        ip = get_client_ip(request)

        if ip and any(ip.startswith(prefix + '.') for prefix in BLOCKED_IP_PREFIXES):
            return abort(403, description="Access blocked IP.")

        # 차단된 경우 -> 시간 지난 건 해제
        if ip and ip in BLOCKED_IPS:
            if datetime.now() >= BLOCKED_IPS[ip]:
                del BLOCKED_IPS[ip]  # 차단 해제
            else:
                return abort(403, description="Access blocked IP.")

        if not ip:
            print('# No ip information')
            return

        ###################### 엔드포인트 허용 ######################
        if request.path == '/auth/logout':
            return

        if request.path.startswith('/static'):
            return

        if request.path.startswith('/service-worker.js'):
            return

        if not current_user.is_authenticated: # PERMANENT_SESSION_LIFETIME 를 설정하면 redis 확인 전에 세션이 만료된다
            return  #  비회원은 인증 체크/검증을 하지 않는다

        check_active_session() # redis ttl, 세션 동기화

        if request.path == '/':
            return


        ###################### 세션 잠금 확인 ###################### >> 로그인에서 처리
        # if 'lockout_time' in session and session['lockout_time']:
        #     lockout_time = session['lockout_time']
        #
        #     # lockout_time 값이 문자열인지 확인
        #     if isinstance(lockout_time, str):
        #         # 문자열을 datetime 객체로 변환
        #         lockout_time = datetime.fromisoformat(lockout_time)
        #     else:
        #         # 예상치 못한 데이터 타입이면 세션 초기화
        #         session.pop('lockout_time', None) # dict.pop(key[, default]) default: null일경우 기본값
        #         session['attempts'] = 0
        #         return
        #
        #     # 현재 시간을 UTC로 설정
        #     now = datetime.now(timezone.utc)
        #
        #     if now >= lockout_time:
        #         session.pop('lockout_time', None)  # lockout_time 제거
        #         session['attempts'] = 0

        # if check_server_restarted(): # 세션관리는 db로 이관했음 25.05.22.
        #     session.clear()


        ####################### 추가 인증 #########################
        # if request.path.startswith('/func/memo'):

        # paths_to_check = ['/func/memo', '/func/chat', '/func/log']
        # if request.path.startswith(tuple(paths_to_check)):

        if request.path.startswith(('/func/memo', '/func/chat')): # tuple
            if not current_user.is_authenticated:
                return redirect(url_for("auth.logout"))

            now = datetime.now()
            weekday = now.weekday()   # 0=월요일, ..., 4=금요일
            hour = now.hour
            check_date_conditions = True

            # 월 08:00 ~ 금 20:00 사이면 추가 검증 X
            if ( (weekday == 0 and hour >= 8) or            # 월요일 8시 이후
                    (weekday > 0 and weekday < 4) or        # 화, 수, 목 (종일)
                    (weekday == 4 and hour <= 20) ):        # 금요일 20시 이전
                check_date_conditions = False

            if check_date_conditions: # 평일에만 추가인증 안함
            # if False: # 추가인증 안함
            # if True: # 추가인증 필수
                url = request.path
                parts = url.split("/")
                base_path = "/" + "/".join(parts[1:3])

                verified = session.get(SECOND_PASSWORD_SESSION_KEY) # 로그인 후 추가 인증을 했는지 여부
                # verified_at_str = session.get('second_password_verified_at') # 마지막 인증 시간
                verified_at_str = get_verified_time(current_user.get_id())

                # nh에게 추가 검증을 요구
                if not verified and current_user.get_id() == app.config['GUEST_USERNAME']:
                    return redirect(url_for('auth.verify_password', next=base_path))

                # redis에 추가 검증 시간이 없으면
                if not verified_at_str:
                    # 인증 안했거나 인증시간 없음 → 인증 페이지로 이동
                    return redirect(url_for('auth.verify_password', next=base_path))

                # 시간 파싱 실패 → 인증 무효 처리
                try:
                    verified_at = datetime.fromisoformat(verified_at_str)
                except Exception:
                    session.pop(SECOND_PASSWORD_SESSION_KEY, None)
                    session.pop('second_password_verified_at', None)
                    return redirect(url_for('auth.verify_password', next=base_path))

                # 추가 검증 후 10분 초과 시
                # if datetime.now() - verified_at > timedelta(seconds=5):
                if datetime.now() - verified_at > timedelta(minutes=10):
                    print('    # The second password authentication time has expired : ', current_user.get_id())
                    session.pop(SECOND_PASSWORD_SESSION_KEY, None)
                    session.pop('second_password_verified_at', None)
                    return redirect(url_for('auth.verify_password', next=base_path))

            # 현재 uri 요청을 반복하면 세션 시간 갱신
            # session['second_password_verified_at'] = datetime.now().isoformat()
            save_verified_time(current_user.get_id())



        # GUEST_USERNAME 사용자에 대한 검증
        if current_user.get_id() == app.config['GUEST_USERNAME']:
            last_active = session.get("last_active")
            if last_active:
                now = datetime.now().timestamp()
                elapsed = now - last_active
                timeout = GUEST_SESSION_EXPIRATION_TIME.total_seconds()

                if elapsed > timeout:
                    print(f"    request.path - {request.path}")
                    print(f"    before_request - ⏱  경과 시간: {format_hms(elapsed)} redirect logout")
                    return redirect(url_for("auth.logout"))

                session["last_active"] = now

            # print('request.path', request.path)
            if not any(request.path.startswith(path) for path in ALLOWED_PATHS):
                if any(request.path.startswith(path) for path in BLOCKED_PATHS):
            # if any(re.match(pattern, request.path) for pattern in BLOCKED_PATTERNS):
                    print(f"    request.path - {request.path} : 로깅 여기서 302 ?? ")
                    return redirect(url_for('auth.logout'))
        else:
            pass

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

    @app.route("/htmltest")
    def get_test():
        return render_template('test.html', version=int(time.time()))

    @app.route("/protected")
    @jwt_required()
    def protected():
        user_id = get_jwt_identity()
        return f"Hello {user_id}"

    @app.after_request
    def track_404(response):
        # ip = request.remote_addr
        ip = request.environ.get("HTTP_X_REAL_IP", request.environ.get("REMOTE_ADDR", "-")).strip()

        # 세션이 없음 + 404 응답이었으면 카운트 증가
        if not current_user.is_authenticated and response.status_code == 404:
            now = time.time()
            dq = ip_404_log[ip] # 키에 해당하는 10칸 짜리 deque를 가져온다, 없으면 생성, 있으면 반환
            dq.append(now)      # 요청이 들어올 때마다 해당 시간을 넣는다.

            # 5초 이내 404가 5회 이상?
            # 파이썬 리스트 컴프리헨션을 사용한 “필터링” > for t in dq
            recent = [t for t in dq if now - t <= BLOCK_THRESHOLD] # 지금부터 BLOCK_THRESHOLD 이내인 값만 리스트로 반환
            # recent = [t for t in dq] # 5회 누적으로 수정, 새로운 list 타입 생성
            if len(recent) >= BLOCK_THRESHOLD:
                until = datetime.now() + BLOCK_DURATION # value
                BLOCKED_IPS[ip] = until
                save_blocked_ip(ip, until)  # ✅ 파일에 추가 저장
                # print(f"🚫 {ip} 차단됨 - 404 {BLOCK_THRESHOLD}회 초과")

            # count, _ = IP_404_COUNTS.get(ip, (0, datetime.now())) # 파라미터 2개로 각각의 값을 가져온다
            # count += 1
            # IP_404_COUNTS[ip] = (count, datetime.now())
            #
            # # 5번 넘으면 차단
            # if count >= BLOCK_THRESHOLD:
            #     until = datetime.now() + BLOCK_DURATION # value
            #     BLOCKED_IPS[ip] = until
            #     save_blocked_ip(ip, until)  # ✅ 파일에 추가 저장
            #     print(f"🚫 IP {ip} is blocked until {until}")
            #     del IP_404_COUNTS[ip]

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
