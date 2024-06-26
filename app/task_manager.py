import cmd
import threading
import time
import os
import glob
import subprocess
from datetime import datetime

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
        self.creation_time = datetime.now()  # 예시로 현재 시간을 사용
        self.initial_thumbnail_created = False
        self.thumbnail_duration = 0;


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
        current_time = datetime.now()

        if self.file_name and self.creation_time:
            if not self.initial_thumbnail_created:
                # 최초 썸네일 생성 (파일 시작 1초 후)
                initial_thumbnail_path = os.path.join(self.work_directory, self.file_name.replace('.ts', '_thumb.jpg'))
                initial_cmd = f"ffmpeg -y -i {os.path.join(self.work_directory, self.file_name)} -ss 1 -vframes 1 {initial_thumbnail_path}"
                result = subprocess.run(initial_cmd, shell=True, capture_output=True, text=True, encoding='utf-8')
                if result.returncode == 0:
                    self.thumbnail_path = initial_thumbnail_path
                    self.initial_thumbnail_created = True
                    self.thumbnail_update_time = current_time.isoformat()
                    # print(f"Initial thumbnail created at {self.thumbnail_path}")
                else:
                    print("Failed to create initial thumbnail")

            elif self.thumbnail_update_time:
                last_update_time = datetime.fromisoformat(self.thumbnail_update_time)

                # 이후 썸네일은 마지막 썸네일 생성 시간으로부터 매 분마다 생성
                if (current_time - last_update_time).total_seconds() >= 60:
                    self.thumbnail_duration += 60
                    thumbnail_path = os.path.join(self.work_directory, f"{self.file_name.replace('.ts', '')}_thumb.jpg")
                    cmd = f"ffmpeg -y -i {os.path.join(self.work_directory, self.file_name)} -ss {self.thumbnail_duration} -frames:v 1 {thumbnail_path}"
                    # print(f"Executing command: {cmd}")
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8')
                    if result.returncode == 0:
                        self.thumbnail_path = thumbnail_path
                        self.thumbnail_update_time = current_time.isoformat()
                    else:
                        print(f"Failed to create thumbnail at {self.thumbnail_duration} minute mark")

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

# 작업 상태를 주기적으로 업데이트하는 스레드
def update_task_status():
    while True:
        for task in tasks:
            task.update_last_modified()
        time.sleep(10)

# 스레드 시작
threading.Thread(target=update_task_status, daemon=True).start()