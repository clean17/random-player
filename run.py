import os
import glob
import signal
import atexit
import subprocess
from collections import defaultdict
# from flask_cors import CORS
from config.config import settings

NODE_SERVER_PATH = settings['NODE_SERVER_PATH']
node_process = None
already_cleaned = False

# CORS(app, origins="http://127.0.0.1:3000", supports_credentials=True) # 해당 출처를 통해서만 리소스 접근 허용


# Ctrl+C 이벤트 핸들러
def signal_handler(sig, frame):
    logger.info("############################### Shutdown server.... ####################################")
    pid = os.getpid()
    os.kill(pid, signal.SIGTERM) # 다른 파이썬 종료시키지 않고 자신만 종료

    # os.system('taskkill /f /im python.exe')
    # sys.exit(0)

def cleanup():
    global already_cleaned
    if already_cleaned:
        return
    already_cleaned = True

    print("🧹 서버 종료 중: 자식 프로세스 정리")
    if node_process is not None and node_process.poll() is None:
        try:
            if os.name == 'nt':
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(node_process.pid)])
            else:
                node_process.terminate()
        except Exception as e:
            print(f"⚠️ 종료 중 예외: {e}")

# 애플리케이션 종료 후 실행
def on_exit():
    print("프로그램이 종료됩니다.")
    cleanup()

    # 로그 파일 패턴 읽기
    log_files = glob.glob("logs/app_*.log.20-*")

    if not log_files:
        # print("병합할 로그 파일이 없습니다.")
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


# 0: werkzeug, 1: waitress
select_server = 1


if __name__ == '__main__':
    # SIGINT(인터럽트 시그널, 보통 Ctrl+C 누름)에 대한 핸들러를 등록
    signal.signal(signal.SIGINT, signal_handler)

    # 'npm run dev' 실행 (백그라운드 실행)
    node_process = subprocess.Popen(["cmd", "/c", "node src/server_io.js"], cwd=NODE_SERVER_PATH, text=True)

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
