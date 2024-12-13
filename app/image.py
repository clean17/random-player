# image.py
import os
import re
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, send_from_directory, abort
from flask_login import login_required
from send2trash import send2trash
from jinja2 import Environment
from config import settings
import random
import time
from urllib.parse import unquote
import shutil

image_bp = Blueprint('image', __name__)
limit_page_num = 100
shuffled_images = None

# 설정
IMAGE_DIR = settings['IMAGE_DIR']
# IMAGE_DIR = os.path.join(os.getcwd(), 'images')
MOVE_DIR = settings['MOVE_DIR']
REF_IMAGE_DIR = settings['REF_IMAGE_DIR']
TRIP_IMAGE_DIR = settings['TRIP_IMAGE_DIR']
KOSPI_DIR = settings['KOSPI_DIR']
KOSDAQ_DIR = settings['KOSDAQ_DIR']
SP500_DIR = settings['SP500_DIR']

# 시장 디렉터리 매핑
DIRECTORY_MAP = {
    'kospi': KOSPI_DIR,
    'kospi_10': KOSDAQ_DIR,
    'sp500': SP500_DIR
}

# MOVE_DIR = os.path.join(os.getcwd(), 'move')
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(MOVE_DIR, exist_ok=True)




def initialize_images():
    global shuffled_images
    images = os.listdir(REF_IMAGE_DIR)
    random.seed(time.time())
    random.shuffle(images)
    shuffled_images = images

def get_ref_images(start, count):
    global shuffled_images
    if shuffled_images is None:
        initialize_images()
    return shuffled_images[start:start + count]

# 애플리케이션 실행 시 한 번 셔플된 리스트를 초기화
initialize_images()


def get_images(start, count):
    images = os.listdir(IMAGE_DIR)
    images.sort()
    return images[start:start + count]

def get_trip_images(start, count):
    trip_images = os.listdir(TRIP_IMAGE_DIR)
    trip_images.sort()
    return trip_images[start:start + count]

""" def get_ref_images(start, count):
    images = os.listdir(REF_IMAGE_DIR)
    random.seed(time.time())
    random.shuffle(images)
    return images[start:start + count] """

def get_stock_graphs(dir, start, count):
    images = os.listdir(dir)
    # 정규식을 사용하여 날짜와 숫자 부분을 추출
    def sort_key(filename):
        # match = re.match(r"(\d{8}) \[\s*(-?\d+\.\d+)", filename)
        # if match:
        #     date_part = match.group(1)
        #     number_part = float(match.group(2))
        #     # 날짜는 숫자 그대로 비교, 숫자는 float로 변환하여 비교
        #     return date_part, number_part
        # else:
        #     # 패턴에 맞지 않는 경우를 대비하여 기본 정렬 키 반환
        #     return filename

        # match = re.match(r"(\d{4}-\d{2}-\d{2}|\d{8}) \[\s*(-?\d+\.\d+)", filename)
        match = re.match(r"(\d{4}-\d{2}-\d{2}|\d{8}) \[\s*([-+]?\d+\.\d+)", filename)
        if match:
            # 날짜 부분에서 '-' 제거
            date_part = match.group(1).replace('-', '')
            number_part = float(match.group(2))

            sort_number = 2 if number_part >= 0 else 1

            # 날짜는 숫자 그대로 비교, 숫자는 float로 변환하여 비교
            return date_part, sort_number, number_part
        else:
            # 패턴에 맞지 않는 경우를 대비하여 기본 정렬 키 반환
            return filename

    # 날짜 + 숫자로 내림차순 정렬
    images.sort(key=sort_key, reverse=True)
    return images[start:start + count]


###################### image ########################

@image_bp.route('/images', methods=['GET'])
@login_required
def image_list():
    page = int(request.args.get('page', 1))
    start = (page - 1) * limit_page_num
    images = get_images(start, limit_page_num)
    total_images = len(os.listdir(IMAGE_DIR))
    total_pages = (total_images + limit_page_num-1) // limit_page_num

    return render_template('image_list.html', images=images, page=page, total_pages=total_pages)

