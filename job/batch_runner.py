import os
import datetime
from config.config import settings
# import sched ++ 서버/운영용보다는 테스트·학습용
from apscheduler.schedulers.background import BackgroundScheduler
from concurrent.futures import ThreadPoolExecutor
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from job.batch_process import predict_stock_graph, find_stocks, find_stocks_advanced, find_low_stocks, \
    update_interest_stocks, \
    renew_kiwoom_token_job, renew_kiwoom_mock_token_job, run_crawl_ai_image, update_stocks_daily, run_crawl_ig_image, update_stock_data_daily, \
    update_summary_stock_graph_daily, find_low_stocks_us, generate_fullchain_pem_daily, fetch_stock_data, \
    find_low_stocks_v2, run_kiwoom_trailing_stop, log_kiwoom_account_summary, run_kiwoom_fire_buy, \
    reconcile_kiwoom_fills, \
    run_v8_screen, run_v8_buy, run_v8_exit, run_v8_eod
from job.buy_lotto import async_buy_lotto
# utils패키지의 모듈을 임포트
from job.compress_file import compress_directory_to_zip
from job.renew_stock_close import renew_interest_stocks_close, verify_low_stock_data, update_product_code
# sched 기본 스케줄러, 블로킹
# scheduler = sched.scheduler(time.time, time.sleep)

# 스케줄러 인스턴스 생성 (논블로킹)
# BackgroundScheduler: 백그라운드(별도 스레드)에서 스케줄러 루프를 돌리는 스케줄러
# 웹 서버(메인 흐름) + 스케줄러(백그라운드 스레드)를 한 프로세스 안에서 같이 돌리고 싶을 때 사용\
# FastAPI로 변경하면 AsyncIOScheduler 사용
# scheduler = BackgroundScheduler()


work_directory = settings['WORK_DIRECTORY']
TEMP_IMAGE_DIR = settings['TEMP_IMAGE_DIR']
TRIP_IMAGE_DIR = settings['TRIP_IMAGE_DIR']
DIRECTORIES_TO_COMPRESS = [TEMP_IMAGE_DIR, TRIP_IMAGE_DIR]


scheduler = None
executors = None




def should_predict(market):
    today = datetime.datetime.today().weekday()
    print(f'    ############################### should_predict : {today}, {market} ###############################')
    if market == 'kospi':
        # return today not in (4, 5)    # 금, 토 제외
        return today not in (5, 6)    # 토, 일 제외
    elif market == 'nasdaq':
        return today not in (5, 6)    # 토, 일 제외
    return False


def predict_stock_graph_scheduled(market):
    if should_predict(market):
        predict_stock_graph(market)


def run_weekdays_only(task, *args, **kwargs):
    # 0=월, 1=화, ..., 6=일
    if datetime.datetime.today().weekday() < 5:  # 월(0) ~ 금(4)만 실행
        task(*args, **kwargs)


def run_cumtom_time_only(task):
    # 0=월, 1=화, ..., 6=일
    if datetime.datetime.today().weekday() < 5:  # 월(0) ~ 금(4)만 실행
        now = datetime.datetime.today().time()
        start = datetime.time(9, 20)
        end = datetime.time(20, 0)

        if start <= now <= end:
            task()


def initialize_directories():
    for directory in DIRECTORIES_TO_COMPRESS:
        os.makedirs(directory, exist_ok=True)

