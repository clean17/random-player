import time
import os
import glob
import ffmpeg
import psutil
import subprocess
import datetime
from moviepy.editor import VideoFileClip
from send2trash import send2trash
from config.config import settings
import multiprocessing
import asyncio
# import sched ++ 서버/운영용보다는 테스트·학습용
import schedule
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from concurrent.futures import ThreadPoolExecutor
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from job.batch_process import predict_stock_graph, find_stocks, find_low_stocks, update_interest_stocks, \
    renew_kiwoom_token_job
# utils패키지의 모듈을 임포트
from utils.lotto_schedule import async_buy_lotto
from utils.compress_file import compress_directory_to_zip
from utils.renew_stock_close import renew_interest_stocks_close
from utils.scrap_ig_playwrigit import run_scrap_job

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

# 전역 루프
_loop = None


def start_async_loop_in_background():
    """별도 스레드에서 asyncio 이벤트 루프를 영구 실행"""
    global _loop
    _loop = asyncio.new_event_loop()   # 새로운 이벤트 루프 생성

    def runner():
        asyncio.set_event_loop(_loop)   # 이벤트 루프 설정
        _loop.run_forever()

    t = threading.Thread(target=runner, daemon=True)
    t.start()


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



def create_scheduler():
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


    # 1) 로또 주 1회
    scheduler.add_job(
        async_buy_lotto,
        trigger=CronTrigger(day_of_week="sat", hour=8, minute=0),
        id="lotto_weekly",
        executor="io",
        replace_existing=True
    )

    # 2) 매 6시간마다 압축
    scheduler.add_job(
        compress_directory_to_zip,
        trigger=IntervalTrigger(hours=6),
        id="compression_6_hourly",
        executor="io",
        replace_existing=True
    )

    # 3) 매일 07:00 키움 토큰 갱신
    scheduler.add_job(
        renew_kiwoom_token_job,
        trigger=CronTrigger(hour=7, minute=0),
        # trigger=CronTrigger(second="*/15"),   # 15초 마다
        id="renew_token_daily",
        executor="io",
        replace_existing=True
    )

    # 4) 매일 07:00 나스닥 예측 (CPU 3시간)
    scheduler.add_job(
        predict_stock_graph_scheduled,
        trigger=CronTrigger(hour=7, minute=0),
        id="predict_nasdaq_0700",
        executor="cpu",
        replace_existing=True,
        args=["nasdaq"],
    )

    # 5) 매일 20:00 코스피 예측 (CPU 3시간)
    scheduler.add_job(
        predict_stock_graph_scheduled,
        trigger=CronTrigger(hour=20, minute=0),
        id="predict_kospi_2000",
        executor="cpu",
        replace_existing=True,
        args=["kospi"],
    )

    # 6) 국장 시작 09:05 - run_weekdays_only(find_stocks)
    scheduler.add_job(
        run_weekdays_only,
        trigger=CronTrigger(day_of_week="mon-fri", hour=9, minute=5),
        id="korea_open_0905_find_stocks",
        executor="io",
        replace_existing=True,
        args=[find_stocks],
    )

    # 7) 09:30 ~ 15:30, 30분마다 (평일)
    scheduler.add_job(
        run_weekdays_only,
        trigger=CronTrigger(day_of_week="mon-fri", hour=9, minute=30),
        id="0930_find_stocks",
        executor="io",
        replace_existing=True,
        args=[find_stocks],
    )
    scheduler.add_job(
        run_weekdays_only,
        trigger=CronTrigger(day_of_week="mon-fri", hour="10-15", minute="0,30"),
        id="every_30min_1000_1530_find_stocks",
        executor="io",
        replace_existing=True,
        args=[find_stocks],
    )

    # 8) 09:45~15:45 매시 45분 - run_weekdays_only(find_low_stocks)
    scheduler.add_job(
        run_weekdays_only,
        trigger=CronTrigger(day_of_week="mon-fri", hour="9-15", minute=45),
        id="hourly_0945_1545_find_low_stocks",
        executor="io",
        replace_existing=True,
        args=[find_low_stocks],
    )

    # 9) 월~금 5분마다 - run_cumtom_time_only(update_interest_stocks)
    scheduler.add_job(
        run_cumtom_time_only,
        trigger=CronTrigger(day_of_week="mon-fri", minute="*/5"),
        id="weekday_every_5min_update_interest_stocks",
        executor="io",
        replace_existing=True,
        args=[update_interest_stocks],
    )

    # 10) 매일 02:00 스크랩
    scheduler.add_job(
        run_scrap_job,
        trigger=CronTrigger(hour=2, minute=0),
        id="scrap_daily",
        executor="io",
        replace_existing=True,
    )

    # 11) 09:30 ~ 15:30, 30분마다 (평일) 코스피 종가 수정
    scheduler.add_job(
        renew_interest_stocks_close,
        trigger=CronTrigger(day_of_week="mon-fri", hour="9-15", minute="30"),
        id="renew_interest_close",
        executor="io",
        replace_existing=True
    )

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