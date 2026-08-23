import os
import subprocess
import signal
import threading
import time

try:
    import win32api
    import win32con
    import win32job
    _HAS_WIN32JOB = True
except ImportError:
    _HAS_WIN32JOB = False

_active_processes = set()
_active_processes_lock = threading.Lock()

_job = None
_job_lock = threading.Lock()


def _get_job():
    """서버 프로세스 전용 Windows Job Object.
    kill_all_active_processes()는 서버가 SIGINT/SIGTERM으로 "정상 종료 절차"를 탈 때만
    호출된다 — 그런데 콘솔 창을 그냥 X로 닫거나 작업관리자로 강제 종료하면 그 절차 자체가
    안 불려서 자식(1_/2_/5_ 등)이 고아로 남는 사고가 반복됐다(2026-08-10, 서버 재시작 후에도
    069620.pkl 교체 실패가 재발). JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE를 건 Job에 자식을
    묶어두면, 이 핸들을 쥔 서버 프로세스가 '어떤 방식으로든' 죽는 순간 OS가 핸들을 정리하며
    이 Job에 속한 자식을 전부 강제 종료한다 — Python 코드 경로를 하나도 안 타도 되는,
    유일하게 100% 신뢰 가능한 방법."""
    global _job
    with _job_lock:
        if _job is None:
            _job = win32job.CreateJobObject(None, "")
            info = win32job.QueryInformationJobObject(_job, win32job.JobObjectExtendedLimitInformation)
            info['BasicLimitInformation']['LimitFlags'] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(_job, win32job.JobObjectExtendedLimitInformation, info)
        return _job


def _assign_to_job(pid):
    if not _HAS_WIN32JOB:
        return
    try:
        handle = win32api.OpenProcess(win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, pid)
        win32job.AssignProcessToJobObject(_get_job(), handle)
    except Exception as e:
        print(f"⚠️ Job Object 등록 실패(PID {pid}): {e}")


# 서브프로세스 실행 공용 헬퍼. 예전엔 아래 로직이 함수마다(12곳) 복붙되어 있었는데,
# 어디에도 등록되지 않은 채라 서버가 재시작(특히 os._exit)되면 그 시점에 실행 중이던
# 자식이 고아로 남아 무한정 실행됐다. 예: 2026-08-10 기준 7/28~8/7 사이 시작된
# 1_/2_/5_ 스크립트가 죽지 않고 계속 쌓여, 새로 스케줄된 정상 실행과 같은 pickle
# 파일에 동시에 쓰면서 "파일 교체 실패(WinError 5)"가 스케줄을 고쳐도 재발했다.
# _active_processes에 등록해두면 kill_all_active_processes()가 서버 종료 시 이걸 정리하고,
# Job Object에도 등록해 서버가 비정상 종료돼도 OS가 정리한다(이중 안전장치).
def _run_subprocess(argv, cwd=None):
    process = subprocess.Popen(
        argv,
        cwd=cwd,                               # 자식 프로세스의 현재 작업 디렉토리(working directory) 를 지정
        stdout=subprocess.PIPE,                # 주석하면 자식 프로세스의 출력이 파이프로 캡처되지 않고 기본 출력 스트림으로 흘러간다
        stderr=subprocess.STDOUT,              # stderr도 stdout으로 합치기(편함)
        text=True,                             # stdout에서 읽히는 값이 bytes가 아니라 str(문자열)로
        encoding="utf-8",                      # 부모도 UTF-8로 읽기
        errors="replace",                      # ignore 대신 replace 추천(문제 보이게)
        bufsize=1,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,  # Windows에서 종료 제어용
    )
    _assign_to_job(process.pid)

    with _active_processes_lock:
        _active_processes.add(process)

    try:
        # 출력이 안 나와도 멈춘 것처럼 보이지 않게 poll 방식, 출력이 없는 구간에서 "멈춘 것처럼 보이는 문제" 예방하려면 추천(안정성 ↑)
        while True:
            line = process.stdout.readline()
            if line:
                print(line, end="")
            elif process.poll() is not None:
                break
            else:
                time.sleep(0.05)

    except KeyboardInterrupt:  # "서버/스케줄러에서 돌리고 Ctrl+C로 끌 수 있다"면 잡는 게 맞음
        # Ctrl+C 받으면 자식도 같이 종료 시도
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
            process.wait(timeout=5)
        except Exception:
            process.kill()
            process.wait()
        raise
    finally:
        process.wait()
        with _active_processes_lock:
            _active_processes.discard(process)

    if process.returncode != 0:
        print("returncode =", process.returncode)

    return process