'''
# 매시 정각마다 실행하는 함수
def periodic_compression_task():
    try:
        while True:
            now = datetime.datetime.now()
            next_hour = (now + datetime.timedelta(hours=6)).replace(minute=0, second=0, microsecond=0)
            sleep_duration = (next_hour - now).total_seconds()
            # sleep_duration = 60 # 1분 테스트
            time.sleep(sleep_duration)
            compress_directory_to_zip()
    except KeyboardInterrupt:
        print("압축 작업 중단됨")

def run_async_function(coroutine):
    """ APScheduler(스레드) job에서 코루틴을 루프에 안전하게 던짐 """
    if _loop is None:
        raise RuntimeError("Async loop not started. Call start_async_loop_in_background() first.")

    # loop = asyncio.get_event_loop()
    asyncio.run_coroutine_threadsafe(coroutine, _loop)
    # print("압축 작업 중단됨")
            
async def run_schedule():
    schedule.every().saturday.at("08:00").do(lambda: run_async_function(async_buy_lotto()))
    # schedule.every().day.at("06:00").do(run_crawl_ai_image)
    schedule.every().day.at("07:00").do(renew_kiwoom_token_job)
    schedule.every().day.at("20:00").do(predict_stock_graph_scheduled, 'kospi')
    schedule.every().day.at("07:00").do(predict_stock_graph_scheduled, 'nasdaq')

    # 국장 시작
    schedule.every().day.at("09:05").do(run_weekdays_only, find_stocks)

    # 10시부터 15시까지 1시간마다 실행
    for h in range(10, 16):  # 10 ~ 15
        schedule.every().day.at(f"{h:02d}:00").do(run_weekdays_only, find_stocks)

    # 9:30부터 15:30시까지 1시간마다 실행
    for h in range(9, 16):  # 9 ~ 15
        schedule.every().day.at(f"{h:02d}:30").do(run_weekdays_only, find_stocks)
        schedule.every().day.at(f"{h:02d}:45").do(run_weekdays_only, find_low_stocks)
        # schedule.every().day.at(f"{h:02d}:30").do(run_weekdays_only, renew_interest_stocks_close)

    # 월~금, 5분마다 실행
    schedule.every(5).minutes.do(run_cumtom_time_only, update_interest_stocks)

    while True:
        # print("[Scheduler] 현재시간:", datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        schedule.run_pending()
        await asyncio.sleep(60)  # 1분마다 체크

def start_lotto_scheduler():
    """멀티프로세싱 환경에서 비동기 스케줄러 실행"""
    # loop = asyncio.get_event_loop()
    # RuntimeError: There is no current event loop in thread 에러 발생
    # 즉, asyncio는 기본적으로 메인 스레드에서만 event loop를 자동으로 만들어줌
    # 서브 스레드에서는 직접 만들어야 한다

    loop = asyncio.new_event_loop()  # 새로운 이벤트 루프 생성
    asyncio.set_event_loop(loop)  # 이벤트 루프 설정
    try:
        loop.run_until_complete(run_schedule())  # 비동기 코드 실행
    except KeyboardInterrupt:
        print("스케줄러 종료됨")


# 주기적 작업을 위한 프로세스 시작 (두 개의 별도 프로세스를 데몬으로 실행, 앱이 또 생성됨)
# asyncio 또는 threading.Thread를 사용하면, Waitress 앱 하나 안에서 주기작업, 스케줄러 등을 백그라운드에서 실행 가능
# 압축, 스케줄러, 로그 체크 같은 작업이 I/O 중심이면 → threading 또는 asyncio로 충분
# 진짜 병렬 CPU 계산이라면 → multiprocessing
def start_periodic_task(): # 주석 처리됨, 사용하지 않는중
    processes = []
    process = multiprocessing.Process(target=periodic_compression_task)
    process.daemon = True
    process.start()
    processes.append(process)

    process2 = multiprocessing.Process(target=start_lotto_scheduler)
    process2.daemon = True
    process2.start()
    processes.append(process2)

    return processes

# threading
def start_background_tasks():
    threading.Thread(target=periodic_compression_task, daemon=True).start()
    threading.Thread(target=start_lotto_scheduler, daemon=True).start()
'''

def debug_scheduler():
    print("Scheduler running.... ")