@image_bp.route('/trip_images', methods=['GET'])
@login_required
def trip_image_list():
    page = int(request.args.get('page', 1))
    start = (page - 1) * limit_page_num
    images = get_trip_images(start, limit_page_num)
    total_images = len(os.listdir(TRIP_IMAGE_DIR))
    total_pages = (total_images + limit_page_num-1) // limit_page_num

    return render_template('trip_image_list.html', images=images, page=page, total_pages=total_pages)

@image_bp.route('/ref_images', methods=['GET'])
@login_required
def ref_image_list():
    page = int(request.args.get('page', 1))
    start = (page - 1) * limit_page_num
    images = get_ref_images(start, limit_page_num)
    total_images = len(os.listdir(REF_IMAGE_DIR))
    total_pages = (total_images + limit_page_num-1) // limit_page_num

    return render_template('ref_image_list.html', images=images, page=page, total_pages=total_pages)

@image_bp.route('/move_image/<imagepath>/<filename>', methods=['POST'])
@login_required
def move_image(imagepath, filename):
    # imagepath의 값에 따라 src_path 결정
    if imagepath == "image":
        src_path = os.path.join(IMAGE_DIR, filename)
    elif imagepath == "ref_image":
        src_path = os.path.join(REF_IMAGE_DIR, filename)
    elif imagepath == "trip_image":
        src_path = os.path.join(TRIP_IMAGE_DIR, filename)
    else:
        return jsonify({'status': 'error', 'message': 'Invalid imagepath'}), 400

    dest_path = os.path.join(MOVE_DIR, filename)
    if os.path.exists(src_path):
        os.rename(src_path, dest_path)
        return jsonify({'status': 'success'})
    else:
        return jsonify({'status': 'error', 'message': 'File not found'}), 404


# @image_bp.route('/delete_images/<path:filename>', methods=['POST'])
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

@image_bp.route('/trip_images/<filename>')
@login_required
def get_trip_image(filename):
    return send_from_directory(TRIP_IMAGE_DIR, filename)

@image_bp.route('/ref_images/<filename>')
@login_required
def get_ref_image(filename):
    return send_from_directory(REF_IMAGE_DIR, filename)

@image_bp.route('/suffle/ref_images', methods=['POST'])
@login_required
def suffle_image():
    initialize_images()
    return jsonify({'status': 'success'})


###################### stock ##########################

@image_bp.route('/stock_grahps/<market>', methods=['GET'])
@login_required
def stock_graph_list(market):
    directory = DIRECTORY_MAP.get(market.lower())
    page = int(request.args.get('page', 1))
    start = (page - 1) * limit_page_num

    if directory is not None:
        images = get_stock_graphs(directory, start, limit_page_num)
    else:
        abort(404)  # 유효하지 않은 market 값에 대해 404 에러 반환

    total_images = len(os.listdir(directory))
    total_pages = (total_images + limit_page_num-1) // limit_page_num

    # print(market, directory, total_pages, images)
    return render_template('stock_graph_list.html', images=images, page=page, total_pages=total_pages, market=market)

@image_bp.route('/stock_graphs/<market>/<filename>')
@login_required
def get_stock_graph(market, filename):
    directory = DIRECTORY_MAP.get(market.lower())

    if directory is not None:
        return send_from_directory(directory, filename)
    else:
        abort(404)  # 유효하지 않은 market 값에 대해 404 에러 반환

@image_bp.route('/move_stock_image/<market>/<path:filename>', methods=['POST'])
@login_required
def move_stock_image(market, filename):
    # filename = unquote(filename)  # URL 디코딩 처리
    directory = DIRECTORY_MAP.get(market.lower())

    if directory is None:
        return jsonify({'status': 'error', 'message': 'Invalid market specified'}), 400

    src_path = os.path.join(directory, filename)
    # dest_path = os.path.join(MOVE_DIR, filename)
    if os.path.exists(src_path):
        try:
            # shutil.move(src_path, dest_path)
            send2trash(src_path)
            return jsonify({'status': 'success'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
    else:
        return jsonify({'status': 'error', 'message': 'File not found'}), 404


# Jinja2 템플릿에서 max와 min 함수 사용을 위한 설정
def environment(**options):
    env = Environment(**options)
    env.globals.update(max=max, min=min)
    return env
