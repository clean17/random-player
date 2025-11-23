"""
모든 파이썬 프로세스를 죽인다

import os,subprocess #모듈 호출
print(os.system('tasklist')) #프로세스 목록 출력
os.system('taskkill /f /im python.exe')
"""


"""
모든 파이썬 프로세스와 자식 프로세스를 죽인다

import subprocess

def kill_process_with_children(pid):
    try:
        subprocess.run(['taskkill', '/PID', str(pid), '/F', '/T'], check=True)
        print(f"Process {pid} and its children have been successfully terminated.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to terminate process {pid} and its children: {e}")

kill_process_with_children(8056)
"""
