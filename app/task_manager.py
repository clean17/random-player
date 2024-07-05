# import sched
from apscheduler.schedulers.background import BackgroundScheduler
import threading
import time
import os
import glob
import subprocess
from datetime import datetime, timedelta
import logging

tasks = []

# scheduler = sched.scheduler(time.time, time.sleep) # sched 기본 스케줄러, 블로킹

# 스케줄리 인스턴스 생성 (논블로킹)
scheduler = BackgroundScheduler()

class Task:
    def __init__(self, pid, file_pattern, work_directory):
        self.pid = pid
        self.file_pattern = file_pattern
        self.work_directory = work_directory
        self.last_modified_time = None
        self.file_name = None
        self.thumbnail_path = None
        self.thumbnail_update_time = None
        self.creation_time = datetime.now()
        self.initial_thumbnail_created = False
        self.thumbnail_duration = 0


    def update_last_modified(self):
        latest_file = self.get_latest_file()
        if latest_file:
            # print('################################ ', latest_file, self.thumbnail_update_time)
            self.file_name = os.path.basename(latest_file)
            self.last_modified_time = datetime.fromtimestamp(os.path.getmtime(latest_file)).strftime('%Y-%m-%d %H:%M:%S')
            self.creation_time = datetime.fromtimestamp(os.path.getctime(latest_file))
            # process = multiprocessing.Process(target=self.generate_thumbnail)
            # process.start() # multiprocessing는 메모리를 공유하지 않는다 -> class의 필드를 공유하지 않음
            thread = threading.Thread(target=self.generate_thumbnail)
            thread.start()

    #def get_latest_file(self):
        # 파일 수정 시간이 딜레이 되는 이슈
        # files = glob.glob(self.file_pattern)
        #if not files:
        #    return None

        #latest_file = max(files, key=os.path.getctime)
        #return latest_file
        #try:
        #    files = [os.path.join(self.work_directory, f) for f in os.listdir(self.work_directory) if self.file_pattern in f]
        #    latest_file = max(files, key=os.path.getmtime)
        #    return latest_file
        #except ValueError:
        #    return None

    def get_latest_file(self):

        search_pattern = os.path.join(self.work_directory, self.file_pattern)
        files = glob.glob(search_pattern)

        if not files:
            return None

        latest_file = max(files, key=os.path.getmtime)
        return latest_file

    def generate_thumbnail(self):
        if self.file_name and self.creation_time:
            if not self.initial_thumbnail_created:
                # 최초 썸네일 생성 (파일 시작 1초 후)
                initial_thumbnail_path = os.path.join(self.work_directory, self.file_name.replace('.ts', '_thumb.jpg'))
                initial_cmd = f"ffmpeg -y -i {os.path.join(self.work_directory, self.file_name)} -ss 1 -vframes 1 -s 426x240 -q:v 10 {initial_thumbnail_path}"
                result = subprocess.run(initial_cmd, shell=True, capture_output=True, text=True, encoding='utf-8')
                if result.returncode == 0:
                    self.thumbnail_path = initial_thumbnail_path
                    self.initial_thumbnail_created = True
                    self.thumbnail_update_time = datetime.now().isoformat()
                    # print(f"Initial thumbnail created at {self.thumbnail_path}")
                else:
                    print("Failed to create initial thumbnail. Error: {result.stderr}")

            elif self.thumbnail_update_time:
                current_time = datetime.now() # ok
                last_update_time = datetime.fromisoformat(self.thumbnail_update_time)

                modification_time = datetime.strptime(self.last_modified_time, '%Y-%m-%d %H:%M:%S')
                duration = modification_time - self.creation_time # 파일수정 - 생성
                thumb_duration = duration.total_seconds()

                thumb_time_difference = (current_time - last_update_time).total_seconds() # 마지막 썸네일 생성시간 차
                # print(self.file_name, time_difference)
                # print('self.last_modified_time', self.last_modified_time)
                # print('thumb_duration', thumb_duration)
                if thumb_time_difference >= 60:
                    # self.thumbnail_duration = (current_time - self.creation_time).total_seconds()
                    thumbnail_path = os.path.join(self.work_directory, f"{self.file_name.replace('.ts', '')}_thumb.jpg")
                    cmd = f"ffmpeg -y -i {os.path.join(self.work_directory, self.file_name)} -ss {int(thumb_duration)} -frames:v 1 -s 426x240 -q:v 10 {thumbnail_path}"
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8')
                    if result.returncode == 0:
                        self.thumbnail_path = thumbnail_path
                        self.thumbnail_update_time = datetime.now().isoformat()
                    else:
                        print(f"Failed to create thumbnail at {thumb_duration} second mark. Error: {result.stderr}")

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

def cleanup_tasks():
    global tasks
    current_time = datetime.now()
    threshold_time = timedelta(minutes=20)  # 20분
    format_str = '%Y-%m-%d %H:%M:%S'
    tasks = [task for task in tasks if current_time - datetime.strptime(task.last_modified_time, format_str) < threshold_time]

# 작업 상태를 주기적으로 업데이트하는 스레드
def update_task_status():
    # while True:
    #     for task in tasks:
    #         task.update_last_modified()
    #     time.sleep(10)

    # 10초마다 반복 실행
    # while True:
    #     start_time = time.time()
    #     for task in tasks:
    #         task.update_last_modified()
    #
    #     # 다음 실행 시간을 계산
    #     end_time = time.time()
    #     elapsed_time = end_time - start_time
    #     next_run_in = max(10 - elapsed_time, 0)
    #     time.sleep(next_run_in)

    for task in tasks:
        task.update_last_modified()


# 스레드 시작 (썸네일 생성이 늘어진다..?)
# threading.Thread(target=update_task_status, daemon=True).start()

# 스케줄러에 작업 추가
scheduler.add_job(update_task_status, 'interval', seconds=15)
scheduler.add_job(cleanup_tasks, 'interval', minutes=5)

scheduler.start()
