"""모의투자 계좌 자동매매 프로세스 (2026-08-20).

실전(run.py, v8 전략)과 **별도 프로세스**로 띄워 모의계좌에서 fire 전략을 돌린다.

    venv/Scripts/python.exe run_mock.py

━━━ 왜 별도 프로세스인가 ━━━
`KIWOOM_ENV` 를 이 파일 맨 위에서 'mock' 으로 못박고 auto_trading 모듈을 import 한다.
그 모듈들은 import 시점에 계좌번호·상태파일 경로를 모듈 상수로 굳히므로, 프로세스를 나누면
계좌번호·토큰·API 호스트·상태파일·거래이력이 전부 자동으로 분리된다. 자세한 근거는
job/batch_runner.create_mock_scheduler() docstring 참고.

⚠️ **os.environ 설정이 dotenv import 보다 먼저여야 한다.** load_dotenv 는 기본 override=False
   라서 이미 설정된 OS 환경변수를 덮지 않는다 — 그래서 여기서 먼저 박아두면 .env 의
   KIWOOM_ENV=real 을 이긴다. (2026-08-20 실측 확인)

━━━ 이 프로세스가 하지 않는 것 ━━━
Flask 서버, node 서버, pkl 갱신, 스크래핑을 띄우지 않는다. 메인 프로세스가 이미 하고 있고,
pkl 을 두 프로세스가 쓰면 잠금 사고가 난다. fire 전략은 pkl 을 읽기만 한다.

종료: Ctrl+C
"""
import os

# ★ 다른 어떤 import 보다 먼저 — auto_trading 모듈이 import 시점에 이 값을 읽는다.
os.environ['KIWOOM_ENV'] = 'mock'

import signal                                    # noqa: E402
import sys                                       # noqa: E402
import time                                      # noqa: E402

from job.batch_runner import create_mock_scheduler   # noqa: E402

_LOCK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'logs', 'kiwoom_trading', '.run_mock.lock')
_lock_fh = None


def acquire_single_instance():
    """이 프로세스가 유일한 모의 자동매매 인스턴스인지 보장. 중복이면 False.

    ★ PID 파일 방식을 쓰지 않는다. 예전에 죽은 PID 를 가리키는 유령 잠금 파일 때문에 며칠간
      작업이 막힌 사고가 있었다. 여기서는 **OS 파일 잠금**을 프로세스 수명 동안 들고 있는다 —
      프로세스가 죽으면 OS 가 잠금을 자동 해제하므로 유령 잠금이 원리적으로 생기지 않는다.

    중복 실행이 위험한 이유: 두 인스턴스가 각각 15:21 fire 잡을 돌려 **같은 종목을 두 번 매수**한다.
    """
    global _lock_fh
    os.makedirs(os.path.dirname(_LOCK_PATH), exist_ok=True)
    try:
        _lock_fh = open(_LOCK_PATH, 'a+')
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        if _lock_fh:
            _lock_fh.close()
            _lock_fh = None
        return False
    _lock_fh.seek(0)
    _lock_fh.truncate()
    _lock_fh.write(f'{os.getpid()}\n')     # 진단용 기록일 뿐, 판정에는 쓰지 않는다
    _lock_fh.flush()
    return True


def main():
    if not acquire_single_instance():
        print('[SKIP] 모의 자동매매가 이미 다른 프로세스에서 돌고 있다 — 이 인스턴스는 종료한다.\n'
              f'       (잠금: {_LOCK_PATH})')
        return 0

    from auto_trading.kiwoom_api import KIWOOM_ENV, get_account_credentials, _cfg_for
    acnt_no, _ = get_account_credentials()
    if not acnt_no:
        print('[FATAL] 모의계좌 정보가 .env에 없다 (KIWOOM_MOCK_ACNT_NO / KIWOOM_MOCK_ACNT_PWD)')
        return 1

    print('=' * 68)
    print(f' 모의투자 자동매매 프로세스')
    print(f'   KIWOOM_ENV : {KIWOOM_ENV}')
    print(f'   API host   : {_cfg_for()["base_url"]}')
    print(f'   계좌번호    : {acnt_no}')
    print(f'   전략        : fire (15:21 동시호가 시장가 매수 / 손절 -6% + 보유 15영업일, 트레일링 없음)')
    print('=' * 68)

    scheduler = create_mock_scheduler()

    stopping = {'flag': False}

    def _stop(signum, frame):
        if stopping['flag']:
            return
        stopping['flag'] = True
        print('\n종료 중...')
        try:
            scheduler.shutdown(wait=False)
        except Exception as e:
            print(f'스케줄러 종료 실패: {e}')

    signal.signal(signal.SIGINT, _stop)
    try:
        signal.signal(signal.SIGTERM, _stop)
    except (AttributeError, ValueError):
        pass  # 윈도우에서 SIGTERM 미지원인 경우

    try:
        while not stopping['flag']:
            time.sleep(1)
    except KeyboardInterrupt:
        _stop(None, None)
    print('종료 완료')
    return 0


if __name__ == '__main__':
    sys.exit(main())
