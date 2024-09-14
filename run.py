import os
import signal
import sys
import logging
from waitress import serve
from app import create_app
from werkzeug.middleware.proxy_fix import ProxyFix
# from flask_cors import CORS

'''
127.0.0.1로 시작하는 로그 제거 필터링

class NoHTTPRequestLogFilter(logging.Filter):
    def filter(self, record):
        return not record.getMessage().startswith('127.0.0.1')

# 모든 로그 핸들러에 대해 필터 적용
for handler in app.logger.handlers:
    handler.addFilter(NoHTTPRequestLogFilter())
'''

# Create a logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('### %(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 전역 로거  (웹요청이 아닌 파이썬 내부 로그를 출력) - root
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)

# Create a file handler for logging
file_handler = logging.FileHandler('logs/app.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)




# APScheduler 로거
logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)

# Flask가 내부적으로 사용하는 Werkzeug 서버 (app.run())
# Werkzeug 로거    --- app.run()
logging.getLogger('werkzeug').setLevel(logging.INFO)

# Waitress 로거    --- serve()
waitress_logger = logging.getLogger('waitress')
# Waitress 로그를 root로 전파하지 않음
# waitress_logger.propagate = False # 전파하지 않으면 file에 로그가 남지 않는다

if not waitress_logger.handlers:  # 핸들러가 없다면 추가
    waitress_logger.addHandler(console_handler)
    waitress_logger.setLevel(logging.INFO)

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

app = create_app()



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
    logger.info("#### Exiting server... ####")
    pid = os.getpid()
    os.kill(pid, signal.SIGTERM) # 다른 파이썬 종료시키지 않고 자신만 종료

    # os.system('taskkill /f /im python.exe')
    # sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    logger.info("#### Starting server.... ####")
    # app.run(debug=True, host='0.0.0.0', port=8090)
    # app.run(debug=True, host='0.0.0.0', port=443, ssl_context=('cert.pem', 'key.pem'), threaded=True) # Flask 내장 서버

    serve(app, host='0.0.0.0', port=8090, threads=6)  # Waitress 서버, SSL 설정은 nginx에서 처리한다

'''
Flask 내장 서버 - 코드 수정 시 자동 재시작, 부하처리 오류복구 기능 부족, threaded=True으로 멀티스레드 보장되지는 않는다, 개발용
Waitress 서버 - Python WSGI 서버, Waitress는 워커(프로세스)와 스레드 설정을 통해 병렬 처리를 훨씬 더 세밀하게 제어, IO 바운드 작업에서 성능을 극대화 >> 대규모 트래픽과 안정성
'''