def create_mock_scheduler():
    """모의투자 계좌 전용 스케줄러 (2026-08-20).

    ━━━ 왜 별도 프로세스인가 ━━━
    `kiwoom_fire_strategy` / `kiwoom_trailing_stop` 은 **import 시점에** 계좌번호와 상태파일
    경로를 모듈 상수로 굳힌다(`ACNT_NO`, `STATE_FILE`, `FIRE_STATE_FILE` ...).
    한 프로세스에서 실전(v8)과 모의(fire)를 같이 돌리려면 그 모듈 상수를 환경별 인스턴스로
    쪼개야 하는데, 그건 지금 실계좌가 붙어 있는 코드를 통째로 건드리는 일이다.
    별도 프로세스로 띄우면 `KIWOOM_ENV=mock` 하나로 전부 자동 분리된다 —
    계좌번호·토큰·API 호스트·상태파일(`*_mock.json`)·거래이력(`trades_mock.jsonl`) 모두.

    레이트리밋도 별도 프로세스가 유리하다. `_RATE_LIMIT_SLEEP` 은 프로세스 전역이고 키움 한도는
    계좌·토큰당이므로, 다른 계좌를 별 프로세스로 붙이면 실전 쪽 예산을 잠식하지 않는다.

    ━━━ 여기에 등록하지 않는 것 (중요) ━━━
    pkl 갱신·스크래핑·로또·Flask·node 는 **절대 넣지 않는다.** 메인 프로세스가 이미 돌리고 있고,
    두 프로세스가 같은 pkl 을 쓰면 잠금 사고가 난다(과거 WinError5 pickle 잠금이 죽은 PID
    유령 참조로 며칠 지속된 전례). fire 전략은 pkl 을 **읽기만** 하므로 안전하다.
    v8 잡도 넣지 않는다 — 모의는 '예전 방식(fire)' 으로 돌리는 것이 목적이다.

    ⚠️ `market_breadth_cache.json` 은 계좌와 무관한 시장지표라 env 분리가 안 돼 있다.
       두 프로세스가 같은 파일을 쓸 수 있는데, 하루 1회 쓰기이고 값이 같아 실害는 없다.
       (BREADTH_MIN=0.0 으로 게이트가 꺼져 있어 매수 판단에도 쓰이지 않는다.)
    """
    global scheduler, executors
    from auto_trading.kiwoom_api import KIWOOM_ENV
    if KIWOOM_ENV != 'mock':
        raise RuntimeError(
            f'create_mock_scheduler()는 KIWOOM_ENV=mock 에서만 실행해야 한다 (현재 {KIWOOM_ENV!r}). '
            'run_mock.py 로 띄우거나 프로세스 환경변수에 KIWOOM_ENV=mock 을 주고 실행할 것.')
    print('🕒 Mock scheduler start.... (KIWOOM_ENV=mock, fire 전략)')

    executors = {"io": ThreadPoolExecutor(max_workers=4)}
    scheduler = BackgroundScheduler(
        timezone="Asia/Seoul",
        executors=executors,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
    )

    # 모의 토큰 갱신 — 이 프로세스의 os.environ 에 반영되어야 하므로 자기 프로세스에서 돌린다.
    # (메인 프로세스가 갱신해 .env 에 써도 이 프로세스의 메모리에는 반영되지 않는다.
    #  401 자동 재발급 경로가 있어 없어도 동작하지만, 장 시작 전에 미리 받아둔다.)
    scheduler.add_job(
        renew_kiwoom_mock_token_job,
        trigger=CronTrigger(hour=6, minute=55),
        id="mock_renew_token", executor="io", replace_existing=True,
    )

    # fire 자동매수 — 평일 15:21 1회 (2026-08-25: 연속거래 시장가(15:18→15:19) 대신
    # 동시호가(15:20~15:30) 시장가로 전환, 사용자 요청).
    # 계기: 15:18/19에 연속거래 시장가로 사면 그 순간 현재가에 체결되는데, 백테스트는
    # '신호일 종가'를 매수가로 가정한다(kiwoom_fire_strategy.py 헤더 참고). 실측으로
    # 15:18 매수 후 종가까지 평균 -0.9% 추가 하락이 관측됐다 — 체결가 자체가 백테스트
    # 가정과 어긋나고 있었다는 뜻. 동시호가에 시장가로 들어가면 KRX가 15:30에 정하는
    # 균형가격(=그날 종가) 그대로 체결되어 이 갭이 없어진다(auto_trading/kiwoom_trailing_stop.py
    # is_closing_auction_open() 참고 — is_market_open()과 별개 게이트를 쓴다).
    # 15:21로 잡은 이유: 동시호가는 구간 내 아무 때 들어가도 체결가가 같으므로 정각(15:20:00)
    # 직후를 피해 스케줄러 지터에 여유를 주고, 15:30 마감까지 ~9분을 남겨 스크리닝+매수
    # 루프(2026-08-24 실측 28초)가 429 재시도로 늘어져도 넉넉하다.
    scheduler.add_job(
        run_kiwoom_fire_buy,
        trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=21),
        id="mock_fire_buy", executor="io", replace_existing=True,
    )

    # fire 청산 (손절 -6% / 보유 5영업일) — 30초. v8 소유권 집합이 모의에서는 비어 있으므로
    # 모의 보유 종목 전부를 이 잡이 담당한다.
    scheduler.add_job(
        run_kiwoom_trailing_stop,
        trigger=IntervalTrigger(seconds=30),
        id="mock_trailing_stop", executor="io", replace_existing=True,
    )

    # 계좌 현황 로그 (10분) / 체결 정산 (20:10)
    scheduler.add_job(
        log_kiwoom_account_summary,
        trigger=IntervalTrigger(minutes=10),
        id="mock_account_summary", executor="io", replace_existing=True,
    )
    scheduler.add_job(
        reconcile_kiwoom_fills,
        trigger=CronTrigger(day_of_week="mon-fri", hour=20, minute=10),
        id="mock_reconcile_fills", executor="io", replace_existing=True,
    )

    scheduler.start()
    for j in scheduler.get_jobs():
        print(f'  · {j.id:<22}{j.trigger}')
    return scheduler


