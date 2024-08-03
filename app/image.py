# image.py
import os
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, send_from_directory
from flask_login import login_required
from send2trash import send2trash
from jinja2 import Environment
from config import settings

image_bp = Blueprint('image', __name__)
limit_page_num = 50

# 설정
IMAGE_DIR = settings['IMAGE_DIR']
# IMAGE_DIR = os.path.join(os.getcwd(), 'images')
MOVE_DIR = settings['MOVE_DIR']
REF_IMAGE_DIR = settings['REF_IMAGE_DIR']
# MOVE_DIR = os.path.join(os.getcwd(), 'move')
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(MOVE_DIR, exist_ok=True)

def get_images(start, count):
    images = os.listdir(IMAGE_DIR)
    images.sort()
    return images[start:start + count]

def get_ref_images(start, count):
    images = os.listdir(REF_IMAGE_DIR)
    images.sort()
    return images[start:start + count]

@image_bp.route('/images', methods=['GET'])
@login_required
def image_list():
    page = int(request.args.get('page', 1))
    start = (page - 1) * limit_page_num
    images = get_images(start, limit_page_num)
    total_images = len(os.listdir(IMAGE_DIR))
    total_pages = (total_images + limit_page_num-1) // limit_page_num

    return render_template('image_list.html', images=images, page=page, total_pages=total_pages)

@image_bp.route('/ref_images', methods=['GET'])
@login_required
def ref_image_list():
    page = int(request.args.get('page', 1))
    start = (page - 1) * limit_page_num
    images = get_ref_images(start, limit_page_num)
    total_images = len(os.listdir(REF_IMAGE_DIR))
    total_pages = (total_images + limit_page_num-1) // limit_page_num

    return render_template('ref_image_list.html', images=images, page=page, total_pages=total_pages)

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
    images_to_delete = request.form.getlist('images[]')
    moved_images = os.listdir(MOVE_DIR)

    for image in images_to_delete:
        if image not in moved_images:
            send2trash(os.path.join(IMAGE_DIR, image))

    page = int(request.form.get('page', 1))
    return redirect(url_for('image.image_list', page=page))

@image_bp.route('/images/<filename>')
@login_required
def get_image(filename):
    return send_from_directory(IMAGE_DIR, filename)

@image_bp.route('/ref_images/<filename>')
@login_required
def get_ref_image(filename):
    return send_from_directory(REF_IMAGE_DIR, filename)

# Jinja2 템플릿에서 max와 min 함수 사용을 위한 설정
def environment(**options):
    env = Environment(**options)
    env.globals.update(max=max, min=min)
    return env
