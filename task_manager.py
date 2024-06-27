import json
import os
import signal
import subprocess
import time
import shutil
import threading
class TaskManager:
    def __init__(self, work_directory):
        self.tasks = []
        self.work_directory = work_directory
        self.load_tasks()

    def start_task(self, command, keyword):
        if command.endswith(".bat"):
            command = f"cmd.exe /c \"{command}\""
        process = subprocess.Popen(command, shell=True, cwd=self.work_directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        video_path = self.extract_video_path(command)
        try:
            self.start_thumbnail_generation(video_path)
        except Exception as e:
            print(f"Failed to generate thumbnails for {video_path}: {e}")
        task_info = {'pid': process.pid, 'keyword': keyword, 'command': command, 'video_path': video_path}
        self.tasks.append({'process': process, 'info': task_info})
        self.save_tasks()
        return process.pid

    def extract_video_path(self, command):
        parts = command.split()
        return parts[-1].strip('"')

    def generate_thumbnail(self, video_path):
        thumbnail_name = f"thumbnail_{int(time.time())}.png"
        thumbnail_path = os.path.join(self.work_directory, thumbnail_name)
        static_thumbnail_path = os.path.join('static', thumbnail_name)
        command = f"ffmpeg -i \"{video_path}\" -ss 00:00:01.000 -vframes 1 \"{thumbnail_path}\""
        subprocess.run(command, shell=True)
        shutil.copy(thumbnail_path, static_thumbnail_path)
        return static_thumbnail_path

    def generate_thumbnails(self, video_path, interval=60):
        while True:
            thumbnail_name = f"thumbnail_{int(time.time())}.png"
            thumbnail_path = os.path.join(self.work_directory, thumbnail_name)
            static_thumbnail_path = os.path.join('static', thumbnail_name)
            command = f"ffmpeg -i \"{video_path}\" -ss 00:00:01.000 -vframes 1 \"{thumbnail_path}\""
            subprocess.run(command, shell=True)
            shutil.copy(thumbnail_path, static_thumbnail_path)
            print(f"Generated {static_thumbnail_path}")
            time.sleep(interval)

    def start_thumbnail_generation(self, video_path):
        thread = threading.Thread(target=self.generate_thumbnails, args=(video_path,))
        thread.daemon = True  # 데몬 쓰레드로 설정하여 메인 프로그램이 종료될 때 자동으로 종료되도록 함
        thread.start()

    def get_running_tasks(self):
        self.tasks = [task for task in self.tasks if task['process'].poll() is None]
        return self.tasks

    def stop_task(self, pid):
        task = next((task for task in self.tasks if task['process'].pid == pid), None)
        if task:
            os.kill(task['process'].pid, signal.SIGTERM)
            self.tasks.remove(task)
            self.save_tasks()

    def save_tasks(self):
        tasks_info = [task['info'] for task in self.tasks if task['process'].poll() is None]
        with open('tasks.json', 'w') as f:
            json.dump(tasks_info, f)

    def load_tasks(self):
        if os.path.exists('tasks.json'):
            try:
                with open('tasks.json', 'r') as f:
                    tasks_info = json.load(f)
                    for task_info in tasks_info:
                        try:
                            process = subprocess.Popen(task_info['command'], shell=True, cwd=self.work_directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
                            self.tasks.append({'process': process, 'info': task_info})
                            self.start_thumbnail_generation(task_info['video_path'])
                        except Exception as e:
                            print(f"Failed to load task {task_info['pid']}: {e}")
            except (json.JSONDecodeError, FileNotFoundError):
                print("tasks.json is empty or invalid")
