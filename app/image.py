# image.py
import os
import re
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, send_from_directory, abort
from flask_login import login_required, current_user
from send2trash import send2trash
from jinja2 import Environment
from config.config import settings
import random
import time
import urllib.parse
import shutil

image_bp = Blueprint('image', __name__)
LIMIT_PAGE_NUM = 50
shuffled_images = None

# 설정
IMAGE_DIR = settings['IMAGE_DIR']
IMAGE_DIR2 = settings['IMAGE_DIR2']
MOVE_DIR = settings['MOVE_DIR']
REF_IMAGE_DIR = settings['REF_IMAGE_DIR']
TRIP_IMAGE_DIR = settings['TRIP_IMAGE_DIR']
TEMP_IMAGE_DIR = settings['TEMP_IMAGE_DIR']
DEL_TEMP_IMAGE_DIR = settings['DEL_TEMP_IMAGE_DIR']
KOSPI_DIR = settings['KOSPI_DIR']
SP500_DIR = settings['SP500_DIR']

# 시장 디렉터리 매핑
DIRECTORY_MAP = {
    'kospi': KOSPI_DIR,
    'nasdaq': SP500_DIR
}

# MOVE_DIR = os.path.join(os.getcwd(), 'move')
os.makedirs(IMAGE_DIR, exist_ok=True)
os.makedirs(MOVE_DIR, exist_ok=True)




def initialize_shuffle_images():
    global shuffled_images
    images = [
        f for f in os.listdir(REF_IMAGE_DIR)
        if os.path.isfile(os.path.join(REF_IMAGE_DIR, f))
           and not f.lower().endswith(('.zip', '.ini'))
    ]
    random.seed(time.time())
    random.shuffle(images)
    shuffled_images = images

def get_ref_images(start, count):
    global shuffled_images
    if shuffled_images is None:
        initialize_shuffle_images()
    return shuffled_images[start:start + count]

# 애플리케이션 실행 시 한 번 셔플된 리스트를 초기화
initialize_shuffle_images()


def get_images(start, count, dir):
    if dir == REF_IMAGE_DIR:
        images = shuffled_images
    else:
        images = [
            f for f in os.listdir(dir)
            if not f.lower().endswith(('.zip', '.ini'))  # ✅ .zip 파일 제외
        ]
        images.sort()
    return images[start:start + count]

def get_subdir_images(start, count, dirs):
    if isinstance(dirs, str):
        dirs = [dirs]

    images = []
    for dir_path in dirs:
        for subdir in os.listdir(dir_path):
            subdir_path = os.path.join(dir_path, subdir)
            if os.path.isdir(subdir_path):
                for f in os.listdir(subdir_path):
                    full_path = os.path.join(subdir_path, f)
                    if os.path.isfile(full_path) and not f.lower().endswith(('.zip', '.ini')):
                        # 내부 디렉토리명과 파일명을 붙임 (ex: data1/filename.jpg)
                        images.append(f"{subdir}/{f}")
    images.sort()
    return images[start:start + count]


def get_subdir_and_reels_images(start, count, parent_dir):
    images = []
    for subdir in os.listdir(parent_dir):
        subdir_path = os.path.join(parent_dir, subdir)
        if os.path.isdir(subdir_path):
            # 1. dirA, dirB 바로 아래 파일
            for f in os.listdir(subdir_path):
                file_path = os.path.join(subdir_path, f)
                if os.path.isfile(file_path) and not f.lower().endswith(('.zip', '.ini')):
                    images.append(f"{subdir}/{f}")
            # 2. reels 서브디렉토리의 파일도 포함
            reels_path = os.path.join(subdir_path, "reels")
            if os.path.isdir(reels_path):
                for f in os.listdir(reels_path):
                    reels_file_path = os.path.join(reels_path, f)
                    if os.path.isfile(reels_file_path) and not f.lower().endswith(('.zip', '.ini')):
                        images.append(f"{subdir}/reels/{f}")
    images.sort()
    return images[start:start + count]