def create_scheduler():
    global scheduler, executors
    print("🕒 Scheduler start.... ")

    # I/O는 스레드, CPU는 프로세스
    executors = {
        "io": ThreadPoolExecutor(max_workers=8),
        "cpu": ProcessPoolExecutor(max_workers=2),  # CPU 작업 성격/서버 코어에 맞게 조절
    }
    job_defaults = {
        "coalesce": True,          # 밀린 작업 1개로 합치기
        "max_instances": 1,        # 같은 job 중복 실행 방지
        "misfire_grace_time": 300  # 5분 정도 늦어도 실행 허용
    }

    scheduler = BackgroundScheduler(
        timezone="Asia/Seoul",
        executors=executors,
        job_defaults=job_defaults
    )


    # 0) 스케줄러 동작 확인용 (1시간 간격)
    scheduler.add_job(
        debug_scheduler,
        # trigger=IntervalTrigger(minutes=5),
        trigger=IntervalTrigger(hours=1),
        id="debug_scheduler",
        executor="io",
        replace_existing=True
    )

    # 1-1) 로또 주 1회
    # scheduler.add_job(
    #     async_buy_lotto,
    #     trigger=CronTrigger(day_of_week="sat", hour=8, minute=0),
    #     id="lotto_weekly",
    #     executor="io",
    #     replace_existing=True
    # )

    # 1-2) 매 6시간마다 압축
    scheduler.add_job(
        compress_directory_to_zip,
        trigger=IntervalTrigger(hours=6),
        id="compression_6_hourly",
        executor="io",
        replace_existing=True
    )

    # 1-3) 매일 02:00 스크랩
    scheduler.add_job(
        run_crawl_ig_image,
        trigger=CronTrigger(hour=2, minute=0),
        id="scrap_ig_daily",
        executor="io",
        replace_existing=True,
    )

    # 1-4) 매일 04:00 스크랩
    scheduler.add_job(
        run_crawl_ai_image,
        trigger=CronTrigger(hour=4, minute=0),
        id="scrap_ai_daily",
        executor="io",
        replace_existing=True,
    )

    ####################################################################

    # 2) 매일 07:00 키움 토큰 갱신 (실전)
    scheduler.add_job(
        renew_kiwoom_token_job,
        trigger=CronTrigger(hour=7, minute=0),
        # trigger=CronTrigger(second="*/15"),   # 15초 마다
        id="renew_token_daily",
        executor="io",
        replace_existing=True
    )

    # 2-0-0-1) 매일 06:55 키움 토큰 갱신 (모의투자) — 실전 잡과 겹치지 않도록 5분 앞에 배치.
    #          모의투자 토큰은 예정된 갱신이 없어 kiwoom_api._call()의 401 재시도로만 반응형
    #          갱신되고 있었다(2026-08-12 확인). 그 반응형 경로는 그대로 두고 선제 갱신을 더한다.
    scheduler.add_job(
        renew_kiwoom_mock_token_job,
        trigger=CronTrigger(hour=6, minute=55),
        id="renew_mock_token_daily",
        executor="io",
        replace_existing=True
    )

    # 2-0) 키움 트레일링 스탑 (장중 30초마다, 내부에서 장시간 아니면 즉시 리턴)
    #      실전 전환 전 반드시 KIWOOM_ENV=mock으로 먼저 검증할 것 (auto_trading/kiwoom_trailing_stop.py 상단 주석 참고)
    scheduler.add_job(
        run_kiwoom_trailing_stop,
        trigger=IntervalTrigger(seconds=30),
        id="kiwoom_trailing_stop_30s",
        executor="io",
        replace_existing=True,
    )

    # 2-0-0) 체결 정산 — 거래이력에 실제 체결가/체결수량/수수료/세금/슬리피지를 채워넣는다.
    #        ka10076이 '당일분'만 주므로 같은 날 안에 돌려야 한다. NXT 애프터마켓(20:00) 종료 후
    #        20:10에 한 번 돌려 그날 모든 체결을 잡는다. 조회 전용이라 장 시간 체크를 하지 않는다.
    #        이미 정산된 건은 건너뛰므로 여러 번 돌아도 안전하다(idempotent).
    scheduler.add_job(
        reconcile_kiwoom_fills,
        trigger=CronTrigger(day_of_week="mon-fri", hour=20, minute=10),
        id="kiwoom_reconcile_fills",
        executor="io",
        replace_existing=True,
    )

    # 2-0-1) 키움 계좌 총자산 현황 로그 (장중 10분마다)
    scheduler.add_job(
        log_kiwoom_account_summary,
        trigger=IntervalTrigger(minutes=10),
        id="kiwoom_account_summary_10m",
        executor="io",
        replace_existing=True,
    )

    # 2-0-2) fire 자동매수 (H2 필터 + 시장폭 레짐) — 장 마감 직전 1회만 실행.
    #        근거: 백테스트(fire_backtest_result.csv)가 '신호일 종가 매수' 가정이고, H2 필터 자체가
    #        일봉 지표(20일 신고가 대비/당일 등락률)라 장중에 평가하면 아직 절반만 만들어진 일봉으로
    #        판단하게 된다. pkl 정규장 마지막 갱신이 15:10이라 그 이후 평가.
    #        예전엔 :15/:35/:55로 하루 21번 돌아 (1) 아침 급등 추격분이 하루 매수 한도를 먼저
    #        소진했고(실매수 5건 전부 09:35~10:55), (2) 15:35/15:55는 NXT 시간대인데 buy_market의
    #        기본 거래소가 KRX라 세션 불일치 주문이 나갈 수 있었다.
    #        2026-08-25: mock과 동일하게 15:20~15:30 동시호가 시장가 매수로 전환(mock_fire_buy
    #        주석 참고 — 연속거래 시장가는 체결가가 '그 순간 현재가'라 백테스트의 '종가 매수'
    #        가정과 어긋난다. 실측 -0.9% 갭). 되살릴 때는 is_closing_auction_open() 게이트와
    #        15:21 트리거를 그대로 맞출 것 — is_market_open()/15:18을 쓰면 이 갭이 재발한다.
    # ⚠️ 2026-08-19 v8 전환으로 중단. fire 는 '당일 급등 추격(시장가)'이고 v8 은 '급락 대기(지정가)'라
    #    방향이 정반대이고, 같은 예수금을 두고 경쟁한다(v8 은 미체결 지정가로 예수금을 묶는다).
    #    되돌리려면 아래 주석을 풀고 kiwoom_v8_strategy.V8_ENABLED = False 로 바꾼 뒤 재시작.
    # scheduler.add_job(
    #     run_kiwoom_fire_buy,
    #     trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=21),
    #     id="kiwoom_fire_buy",
    #     executor="io",
    #     replace_existing=True,
    # )

    # ── 2-0-3) v8 전략 (매일 스크리닝 + 지정가 매수) ─────────────────────────
    # 근거: C:\my-project\strategy-ab-backtest\ANALYSIS_V8.md
    # 2026-08-19 가동 시작. 상세는 auto_trading/V8_SWITCHOVER.md
    #
    #   청산 소유권 분리 — 두 청산 모듈이 동시에 돌지만 담당 종목이 겹치지 않는다.
    #     · v8 이 매수 주문을 낸 종목  -> kiwoom_v8_exit  (ATR 샹들리에/트레일링 절반/익절/10일)
    #     · 그 외 기존 보유 종목        -> kiwoom_trailing_stop (손절 -6% / 보유 5일)
    #     기준은 kiwoom_v8_strategy.v8_owned_codes() = pending 파일의 ordered 원장.
    #
    #   되돌리기: kiwoom_v8_strategy.V8_ENABLED=False, kiwoom_v8_exit.V8_EXIT_ENABLED=False,
    #            위 kiwoom_fire_buy 주석 해제, 프로세스 재시작.
    #            (또는 backup/auto_trading_20260819_101232/ 를 덮어쓰기)
    # ⚠️ pkl 갱신(minutely_20_fetch_stock_data)은 09-15시의 :10/:30/:50 에 돈다.
    #    v8 지정가 = 당일 '종가' x 0.70 이므로 확정 종가가 들어온 뒤에 스크리닝해야 한다.
    #    KRX 정규장 15:20 종료 + 종가단일가 15:20~15:30 -> 15:50 갱신분이 첫 확정 종가다.
    #    15:45 에 돌리면 15:30 갱신분(종가단일가 진행중 값)으로 지정가가 정해진다.
    scheduler.add_job(
        run_v8_screen,
        trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=55),
        id="v8_screen", executor="io", replace_existing=True,
    )
    scheduler.add_job(
        run_v8_buy,
        trigger=IntervalTrigger(seconds=60),
        id="v8_buy", executor="io", replace_existing=True,
    )
    scheduler.add_job(
        run_v8_exit,
        trigger=IntervalTrigger(seconds=30),
        id="v8_exit", executor="io", replace_existing=True,
    )
    # peak 갱신도 당일 확정 고가가 필요하므로 15:50 갱신분 뒤에 둔다(스크리닝보다 먼저).
    scheduler.add_job(
        run_v8_eod,
        trigger=CronTrigger(day_of_week="mon-fri", hour=15, minute=52),
        id="v8_eod", executor="io", replace_existing=True,
    )

    # 2-1) 데이터 파일 (pkl) 전체 갱신 (월~금 새벽 2시 전체 종목 데이터 fetch)
    scheduler.add_job(
        update_stock_data_daily,
        trigger=CronTrigger(day_of_week="mon-fri", hour=2, minute=0),
        id="update_stock_data_daily",
        executor="io",
        replace_existing=True,
    )

    # 2-2) 월요일 09:01 국장 종목 '신규상장/상장폐지' 갱신 (vpn으로 엑셀 다운 받고 stocks 테이블 merge)
    scheduler.add_job(
        update_stocks_daily,
        trigger=CronTrigger(day_of_week="mon", hour=9, minute=1),
        id="renewal_stocks_weekly",
        executor="io",
        replace_existing=True,
    )

    # 2-3) 데이터 파일 (pkl) 전체 갱신 >>> 관심종목, 저점 계산에 사용 - 20분 간격
    scheduler.add_job(
        fetch_stock_data,
        trigger=CronTrigger(day_of_week="mon-fri", hour="09-15", minute="10,30,50"),
        id="minutely_20_fetch_stock_data",
        executor="io",
        replace_existing=True,
    )

    # 2-4) 매일 토스증권 product_code 갱신
    scheduler.add_job(
        update_product_code,
        trigger=CronTrigger(day_of_week="mon-fri", hour=6, minute=0),
        id="update_product_code",
        executor="io",
        replace_existing=True,
    )


    # 4) 매일 07:00 나스닥 예측 (CPU 3시간)
    # scheduler.add_job(
    #     predict_stock_graph_scheduled,
    #     trigger=CronTrigger(hour=7, minute=0),
    #     id="predict_nasdaq_0700",
    #     executor="cpu",
    #     replace_existing=True,
    #     args=["nasdaq"],
    # )

    # 5) 매일 20:00 코스피 예측 (CPU 3시간)
    # scheduler.add_job(
    #     predict_stock_graph_scheduled,
    #     trigger=CronTrigger(hour=20, minute=0),
    #     id="predict_kospi_2000",
    #     executor="cpu",
    #     replace_existing=True,
    #     args=["kospi"],
    # )

    # 3) 국장 시작 - 2_finding_stocks_with_increased_volume.py (09:03, 09:20~20:00, 20분마다)
    scheduler.add_job(
        find_stocks,
        trigger=CronTrigger(day_of_week="mon-fri", hour=9, minute=3),
        id="korea_open_0905_find_stocks",
        executor="io",
        replace_existing=True,
    )
    scheduler.add_job(
        find_stocks,
        trigger=CronTrigger(day_of_week="mon-fri", hour=9, minute="20,40"),
        id="0930_find_stocks",
        executor="io",
        replace_existing=True,
    )
    scheduler.add_job(
        find_stocks,
        trigger=CronTrigger(day_of_week="mon-fri", hour="10-19", minute="0,20,40"),
        id="every_30min_1000_1530_find_stocks",
        executor="io",
        replace_existing=True,
    )
    scheduler.add_job(
        find_stocks,
        trigger=CronTrigger(day_of_week="mon-fri", hour=20, minute=15),
        id="2000_find_stocks",
        executor="io",
        replace_existing=True,
    )

    # 3-0) 신호 재설계 병행검증(target='interest_v2') — find_stocks와 완전히 같은 빈도로,
    # 분만 +4 오프셋(다른 쓰기/읽기 스케줄 어디에도 안 걸리는 자리). safe_replace_pickle에 걸린
    # 상호배제 락 덕에 겹쳐도 데이터는 안전하지만, 굳이 겹쳐서 서로 대기시킬 필요는 없어 분리했다.
    scheduler.add_job(
        find_stocks_advanced,
        trigger=CronTrigger(day_of_week="mon-fri", hour=9, minute=4),
        id="korea_open_0904_find_stocks_advanced",
        executor="io",
        replace_existing=True,
    )
    scheduler.add_job(
        find_stocks_advanced,
        trigger=CronTrigger(day_of_week="mon-fri", hour=9, minute="24,44"),
        id="0930_find_stocks_advanced",
        executor="io",
        replace_existing=True,
    )
    scheduler.add_job(
        find_stocks_advanced,
        trigger=CronTrigger(day_of_week="mon-fri", hour="10-19", minute="4,24,44"),
        id="every_30min_1000_1530_find_stocks_advanced",
        executor="io",
        replace_existing=True,
    )
    scheduler.add_job(
        find_stocks_advanced,
        trigger=CronTrigger(day_of_week="mon-fri", hour=20, minute=19),
        id="2000_find_stocks_advanced",
        executor="io",
        replace_existing=True,
    )

    # 3-1) 월~금 5분마다 오늘 급상승 종목 데이터 파일 갱신  (update_interest_stocks)
    # 분 오프셋을 2로 둔 이유: find_stocks(0,20,40분)·find_low_stocks(5,15,25,35,45,55분)와
    # 같은 pickle 파일에 동시에 safe_replace_pickle()을 시도해 "액세스가 거부되었습니다"
    # (WinError 5) 재시도 실패가 반복됐다. "*/5"(0,5,10,...,55)는 두 스케줄과 전부 겹쳤어서
    # 아무 데도 안 걸리는 2,7,12,...,57 그리드로 옮겼다.
    scheduler.add_job(
        run_cumtom_time_only,
        trigger=CronTrigger(day_of_week="mon-fri", hour="9-20", minute="2-59/5"),
        id="weekday_every_5min_update_interest_stocks",
        executor="io",
        replace_existing=True,
        args=[update_interest_stocks],
    )

    # 3-2) 09:30 ~ 20:30, 30분마다 최근 관심 종목 (국장) 종가를 수정 (stocks 테이블 only)
    scheduler.add_job(
        renew_interest_stocks_close,
        trigger=CronTrigger(day_of_week="mon-fri", hour="9-20", minute="0,30"),
        id="renew_interest_close",
        executor="io",
        replace_existing=True
    )


    # 4) 저점 매수 찾기 >> 10:05 - 19:55 (매 시각의 5분부터 59분까지, 10분 간격으로 실행)
    scheduler.add_job(
        find_low_stocks,
        trigger=CronTrigger(day_of_week="mon-fri", hour="10-19", minute="5-59/10"),
        id="hourly_1505_find_low_stocks",
        executor="io",
        replace_existing=True,
    )
    scheduler.add_job(
        find_low_stocks_v2,
        trigger=CronTrigger(day_of_week="mon-fri", hour="10-19", minute="6-59/10"),
        id="hourly_1505_find_low_stocks_v2",
        executor="io",
        replace_existing=True,
    )
    # 8-1) 08:00 - 미장 저점 매수 찾기
    # scheduler.add_job(
    #     find_low_stocks_us,
    #     trigger=CronTrigger(day_of_week="mon-fri", minute="0"),
    #     id="daily_0800_find_low_stocks_us",
    #     executor="io",
    #     replace_existing=True,
    # )


    # 5) 상승주 그래프 갱신
    scheduler.add_job(
        update_summary_stock_graph_daily,
        trigger=CronTrigger(day_of_week="mon-fri", hour="9-19", minute="5-59/10"),
        id="update_summary_stocks_graph",
        executor="io",
        replace_existing=True,
    )
    scheduler.add_job(
        update_summary_stock_graph_daily,
        trigger=CronTrigger(day_of_week="mon-fri", hour=20, minute=5),
        id="update_summary_stocks_graph_2",
        executor="io",
        replace_existing=True,
    )


    # 17) 저점+급상승 종목 신뢰도 검증 (계속해서 조건 만족하는것만 남기려는 의도)
    scheduler.add_job(
        verify_low_stock_data,
        trigger=CronTrigger(day_of_week="mon-fri", hour="9-19", minute="*/1"),
        id="verify_low_stock_data",
        executor="io",
        replace_existing=True,
    )


    ####################################################################

    # 99) 매일 10:00 full-chain.pem 생성 (인증서)
    scheduler.add_job(
        generate_fullchain_pem_daily,
        trigger=CronTrigger(hour=10, minute=0),
        id="generate_fullchain_pem_daily",
        executor="io",
        replace_existing=True,
    )

    scheduler.start()
    return scheduler




