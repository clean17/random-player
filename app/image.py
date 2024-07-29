# image.py
import os
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, send_from_directory
from flask_login import login_required
from send2trash import send2trash
from jinja2 import Environment

image_bp = Blueprint('image', __name__)

# 설정
IMAGE_DIR = os.path.join(os.getcwd(), 'images')
MOVE_DIR = os.path.join(os.getcwd(), 'move')
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(MOVE_DIR, exist_ok=True)

def get_images(start, count):
    images = os.listdir(IMAGE_DIR)
    images.sort()
    return images[start:start + count]

@image_bp.route('/images', methods=['GET'])
@login_required
def image_list():
    page = int(request.args.get('page', 1))
    start = (page - 1) * 50
    images = get_images(start, 50)
    total_images = len(os.listdir(IMAGE_DIR))
    total_pages = (total_images + 49) // 50

    return render_template('image_list.html', images=images, page=page, total_pages=total_pages)

@image_bp.route('/move_image/<filename>', methods=['POST'])
@login_required
def move_image(filename):
    src_path = os.path.join(IMAGE_DIR, filename)
    dest_path = os.path.join(MOVE_DIR, filename)
    if os.path.exists(src_path):
        os.rename(src_path, dest_path)
        return jsonify({'status': 'success'})
    else:
        return jsonify({'status': 'error', 'message': 'File not found'}), 404

@image_bp.route('/delete_images', methods=['POST'])
@login_required
def delete_images():
    images = os.listdir(IMAGE_DIR)
    moved_images = os.listdir(MOVE_DIR)

    for image in images:
        if image not in moved_images:
            send2trash(os.path.join(IMAGE_DIR, image))

    return jsonify({'status': 'success'})

@image_bp.route('/images/<filename>')
@login_required
def get_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

# Jinja2 템플릿에서 max와 min 함수 사용을 위한 설정
def environment(**options):
    env = Environment(**options)
    env.globals.update(max=max, min=min)
    return env
