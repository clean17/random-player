import io
import logging
import os
import signal
import sys
from waitress import serve
from werkzeug.middleware.proxy_fix import ProxyFix
from app.task_manager import start_periodic_task
from logger_config import setup_logging
from app import create_app, socketio
from flask_cors import CORS
import subprocess



# 1️⃣ 로그 설정 적용
logger = setup_logging()

# 2️⃣ Flask 앱 생성
app = create_app()
# CORS(app, origins="http://127.0.0.1:3000", supports_credentials=True)

'''
Hop-by-Hop: HTTP/1.1 프로토콜에서 사용하는 헤더
프록시나 게이트웨이를 통과하는 동안 다른 연결로 전달되지 않아야 한다

Connection, Keep-Alive, ...

서버-애플리케이션 인터페이스에서 사용하면 안된다
Hop-by-Hop 헤더를 제거하는 미들웨어
'''
class HopByHopHeaderFilter(object):
    hop_by_hop_headers = {
        'connection',
        'keep-alive',
        'proxy-authenticate',
        'proxy-authorization',
        'te',
        'trailer',
        'transfer-encoding',
        'upgrade',
    }
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        def custom_start_response(status, headers, exc_info=None):
            filtered_headers = [(key, value) for key, value in headers if key.lower() not in self.hop_by_hop_headers]
            return start_response(status, filtered_headers, exc_info)
        return self.app(environ, custom_start_response)

# ProxyFix 미들웨어 적용 (리버스 프록시 뒤에서 올바르게 동작하도록)
# 리버스 프록시 뒤에 있는 Flask를 처리하는 ProxyFix 미들웨어 적용, 헤더 전달용
# x_proto=1: X-Forwarded-Proto 헤더에 담긴 정보를 Flask가 요청이 HTTPS로 들어왔는지 인식하도록 한다
# x_host=1: X-Forwarded-Host 헤더에 담긴 호스트 정보를 Flask가 올바른 도메인/호스트를 인식하도록 한다
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Hop-by-Hop 헤더 필터 미들웨어 적용
app.wsgi_app = HopByHopHeaderFilter(app.wsgi_app)

# nginx(ssl)를 추가하고 나서 아래 설정을 추가하면 /get_tasks의 _external=True가 https:// 로 이미지 경로를 생성한다
class ReverseProxied:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ['wsgi.url_scheme'] = 'https'  # HTTPS로 설정
        return self.app(environ, start_response)

# app.wsgi_app = ReverseProxied(app.wsgi_app)

def signal_handler(sig, frame):
    logger.info("#### Register Server Shutdown Handler... ####")
    pid = os.getpid()
    os.kill(pid, signal.SIGTERM) # 다른 파이썬 종료시키지 않고 자신만 종료

    # os.system('taskkill /f /im python.exe')
    # sys.exit(0)

if __name__ == '__main__':
    # 서버 종료 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    logger.info("################################### Starting server.... ####################################")

    start_periodic_task() # 업로드 파일 압축파일 생성

    # Node.js 프로젝트 경로 (이스케이프 문제 해결)
    node_project_path = r"C:\my-project\nodejs-wss"

    # 'npm run dev' 실행 (백그라운드 실행)
    process = subprocess.Popen(["cmd", "/c", "npm run dev"], cwd=node_project_path, text=True)

    # 서버가 실행되는 동안 다른 작업을 수행할 수 있음
    print("Node.js 서버가 실행되었습니다.")

    app.run(debug=True, host='0.0.0.0', port=8090) # __init__.py 에서 WebSocket 기능을 추가함
    # socketio.run(app, debug=True, host='0.0.0.0', port=8090) # Flask + WebSocket 서버 동시 실행
    # app.run(debug=True, host='0.0.0.0', port=443, ssl_context=('cert.pem', 'key.pem'), threaded=True) # Flask 내장 서버

    # serve(app, host='0.0.0.0', port=8090, threads=6)  # Waitress 서버, SSL 설정은 nginx에서 처리한다 / WebSocket 미지원