'''
< 파이썬의 스케줄러 방식 추천 >

| 항목           | APScheduler | schedule | asyncio + while |
| -------------- | ----------- | -------- | --------------- |
| 외부 라이브러리  | O           | O        | X               |
| Flask 궁합     | ⭐⭐⭐⭐⭐ | ⭐⭐    | ⭐⭐⭐         |
| 시간 정확도     | ⭐⭐⭐⭐⭐ | ⭐⭐    | ⭐⭐⭐⭐       |
| 타임존 지원     | ⭐⭐⭐⭐⭐ | ❌      | 직접 처리         |
| 크론 표현식     | O           | ❌      | ❌               |
| 서버 재시작 내성 | ⭐⭐⭐     | ⭐      | ⭐⭐            |
| CPU 점유       | 매우 낮음     | 낮음     | 매우 낮음        |
| 메모리         | +수 MB       | 거의 없음 | 없음             |
| 실무 사용 빈도  | 매우 높음     | 낮음     | 중간             |
| 유지보수성      | 매우 좋음     | 나쁨     | 보통             |

>> 단점 정리
  APScheduler
    Flask 다중 워커(gunicorn 등)에서는 job 중복 실행 주의 필요
  schedule
    프로세스가 block됨
    시간 정확도 낮음 (드리프트 발생)
  asyncio + while
    스케줄 표현이 복잡
    여러 작업 늘어나면 지옥
    서버 재시작 시 보정 로직 직접 구현
    
>> 추천 구현 예시
```
Flask + APScheduler

from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from zoneinfo import ZoneInfo

app = Flask(__name__)
scheduler = BackgroundScheduler(timezone=ZoneInfo("Asia/Seoul"))

def daily_job():
    print("하루 1번 실행")

def hourly_job():
    print("9~15시, 1시간마다 실행")

@app.before_first_request
def start_scheduler():
    scheduler.add_job(daily_job, 'cron', hour=0, minute=5)        # 매일 00:05 실행
    scheduler.add_job(hourly_job, 'cron', hour='9-15', minute=10) # 9~15시 10분이 될 때마다 실행
    scheduler.add_job(job_10min, 'cron', minute='*/10')           # 10분마다 실행
    scheduler.add_job(job_min_end_5, 'cron', hour='9-10', minute='5,15,25,35,45,55') # 9~15시 5로 끝나는 분마다
    scheduler.add_job(job, 'cron', ..., max_instances=1, coalesce=True) # 작업이 길이진다면
    # max_instances=1: 이전 실행이 아직 끝나지 않았으면 중복 실행 제한    
    # coalesce=True: 밀린 실행이 여러 번 생기면 1번으로 합쳐서 실행
    scheduler.add_job(job, 'interval', seconds=5)
    scheduler.start()
``` 
'''

