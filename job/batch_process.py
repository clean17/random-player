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


# ─────────────────────────────────────────────────────────────────────────────
# 서버 기동 시 1회 호출. 이전 세대가 남긴 고아 multiprocessing 워커를 정리한다.
#
# 왜 필요한가 —
#   AutoSales.py 쪽 배치(4_find_low_point_v2.py:600, 5_generate_interest_stocks_graph.py:213)는
#   ProcessPoolExecutor로 워커를 8~10개 띄운다. 서버가 정상 종료 절차를 못 타면
#   (예: Ctrl+Break — utils.common.register_shutdown_handlers 참고, 콘솔 X, 작업관리자 강제 종료)
#   kill_all_active_processes()가 안 불리고, 이때 Job Object 안전장치도 이 워커들까진 못 막는다.
#   venv\Scripts\python.exe 가 Store 파이썬을 자식으로 다시 띄우는 구조라, Job에 등록되는 건
#   스텁뿐이고 실제 인터프리터와 그 워커는 Job 밖이기 때문이다.
#   (2026-08-30 실측: IsProcessInJob(실제 인터프리터, 우리Job) = False)
#
#   게다가 이 워커들은 스스로 죽지도 않는다. 원래 부모가 죽으면 작업 큐 파이프에서 EOF를 받고
#   종료해야 하는데, 워커끼리 그 파이프의 쓰기 핸들을 서로 상속받고 있어서 하나라도 살아있는 한
#   아무도 EOF를 보지 못한다. 실제로 5일간 23개가 쌓여 CPU를 105분 갉아먹었다.
#
# 판정 근거 —
#   Windows는 부모가 죽어도 자식을 재부모화하지 않는다(Unix의 init 인계가 없다).
#   ParentProcessId 필드는 죽은 PID를 그대로 가리키는 허상이 되고, 그 PID는 나중에 다른
#   프로세스에 재사용될 수 있다. 그래서 OS의 PPID를 믿지 않고,
#     (1) 명령줄에 multiprocessing이 직접 박아둔 parent_pid=NNNN 를 1차 근거로 삼고
#     (2) 그 PID가 없거나, 살아있어도 워커보다 나중에 생성됐으면(=PID 재사용) 고아로 본다
#     (3) 우리 프로젝트 venv 로 실행된 것만 대상으로 한다 (남의 프로세스를 죽이지 않기 위해)
#     (4) min_age_sec 보다 어린 워커는 건너뛴다 (지금 막 뜨는 정상 풀과의 경합 방지)
# ─────────────────────────────────────────────────────────────────────────────
_MP_WORKER_VENVS = (
    r"c:\my-project\autosales.py\venv",
    r"c:\my-project\random-player\venv",
)


def sweep_orphan_mp_workers(min_age_sec=120, dry_run=False):
    try:
        import psutil
    except ImportError:
        print("⚠️ psutil 없음 — 고아 워커 청소를 건너뛴다")
        return []

    import re
    now = time.time()
    killed = []

    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            info = proc.info
            if not (info['name'] or '').lower().startswith('python'):
                continue

            cmdline = ' '.join(info['cmdline'] or ())
            # multiprocessing spawn 워커만
            if 'spawn_main' not in cmdline or '--multiprocessing-fork' not in cmdline:
                continue
            # 우리 프로젝트 venv 로 뜬 것만
            if not any(v in cmdline.lower() for v in _MP_WORKER_VENVS):
                continue
            # 갓 뜬 워커는 건드리지 않는다
            age = now - info['create_time']
            if age < min_age_sec:
                continue

            m = re.search(r'parent_pid=(\d+)', cmdline)
            if not m:
                continue
            parent_pid = int(m.group(1))

            # 부모가 살아있고, 워커보다 먼저 생성됐다면 정상 — 건너뛴다.
            # (부모가 워커보다 나중에 생성됐다면 PID가 재사용된 것이므로 고아로 본다)
            try:
                parent = psutil.Process(parent_pid)
                if parent.create_time() <= info['create_time']:
                    continue
                reason = f"부모 PID {parent_pid} 는 PID 재사용된 다른 프로세스"
            except psutil.NoSuchProcess:
                reason = f"부모 PID {parent_pid} 없음"

            hours = age / 3600
            if dry_run:
                print(f"   [DRY-RUN] 고아 워커 PID {info['pid']} ({hours:.1f}시간 방치) — {reason}")
            else:
                print(f"🧹 고아 워커 정리: PID {info['pid']} ({hours:.1f}시간 방치) — {reason}")
                proc.kill()
            killed.append(info['pid'])

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception as e:
            print(f"⚠️ 고아 워커 검사 중 예외 (PID {info.get('pid')}): {e}")

    if killed:
        verb = "발견" if dry_run else "정리"
        print(f"🧹 고아 multiprocessing 워커 {len(killed)}개 {verb}")
    return killed


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


# 전 종목 공용 LightGBM 예측(job/train_global_lgbm.py로 미리 학습된 모델) — 위 predict_stock_graph
# (구버전 multi_kor_stocks.py/new_nasdaq_multi.py)와는 별개 트랙. 결과는 F:\lgbm_stocks\<YYYYMMDD>\
# <kr|us>\ 에 저장되고 /image/lgbm-stocks/<kr|us> 로 조회한다(app/image.py 참고).
def predict_kr_stocks_lgbm():
    print('    ############################### predict_kr_stocks_lgbm ###############################')
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\job\multi_kor_stocks_lgbm.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\AutoSales.py")


def predict_us_stocks_lgbm():
    print('    ############################### predict_us_stocks_lgbm ###############################')
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\job\multi_us_stocks_lgbm.py"
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

def fetch_us_stock_data():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\job\0-1_periodically_fetch_stock_data_us.py"
    _run_subprocess([venv_python, "-u", "-X", "utf8", py_script], cwd=r"C:\my-project\AutoSales.py")



def generate_fullchain_pem_daily():
    print('    ############################### generate_fullchain_pem_daily ###############################')
    _run_subprocess(["cmd", "/c", r"C:\nginx\nginx-1.26.2\ssl\renew_chickchick_cert.bat"])
    _run_subprocess(["cmd", "/c", r"C:\nginx\nginx-1.26.2\ssl\make_fullchain.bat"])


def run_kiwoom_trailing_stop():
    # is_market_open()이 아니라 전용 게이트(15:19 종료) — fire 자동매수(15:19 시작)와
    # is_market_open()을 공유하면 fire가 트리거되는 순간 이미 막혀버린다.
    from auto_trading.kiwoom_trailing_stop import run_cycle, is_trailing_window_open, _log
    if not is_trailing_window_open():
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
    # is_market_open()이 아니라 동시호가 전용 게이트(15:20~15:30) — 2026-08-25부터
    # 연속거래 시장가(15:18/19) 대신 동시호가 시장가로 바꿔 '종가 매수'가 되게 한다.
    from auto_trading.kiwoom_trailing_stop import is_closing_auction_open, _log
    if not is_closing_auction_open():
        return
    try:
        from auto_trading.kiwoom_fire_strategy_mock import run_fire_buy_cycle
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