def get_reverse_images(start, count, dir):
    images = sorted(
        [f for f in os.listdir(dir) if not f.lower().endswith(('.zip', '.ini'))],
        reverse=True
    )
    return images[start:start + count]


def get_stock_graphs(dir, start, count):
    all_items = os.listdir(dir)
    images = [f for f in all_items if os.path.isfile(os.path.join(dir, f))]
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


# Jinja2 템플릿에서 max와 min 함수 사용을 위한 설정
def environment(**options):
    env = Environment(**options)
    env.globals.update(max=max, min=min)
    return env


def count_non_zip_files(directory):
    return len([
        f for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f)) and not f.lower().endswith('.zip')
    ])


def count_non_zip_files_in_subfolders(parent_dir):
    count = 0
    for entry in os.listdir(parent_dir):
        sub_path = os.path.join(parent_dir, entry)
        if os.path.isdir(sub_path):
            # 하위 디렉토리 내부 파일만 카운트
            for f in os.listdir(sub_path):
                file_path = os.path.join(sub_path, f)
                if os.path.isfile(file_path) and not f.lower().endswith('.zip'):
                    count += 1
    return count


def count_non_zip_files_in_subfolders_and_reels(parent_dir):
    count = 0
    for subdir in os.listdir(parent_dir):
        subdir_path = os.path.join(parent_dir, subdir)
        if os.path.isdir(subdir_path):
            # 1. dirA, dirB 바로 아래 파일
            for f in os.listdir(subdir_path):
                file_path = os.path.join(subdir_path, f)
                if os.path.isfile(file_path) and not f.lower().endswith('.zip'):
                    count += 1
            # 2. reels 서브디렉토리의 파일도 포함
            reels_path = os.path.join(subdir_path, "reels")
            if os.path.isdir(reels_path):
                for f in os.listdir(reels_path):
                    reels_file_path = os.path.join(reels_path, f)
                    if os.path.isfile(reels_file_path) and not f.lower().endswith('.zip'):
                        count += 1
    return count


def clean_filename(filename):
    # Windows에서 허용되지 않는 문자(: * ? " < > | / \)를 _로 변경
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

###################### image ########################

