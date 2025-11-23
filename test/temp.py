# from datetime import datetime, timedelta
# import pytz
# import time
#
# utc_now = datetime.utcnow()
# utc_now = utc_now.replace(tzinfo=pytz.utc)  # UTC timezone 명시
# korea_tz = pytz.timezone('Asia/Seoul')
# now = utc_now.astimezone(korea_tz)
#
# print(now)
#
# print(datetime.now())
#
# print(time.time())
#
# dt = datetime.fromtimestamp(time.time())  # 현지(시스템 타임존) datetime 객체로 변환
# print(dt)  # datetime.now()와 동일 포맷
# print(datetime.now().timestamp())



import schedule
import time
import subprocess

def test_scheduler():
    script_dir = r'C:\my-project\AutoSales.py'
    venv_activate = r'venv\Scripts\activate'
    py_script = r'python test_scheduler.py'

    # 전체 명령어 (venv 활성화 → 스크립트 실행)
    # 주의: activate.bat는 cmd에서만 인식, powershell은 다름
    cmd = f'cmd /c "cd /d {script_dir} && {venv_activate} && {py_script} && exit"'

    # subprocess 실행
    process = subprocess.Popen(
        cmd,
        # creationflags=subprocess.CREATE_NEW_CONSOLE,  # ⭐️ 새 콘솔창에서 실행!
        stdout=subprocess.PIPE, # 버퍼가 꽉 차서 죽는다 ? > 서브프로세스(=실행된 명령)의 표준출력(stdout)이 '파이썬 부모 프로세스'로 파이프로 전달
        stderr=subprocess.PIPE,
        text=True,
        shell=True,
        encoding='utf-8'
    )
    stdout, stderr = process.communicate()
    # print("STDOUT:", stdout)
    # print("STDERR:", stderr)

schedule.every(1).seconds.do(test_scheduler)

while True:
    schedule.run_pending()
    time.sleep(1)







"""
드라이브의 남은 용량을 구하는 함수
>> F: 드라이브의 남은 용량: 160.93 GB

PowerShell 명령어 : Get-PSDrive -PSProvider FileSystem
"""
import shutil

def get_drive_free_space(drive):
    total, used, free = shutil.disk_usage(drive)
    free_gb = free / (1024 ** 3)  # Convert bytes to GB
    return free_gb

drive = 'F:'
free_space_gb = get_drive_free_space(drive)
print(f"{drive} 드라이브의 남은 용량: {free_space_gb:.2f} GB")



"""
텍스트 파일을 한 줄씩 읽어서 인덱스를 맨 앞에 붙여서 새로운 파일을 생성
"""
input_file = "data/chat.txt"    # 기존 파일 경로
output_file = "data/chat_2.txt"  # 수정된 결과를 저장할 파일 경로

with open(input_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

with open(output_file, "w", encoding="utf-8") as f:
    for idx, line in enumerate(lines, start=1):
        f.write(f"{idx} | {line.strip()}\n")



"""
문자 인코딩 변경 [ISO >> UTF-8]
"""
# 깨진 문자 (예: UTF-8을 ISO-8859-1로 잘못 인코딩한 경우)
broken_string = 'ê°ë°ìë²'

# 깨진 문자열을 바이너리 데이터로 변환
bytes_data = broken_string.encode('ISO-8859-1')

# 바이너리 데이터를 올바른 인코딩 방식으로 디코딩
correct_string = bytes_data.decode('UTF-8')

print(correct_string)