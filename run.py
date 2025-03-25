import io
import logging
import os
import signal
import sys
from waitress import serve
from werkzeug.middleware.proxy_fix import ProxyFix
from app.task_manager import start_periodic_task
from logger_config import setup_logging
from app import create_app
from flask_cors import CORS
import subprocess
import glob
from config import settings
import atexit
from collections import defaultdict


NODE_SERVER_PATH = settings['NODE_SERVER_PATH']


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

# 애플리케이션 종료 후 실행
# def on_exit():
#     print("프로그램이 종료됩니다.")
#     lock_files = glob.glob("logs/.__app_*.lock")  # logs 폴더 내 __app_*.lock 파일 목록 가져오기
#
#     for lock_file in lock_files:
#         try:
#             os.remove(lock_file)
#         except Exception as e:
#             print(f"Error deleting {lock_file}: {e}")  # 삭제 실패 시 오류 출력

def on_exit():
    print("프로그램이 종료됩니다.")

    # 로그 파일 패턴 읽기
    log_files = glob.glob("logs/app_*.log.20-*")

    if not log_files:
        print("병합할 로그 파일이 없습니다.")
        return

    # 로그 그룹화: "app_250320.log" 같은 base 경로를 key로 묶기
    grouped_logs = defaultdict(list)
    for path in log_files:
        # 예: logs/app_250320.log.2025-03-20 → logs/app_250320.log
        base_path = path.rsplit('.', 1)[0]  # 마지막 .을 기준으로 자르기
        grouped_logs[base_path].append(path)

    # 각 그룹별로 병합 처리
    for base_log_path, files in grouped_logs.items():
        files.sort()  # 날짜순 정렬

        try:
            with open(base_log_path, 'a', encoding='utf-8') as merged_file:
                for file_path in files:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        merged_file.write(f.read())
                        merged_file.write("\n")
                    os.remove(file_path)
                    print(f"{file_path} → 병합 후 삭제됨")

            print(f"📦 모든 로그가 {base_log_path} 에 병합되었습니다.\n")

        except Exception as e:
            print(f"❌ 병합 중 오류 발생 ({base_log_path}): {e}")

    # 락 파일 삭제 (기존 코드 유지)
    lock_files = glob.glob("logs/.__app_*.lock")
    for lock_file in lock_files:
        try:
            os.remove(lock_file)
        except Exception as e:
            print(f"Error deleting {lock_file}: {e}")

atexit.register(on_exit)

if __name__ == '__main__':
    # 서버 종료 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    logger.info("################################### Starting server.... ####################################")

    start_periodic_task() # 업로드 파일 압축파일 생성

    # 'npm run dev' 실행 (백그라운드 실행)
    process = subprocess.Popen(["cmd", "/c", "node src/server_io.js"], cwd=NODE_SERVER_PATH, text=True)


    app.run(debug=True, host='0.0.0.0', port=8090, use_reloader=False) # __init__.py 에서 WebSocket 기능을 추가함
    # app.run(debug=True, host='0.0.0.0', port=443, ssl_context=('cert.pem', 'key.pem'), threaded=True) # Flask 내장 서버

    # serve(app, host='0.0.0.0', port=8090, threads=6)  # Waitress 서버, SSL 설정은 nginx에서 처리한다 / WebSocket 미지원