# 서버 종료 시(cleanup()에서 호출) 아직 살아있는 자식을 강제 종료한다.
# taskkill /T로 트리 전체를 죽여 자식의 자식(예: cmd /c 로 띈 경우)까지 정리한다.
def kill_all_active_processes():
    with _active_processes_lock:
        procs = list(_active_processes)

    for process in procs:
        if process.poll() is not None:
            continue
        try:
            print(f"🧹 자식 프로세스 강제 종료: PID {process.pid}")
            if os.name == 'nt':
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(process.pid)])
            else:
                process.kill()
                process.wait()
        except Exception as e:
            print(f"⚠️ 자식 프로세스 종료 실패: PID {process.pid} {e}")


def renew_kiwoom_token_job():
    print('    ############################### renew_kiwoom_token ###############################')
    venv_python = r"C:\my-project\random-player\venv\Scripts\python.exe"
    py_script = r"C:\my-project\random-player\auto_trading\renew_kiwoom_token.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\random-player")


def renew_kiwoom_mock_token_job():
    # 실전 토큰(위 renew_kiwoom_token_job)은 매일 07:00에 선제 갱신되는데, 모의투자 토큰은
    # 예정된 갱신이 없어서 kiwoom_api._call()의 401 재시도 로직에만 기대고 있었다(2026-08-12,
    # 실계좌 토큰 07:00:06 발급 후 모의투자 토큰이 08:00:47에 예정 없이 재발급된 것으로 확인 —
    # 이전 모의 토큰이 만료된 시점에 트레일링 30초 잡이 401을 맞고 그제서야 반응형으로 갱신됨).
    # 그 반응형 경로는 그대로 두고(장애 시 자동 복구 안전장치), 매일 아침 선제 갱신도 추가한다.
    print('    ############################### renew_kiwoom_mock_token ###############################')
    venv_python = r"C:\my-project\random-player\venv\Scripts\python.exe"
    py_script = r"C:\my-project\random-player\auto_trading\renew_kiwoom_token.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script, "--mock"], cwd=r"C:\my-project\random-player")


def run_crawl_ai_image():
    print('    ############################### run_crawl_ai_image ###############################')
    venv_python = r"C:\my-project\random-player\venv\Scripts\python.exe"
    py_script = r"C:\my-project\random-player\job\scrap\scrap_ai_by_playwright_async.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\random-player")


def run_crawl_ig_image():
    print('    ############################### run_crawl_gm_image ###############################')
    venv_python = r"C:\my-project\random-player\venv\Scripts\python.exe"
    py_script = r"C:\my-project\random-player\job\scrap\scrap_gm_playwrigit.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\random-player")


'''
cd /d C:\my-project\AutoSales.py
venv\Scripts\activate
python multi_kor_stocks.py
'''
def predict_stock_graph(stock):
    print(f'    ############################### predict_stock_graph : {stock} ###############################')
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    if stock == 'kospi':
        py_script = r"C:\my-project\AutoSales.py\job\multi_kor_stocks.py"
    if stock == 'nasdaq':
        py_script = r"C:\my-project\AutoSales.py\job\new_nasdaq_multi.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\AutoSales.py")


def update_interest_stocks():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\job\1_periodically_update_today_interest_stocks.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\AutoSales.py")


def find_stocks():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\job\2_finding_stocks_with_increased_volume.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\AutoSales.py")


# 신호 재설계 병행검증(target='interest_v2') — find_stocks(기존 2_)와 완전히 분리된 트랙.
# 기존 화면/자동매수는 target='interest'만 보므로 이 결과는 실거래에 영향을 주지 않는다.
def find_stocks_advanced():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\job\2_finding_stocks_advanced.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\AutoSales.py")


def find_low_stocks():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\job\4_find_low_point.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\AutoSales.py")


def find_low_stocks_v2():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\job\4_find_low_point_v2.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\AutoSales.py")


def find_low_stocks_us():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\job\4-1_find_low_point_us.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\AutoSales.py")


