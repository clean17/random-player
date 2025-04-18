import os
import signal
import subprocess
# from flask_cors import CORS
from config.config import settings
from utils.common import signal_handler, cleanup, on_exit

NODE_SERVER_PATH = settings['NODE_SERVER_PATH']
# CORS(app, origins="http://127.0.0.1:3000", supports_credentials=True) # 해당 출처를 통해서만 리소스 접근 허용


# 0: werkzeug, 1: waitress
select_server = 0


if __name__ == '__main__':
    # SIGINT(인터럽트 시그널, 보통 Ctrl+C 누름)에 대한 핸들러를 등록
    signal.signal(signal.SIGINT, signal_handler)

    # 'npm run dev' 실행 (백그라운드 실행)
#     node_process = subprocess.Popen(["cmd", "/c", "node src/server_io.js"], cwd=NODE_SERVER_PATH, text=True)

    if select_server == 0: # werkzeug
        from app.task_manager import start_periodic_task, start_background_tasks
        from utils.wsgi_midleware import logger
        logger.info("############################### Starting server.... ####################################")
        from app import create_app # Flask, # create_app 에서 WebSocket 기능을 추가함

        # ✅ 앱 인스턴스
        app = create_app()

        # 업로드 디렉토리 압축파일 생성, 로또 구매 배치
        # start_periodic_task()
#         start_background_tasks()

        app.run(debug=True, host='0.0.0.0', port=8090, use_reloader=False, threaded=True)
#         app.run(debug=True, host='0.0.0.0', port=443, ssl_context=('cert.pem', 'key.pem'), threaded=True)

    if select_server == 1: # waitress 서버
        from waitress import serve
        from app.task_manager import start_periodic_task, start_background_tasks
        from utils.wsgi_midleware import RequestLoggingMiddleware, logger
#         from utils.wsgi_midleware import RequestLoggingMiddleware, HopByHopHeaderFilter, ReverseProxied, logger
        logger.info("############################### Starting server.... ####################################")
        from app import create_app

        app = create_app()

        # 커스텀 로깅 설정 미들웨어 적용
        app.wsgi_app = RequestLoggingMiddleware(app.wsgi_app)

        # Hop-by-Hop 헤더 필터 미들웨어 적용
        # app.wsgi_app = HopByHopHeaderFilter(app.wsgi_app)

        # 모든 요청에 대해 URL 스킴(scheme)을 강제로 HTTPS로 설정, 리버스 프록시 환경에서도 클라이언트 요청을 HTTPS로 인식하여 보안 기능 동작하도록 함
        # app.wsgi_app = ReverseProxied(app.wsgi_app)

        # 업로드 디렉토리 압축파일 생성, 로또 구매 배치
        # start_periodic_task()
#         start_background_tasks()

        serve(app, host='0.0.0.0', port=8090, threads=6, max_request_body_size=1024*1024*1024*50)  # Waitress 서버, SSL 설정은 nginx에서 처리한다 / WebSocket 미지원, 50GB