@image_bp.route('/pages', methods=['GET'])
@login_required
def image_list():
    # ?title=video-call&dir=temp
    # if current_user.username == settings['GUEST_USERNAME']:
    dir = request.args.get('dir')
    firstRequst = request.args.get('firstRequst')
    selected_dir = request.args.get('title')
    isSlide = request.args.get('slide', '')
    title_list = []
    images = []
    images_length = 0
    page = int(request.args.get('page', 1))
    start = (page - 1) * LIMIT_PAGE_NUM

    if (hasattr(current_user, 'username') and current_user.username == settings['GUEST_USERNAME']) or dir == 'temp' or dir == 'trip':
        # images = get_images(start, LIMIT_PAGE_NUM, TEMP_IMAGE_DIR)
        # images_length = count_non_zip_files(TEMP_IMAGE_DIR)
        template_html = 'trip_image_list.html'
        title_list = sorted([d for d in os.listdir(TEMP_IMAGE_DIR) if os.path.isdir(os.path.join(TEMP_IMAGE_DIR, d))])

        # 선택된 title 값 가져오기 (없다면 첫 번째 값 자동 선택)
        if not selected_dir or selected_dir not in title_list:
            # selected_dir = title_list[0] if title_list else ''  # 첫 번째 항목 자동 선택
            selected_dir = title_list[0] if title_list else TEMP_IMAGE_DIR  # 첫 번째 항목 자동 선택

        target_dir = os.path.join(TEMP_IMAGE_DIR, selected_dir)
        if selected_dir == 'video-call':
            images = get_reverse_images(start, LIMIT_PAGE_NUM, target_dir)
        else:
            images = get_images(start, LIMIT_PAGE_NUM, target_dir)
        images_length = count_non_zip_files(target_dir)
        dir = 'temp'


    elif dir == 'refine':
        if firstRequst == 'True':
            initialize_shuffle_images() # ref는 처음 조회 시 이미지 셔플을 사용한다
        images_length = count_non_zip_files(REF_IMAGE_DIR)
        if isSlide == 'y':
            images = get_images(0, images_length, REF_IMAGE_DIR)
            return jsonify({"slide_show_images": images})
        else:
            images = get_images(start, LIMIT_PAGE_NUM, REF_IMAGE_DIR)
        template_html = 'ref_image_list.html'
    elif dir == 'image':
        images = get_images(start, LIMIT_PAGE_NUM, IMAGE_DIR)
        images_length = count_non_zip_files(IMAGE_DIR)
        template_html = 'image_list.html'
    elif dir == 'image2':
        images = get_subdir_and_reels_images(start, LIMIT_PAGE_NUM, IMAGE_DIR2)
        images_length = count_non_zip_files_in_subfolders_and_reels(IMAGE_DIR2)
        template_html = 'image_list.html'
    # elif dir == 'trip':
    #     images = get_images(start, LIMIT_PAGE_NUM, TRIP_IMAGE_DIR)
    #     images_length = count_non_zip_files(TRIP_IMAGE_DIR)
    #     template_html = 'trip_image_list.html'

    total_pages = (images_length + LIMIT_PAGE_NUM-1) // LIMIT_PAGE_NUM

    return render_template(template_html, images=images, page=page, title=selected_dir,
                           total_pages=total_pages, images_length=images_length, dir=dir,
                           selected_dir=selected_dir, title_list=title_list, version=int(time.time()))


@image_bp.route('/move-image', methods=['POST'], endpoint='move-image')
@login_required
def move_image():
    # imagepath의 값에 따라 src_path 결정
    imagepath = request.get_json().get('imagepath')
    subpath = request.get_json().get('subpath', '')
    filename = request.get_json().get('filename')
    filename = urllib.parse.unquote(filename)

    filename = os.path.join(os.path.dirname(filename),
                            clean_filename(os.path.basename(filename)))
    dest_path = os.path.join(MOVE_DIR,
                             clean_filename(os.path.basename(filename)))

    name_without_ext = os.path.splitext(filename)[0]


    # send2trash(os.path.join(IMAGE_DIR2, new_path)) # 휴지통으로 보낸다

    if imagepath == "image":
        src_path = os.path.join(IMAGE_DIR, filename)
        thumb_dir = os.path.join(IMAGE_DIR, "thumb")
    elif imagepath == "image2":
        src_path = os.path.join(IMAGE_DIR2, filename)
        thumb_dir = os.path.join(IMAGE_DIR2, "thumb")
    elif imagepath == "ref_image":
        src_path = os.path.join(REF_IMAGE_DIR, filename)
        thumb_dir = os.path.join(REF_IMAGE_DIR, "thumb")
    elif imagepath == "trip_image":
        src_path = os.path.join(TRIP_IMAGE_DIR, filename)
        thumb_dir = os.path.join(TRIP_IMAGE_DIR, "thumb")
    elif imagepath == "temp_image":
        dest_path = os.path.join(DEL_TEMP_IMAGE_DIR, filename)
        src_path = os.path.join(TEMP_IMAGE_DIR, subpath, filename)
        thumb_dir = os.path.join(TEMP_IMAGE_DIR, subpath, "thumb")
    else:
        return jsonify({'status': 'error', 'message': 'Invalid imagepath'}), 400

    webp_file = os.path.join(thumb_dir, name_without_ext + ".webp")

    # 존재하면 휴지통으로 이동
    if os.path.exists(webp_file):
        send2trash(webp_file)

    # print('src_path', src_path)
    if os.path.exists(src_path):
        # os.rename(src_path, dest_path) # OS ERROR : 다른 드라이브로 이동시킬 수 없다, shutil 사용을 권장
        shutil.move(src_path, dest_path) # src_path > dest_path 이동
        return jsonify({'status': 'success'})
    else:
        return jsonify({'status': 'error', 'message': 'File not found'}), 404


