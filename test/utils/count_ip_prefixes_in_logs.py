import os
import re
from collections import Counter

def count_ip_prefixes_in_logs(log_dir):
    prefix_counter = Counter()
    # log 파일만 찾기
    for filename in os.listdir(log_dir):
        if filename.endswith('.log'):
            file_path = os.path.join(log_dir, filename)
            with open(file_path, encoding='utf-8') as f:
                for line in f:
                    # "GET / HTTP/1.1" 302 가 있는 라인만
                    if '"GET / HTTP/1.1" 302' in line:
                        # IP 추출: INFO - 65.49.1.238 - - ...
                        m = re.search(r'INFO - (\d+)\.', line)
                        if m:
                            prefix = m.group(1)
                            prefix_counter[prefix] += 1
    # 많은 순서대로 출력
    for prefix, count in prefix_counter.most_common():
        print(f"{prefix}: {count}회")

# 사용 예시
count_ip_prefixes_in_logs('./logs')
