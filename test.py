import subprocess
import threading
import time
import signal
import sys
import os
import glob
from datetime import datetime
import re

# 현재 날짜를 YYMMDD 형식으로 가져오기
current_date = datetime.now().strftime('%y%m%d')

# BAT 파일을 실행할 때 keyword와 url 인수를 전달
keyword = "output"
url = ""

# BAT 파일이 위치한 디렉토리
bat_file_directory = "f:/m"

# 작업 결과를 저장할 디렉토리 및 파일 패턴
output_directory = "f:/test"
file_pattern = f"{output_directory}/{current_date}{keyword}_*.ts"

# 전역 변수로 프로세스를 저장
process = None

def signal_handler(sig, frame):
    global process
    if process is not None:
        process.terminate()
        process.wait()
    sys.exit(0)

# SIGINT (Ctrl + C) 신호를 처리할 핸들러 설정
signal.signal(signal.SIGINT, signal_handler)

def get_latest_file(pattern):
    files = glob.glob(pattern)
    if not files:
        return None
    
    # 정규 표현식을 사용하여 파일 이름 끝의 숫자를 추출
    file_re = re.compile(rf"{current_date}{keyword}_(\d+)\.ts")
    latest_file = None
    max_index = -1
    
    for file in files:
        match = file_re.search(file)
        if match:
            index = int(match.group(1))
            if index > max_index:
                max_index = index
                latest_file = file
                
    return latest_file

def read_output(pipe):
    while True:
        line = pipe.readline()
        if not line:
            break
        print(line.strip())

# Windows Terminal을 사용하여 새로운 탭에서 BAT 파일 실행
cmd = f"cmd /c \"{bat_file_directory}/ff.bat {keyword} {url}\""
process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True, cwd=bat_file_directory)

# 프로세스 PID 가져오기
print(f"Started process with PID: {process.pid}")

# stdout과 stderr를 읽는 스레드 시작
stdout_thread = threading.Thread(target=read_output, args=(process.stdout,))
stderr_thread = threading.Thread(target=read_output, args=(process.stderr,))
stdout_thread.start()
stderr_thread.start()

# 파일의 마지막 수정 시간을 1초마다 출력
try:
    while True:
        latest_file = get_latest_file(file_pattern)
        if latest_file:
            last_modified_time = os.path.getmtime(latest_file)
            readable_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_modified_time))
            print(f"Last modified time of {latest_file}: {readable_time}")
        else:
            print(f"No matching files found with pattern: {file_pattern}")
        
        time.sleep(1)

        retcode = process.poll()  # None이면 아직 실행 중
        if retcode is not None:
            break

    # 스레드가 완료될 때까지 대기
    stdout_thread.join()
    stderr_thread.join()
except KeyboardInterrupt:
    signal_handler(signal.SIGINT, None)