# @image_bp.route('/delete-images/<path:filename>', methods=['POST'], endpoint='delete-images')
# 어디서 사용하는지 확인 필요
@image_bp.route('/delete-images', methods=['POST'], endpoint='delete-images')
@login_required
def delete_images():
    images_to_delete = request.form.getlist('images[]')
    moved_images = os.listdir(MOVE_DIR)
    dir = request.args.get('dir')

    for image in images_to_delete:
        if image not in moved_images:
            if dir == 'image':
                raw_path = os.path.join(IMAGE_DIR, image)
                safe_path = os.path.normpath(raw_path)
                send2trash(safe_path) # 휴지통으로 보낸다
            elif dir == 'image2':
                # only_filename = os.path.basename(image)
                dir_part = os.path.dirname(image)
                file_part = os.path.basename(image)
                clean_file_part = clean_filename(file_part)
                new_path = os.path.join(IMAGE_DIR2, dir_part, clean_file_part)
                safe_path = os.path.normpath(new_path)
                send2trash(safe_path) # 휴지통으로 보낸다


    page = int(request.form.get('page', 1))
    return redirect(url_for('image.image_list', page=page, dir=dir))


@image_bp.route('/images')
@login_required
def get_image():
    filename = request.args.get('filename')
    dir = request.args.get('dir')
    selected_dir = request.args.get('selected_dir', '')

    if dir == 'image':
        base_dir = IMAGE_DIR
    elif dir == 'image2':
        base_dir = IMAGE_DIR2
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

    # ✅ thumb 디렉토리 경로 설정
    thumb_dir = os.path.join(base_dir, 'thumb')
    name_without_ext, _ = os.path.splitext(filename)
    webp_name = name_without_ext + '.webp'
    webp_path = os.path.join(thumb_dir, webp_name)

    # ✅ webp 썸네일이 존재하면 반환
    if os.path.exists(webp_path):
        return send_from_directory(thumb_dir, webp_name)

    # ✅ 기존 파일 경로에서 반환
    return send_from_directory(base_dir, filename)

@image_bp.route('/shuffle/ref-images', methods=['POST'], endpoint='shuffle/ref-images')
@login_required
def shuffle_image():
    initialize_shuffle_images()
    return jsonify({'status': 'success'})


###################### stock ##########################

@image_bp.route('/stock-graph-list/<market>', methods=['GET'], endpoint='stock-graph-list')
@login_required
def stock_graph_list(market):
    directory = DIRECTORY_MAP.get(market.lower())
    page = int(request.args.get('page', 1))
    start = (page - 1) * LIMIT_PAGE_NUM

    if directory is not None:
        images = get_stock_graphs(directory, start, LIMIT_PAGE_NUM)
    else:
        abort(404)  # 유효하지 않은 market 값에 대해 404 에러 반환

    images_length = len(os.listdir(directory))
    total_pages = (images_length + LIMIT_PAGE_NUM-1) // LIMIT_PAGE_NUM

    # print(market, directory, total_pages, images)
    return render_template('stock_graph_list.html', images=images, page=page, total_pages=total_pages, market=market)

@image_bp.route('/stock-graphs/<market>/<filename>', endpoint='stock-graphs')
@login_required
def get_stock_graph(market, filename):
    directory = DIRECTORY_MAP.get(market.lower())

    if directory is not None:
        return send_from_directory(directory, filename)
    else:
        abort(404)  # 유효하지 않은 market 값에 대해 404 에러 반환

@image_bp.route('/move-stock-image/<market>/<path:filename>', methods=['POST'], endpoint='move-stock-image')
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

