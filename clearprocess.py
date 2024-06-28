import os,subprocess #모듈 호출
print(os.system('tasklist')) #프로세스 목록 출력
os.system('taskkill /f /im python.exe')