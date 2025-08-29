# import sched
from apscheduler.schedulers.background import BackgroundScheduler
import threading
import time
import os
import glob
import ffmpeg
import psutil
import subprocess
from datetime import datetime, timedelta
# from multiprocessing import Process, Manager
import multiprocessing
from moviepy.editor import VideoFileClip
from send2trash import send2trash
from concurrent.futures import ThreadPoolExecutor
from config.config import settings
import zipfile
import asyncio
import schedule
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.executors.asyncio import AsyncIOExecutor
from utils.lotto_schedule import async_buy_lotto
from utils.compress_file import compress_directory, compress_directory_to_zip
import re

tasks = []

# sched 기본 스케줄러, 블로킹
# scheduler = sched.scheduler(time.time, time.sleep)

# 스케줄러 인스턴스 생성 (논블로킹)
scheduler = BackgroundScheduler()
work_directory = settings['WORK_DIRECTORY']
TEMP_IMAGE_DIR = settings['TEMP_IMAGE_DIR']
TRIP_IMAGE_DIR = settings['TRIP_IMAGE_DIR']
DIRECTORIES_TO_COMPRESS = [TEMP_IMAGE_DIR, TRIP_IMAGE_DIR]

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

class Task:
    def __init__(self, pid, file_pattern, work_directory, url):
        self.pid = pid
        self.file_pattern = file_pattern
        self.work_directory = work_directory
        self.last_modified_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.last_checked_time = None
        self.file_name = None
        self.thumbnail_path = None
        self.thumbnail_update_time = None
        self.creation_time = datetime.now()
        self.initial_thumbnail_created = False
        self.thumbnail_duration = 0
        self.url = url
        #self.executor = ThreadPoolExecutor(max_workers=10) # 스레드 풀

    def update_last_modified(self):
        latest_file = self.get_latest_file()
        # print(f"Latest file: {latest_file}")
        if latest_file is not None:
            self.file_name = os.path.basename(latest_file)
            if not self.initial_thumbnail_created:
                self.creation_time = datetime.fromtimestamp(os.path.getctime(latest_file))
            if latest_file is not None:
                last_modified_time = datetime.fromtimestamp(os.path.getmtime(latest_file))
                if self.last_checked_time is None or last_modified_time != self.last_checked_time:
                    self.last_modified_time = last_modified_time.strftime('%Y-%m-%d %H:%M:%S')
                    self.last_checked_time = last_modified_time
                    # print(f"######### Updated ######### : {self.file_name} - - {self.thumbnail_update_time} - - {self.last_modified_time}")
                    self.set_param_generate_thumbnail()

    def set_param_generate_thumbnail(self):
        # 처음부터 ffmpeg를 import 했으면 multiprocessing을 사용할 이유가 있었을까?
        params = {
            'pid': self.pid,
            'file_name': self.file_name,
            'work_directory': self.work_directory,
            'initial_thumbnail_created': self.initial_thumbnail_created,
            'thumbnail_path': self.thumbnail_path,
            'thumbnail_update_time': self.thumbnail_update_time,
            'last_modified_time': self.last_modified_time,
            'creation_time': self.creation_time,
        }

        # multiprocessing.Manager > 공유 dict
        manager = Manager()
        return_dict = manager.dict()
        process = Process(target=self.generate_thumbnail, args=(params, return_dict))
        process.start()
        process.join()

        # 프로세스가 완료된 후 공유된 dict에서 결과를 가져옴
        self.thumbnail_path = return_dict.get('thumbnail_path')
        self.thumbnail_update_time = return_dict.get('thumbnail_update_time')
        self.initial_thumbnail_created = return_dict.get('initial_thumbnail_created')

    def get_latest_file(self):
        search_pattern = os.path.join(self.work_directory, self.file_pattern)
        files = glob.glob(search_pattern)

        if not files:
            return None

        latest_file = max(files, key=os.path.getctime) # 수정시간 딜레이 이슈
        # latest_file = max(files, key=os.path.getmtime)
        return latest_file

    def generate_thumbnail(self, params, return_dict):
        pid = params.get("pid")
        file_name = params.get("file_name")
        work_directory = params.get("work_directory")
        creation_time = params.get("creation_time")
        last_modified_time = params.get("last_modified_time")
        initial_thumbnail_created = params.get("initial_thumbnail_created")
        thumbnail_update_time = params.get("thumbnail_update_time")
        thumbnail_path = os.path.join(work_directory, file_name.replace('.ts', '_thumb.webp'))
        target_file = os.path.join(work_directory, file_name)


        if file_name and creation_time and is_process_running(pid):
            if not initial_thumbnail_created:
                # 최초 썸네일 생성 (파일 시작 1초 후)
                (
                    ffmpeg.input(target_file, ss=1)
                    .output(thumbnail_path, vframes=1, q=85, pix_fmt='yuvj420p', loglevel="error", update=1)
                    .run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
                )
                if os.path.exists(thumbnail_path):
                    initial_thumbnail_created = True
                    thumbnail_update_time = datetime.now().isoformat()
                else:
                    print("Failed to create initial thumbnail.")

            elif thumbnail_update_time:
                current_time = datetime.now()
                last_update_time = datetime.fromisoformat(thumbnail_update_time)

                modification_time = datetime.strptime(last_modified_time, '%Y-%m-%d %H:%M:%S')
                duration = modification_time - creation_time
                thumb_duration = duration.total_seconds()
                thumb_time_difference = (current_time - last_update_time).total_seconds()

                video_duration = get_video_duration(target_file)
                if thumb_duration > video_duration:
                    thumb_duration = video_duration - 5

                if thumb_time_difference >= 30:
                    try:
                        (
                            ffmpeg.input(target_file, ss=int(thumb_duration))
                            .output(thumbnail_path, vframes=1, q=85, pix_fmt='yuvj420p', loglevel="error", update=1) # s='640x360'
                            .run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
                        )
                    except ffmpeg.Error as e:
                        # print('stdout:', e.stdout.decode('utf8'))
                        print('stderr:', e.stderr.decode('utf8'))

                    if os.path.exists(thumbnail_path):
                        thumbnail_update_time = datetime.now().isoformat()
                        # print(f"Created Thumbnail at {file_name} {thumb_duration} second mark.")
                    else:
                        print(f"Failed to create thumbnail at {thumb_duration} second mark.")



            return_dict['thumbnail_path'] = thumbnail_path
            return_dict['initial_thumbnail_created'] = initial_thumbnail_created
            return_dict['thumbnail_update_time'] = thumbnail_update_time

    @staticmethod
    def terminate(pid):
        try:
            subprocess.run(['taskkill', '/PID', str(pid), '/F', '/T'], check=True)
            print(f"Process {pid} and its children have been successfully terminated.")
        except subprocess.CalledProcessError as e:
            print(f"Failed to terminate process {pid} and its children: {e}")
        except Exception as e:
            print(f"An error occurred: {e}")

