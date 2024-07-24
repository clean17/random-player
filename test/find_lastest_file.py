import os
import glob

class Task:
    def __init__(self, pid, file_pattern, work_directory):
        self.pid = pid
        self.file_pattern = file_pattern
        self.work_directory = work_directory

    def get_latest_file(self):
        search_pattern = os.path.join(self.work_directory, self.file_pattern)
        print(f"Search pattern: {search_pattern}")
        files = glob.glob(search_pattern)

        if not files:
            return None

        latest_file = max(files, key=os.path.getctime)
        return latest_file

# Example usage
settings = {'WORK_DIRECTORY': 'F:\\test'}
current_date_str = '240724'
keyword = '니니'
file_pattern = f"{current_date_str}{keyword}_*.ts"
tasks = []
tasks.append(Task(12345, file_pattern, settings['WORK_DIRECTORY']))

# Test the method
latest_file = tasks[0].get_latest_file()
print(latest_file)
