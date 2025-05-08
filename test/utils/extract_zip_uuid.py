import os, uuid
from datetime import datetime
from zipfile import ZipFile

target_dir = r'F:\merci_server_file_dir'
os.makedirs(target_dir, exist_ok=True)

filename = 'test.zip'

archive_path = os.path.join(target_dir, filename)
print(archive_path)
saved_files = []

def extract_zip_test(path):
    with ZipFile(path, 'r') as zip_ref:
        zip_ref.extractall(target_dir) # 실제로 압축 해제됨
        # zip 파일 내 모든 파일 경로 추가 (디렉터리 구조 유지)
        for extracted_file in zip_ref.namelist():
            extracted_path = os.path.join(target_dir, extracted_file)
            # 파일인 경우에만 추가
            if os.path.isfile(extracted_path):
                # saved_files.append(extracted_path)
                base_filename = os.path.basename(extracted_path)
                name, ext = os.path.splitext(base_filename)
                # now_str = datetime.now().strftime('%Y%m%d_%H%M%S')  # 날짜+시간
                # uuid_filename = f"{name}_{now_str}_{uuid.uuid4().hex}{ext.lower()}"
                uuid_filename = f"{name}_{uuid.uuid4().hex}{ext.lower()}"
                saved_files.append(uuid_filename)


    return saved_files

print(extract_zip_test(archive_path))


