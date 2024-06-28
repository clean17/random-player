import cmd
import threading
import time
import os
import glob
import subprocess
from datetime import datetime, timedelta

tasks = []

class Task:
    def __init__(self, pid, file_pattern, work_directory):
        self.pid = pid
        self.file_pattern = file_pattern
        self.work_directory = work_directory
        self.last_modified_time = None
        self.file_name = None
        self.thumbnail_path = None
        self.thumbnail_update_time = None
        # self.creation_time = None
        self.initial_thumbnail_created = False

        self.creation_time = datetime.now()  # 예시로 현재 시간을 사용

    def update_last_modified(self):
        latest_file = self.get_latest_file()
        if latest_file:
            self.file_name = os.path.basename(latest_file)
            self.last_modified_time = datetime.fromtimestamp(os.path.getmtime(latest_file)).strftime('%Y-%m-%d %H:%M:%S')
            self.creation_time = datetime.fromtimestamp(os.path.getctime(latest_file))
            self.generate_thumbnail()

    def get_latest_file(self):
        files = glob.glob(self.file_pattern)
        if not files:
            return None

        latest_file = max(files, key=os.path.getctime)
        return latest_file

    def generate_thumbnail(self):
        if self.file_name and self.creation_time:
            if not self.initial_thumbnail_created:
                # 최초 썸네일 생성 (파일 시작 1초 후)
                initial_thumbnail_path = os.path.join(self.work_directory, self.file_name.replace('.ts', '_0s.jpg'))
                initial_cmd = f"ffmpeg -y -i {os.path.join(self.work_directory, self.file_name)} -ss 1 -vframes 1 {initial_thumbnail_path}"
                print(f"Executing command: {initial_cmd}")
                result = subprocess.run(initial_cmd, shell=True)
                print(f"Command result: {result.returncode}")
                if result.returncode == 0:
                    self.thumbnail_path = initial_thumbnail_path
                    self.initial_thumbnail_created = True
                    print(f"Initial thumbnail created at {self.thumbnail_path}")
                else:
                    print("Failed to create initial thumbnail")

            current_time = datetime.now()
            # 이후 썸네일은 파일 생성 시간으로부터 매 분마다 생성
            if not self.thumbnail_update_time or (current_time - self.thumbnail_update_time).seconds >= 60:
                thumbnail_time = self.creation_time + timedelta(seconds=60 * (self.creation_time.minute + 1))  # 첫 번째 썸네일은 생성 후 1분
                print(f"########################################### {thumbnail_time} ##############################################")
                while thumbnail_time < current_time:
                    thumbnail_path = os.path.join(self.work_directory, f"{self.file_name.replace('.ts', '')}_{thumbnail_time.minute}.jpg")
                    cmd = f"ffmpeg -y -i {os.path.join(self.work_directory, self.file_name)} -ss {thumbnail_time.minute * 60} -vframes 1 {thumbnail_path}"
                    print(f"Executing command: {cmd}")
                    result = subprocess.run(cmd, shell=True)
                    print(f"Command result: {result.returncode}")
                    if result.returncode == 0:
                        self.thumbnail_path = thumbnail_path
                        print(f"Thumbnail created at {self.thumbnail_path}")
                    else:
                        print(f"Failed to create thumbnail at {thumbnail_time.minute} minute mark")
                    thumbnail_time += timedelta(minutes=1)

                self.thumbnail_update_time = current_time
                print(f"Updated thumbnail update time to {self.thumbnail_update_time}")
    @staticmethod
    def terminate(pid):
        """특정 PID와 그 자식 프로세스를 강제로 종료합니다."""
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

# 작업 상태를 주기적으로 업데이트하는 스레드
def update_task_status():
    while True:
        for task in tasks:
            task.update_last_modified()
        time.sleep(3)

# 스레드 시작
threading.Thread(target=update_task_status, daemon=True).start()
