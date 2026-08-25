import os
import signal
import subprocess
import sys
# from flask_cors import CORS
from config.config import settings
from utils.common import signal_handler, register_shutdown_handlers, cleanup
from job.batch_runner import initialize_directories, create_scheduler

NODE_SERVER_PATH = settings['NODE_SERVER_PATH']


def spawn_mock_trading():
    """모의투자 자동매매(run_mock.py)를 자식 프로세스로 띄운다. (2026-08-20)

    왜 별 프로세스인가: kiwoom_fire_strategy_mock / kiwoom_trailing_stop 이 import 시점에 계좌번호와
    상태파일 경로를 모듈 상수로 굳히므로, 한 프로세스에서 실전(v8)과 모의(fire)를 같이 돌릴 수
    없다. KIWOOM_ENV=mock 인 별 프로세스로 띄우면 계좌·토큰·호스트·상태·이력·로그가 전부
    자동 분리된다. 상세는 job/batch_runner.create_mock_scheduler() docstring 참고.

    중복 실행은 run_mock.py 쪽 OS 파일 잠금이 막는다 — 수동으로 이미 띄워둔 게 있으면
    이 자식은 즉시 '[SKIP]' 을 찍고 스스로 종료한다. 그래서 여기서 따로 검사하지 않는다.
    """
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run_mock.py')
    if not os.path.exists(script):
        print(f'⚠️ run_mock.py 없음, 모의 자동매매 생략: {script}')
        return None
    try:
        # sys.executable = 현재 실행 중인 venv 파이썬. 시스템 파이썬으로 뜨면 psycopg 등이 없다.
        proc = subprocess.Popen([sys.executable, '-u', script],
                                cwd=os.path.dirname(script))
        print(f'🧪 모의투자 자동매매 시작 (run_mock.py, pid={proc.pid})')
        return proc
    except Exception as e:
        print(f'⚠️ 모의투자 자동매매 시작 실패: {e}')
        return None
# CORS(app, origins="http://127.0.0.1:3000", supports_credentials=True) # 해당 출처를 통해서만 리소스 접근 허용


# 0: werkzeug, 1: waitress
select_server = 1


if __name__ == '__main__':
    # SIGINT(인터럽트 시그널, 보통 Ctrl+C 누름)에 대한 핸들러를 등록
    # signal.signal(signal.SIGINT, signal_handler)

    initialize_directories()

    # 업로드 디렉토리 압축파일 생성, 로또 구매 배치
    # start_periodic_task() # multiprocessing

    # acquire_lock() # thread 중복 실행 방지
    # start_background_tasks() # thread

    # create_app()의 모듈 import가 끝나기 전에 스케줄러(백그라운드 스레드)가 먼저 같은 모듈을
    # import 하려 들면 importlib 모듈 락이 스레드 간에 충돌해 데드락/KeyError가 날 수 있다.
    # 그래서 앱 import(create_app)를 먼저 끝내고 나서 스케줄러를 시작한다.
    scheduler = None
    node_process = None
    mock_process = None

    try:
        if select_server == 0: # werkzeug, 개발
            from utils.wsgi_midleware import logger
            from werkzeug.middleware.proxy_fix import ProxyFix
            logger.info("############################### Starting server.... ####################################")
            from app import create_app # Flask, # create_app 에서 WebSocket 기능을 추가함
            app = create_app()

            scheduler = create_scheduler()
            # 'npm run dev' 실행 (백그라운드 실행)
            node_process = subprocess.Popen(["cmd", "/c", "node src/server_io.js"], cwd=NODE_SERVER_PATH, text=True)
            # 모의투자 자동매매 (별 프로세스, KIWOOM_ENV=mock)
            mock_process = spawn_mock_trading()
            # 종료 핸들러
            register_shutdown_handlers(scheduler, node_process, [mock_process])

            # 실제 클라이언트 IP (X-Forwarded-For) 를 읽도록
            app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
            app.run(debug=True, host='0.0.0.0', port=8088, use_reloader=True, threaded=True)
            # app.run(debug=True, host='0.0.0.0', port=443, ssl_context=('cert.pem', 'key.pem'), threaded=True)

        if select_server == 1: # waitress, 운영
            from waitress import serve
            from utils.wsgi_midleware import RequestLoggingMiddleware, HopByHopHeaderFilter, ReverseProxied, logger
            logger.info("############################### Starting server.... ####################################")
            from app import create_app
            app = create_app()

            scheduler = create_scheduler()
            # 'npm run dev' 실행 (백그라운드 실행)
            node_process = subprocess.Popen(["cmd", "/c", "node src/server_io.js"], cwd=NODE_SERVER_PATH, text=True)
            # 모의투자 자동매매 (별 프로세스, KIWOOM_ENV=mock)
            mock_process = spawn_mock_trading()
            # 종료 핸들러
            register_shutdown_handlers(scheduler, node_process, [mock_process])

            # Hop-by-Hop 헤더 필터 미들웨어 적용
            app.wsgi_app = HopByHopHeaderFilter(app.wsgi_app)
            # 커스텀 로깅 설정 미들웨어 적용
            app.wsgi_app = RequestLoggingMiddleware(app.wsgi_app)
            # 모든 요청에 대해 URL 스킴(scheme)을 강제로 HTTPS로 설정, 리버스 프록시 환경에서도 클라이언트 요청을 HTTPS로 인식하여 보안 기능 동작하도록 함
            app.wsgi_app = ReverseProxied(app.wsgi_app)

            # serve(app, host='0.0.0.0', port=8090, threads=12, max_request_body_size=1024*1024*1024*50)  # Waitress 서버, SSL 설정은 nginx에서 처리한다 / WebSocket 미지원, 50GB
            # nginx 프록시 서버만 접근 허용
            serve(app, host='127.0.0.1', port=8090, threads=12, max_request_body_size=1024*1024*1024*50)  # Waitress 서버, SSL 설정은 nginx에서 처리한다 / WebSocket 미지원, 50GB
    finally:
        cleanup(scheduler, node_process, [mock_process])