'''
< 파이썬 비동기·동시 처리 방법 비교표 >

| 비교 항목 ↓ / 방식 → | asyncio (코루틴)          | threading          | ThreadPoolExecutor | ProcessPoolExecutor  | asyncio + to_thread | asyncio + ProcessPool |
| ------------------ | ------------------------- | ----------------- | -------------------| -------------------- | ------------------- | --------------------- |
| 실행 단위           | 코루틴(Task)               | 스레드             | 스레드(풀)          | 프로세스(풀)           | 코루틴 + 스레드      | 코루틴 + 프로세스       |
| 주 용도             | I/O 대기 병렬화            | 간단 동시 실행      | 블로킹 I/O 병렬     | CPU 연산 병렬          | async에서 블로킹 분리 | async에서 CPU 병렬     |
| 대표 예시           | Playwright async, aiohttp | 간단 백그라운드 작업 | requests 병렬 호출  | 이미지/영상/대규모 계산 | async + requests    | async 수집 + ML 전처리 |
| Flask 궁합         | ⚠️ 애매 (WSGI)             | ✅ 무난           | ✅ 좋음            | ⚠️ 운영 복잡           | ⚠️ 배치/보조용       | ⚠️ 분리 권장           |
| FastAPI 궁합       | ✅ 최적                    | ⚠️ 가능           | ✅ 좋음            | ⚠️ 가능               | ✅ 매우 좋음         | ✅ 좋음               |
| 코드 난이도         | 중                         | 중                | 낮음~중             | 중~높음               | 낮음~중              | 높음                   |
| 메모리 사용         | ⭐ (매우 적음)             | ⭐⭐              | ⭐⭐              | ⭐⭐⭐⭐            | ⭐⭐                | ⭐⭐⭐⭐             |
| 실무 사용 빈도      | ⭐⭐⭐⭐⭐               | ⭐⭐⭐           | ⭐⭐⭐⭐          | ⭐⭐⭐              | ⭐⭐⭐⭐            | ⭐⭐~⭐⭐⭐          |

프로세스를 사용하는 방법은 GIL 영향이 없고, 객체 공유가 어렵고, I/O 병렬 처리가 비효율적이고, CPU코어를 병렬로 사용할 수 있다
프로세스를 사용하는 방법은 프로세스간 공유를 위해 list, dict, tuple, set같은 것들을 pickle로 저장한 뒤 전달해야 한다

>> 핵심 정리
  asyncio (코루틴)
    I/O 기다림 최강자, CPU는 직접 못 씀, 네트워크/웹 자동화
  threading
    간단히 몇 개만” 동시에 돌리고 싶을 때(직접 제어)
  ThreadPoolExecutor
    블로킹 I/O를 여러 개 병렬로 돌릴 때, CPU는 사실상 1개만 씀, GIL, I/O 위주
    스레드를 풀로 묶어서, 작업 큐 기반으로 동시에 여러 작업을 처리하게 해주는 고수준 비동기 API
  ProcessPoolExecutor
    CPU 연산을 코어 여러 개로 진짜 병렬 처리할 때, 비용·제약 큼
  asyncio + to_thread
    async 흐름 유지하면서 특정 블로킹 함수를 “잠깐” 스레드로 빼고 싶을 때
  asyncio + ProcessPool
    async 앱에서 CPU 무거운 부분만 프로세스로 빼서 병렬 처리할 때(전처리/연산 파이프라인)


```
import asyncio

async def fetch(name, delay):
    await asyncio.sleep(delay)   # I/O 대기라고 가정
    return f"{name} done"

async def main():
    results = await asyncio.gather(
        fetch("A", 1),
        fetch("B", 2),
        fetch("C", 1),
    )
    print(results)

asyncio.run(main())

```

```
import threading
import time

def work(name):
    time.sleep(1)  # 블로킹 작업
    print(f"{name} done")

t1 = threading.Thread(target=work, args=("A",))
t2 = threading.Thread(target=work, args=("B",))

t1.start(); t2.start()
t1.join();  t2.join()

```

```
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

def blocking_call(x):
    time.sleep(1)
    return x * 2

with ThreadPoolExecutor(max_workers=5) as ex:
    futures = [ex.submit(blocking_call, i) for i in range(10)]
    for f in as_completed(futures):
        print(f.result())

```

```
from concurrent.futures import ProcessPoolExecutor
import os

def cpu_heavy(n: int) -> int:
    s = 0
    for i in range(10_000_00):  # CPU를 좀 쓰는 작업(예시)
        s += (i * n) % 97
    return s

if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as ex:
        results = list(ex.map(cpu_heavy, range(1, 9)))
    print(results)

```

```
import asyncio
import time

def blocking_job(x):
    time.sleep(2)
    return x + 10

async def main():
    # 블로킹 함수를 스레드로 보내고 결과를 await
    r = await asyncio.to_thread(blocking_job, 5)
    print(r)

asyncio.run(main())

```

```
import asyncio
from concurrent.futures import ProcessPoolExecutor

def cpu_heavy(x: int) -> int:
    s = 0
    for i in range(5_000_00):
        s += (i * x) % 97
    return s

async def main():
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor(max_workers=4) as pool:
        tasks = [
            loop.run_in_executor(pool, cpu_heavy, i)
            for i in range(1, 9)
        ]
        results = await asyncio.gather(*tasks)
    print(results)

asyncio.run(main())

```

'''

'''
# 1. multiprocessing는 메모리를 공유하지 않는다 -> class의 필드를 공유하지 않음
# process = multiprocessing.Process(target=self.generate_thumbnail)
# process.start() 
# 2. 스레드를 무한히 생성하는 오류
#thread = threading.Thread(target=self.generate_thumbnail) 
#thread.start()
# 3. 자식 프로세스가 무한히 증식한다..
#self.executor.submit(self.generate_thumbnail) 
'''