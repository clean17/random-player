from flask import Blueprint, Flask, render_template, request, jsonify
import os
from datetime import datetime
from flask_login import login_required
from config import settings
from werkzeug.utils import secure_filename

upload = Blueprint('upload', __name__)

TEMP_IMAGE_DIR = settings['TEMP_IMAGE_DIR']
HTM_DIRECTORY = settings['HTM_DIRECTORY']

@upload.route('/', methods=['GET'])
@login_required
def get_file_upload_html():
    return render_template('file_uploader.html')

@upload.route('/', methods=['POST'])
@login_required
def upload_file():
    if 'files[]' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    uploaded_files = request.files.getlist("files[]")  # Uppy로 업로드된 파일 리스트
    title = request.form.get("title", "Untitled")  # 'title' 데이터 받기
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
            file_path = os.path.join(target_dir, f"{filename}")
            file.save(file_path)
            saved_files.append(file_path)

    return jsonify({"status": "success", "files": saved_files})