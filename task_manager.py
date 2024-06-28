import threading
import time
import os
import glob
import subprocess
import signal
import win32api
import win32con
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
        self.creation_time = None
        self.initial_thumbnail_created = False

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
                initial_thumbnail_path = os.path.join(self.work_directory, self.file_name.replace('.ts', '_1sec.jpg'))
                initial_cmd = f"ffmpeg -y -i {os.path.join(self.work_directory, self.file_name)} -ss 1 -vframes 1 {initial_thumbnail_path}"
                subprocess.call(initial_cmd, shell=True)
                self.thumbnail_path = initial_thumbnail_path
                self.initial_thumbnail_created = True

            current_time = datetime.now()
            # 이후 썸네일은 파일 생성 시간으로부터 매 분마다 생성
            if not self.thumbnail_update_time or (current_time - self.thumbnail_update_time).seconds >= 60:
                thumbnail_time = self.creation_time + timedelta(seconds=60 * (self.creation_time.minute + 1))  # 첫 번째 썸네일은 생성 후 1분
                while thumbnail_time < current_time:
                    thumbnail_path = os.path.join(self.work_directory, f"{self.file_name.replace('.ts', '')}_{thumbnail_time.minute}min.jpg")
                    cmd = f"ffmpeg -y -i {os.path.join(self.work_directory, self.file_name)} -ss {thumbnail_time.minute * 60} -vframes 1 {thumbnail_path}"
                    subprocess.call(cmd, shell=True)
                    self.thumbnail_path = thumbnail_path
                    thumbnail_time += timedelta(minutes=1)

                self.thumbnail_update_time = current_time

    def terminate(self):
        try:
            # 프로세스 그룹에 CTRL+C 이벤트 전송
            if self.process.pid > 0:  # 유효한 PID가 있는지 확인
                win32api.GenerateConsoleCtrlEvent(win32con.CTRL_C_EVENT, -self.process.pid)  # 프로세스 그룹 ID에 음수를 사용
        except Exception as e:
            print("Failed to send CTRL+C:", e)


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
