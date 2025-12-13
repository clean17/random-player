# import sched
from apscheduler.schedulers.background import BackgroundScheduler
import threading
import time
import os
import re
import glob
import ffmpeg
import psutil
import subprocess
import datetime
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
# from utils.renew_stock_close import renew_interest_stocks_close
from utils.scrap_ig_playwrigit import run_scrap

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
        self.last_modified_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.last_checked_time = None
        self.file_name = None
        self.thumbnail_path = None
        self.thumbnail_update_time = None
        self.creation_time = datetime.datetime.now()
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
                self.creation_time = datetime.datetime.fromtimestamp(os.path.getctime(latest_file))
            if latest_file is not None:
                last_modified_time = datetime.datetime.fromtimestamp(os.path.getmtime(latest_file))
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
                    thumbnail_update_time = datetime.datetime.now().isoformat()
                else:
                    print("Failed to create initial thumbnail.")

            elif thumbnail_update_time:
                current_time = datetime.datetime.now()
                last_update_time = datetime.datetime.fromisoformat(thumbnail_update_time)

                modification_time = datetime.datetime.strptime(last_modified_time, '%Y-%m-%d %H:%M:%S')
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
                        thumbnail_update_time = datetime.datetime.now().isoformat()
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
    return datetime.datetime.now().strftime('%y%m%d')


image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')

# 작업이 끝난 task 목록 제거
def cleanup_tasks():
    global tasks
    directory = work_directory
    if not tasks:
        return

    current_time = datetime.datetime.now()
    threshold_time = datetime.timedelta(minutes=15)  # 15분
    format_str = '%Y-%m-%d %H:%M:%S'
    new_tasks = []

    for task in tasks:
        task_time = datetime.datetime.strptime(task.last_modified_time, format_str)
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
        threshold_time = datetime.timedelta(minutes=30)  # 30분
        for filename in os.listdir(directory):
            if filename.lower().endswith(image_extensions):
                file_path = os.path.join(directory, filename)
                creation_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
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
            now = datetime.datetime.now()
            next_hour = (now + datetime.timedelta(hours=6)).replace(minute=0, second=0, microsecond=0)
            sleep_duration = (next_hour - now).total_seconds()
            # sleep_duration = 60 # 1분 테스트
            time.sleep(sleep_duration)
            compress_directory_to_zip()
    except KeyboardInterrupt:
        print("압축 작업 중단됨")

def run_async_function(coroutine):
    """ 스케줄러에서 비동기 함수를 실행하는 래퍼 함수 """
    loop = asyncio.get_event_loop()
    asyncio.run_coroutine_threadsafe(coroutine, loop)
    # print("압축 작업 중단됨")

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


async def run_schedule():
#     schedule.every().wednesday.at("10:01").do(lambda: asyncio.create_task(async_buy_lotto()))
    schedule.every().saturday.at("08:00").do(lambda: run_async_function(async_buy_lotto()))
    # schedule.every().day.at("06:00").do(run_crawl_ai_image)
    schedule.every().day.at("07:00").do(renew_kiwoom_token)
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

def run_crawl_ai_image():
    print('    ############################### run_crawl_image ###############################')
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

def find_stocks():
    script_dir = r'C:\my-project\AutoSales.py'
    venv_activate = r'venv\Scripts\activate'
    py_script = r'python 2_finding_stocks_with_increased_volume.py'

    cmd = f'cmd /c "cd /d {script_dir} && {venv_activate} && {py_script} && exit"'

    # subprocess 실행
    process = subprocess.Popen(
        cmd,
        text=True,
        shell=True,
        encoding='utf-8',
        errors="ignore" # 디코딩 안되는 문자 무시
    )

def find_low_stocks():
    script_dir = r'C:\my-project\AutoSales.py'
    venv_activate = r'venv\Scripts\activate'
    py_script = r'python 4_find_low_point.py'

    cmd = f'cmd /c "cd /d {script_dir} && {venv_activate} && {py_script} && exit"'

    # subprocess 실행
    process = subprocess.Popen(
        cmd,
        text=True,
        shell=True,
        encoding='utf-8',
        errors="ignore" # 디코딩 안되는 문자 무시
    )

def update_interest_stocks():
    script_dir = r'C:\my-project\AutoSales.py'
    venv_activate = r'venv\Scripts\activate'
    py_script = r'python 1_periodically_update_today_interest_stocks.py'

    cmd = f'cmd /c "cd /d {script_dir} && {venv_activate} && {py_script} && exit"'

    # subprocess 실행
    process = subprocess.Popen(
        cmd,
        text=True,
        shell=True,
        encoding='utf-8',
        errors="ignore" # 디코딩 안되는 문자 무시
    )


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