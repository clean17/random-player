########################### 기본 사용 방법 (스레드 풀 생성 후 즉시 사용)
# from concurrent.futures import ThreadPoolExecutor
# import time
#
# # 작업 함수
# def task(n):
#     print(f"Task {n} starting")
#     time.sleep(2)  # 작업 시뮬레이션
#     print(f"Task {n} completed")
#     return f"Result of task {n}"
#
# # 스레드 풀 사용
# with ThreadPoolExecutor(max_workers=4) as executor:  # 스레드 4개
#     futures = [executor.submit(task, i) for i in range(10)]  # 10개의 작업 제출
#
# # 결과 처리
# for future in futures:
#     print(future.result())

############################ 스레드 풀을 미리 생성해 재사용
# from concurrent.futures import ThreadPoolExecutor
# import time
#
# # 스레드 풀 생성
# thread_pool = ThreadPoolExecutor(max_workers=4)
#
# # 작업 함수
# def task(n):
#     print(f"Task {n} starting")
#     time.sleep(2)  # 작업 시뮬레이션
#     print(f"Task {n} completed")
#     return f"Result of task {n}"
#
# # 여러 곳에서 스레드 풀 사용
# def process_tasks():
#     futures = [thread_pool.submit(task, i) for i in range(5)]
#     for future in futures:
#         print(future.result())
#
# process_tasks()
# process_tasks()
#
# # 스레드 풀 종료 (명시적으로 닫아야 함)
# thread_pool.shutdown()

############################## 필요한 경우 동적 설정

from concurrent.futures import ThreadPoolExecutor
import os

# CPU 코어 수에 따라 동적 스레드 풀 크기 설정
num_threads = os.cpu_count() * 2  # CPU 코어 수의 2배
thread_pool = ThreadPoolExecutor(max_workers=num_threads)

# 작업 함수
def task(n):
    print(f"Task {n} starting")
    return f"Task {n} completed"

futures = [thread_pool.submit(task, i) for i in range(20)]
for future in futures:
    print(future.result())

'''
1. 스레드 풀이 자동 생성 가능:
    ThreadPoolExecutor는 필요할 때 즉시 생성 가능하며, 사전 설정은 필수가 아닙니다.
2. 스레드 풀 종료:
    스레드 풀이 더 이상 필요하지 않다면 **shutdown()**을 호출해야 합니다.
    예: thread_pool.shutdown(wait=True)
3. with 구문:
    스레드 풀을 한 번 사용하고 자동으로 종료하려면 with 구문을 사용하세요
    
    with ThreadPoolExecutor(max_workers=4) as executor:
    executor.submit(task, 1)
'''