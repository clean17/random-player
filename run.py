import signal
import subprocess
# from flask_cors import CORS
from config.config import settings
from utils.common import signal_handler, register_shutdown_handlers
from job.batch_runner import initialize_directories, start_async_loop_in_background, \
    create_scheduler

NODE_SERVER_PATH = settings['NODE_SERVER_PATH']
# CORS(app, origins="http://127.0.0.1:3000", supports_credentials=True) # 해당 출처를 통해서만 리소스 접근 허용


# 0: werkzeug, 1: waitress
select_server = 1


if __name__ == '__main__':
    # SIGINT(인터럽트 시그널, 보통 Ctrl+C 누름)에 대한 핸들러를 등록
    # signal.signal(signal.SIGINT, signal_handler)
    register_shutdown_handlers()

    initialize_directories()
    start_async_loop_in_background()

    # 업로드 디렉토리 압축파일 생성, 로또 구매 배치
    # start_periodic_task() # multiprocessing

    # acquire_lock() # thread 중복 실행 방지
    # start_background_tasks() # thread

    scheduler = create_scheduler()
    scheduler.start()

    # 'npm run dev' 실행 (백그라운드 실행)
    node_process = subprocess.Popen(["cmd", "/c", "node src/server_io.js"], cwd=NODE_SERVER_PATH, text=True)

    if select_server == 0: # werkzeug, 개발
        from utils.wsgi_midleware import logger
        from werkzeug.middleware.proxy_fix import ProxyFix
        logger.info("############################### Starting server.... ####################################")
        from app import create_app # Flask, # create_app 에서 WebSocket 기능을 추가함
        app = create_app()
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

        # Hop-by-Hop 헤더 필터 미들웨어 적용
        app.wsgi_app = HopByHopHeaderFilter(app.wsgi_app)
        # 커스텀 로깅 설정 미들웨어 적용
        app.wsgi_app = RequestLoggingMiddleware(app.wsgi_app)
        # 모든 요청에 대해 URL 스킴(scheme)을 강제로 HTTPS로 설정, 리버스 프록시 환경에서도 클라이언트 요청을 HTTPS로 인식하여 보안 기능 동작하도록 함
        app.wsgi_app = ReverseProxied(app.wsgi_app)

        # serve(app, host='0.0.0.0', port=8090, threads=12, max_request_body_size=1024*1024*1024*50)  # Waitress 서버, SSL 설정은 nginx에서 처리한다 / WebSocket 미지원, 50GB
        # nginx 프록시 서버만 접근 허용
        serve(app, host='127.0.0.1', port=8090, threads=12, max_request_body_size=1024*1024*1024*50)  # Waitress 서버, SSL 설정은 nginx에서 처리한다 / WebSocket 미지원, 50GB