def is_process_running(pid):
    """ Check if a process with a given pid is running """
    if pid is None:
        print(f"## Process PID {pid} is None ## : ")
        return False
    try:
        # psutil will throw NoSuchProcess exception if pid does not exist
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        # print("##### psutil Error ##### : ", pid)
        return False
    except Exception as e:
        print(f"##### Unexpected error ##### : {str(e)}")
        return False

# 현재 날짜를 YYMMDD 형식으로 가져오기
def current_date():
    return datetime.now().strftime('%y%m%d')


image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')

# 작업이 끝난 task 목록 제거
def cleanup_tasks():
    global tasks
    directory = work_directory
    if not tasks:
        return

    current_time = datetime.now()
    threshold_time = timedelta(minutes=15)  # 15분
    format_str = '%Y-%m-%d %H:%M:%S'
    new_tasks = []

    for task in tasks:
        task_time = datetime.strptime(task.last_modified_time, format_str)
        time_difference = current_time - task_time

        if time_difference < threshold_time:
            if not is_process_running(task.pid):
#                 new_tasks.append(task)
#             else:
#                 print(f"Process with pid {task.pid} is not running. Task {task.file_name} will be terminated.")
                terminate_task(task.pid)
        # 15분 초과하면 제거
        else :
            print(f"######### Task ############ : {task.file_name} - - time_difference : {time_difference}")
            terminate_task(task.pid)

    # 매 정각마다 실행
    if current_time.minute == 0:
        threshold_time = timedelta(minutes=30)  # 30분
        for filename in os.listdir(directory):
            if filename.lower().endswith(image_extensions):
                file_path = os.path.join(directory, filename)
                creation_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                time_difference = current_time - creation_time
                if time_difference > threshold_time:
                    normalized_path = os.path.normpath(file_path)
                    send2trash(normalized_path) # 휴지통
                    # print(f"Moved to trash: {file_name}")

#     tasks[:] = new_tasks
    print(f"Updated tasks array: {[task.file_name for task in tasks]}")

    '''
    파일의 마지막 수정시간이 10분이 넘으면 체크해야한다
    '''
    # delete_short_videos(work_directory, 60)

