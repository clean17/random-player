import os
import re

def rename_m4a_files(directory):
    for filename in os.listdir(directory):
        if filename.lower().endswith('.m4a'):
            # 날짜와 시간 추출 (예: 20250422_162433)
            match = re.search(r'(\d{8})_(\d{6})', filename)
            if match:
                full_date, time = match.groups()
                short_date = full_date[2:]  # 20250422 → 250422
                new_name = f"음성 {short_date}_{time}.m4a"
                old_path = os.path.join(directory, filename)
                new_path = os.path.join(directory, new_name)

                print(f"🔁 {filename} → {new_name}")
                os.rename(old_path, new_path)

    print("✅ 이름 변경 완료")

# 사용 예시
rename_m4a_files(r"C:\Users\user\Downloads\증거")
