import io
import logging
import os
import signal
import sys
from waitress import serve
from app.task_manager import start_periodic_task

from app import create_app
from flask_cors import CORS
import subprocess
import glob
from config import settings
import atexit
from collections import defaultdict
from wsgi_midleware import RequestLoggingMiddleware, HopByHopHeaderFilter, ReverseProxied, logger


NODE_SERVER_PATH = settings['NODE_SERVER_PATH']


# Flask 앱 생성
app = create_app()

# CORS(app, origins="http://127.0.0.1:3000", supports_credentials=True) # 해당 출처를 통해서만 리소스 접근 허용

# 커스텀 로깅 설정 미들웨어 적용
app.wsgi_app = RequestLoggingMiddleware(app.wsgi_app)

# Hop-by-Hop 헤더 필터 미들웨어 적용
# app.wsgi_app = HopByHopHeaderFilter(app.wsgi_app)

# ProxyFix 미들웨어 적용 (리버스 프록시 뒤에서 올바르게 동작하도록)
# Flask가 실제로 클라이언트 요청을 처리할 때, 리버스 프록시(Nginx, Apache) 뒤에 있으면 원래 클라이언트의 정보(프로토콜, 호스트 등)가 프록시의 정보로 덮어쓰여질 수 있다
# ProxyFix는 프록시가 제공하는 HTTP 헤더(예: X-Forwarded-Proto, X-Forwarded-Host)를 읽어 원래 요청 정보를 복원한다
# x_proto=1: X-Forwarded-Proto 헤더에 담긴 정보를 Flask가 요청이 HTTPS로 들어왔는지 인식하도록 한다
# x_host=1: X-Forwarded-Host 헤더에 담긴 호스트 정보를 Flask가 올바른 도메인/호스트를 인식하도록 한다
# app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# 모든 요청에 대해 URL 스킴(scheme)을 강제로 HTTPS로 설정, 리버스 프록시 환경에서도 클라이언트 요청을 HTTPS로 인식하여 보안 기능 동작하도록 함
# app.wsgi_app = ReverseProxied(app.wsgi_app)


# Ctrl+C 이벤트 핸들러
def signal_handler(sig, frame):
    logger.info("#### Register Server Shutdown Handler... ####")
    pid = os.getpid()
    os.kill(pid, signal.SIGTERM) # 다른 파이썬 종료시키지 않고 자신만 종료

    # os.system('taskkill /f /im python.exe')
    # sys.exit(0)

# 애플리케이션 종료 후 실행
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

atexit.register(on_exit) #  프로그램이 정상적으로 종료될 때 호출될 함수를 등록


if __name__ == '__main__':
    logger.info("################################### Starting server.... ####################################")

    # SIGINT(인터럽트 시그널, 보통 Ctrl+C 누름)에 대한 핸들러를 등록
    signal.signal(signal.SIGINT, signal_handler)

    # 업로드 디렉토리 압축파일 생성 배치
    start_periodic_task()

    # 'npm run dev' 실행 (백그라운드 실행)
    subprocess.Popen(["cmd", "/c", "node src/server_io.js"], cwd=NODE_SERVER_PATH, text=True)


    # Flask 내장 서버
    # __init__.py 에서 WebSocket 기능을 추가함
    # app.run(debug=True, host='0.0.0.0', port=8090, use_reloader=False, threaded=True)
    # app.run(debug=True, host='0.0.0.0', port=443, ssl_context=('cert.pem', 'key.pem'), threaded=True)

    serve(app, host='0.0.0.0', port=8090, threads=6)  # Waitress 서버, SSL 설정은 nginx에서 처리한다 / WebSocket 미지원
