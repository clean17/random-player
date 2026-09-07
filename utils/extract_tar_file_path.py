import os
import tarfile

BASE_DIR = r"C:\Users\user\Downloads\03-1.SNS 마이그레이션 시작 20260825"
OUTPUT_FILE = os.path.join(BASE_DIR, "all_tar_file_paths.txt")

paths = set()

for file_name in os.listdir(BASE_DIR):
    if not file_name.lower().endswith(".tar.gz"):
        continue

    tar_path = os.path.join(BASE_DIR, file_name)

    print(f"처리중: {file_name}")

    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            for member in tar:

                # 디렉토리 제외
                if not member.isfile():
                    continue

                path = member.name.replace("\\", "/")

                # 예:
                # sns_extract/LARIS_DATA/FILE/...
                # ↓
                # /LARIS_DATA/FILE/...
                if path.startswith("sns_extract/"):
                    path = "/" + path[len("sns_extract/"):]
                elif not path.startswith("/"):
                    path = "/" + path

                paths.add(path)

    except Exception as e:
        print(f"오류: {file_name}")
        print(e)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for path in sorted(paths):
        f.write(path + "\n")

print()
print("완료")
print(f"총 파일 경로 수: {len(paths):,}")
print(f"결과 파일: {OUTPUT_FILE}")