# 작업 상태를 주기적으로 업데이트하는 스레드
def update_task_status():
    for task in tasks:
        task.update_last_modified()

def terminate_task(pid):
    for task in tasks:
        if task.pid == pid:
            print(f"##### Terminate Task ###### : {task.file_name} ")
            if is_process_running(pid):
                Task.terminate(pid)
            # ffmpeg_handle.kill_task 호출한 경우
            try:
                tasks.remove(task)
                # print(f"Task [ {task.file_name} ] removed from tasks array.")
            except ValueError:
                print(f"Task [ {task.file_name} ] not found in tasks array.")
            break



video_extensions = ('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', 'ts')

# VideoFileClip 클래스로 파일을 직접 연다 (메모리 많이 사용한다)
def get_video_length(file_path):
    try:
        clip = VideoFileClip(file_path)
        duration = clip.duration # 길이를 초 단위로 반환
        clip.close()
        return duration
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None

# ffmpeg로 메타데이터를 가져온다 (메모리 사용량이 적다)
def get_video_duration(filepath):
    try:
        probe = ffmpeg.probe(filepath)
        video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
        return float(video_info['duration'])
    except Exception as e:
        print(f"Error getting video duration: {e}")
        return None
    
def delete_short_videos():
    '''비디오 파일 출력 + args[1] 보다 작으면 휴지통'''
    current_time = time.time()
    min_length = 60 # 1분
    directory = work_directory

    for filename in os.listdir(directory):
        if filename.lower().endswith(video_extensions):
            file_path = os.path.join(directory, filename)
            last_modified_time = os.path.getmtime(file_path)

            if current_time - last_modified_time > 900:  # 15분
                duration = get_video_length(file_path)
                if duration is not None and duration < min_length:
                    if os.path.exists(file_path):
                        normalized_path = os.path.normpath(file_path)
                        try:
                            send2trash(normalized_path)  # 휴지통으로 보내기
                            # print(f"Deleted [ {filename} ] as it is shorter than {min_length} seconds.")
                        except FileNotFoundError:
                            print(f"File not found: {normalized_path}. It may have been deleted already.")
                        except Exception as e:
                            print(f"Error sending {normalized_path} to trash: {e}")
                    else:
                        print(f"File does not exist: {file_path}. Skipping deletion.")


# # 스레드 시작 (썸네일 생성이 늘어진다..?)
# # threading.Thread(target=update_task_status, daemon=True).start()
#
# # 스케줄러에 작업 추가, max_instances 기본 1
# # scheduler.add_job(update_task_status, 'interval', seconds=10, max_instances=6, coalesce=True)
# # scheduler.add_job(cleanup_tasks, 'interval', minutes=1)
# # scheduler.add_job(delete_short_videos, 'interval', minutes=10)
# scheduler.add_job(compress_directory_to_zip, 'interval', minutes=60)
#
# #scheduler.start()


# 매시 정각마다 실행하는 함수
def periodic_compression_task():
    try:
        while True:
            now = datetime.now()
            next_hour = (now + timedelta(hours=6)).replace(minute=0, second=0, microsecond=0)
            sleep_duration = (next_hour - now).total_seconds()
            # sleep_duration = 60 # 1분 테스트
            time.sleep(sleep_duration)
            compress_directory_to_zip()
    except KeyboardInterrupt:
        print("압축 작업 중단됨")

def should_predict(market):
    today = datetime.today().weekday()
    print(f'    ############################### should_predict : {today}, {market} ###############################')
    if market == 'kospi':
        return today not in (4, 5)    # 금, 토 제외
    elif market == 'nasdaq':
        return today not in (5, 6)    # 토, 일 제외
    return False

def predict_stock_graph_scheduled(market):
    if should_predict(market):
        predict_stock_graph(market)

async def run_schedule():
#     schedule.every().wednesday.at("10:01").do(lambda: asyncio.create_task(async_buy_lotto()))
    schedule.every().saturday.at("08:00").do(lambda: run_async_function(async_buy_lotto()))
    schedule.every().day.at("06:00").do(run_crawl_ai_image)
    schedule.every().day.at("07:00").do(renew_kiwoom_token)
    schedule.every().day.at("20:00").do(predict_stock_graph_scheduled, 'kospi')
    schedule.every().day.at("11:00").do(predict_stock_graph_scheduled, 'nasdaq')

    while True:
        # print("[Scheduler] 현재시간:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
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

