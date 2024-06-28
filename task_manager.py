import signal
import threading
import time
import os
import glob
import subprocess
from datetime import datetime

tasks = []

class Task:
    def __init__(self, pid, file_pattern):
        self.pid = pid
        self.file_pattern = file_pattern
        self.last_modified_time = None
        self.file_name = None
        self.thumbnail_path = None

    def update_last_modified(self):
        latest_file = self.get_latest_file()
        if latest_file:
            self.file_name = latest_file
            self.last_modified_time = datetime.fromtimestamp(os.path.getmtime(latest_file))
            self.generate_thumbnail()

    def get_latest_file(self):
        files = glob.glob(self.file_pattern)
        if not files:
            return None
        
        latest_file = max(files, key=os.path.getctime)
        return latest_file

    def generate_thumbnail(self):
        if self.file_name:
            thumbnail_path = self.file_name.replace('.ts', '.jpg')
            cmd = f"ffmpeg -i {self.file_name} -ss 00:00:01.000 -vframes 1 {thumbnail_path}"
            subprocess.call(cmd, shell=True)
            self.thumbnail_path = thumbnail_path

    def terminate(self):
        try:
            os.kill(self.pid, signal.SIGTERM)
        except OSError:
            pass

# 현재 날짜를 YYMMDD 형식으로 가져오기
def current_date():
    return datetime.now().strftime('%y%m%d')

# 작업 상태를 주기적으로 업데이트하는 스레드
def update_task_status():
    while True:
        for task in tasks:
            task.update_last_modified()
        time.sleep(1)

# 스레드 시작
threading.Thread(target=update_task_status, daemon=True).start()
