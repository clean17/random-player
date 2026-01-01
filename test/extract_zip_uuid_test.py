import os, uuid
from datetime import datetime
from zipfile import ZipFile

target_dir = r'F:\merci_server_file_dir\25.05'
os.makedirs(target_dir, exist_ok=True)

filename = 'compressed_25.05_.zip'

archive_path = os.path.join(target_dir, filename)
print(archive_path)
saved_files = []

def extract_zip_test(path):
    """
    zip을 풀어서 안에 들어 있던 실제 파일들 기준으로
    “새로 저장할 파일명 후보 리스트(원래이름+UUID)”를 만들어서 리턴하는 함수
    :param path:
    :return:
    """
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


