import os
import re
from collections import Counter

def count_ip_prefixes_in_logs(log_dir):
    """
    xxx.xxx.xxx.* 형태로 그룹핑
    로그에서 302를 응답받은 IP를 횟수로 출력
    """
    prefix_counter = Counter()
    ip_pattern = re.compile(r'INFO - (\d+\.\d+\.\d+\.\d+)')  # IP 전체 추출

    # log 파일만 찾기
    for filename in os.listdir(log_dir):
        if filename.endswith('.log'):
            file_path = os.path.join(log_dir, filename)
            with open(file_path, encoding='utf-8') as f:
                for line in f:
                    # "GET / HTTP/1.1" 302 가 있는 라인만
                    if '"GET / HTTP/1.1" 302' in line:
                        # 예: INFO - 65.49.1.238 - - ...
                        m = ip_pattern.search(line)
                        if m:
                            full_ip = m.group(1)              # "65.49.1.238"
                            parts = full_ip.split('.')        # ["65", "49", "1", "238"]
                            if len(parts) == 4:
                                prefix = '.'.join(parts[:3])  # "65.49.1"
                                prefix_counter[prefix] += 1

    # 많은 순서대로 출력
    for prefix, count in prefix_counter.most_common():
        if count > 10:
            print(f"{prefix}.*: {count}회")


def count_ip_full_in_logs(log_dir: str, filter_substr='"GET / HTTP/1.1" 302'):
    """
    log_dir 아래의 *.log 파일에서
    - filter_substr 이 포함된 라인만 대상으로
    - 'INFO - <ip> -' 패턴의 전체 IP를 추출해
    - 빈도수를 출력한다.
    """
    ip_re = re.compile(r'INFO\s*-\s*(\d{1,3}(?:\.\d{1,3}){3})\b')
    counter = Counter()

    for filename in os.listdir(log_dir):
        if not filename.endswith('.log'):
            continue
        file_path = os.path.join(log_dir, filename)
        # 인코딩 문제를 피하려면 errors='ignore'
        with open(file_path, encoding='utf-8', errors='ignore') as f:
            for line in f:
                if filter_substr and filter_substr not in line:
                    continue
                m = ip_re.search(line)
                if m:
                    ip = m.group(1)
                    counter[ip] += 1

    # 많이 나온 순으로 출력
    for ip, cnt in counter.most_common():
        if cnt > 10:
            print(f"{ip} : {cnt}회")


count_ip_prefixes_in_logs('./logs')
# count_ip_full_in_logs('./logs')

