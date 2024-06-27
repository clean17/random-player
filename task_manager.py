import json
import os
import subprocess
import time
import shutil

class TaskManager:
    def __init__(self, work_directory):
        self.tasks = []
        self.work_directory = work_directory
        self.load_tasks()

    def start_task(self, command, keyword):
        # Ensure the command runs through cmd.exe in Windows environments
        if command.endswith(".bat"):
            command = f"cmd.exe /c \"{command}\""
        process = subprocess.Popen(command, shell=True, cwd=self.work_directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        video_path = self.extract_video_path(command)
        try:
            thumbnail_path = self.generate_thumbnail(video_path)
        except Exception as e:
            thumbnail_path = None
            print(f"Failed to generate thumbnail for {video_path}: {e}")
        task_info = {'pid': process.pid, 'keyword': keyword, 'command': command, 'thumbnail': thumbnail_path, 'video_path': video_path}
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

    def generate_thumbnails(self, video_path, interval=60, duration=None):
        if duration:
            total_intervals = duration // interval
        else:
            # 비디오 전체 길이를 자동으로 계산하는 로직이 필요할 수 있음
            total_intervals = 100  # 임시 값

        for i in range(total_intervals):
            timestamp = i * interval
            output_filename = f"thumbnail_{timestamp:03d}.png"
            command = [
                "ffmpeg",
                "-ss", str(timestamp),
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",  # 품질 설정
                output_filename
            ]
            subprocess.run(command)
            print(f"Generated {output_filename}")
            time.sleep(interval)

    def get_running_tasks(self):
        self.tasks = [task for task in self.tasks if task['process'].poll() is None]
        return self.tasks

    def stop_task(self, pid):
        task = next((task for task in self.tasks if task['process'].pid == pid), None)
        if task:
            task['process'].terminate()
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
                            process = subprocess.Popen(task_info['command'], shell=True, cwd=self.work_directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                            self.tasks.append({'process': process, 'info': task_info})
                        except Exception as e:
                            print(f"Failed to load task {task_info['pid']}: {e}")
            except (json.JSONDecodeError, FileNotFoundError):
                print("tasks.json is empty or invalid")
