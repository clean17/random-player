import os
import shutil

def move_files_to_parent(parent_dir):
    # parent_dir 안의 모든 항목 확인
    for root, dirs, files in os.walk(parent_dir, topdown=False):
        # 현재 디렉토리의 파일들을 상위 디렉토리로 이동
        for file in files:
            src_path = os.path.join(root, file)
            dst_path = os.path.join(parent_dir, file)

            # 같은 이름의 파일이 이미 있으면 이름 변경
            if os.path.exists(dst_path):
                base, ext = os.path.splitext(file)
                i = 1
                while os.path.exists(os.path.join(parent_dir, f"{base}_{i}{ext}")):
                    i += 1
                dst_path = os.path.join(parent_dir, f"{base}_{i}{ext}")

            shutil.move(src_path, dst_path)

        # 빈 디렉토리 삭제
        for d in dirs:
            dir_path = os.path.join(root, d)
            if not os.listdir(dir_path):
                os.rmdir(dir_path)

# 사용 예시
parent_directory = "G:/tr"
move_files_to_parent(parent_directory)