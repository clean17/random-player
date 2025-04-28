import os
import re
from datetime import datetime, timedelta
import zipfile
from config.config import settings

TEMP_IMAGE_DIR = settings['TEMP_IMAGE_DIR']
TRIP_IMAGE_DIR = settings['TRIP_IMAGE_DIR']
DIRECTORIES_TO_COMPRESS = [TEMP_IMAGE_DIR, TRIP_IMAGE_DIR]

# CPU 바운드 작업: 디렉토리를 압축하는 함수
def compress_directory_to_zip():
    for dir_to_compress in DIRECTORIES_TO_COMPRESS:

        if not os.path.exists(dir_to_compress):
            print(f"Directory does not exist: {dir_to_compress}")
            continue

        # ✅ 디렉토리 이름이 '영상'으로 끝나면 압축하지 않고 건너뛰기
        if os.path.basename(dir_to_compress).endswith('영상'):
            print(f"Skip compressing directory (ends with '영상'): {dir_to_compress}")
            continue

        # 하위 디렉토리 목록 수집
        subdirs = []
        for item in os.listdir(dir_to_compress):
            subdir_path = os.path.join(dir_to_compress, item)
            if os.path.isdir(subdir_path):
                subdirs.append(subdir_path)

        if subdirs:
            # 하위 디렉토리가 있으면 각 하위 디렉토리를 압축
            for subdir_path in subdirs:
                compress_directory(subdir_path)
        else:
            # 하위 디렉토리가 없으면 현재 디렉토리 내의 파일들을 압축
            compress_directory(dir_to_compress)

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    print(f"### {current_time} - All Directory successfully compressed")


def compress_directory(directory):
    #     print(f'compressing to {directory}')
    today_str = datetime.now().strftime("%y%m%d")
    base_name = os.path.basename(directory)
    prefix = f"compressed_{base_name}_"
    new_zip_filename = f"{prefix}{today_str}.zip"
    new_zip_filepath = os.path.join(directory, new_zip_filename)
    old_zip_filename = f"{prefix}.zip"
    old_zip_filepath = os.path.join(directory, old_zip_filename)

    # 압축 전에 이전 날짜의 압축 파일 삭제
    pattern = re.compile(rf"^{re.escape(prefix)}\d{{6}}\.zip$")

    for filename in os.listdir(directory):
        if pattern.match(filename) and filename != new_zip_filename:
            try:
                os.remove(os.path.join(directory, filename))
                print(f"🧹 이전 압축파일 삭제: {filename}")
            except Exception as e:
                print(f"⚠️ 파일 삭제 실패: {filename}, {e}")

    try:
        # ZIP 파일 생성 (기본 ZIP_STORED : 압축 x, ZIP_DEFLATED : deflate 알고리즘으로 압축)
        # with문은 컨텍스트 매니저 역할 + 블록이 끝나면 자동으로 리소스를 정리 (close() 호출)
        with zipfile.ZipFile(new_zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # os.walk()는 디렉터리 내의 모든 파일과 폴더를 재귀적으로 탐색하는 데 사용하는 Python의 내장 함수
            for root, dirs, files in os.walk(directory):
                for file in files: # files만 대상으로 하므로 폴더는 압축하지 않는다
                    # 압축 파일 자체는 포함하지 않음
                    if file == old_zip_filename or file.lower().endswith('.zip'):
                        continue
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, directory) # file과 명칭 동일
                    zipf.write(file_path, arcname)
    except Exception as e:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        print(f"### {current_time} - Error while compressing {directory}: {e}")
        return

    try:
        # 기존 압축파일이 있다면 삭제
        # if os.path.exists(old_zip_filepath):
        #     os.remove(old_zip_filepath)
        # # 새 압축파일의 이름을 기존 압축파일명으로 변경
        # os.rename(new_zip_filepath, old_zip_filepath)

        # 압축 끝난 파일을 .zip01 으로 변경
        zip01_path = old_zip_filepath + "01"
        os.rename(new_zip_filepath, zip01_path)

        # 디렉토리 내의 모든 .zip 파일 삭제
        for f in os.listdir(directory):
            if f.lower().endswith('.zip'):
                try:
                    os.remove(os.path.join(directory, f))
                except Exception as e:
                    print(f"삭제 실패: {f} → {e}")

        # .zip01 → .zip 으로 다시 이름 변경
        os.rename(zip01_path, old_zip_filepath)
    except Exception as e:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        print(f"### {current_time} - Error while renaming zip file: {e}")
