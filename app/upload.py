from flask import Blueprint, Flask, render_template, request, jsonify
import os
from datetime import datetime
from flask_login import login_required
from config import settings

upload = Blueprint('upload', __name__)

TEMP_IMAGE_DIR = settings['TEMP_IMAGE_DIR']

@upload.route('/', methods=['GET'])
@login_required
def get_file_upload_html():
    return render_template('file_uploader.html')

@upload.route('/', methods=['POST'])
@login_required
def upload_file():
    # 오늘 날짜로 디렉토리 생성
    today = datetime.now().strftime('%Y%m%d')
    # time_stamp = datetime.now().strftime('%H%M%S')
    #     target_dir = os.path.join(TEMP_IMAGE_DIR, today)
    target_dir = TEMP_IMAGE_DIR

    if not os.path.exists(target_dir):
        os.makedirs(target_dir)  # 날짜별 디렉토리 생성

    uploaded_files = request.files.getlist("files[]")  # Uppy로 업로드된 파일 리스트
    saved_files = []

    for file in uploaded_files:
        if file.filename:  # 파일명이 있는 경우 저장
            file_path = os.path.join(target_dir, f"{file.filename}")
            file.save(file_path)
            saved_files.append(file_path)

    return jsonify({"status": "success", "files": saved_files})