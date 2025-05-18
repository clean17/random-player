# file.py
import os
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, send_from_directory, abort
from flask_login import login_required, current_user
from config.config import settings

file_bp = Blueprint('file', __name__)

# 설정
IMAGE_DIR = settings['IMAGE_DIR']
REF_IMAGE_DIR = settings['REF_IMAGE_DIR']
TRIP_IMAGE_DIR = settings['TRIP_IMAGE_DIR']
TEMP_IMAGE_DIR = settings['TEMP_IMAGE_DIR']

@file_bp.route('/files')
@login_required
def get_file():
    filename = request.args.get('filename')
    dir = request.args.get('dir')
    selected_dir = request.args.get('selected_dir', '')

    if dir == 'image':
        base_dir = IMAGE_DIR
    elif dir == 'refine':
        base_dir = REF_IMAGE_DIR
    elif dir == 'trip':
        base_dir = TRIP_IMAGE_DIR
    elif dir == 'temp':
        base_dir = TEMP_IMAGE_DIR
        if selected_dir:
            base_dir = os.path.join(TEMP_IMAGE_DIR, selected_dir)
    else:
        abort(400, 'Invalid dir')

    # ✅ 기존 파일 경로에서 반환
    return send_from_directory(base_dir, filename)