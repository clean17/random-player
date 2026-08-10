import functools
import os
import glob
import signal
import atexit
import subprocess
from collections import defaultdict
import logging
from concurrent.futures import ProcessPoolExecutor

from config.db_connect import db_pool
import job.batch_runner as batch_runner

already_cleaned = False
node_process = None

def auto_endpoint(bp_or_app):
    def route_wrapper(rule, **options):
        def decorator(f):
            endpoint = options.get('endpoint') or f.__name__.replace('_', '-')
            options['endpoint'] = endpoint
            return bp_or_app.route(rule, **options)(f)
        return decorator
    return route_wrapper

def register_shutdown_handlers(scheduler=None, node_process=None):
    def handler(sig, frame):
        cleanup(scheduler=scheduler, node_process=node_process)

        # raise SystemExit(0)은 "정상 종료 절차"를 타서, concurrent.futures가 등록해둔
        # atexit 훅(_python_exit)이 "io" ThreadPoolExecutor의 워커 스레드들을 join()하며
        # 대기한다. find_stocks/update_interest_stocks 같은 job은 subprocess가 끝날 때까지
        # (수 분) 그 스레드를 붙잡고 있어서, 마침 그 job이 도는 중에 Ctrl+C를 누르면 프로세스가
        # 안 죽는 것처럼 보였다(그래서 한 번 더 종료해야 했음). os._exit는 atexit/스레드 join을
        # 전부 건너뛰고 즉시 종료하므로 이 대기가 없다 — cleanup()이 위에서 이미 스케줄러/DB/
        # 자식 프로세스를 정리했으니 안전하다.
        os._exit(0)

    signal.signal(signal.SIGINT, handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, handler)  # docker stop / 서비스 종료

# Ctrl+C 이벤트 핸들러
def signal_handler(sig, frame):
    pid = os.getpid()
    os.kill(pid, signal.SIGTERM) # 다른 파이썬 종료시키지 않고 자신만 종료

    # os.system('taskkill /f /im python.exe')
    # sys.exit(0)

def cleanup(scheduler=None, node_process=None):
    global already_cleaned
    if already_cleaned:
        return
    already_cleaned = True

    # 1) APScheduler 먼저 정상 종료 (작업 마무리까지 기다림)
    try:
        print("🧹 서버 종료 중: 스케줄러 정리")
        if scheduler and getattr(scheduler, "running", False):
            # scheduler.shutdown(wait=True)  # wait=True면 실행 중인 job이 끝나길 기다리다가 계속 대기한다
            scheduler.shutdown(wait=False)  # wait=False면 종료를 기다리지 말고 확실히 끈다
    except Exception as e:
        print("scheduler shutdown error:", e)

    # 2) executor(스레드풀, 프로세스풀 등) 확실히 shutdown (중요)
    # (이전엔 `from job.batch_runner import executors`로 import 시점 값(None)을 캡처해서
    #  create_scheduler()가 나중에 채워도 여기선 항상 None이라 이 블록이 통째로 스킵되고 있었다.
    #  모듈 속성으로 매번 최신 값을 읽도록 수정)
    try:
        _executors = batch_runner.executors
        if _executors:
            for name, ex in _executors.items():
                print(f"🧹 executor 종료: {name} ({type(ex).__name__})")
                if isinstance(ex, ProcessPoolExecutor):
                    # ProcessPoolExecutor는 Python 3.8에서 cancel_futures 옵션이 없어 wait=True로 안전하게 종료
                    ex.shutdown(wait=True)
                else:
                    # 다른 executor는 wait=False로 빠르게 종료
                    ex.shutdown(wait=False)
    except Exception as e:
        print("executors shutdown error:", e)

    # 2-1) "io" executor가 돌리던 AutoSales.py 자식 프로세스(find_stocks/update_interest_stocks 등)
    # 강제 종료. executor.shutdown()은 이미 시작된 작업을 취소하지 못해서, 이걸 안 하면 서버가
    # 죽어도 자식은 살아남아 고아가 된 채 계속 pickle 파일을 건드린다 — 이게 스케줄을 고쳐도
    # "파일 교체 실패"가 재발한 실제 원인이었다.
    try:
        print("🧹 서버 종료 중: AutoSales.py 자식 프로세스 정리")
        from job.batch_process import kill_all_active_processes
        kill_all_active_processes()
    except Exception as e:
        print("batch process cleanup error:", e)

    # 3) DB 커넥션 풀 종료
    try:
        print("🧹 서버 종료 중: db_pool 정리")
        if db_pool:
            db_pool.close()
    except Exception as e:
        print("db_pool close error:", e)

    # 4) node_process
    if node_process is not None and node_process.poll() is None:
        try:
            print("🧹 서버 종료 중: 자식 프로세스 정리")
            if os.name == 'nt':
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(node_process.pid)])
            else:
                node_process.terminate()
        except Exception as e:
            print(f"⚠️ 종료 중 예외: {e}")

    # print("⚠️ 강제 종료 진행 (남은 스레드로 인해 종료 지연)")
    # os._exit(0)


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

# atexit.register(on_exit) #  프로그램이 정상적으로 종료될 때 호출될 함수를 등록, 정상: main 종료, ctrl+c는 동작안함


def open_folder(path):
    # 윈도우 탐색기로 해당 경로 열기
    os.startfile(path)