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