def run_crawl_ai_image():
    print('    ############################### run_crawl_ai_image ###############################')
    # 명령어 조합
    # Windows에서는 여러 명령을 &&로 연결하여 한 줄에 실행 가능
    # venv 활성화 후 바로 실행
    script_dir = r'C:\my-project\random-player'
    venv_activate = r'venv\Scripts\activate'
    py_script = r'python utils\crawl_image_by_playwright.py'

    # 전체 명령어 (venv 활성화 → 스크립트 실행)
    # 주의: activate.bat는 cmd에서만 인식, powershell은 다름
    cmd = f'cmd /c "cd /d {script_dir} && {venv_activate} && {py_script} && exit"'

    # subprocess 실행
    process = subprocess.Popen(
        cmd,
        # creationflags=subprocess.CREATE_NEW_CONSOLE,  # ⭐️ 새 콘솔창에서 실행!
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=True,
        # encoding='utf-8',
        encoding="cp949",
        errors="ignore" # 디코딩 안되는 문자 무시
    )
    stdout, stderr = process.communicate()

def renew_kiwoom_token():
    print('    ############################### renew_kiwoom_token ###############################')
    # 명령어 조합
    # Windows에서는 여러 명령을 &&로 연결하여 한 줄에 실행 가능
    # venv 활성화 후 바로 실행
    script_dir = r'C:\my-project\random-player'
    venv_activate = r'venv\Scripts\activate'
    py_script = r'python utils\renew_kiwoom_token.py'

    # 전체 명령어 (venv 활성화 → 스크립트 실행)
    # 주의: activate.bat는 cmd에서만 인식, powershell은 다름
    cmd = f'cmd /c "cd /d {script_dir} && {venv_activate} && {py_script} && exit"'

    # subprocess 실행
    process = subprocess.Popen(
        cmd,
        # creationflags=subprocess.CREATE_NEW_CONSOLE,  # ⭐️ 새 콘솔창에서 실행!
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=True,
        encoding="cp949",
        errors="ignore" # 디코딩 안되는 문자 무시
    )
    stdout, stderr = process.communicate()

'''
cd /d C:\my-project\AutoSales.py
venv\Scripts\activate
python multi_kor_stocks.py
'''
def predict_stock_graph(stock):
    print(f'    ############################### predict_stock_graph : {stock} ###############################')
    script_dir = r'C:\my-project\AutoSales.py'
    venv_activate = r'venv\Scripts\activate'
    if stock == 'kospi':
        py_script = r'python multi_kor_stocks.py'
    if stock == 'nasdaq':
        py_script = r'python new_nasdaq_multi.py'

    # 전체 명령어 (venv 활성화 → 스크립트 실행)
    # 주의: activate.bat는 cmd에서만 인식, powershell은 다름
    cmd = f'cmd /c "cd /d {script_dir} && {venv_activate} && {py_script} && exit"'

    # subprocess 실행
    process = subprocess.Popen(
        cmd,
        # creationflags=subprocess.CREATE_NEW_CONSOLE,  # ⭐️ 새 콘솔창에서 실행!
        # stdout=subprocess.PIPE, # 버퍼가 꽉 차서 죽는다 ? > 서브프로세스(=실행된 명령)의 표준출력(stdout)이 '파이썬 부모 프로세스'로 파이프로 전달
        # stderr=subprocess.PIPE,
        text=True,
        shell=True,
        encoding='utf-8',
        errors="ignore" # 디코딩 안되는 문자 무시
    )
    # stdout, stderr = process.communicate() # 버퍼를 읽어줘야 죽지 않는다
    # print("STDOUT:", stdout)
    # print("STDERR:", stderr)


# 주기적 작업을 위한 프로세스 시작 (두 개의 별도 프로세스를 데몬으로 실행, 앱이 또 생성됨)
# asyncio 또는 threading.Thread를 사용하면, Waitress 앱 하나 안에서 주기작업, 스케줄러 등을 백그라운드에서 실행 가능
# 압축, 스케줄러, 로그 체크 같은 작업이 I/O 중심이면 → threading 또는 asyncio로 충분
# 진짜 병렬 CPU 계산이라면 → multiprocessing
def start_periodic_task():
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

def start_background_tasks():
    threading.Thread(target=periodic_compression_task, daemon=True).start()
    threading.Thread(target=start_lotto_scheduler, daemon=True).start()

def initialize_directories():
    for directory in DIRECTORIES_TO_COMPRESS:
        os.makedirs(directory, exist_ok=True)

initialize_directories()

