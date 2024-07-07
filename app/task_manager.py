# import sched
from apscheduler.schedulers.background import BackgroundScheduler
import threading
import time
import os
import glob
import ffmpeg
import subprocess
from datetime import datetime, timedelta
from multiprocessing import Process, Manager
import logging
from concurrent.futures import ThreadPoolExecutor

tasks = []

# sched 기본 스케줄러, 블로킹
# scheduler = sched.scheduler(time.time, time.sleep)

# 스케줄리 인스턴스 생성 (논블로킹)
scheduler = BackgroundScheduler()

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
    def __init__(self, pid, file_pattern, work_directory):
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
        #self.executor = ThreadPoolExecutor(max_workers=10) # 스레드 풀

    def update_last_modified(self):
        latest_file = self.get_latest_file()
        if not self.initial_thumbnail_created and latest_file is not None:
            self.creation_time = datetime.fromtimestamp(os.path.getctime(latest_file))
            self.file_name = os.path.basename(latest_file)
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

        # latest_file = max(files, key=os.path.getctime) # 수정시간 딜레이 이슈
        latest_file = max(files, key=os.path.getmtime)
        return latest_file

    def generate_thumbnail(self, params, return_dict):
        file_name = params.get("file_name")
        work_directory = params.get("work_directory")
        creation_time = params.get("creation_time")
        last_modified_time = params.get("last_modified_time")
        initial_thumbnail_created = params.get("initial_thumbnail_created")
        thumbnail_update_time = params.get("thumbnail_update_time")
        thumbnail_path = os.path.join(work_directory, f"{file_name.replace('.ts', '')}_thumb.jpg")

        if file_name and creation_time:
            target_file = os.path.join(work_directory, file_name)

            if not initial_thumbnail_created:
                # 최초 썸네일 생성 (파일 시작 1초 후)
                initial_thumbnail_path = os.path.join(work_directory, file_name.replace('.ts', '_thumb.jpg'))
                (
                    ffmpeg.input(target_file, ss=1)
                    .output(initial_thumbnail_path, vframes=1, s='640x360', q=5, pix_fmt='yuvj420p', loglevel="panic", update=1)
                    .run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
                )
                if os.path.exists(initial_thumbnail_path):
                    thumbnail_path = initial_thumbnail_path
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

                if thumb_time_difference >= 30:
                    thumbnail_path = os.path.join(work_directory, f"{file_name.replace('.ts', '')}_thumb.jpg")
                    (
                        ffmpeg.input(target_file, ss=int(thumb_duration))
                        .output(thumbnail_path, vframes=1, s='640x360', q=5, pix_fmt='yuvj420p', loglevel="panic", update=1)
                        .run(overwrite_output=True, capture_stdout=True, capture_stderr=True)
                    )
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


# 현재 날짜를 YYMMDD 형식으로 가져오기
def current_date():
    return datetime.now().strftime('%y%m%d')

# 작업이 끝난 task 목록 제거
def cleanup_tasks():
    global tasks
    current_time = datetime.now()
    threshold_time = timedelta(minutes=11)  # 11분
    format_str = '%Y-%m-%d %H:%M:%S'
    new_tasks = []

    for task in tasks:
        task_time = datetime.strptime(task.last_modified_time, format_str)
        time_difference = current_time - task_time
        print(f"######### Task ############ : {task.file_name} - - time_difference : {time_difference}")

        if time_difference < threshold_time:
            new_tasks.append(task)

    tasks[:] = new_tasks

# 작업 상태를 주기적으로 업데이트하는 스레드
def update_task_status():
    for task in tasks:
        task.update_last_modified()

# 스레드 시작 (썸네일 생성이 늘어진다..?)
# threading.Thread(target=update_task_status, daemon=True).start()

# 스케줄러에 작업 추가, max_instances 기본 1
scheduler.add_job(update_task_status, 'interval', seconds=10, max_instances=3)
scheduler.add_job(cleanup_tasks, 'interval', minutes=1)

scheduler.start()
