import os
import glob # 와일드카드(*, ?) 기반 파일 검색

class Task:
    def __init__(self, pid, file_pattern, work_directory):
        self.pid = pid
        self.file_pattern = file_pattern
        self.work_directory = work_directory

    def get_latest_file(self):
        search_pattern = os.path.join(self.work_directory, self.file_pattern) # 패턴 생성
        print(f"Search pattern: {search_pattern}")
        files = glob.glob(search_pattern) # 와일드 카드 검색

        if not files:
            return None

        latest_file = max(files, key=os.path.getctime) # os.path.getctime(path) 파일의 생성 시간 반환, 리눅스는 메타데이터 변경 시간
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