# 스레드 시작 (썸네일 생성이 늘어진다..?)
# threading.Thread(target=update_task_status, daemon=True).start()

# 스케줄러에 작업 추가, max_instances 기본 1
# scheduler.add_job(update_task_status, 'interval', seconds=10, max_instances=6, coalesce=True)
# scheduler.add_job(cleanup_tasks, 'interval', minutes=1)
# scheduler.add_job(delete_short_videos, 'interval', minutes=10)

# scheduler.add_job(compress_directory_to_zip, 'interval', minutes=60)

# scheduler.start()

'''
threading.Thread - 간단한 비동기 작업, GIL(Global Interpreter Lock) 문제 - 하나의 쓰레드만 인터프리터의 모든 자원을 사용 > 컨텍스트 스위칭 비용이 발생
CPU 바운드 작업에는 multiprocessing 모듈을 사용하는 것이 더 적합 - GIL의 제약을 받지 않는 별도의 프로세스

asyncio - 비동기 I/O 작업에 효율적, 이벤트 루프 기반, 스레드보다 가벼운 구조

concurrent.futures.ThreadPoolExecutor - 스레드 관리를 자동화하고, 실행 결과를 쉽게 추적

---------------------------------------------------------

multiprocessing - 프로세스를 기반으로 병렬 처리를 구현, GIL 영향이 없음, 다중 코어 CPU 활용, 프로세스 간 메모리 분리, 메모리 사용량 높음, 프로세스 생성비용은 스레드 생성비용 보다 높다

concurrent.futures.ThreadPoolExecutor - 스레드를 기반으로 병렬 처리, GIL 영향을 받는다, I/O 바운드 작업에 적합, futures 객체로 작업의 완료 상태를 관리, concurrent.futures API는 작업 제출, 완료 추적, 결과 수집을 간단하게 처리, 다중 코어 활용이 제한적
'''

'''
1. APScheduler
예약된 작업을 등록해서 자동으로 실행하는 "스케줄러" 라이브러리
(정해진 시간, 주기, 크론 등 지원)
- 실행 방식 : 내부적으로 threading, asyncio, processpool 중 선택 가능
- 사용 예 : 주기적 DB 정리, 백업, 알람, 리포트 작업 등

    from apscheduler.schedulers.background import BackgroundScheduler

    def job():
        print("작업 실행!")

    scheduler = BackgroundScheduler()
    scheduler.add_job(job, 'interval', seconds=5)
    scheduler.start()
'''

'''
2. threading
병렬로 코드를 돌리기 위한 Python 내장 방식
실제는 진짜 병렬은 아님 (GIL 영향 받음)
- 실행 방식 : OS 쓰레드를 이용하되 GIL 공유
- 병렬성 : ❌ CPU 병렬성 없음 (단일 Python 인터프리터)
- 적합 작업 : I/O 위주의 반복 작업, 로그 수집, 폴링 등

    import threading

    def background_task():
        while True:
            print("백그라운드 동작")

    t = threading.Thread(target=background_task, daemon=True)
    t.start()

3. asyncio
Python의 비동기 처리 프레임워크 (싱글 스레드 기반)
await, async def, 이벤트 루프 기반으로 작동
- 목적 : 비동기 I/O, 고성능 서버, 병렬 요청 처리
- 실행 방식 : 단일 쓰레드 + 논블로킹 방식 (코루틴 스케줄링)
- 병렬성 : ❌ CPU 병렬은 아님 (하지만 I/O 병렬화에 매우 효율적)
- 적합 작업 : API 호출, 비동기 DB, 파일 I/O 등

    import asyncio

    async def async_task():
        while True:
            print("비동기 작업 중")
            await asyncio.sleep(5)

    asyncio.run(async_task())

4. concurrent.futures.ThreadPoolExecutor
스레드를 풀로 묶어서, 작업 큐 기반으로 동시에 여러 작업을 처리하게 해주는 고수준 비동기 API
- 실행 방식 : 쓰레드 풀 (큐 기반)
- 병렬성 : 제한된 수의 스레드로 병렬 처리

    from concurrent.futures import ThreadPoolExecutor

    def task(x):
        return x * x

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(task, i) for i in range(5)]
        results = [f.result() for f in futures]

- 스레드 수를 제한해서 동시에 실행
    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.submit(task1)
        executor.submit(task2)

- Future 객체로 결과/예외를 다룰 수 있음
    future = executor.submit(task)
    try:
        result = future.result(timeout=5)
    except Exception as e:
        print(f"에러 발생: {e}")
'''