from flask import Blueprint, Flask, render_template, request, jsonify
import os
from datetime import datetime
from flask_login import login_required
from config import settings
from werkzeug.utils import secure_filename
from threading import Thread
from zipfile import ZipFile

upload = Blueprint('upload', __name__)

TEMP_IMAGE_DIR = settings['TEMP_IMAGE_DIR']
HTM_DIRECTORY = settings['HTM_DIRECTORY']

@upload.route('/', methods=['GET'])
@login_required
def get_file_upload_html():
    title_list = sorted([d for d in os.listdir(TEMP_IMAGE_DIR) if os.path.isdir(os.path.join(TEMP_IMAGE_DIR, d))])
    return render_template('file_uploader.html', title_list=title_list)

@upload.route('/', methods=['POST'])
@login_required
def upload_file():
    if 'files[]' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    uploaded_files = request.files.getlist("files[]")  # Uppy로 업로드된 파일 리스트
    title = request.form.get("title", "no_title")  # 'title' 데이터 받기
    if title == "":
        title = "no_title"
    saved_files = []

    # 오늘 날짜로 디렉토리 생성
    today = datetime.now().strftime('%Y%m%d')
    # time_stamp = datetime.now().strftime('%H%M%S')
    target_dir = os.path.join(TEMP_IMAGE_DIR, title)
    #target_dir = TEMP_IMAGE_DIR
    if title == 'htm':
        target_dir = HTM_DIRECTORY

    os.makedirs(target_dir, exist_ok=True)  # 날짜별 디렉토리 생성

    for file in uploaded_files:
        if file and file.filename:  # 파일명이 있는 경우 저장
            filename = secure_filename(file.filename)
            file_ext = os.path.splitext(filename)[1].lower()

            # 압축 파일인 경우
            if file_ext in ['.zip']:
                # 임시로 업로드된 압축파일 저장
                archive_path = os.path.join(target_dir, filename)
                file.save(archive_path)

                # 압축 해제 후, 추출된 파일들의 경로를 saved_files에 추가
                try:
                    with ZipFile(archive_path, 'r') as zip_ref:
                        zip_ref.extractall(target_dir)
                        # zip 파일 내 모든 파일 경로 추가 (디렉터리 구조 유지)
                        for extracted_file in zip_ref.namelist():
                            extracted_path = os.path.join(target_dir, extracted_file)
                            # 파일인 경우에만 추가
                            if os.path.isfile(extracted_path):
                                saved_files.append(extracted_path)
                except Exception as e:
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
                    print(f"### {current_time} - Error while extracting {archive_path}: {e}")
                finally:
                    # 압축 해제 후 임시 압축파일은 삭제 (필요시)
                    if os.path.exists(archive_path):
                        os.remove(archive_path)
            else:
                file_path = os.path.join(target_dir, f"{filename}")
                file.save(file_path)
                saved_files.append(file_path)

    return jsonify({"status": "success", "files": saved_files})

# def handle_uploaded_files(saved_files, title):
#     # 예: 압축 작업, 이미지 처리 등
#     if title != 'htm':
#         zip_path = os.path.join(TEMP_IMAGE_DIR, f"{title}.zip")
#         with ZipFile(zip_path, 'w') as zipf:
#             for f in saved_files:
#                 zipf.write(f, arcname=os.path.basename(f))
#         print(f"압축 완료: {zip_path}")
#
# @upload.route('/', methods=['POST'])
# @login_required
# def upload_file():
#     if 'files[]' not in request.files:
#         return jsonify({"error": "No file uploaded"}), 400
#
#     uploaded_files = request.files.getlist("files[]")
#     title = request.form.get("title", "Untitled")
#     saved_files = []
#
#     target_dir = HTM_DIRECTORY if title == 'htm' else os.path.join(TEMP_IMAGE_DIR, title)
#     os.makedirs(target_dir, exist_ok=True)
#
#     for file in uploaded_files:
#         if file and file.filename:
#             filename = secure_filename(file.filename)
#             file_path = os.path.join(target_dir, filename)
#             file.save(file_path)
#             saved_files.append(file_path)
#
#     # 후처리 비동기로 실행
#     Thread(target=handle_uploaded_files, args=(saved_files, title)).start()
#
#     return jsonify({"status": "success", "files": saved_files})