def update_stocks_daily():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    # py_script = r"C:\my-project\AutoSales.py\job\update_kor_stocks_periodically.py"   # pykrx는 더이상 종목 리스트를 가져올 수 없음
    py_script = r"C:\my-project\AutoSales.py\job\update_kor_stocks_by_xls.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\AutoSales.py")


def update_stock_data_daily():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\job\10_update_stock_data.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\AutoSales.py")


def update_summary_stock_graph_daily():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\job\5_generate_interest_stocks_graph.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\AutoSales.py")


# 전체 종목 데이터 파일(pkl)을 갱신
def fetch_stock_data():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\job\0_periodically_fetch_stock_data.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\AutoSales.py")


def generate_fullchain_pem_daily():
    print('    ############################### generate_fullchain_pem_daily ###############################')
    _run_subprocess(["cmd", "/c", r"C:\nginx\nginx-1.26.2\ssl\renew_chickchick_cert.bat"])
    _run_subprocess(["cmd", "/c", r"C:\nginx\nginx-1.26.2\ssl\make_fullchain.bat"])


def run_kiwoom_trailing_stop():
    from auto_trading.kiwoom_trailing_stop import run_cycle, is_market_open, _log
    if not is_market_open():
        return
    try:
        run_cycle()
    except Exception as e:
        _log.error(f'run_kiwoom_trailing_stop 실패: {e}')


def log_kiwoom_account_summary():
    from auto_trading.kiwoom_trailing_stop import log_account_summary, is_market_open, _log
    if not is_market_open():
        return
    try:
        log_account_summary()
    except Exception as e:
        _log.error(f'log_kiwoom_account_summary 실패: {e}')


def reconcile_kiwoom_fills():
    """당일 거래이력에 실제 체결 데이터(체결가/체결수량/수수료/세금/슬리피지)를 채워넣는다.
    ka10076이 '당일분'만 주므로 반드시 같은 날 장 마감 후에 돌려야 한다.
    is_market_open() 체크를 하지 않는다 — 조회 전용이고, 장 마감 후에 도는 것이 목적이다."""
    from auto_trading.kiwoom_trailing_stop import reconcile_fills, _log
    try:
        reconcile_fills()
    except Exception as e:
        _log.error(f'reconcile_kiwoom_fills 실패: {e}')


def run_kiwoom_fire_buy():
    from auto_trading.kiwoom_trailing_stop import is_market_open, _log
    if not is_market_open():
        return
    try:
        from auto_trading.kiwoom_fire_strategy import run_fire_buy_cycle
        run_fire_buy_cycle()
    except Exception as e:
        _log.error(f'run_kiwoom_fire_buy 실패: {e}')

# ── v8 전략 (매일 스크리닝 + 지정가 매수) ────────────────────────────────────
# 근거: C:\my-project\strategy-ab-backtest\ANALYSIS_V8.md
# ⚠️ 기존 fire(15:18 시장가 추격) / kiwoom_trailing_stop 과 **동시에 켜지 말 것**.
#    방향이 정반대이고, 둘 다 보유 종목 전체를 훑어 서로의 포지션을 청산한다.
#    각 모듈의 V8_ENABLED / V8_EXIT_ENABLED 가 False 면 아래 함수들은 즉시 반환한다.
def run_v8_screen():
    from auto_trading.kiwoom_v8_strategy import run_v8_screen as _f
    from auto_trading.kiwoom_trailing_stop import _log
    try:
        _f()
    except Exception as e:
        _log.error(f'run_v8_screen 실패: {e}')


def run_v8_buy():
    from auto_trading.kiwoom_v8_strategy import run_v8_buy_cycle as _f
    from auto_trading.kiwoom_trailing_stop import is_market_open, _log
    try:
        if is_market_open():
            _f()
    except Exception as e:
        _log.error(f'run_v8_buy 실패: {e}')


def run_v8_exit():
    from auto_trading.kiwoom_v8_exit import run_v8_exit_cycle as _f
    from auto_trading.kiwoom_trailing_stop import is_market_open, _log
    try:
        if is_market_open():
            _f()
    except Exception as e:
        _log.error(f'run_v8_exit 실패: {e}')


def run_v8_eod():
    from auto_trading.kiwoom_v8_exit import run_v8_eod as _f
    from auto_trading.kiwoom_trailing_stop import _log
    try:
        _f()
    except Exception as e:
        _log.error(f'run_v8_eod 실패: {e}')
