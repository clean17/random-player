import threading
import time
import os
import glob
from datetime import datetime

tasks = []

class Task:
    def __init__(self, pid, file_pattern):
        self.pid = pid
        self.file_pattern = file_pattern
        self.last_modified_time = None
        self.file_name = None

    def update_last_modified(self):
        latest_file = self.get_latest_file()
        if latest_file:
            self.file_name = latest_file
            self.last_modified_time = os.path.getmtime(latest_file)

    def get_latest_file(self):
        files = glob.glob(self.file_pattern)
        if not files:
            return None
        
        latest_file = max(files, key=os.path.getctime)
        return latest_file

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
