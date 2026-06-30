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
from urllib.parse import unquote
from dataclasses import dataclass
from typing import Final, Optional
from datetime import datetime
import job.batch_runner as batch_runner

image_bp = Blueprint('image', __name__)


# 이미지 배열
ai_image_arr = []
ig_image_arr = []
cos_image_arr = []
moved_image_arr = []
refined_image_arr = []
ref_shuffled_images = None

# 설정
LIMIT_PAGE_NUM = 1000
IMAGE_DIR = settings['IMAGE_DIR']
IMAGE_DIR2 = settings['IMAGE_DIR2']
MOVE_DIR = settings['MOVE_DIR']
REF_IMAGE_DIR = settings['REF_IMAGE_DIR']
TRIP_IMAGE_DIR = settings['TRIP_IMAGE_DIR']
TEMP_IMAGE_DIR = settings['TEMP_IMAGE_DIR']
DEL_TEMP_IMAGE_DIR = settings['DEL_TEMP_IMAGE_DIR']
COS_DIR = settings['COS_DIR']
KOSPI_DIR = settings['KOSPI_DIR']
SP500_DIR = settings['SP500_DIR']
INTEREST_DIR = settings['INTEREST_DIR']
LOW_KOSPI_DIR = settings['LOW_KOSPI_DIR']

# 시장 디렉터리 매핑
DIRECTORY_MAP = {
    'kospi': KOSPI_DIR,
    'nasdaq': SP500_DIR,
    'interest': INTEREST_DIR,
    'kospil': LOW_KOSPI_DIR,
}

EXCLUDE_SUFFIXES: Final = (".zip", ".ini", ".Identifier")  # 불변 튜플


@dataclass
class DirConfig:
    base_dir: str
    image_arr: list
    template: str
    source_type: Optional[str] = None


DIR_CONFIG: Final = {
    'image':  DirConfig(IMAGE_DIR,  ai_image_arr,   'image_list_masonry.html'),
    'image2': DirConfig(IMAGE_DIR2, ig_image_arr,   'image_list_masonry.html', 'ig'),
    'cos':    DirConfig(COS_DIR,    cos_image_arr,  'image_list_masonry.html'),
    'move':   DirConfig(MOVE_DIR,   moved_image_arr,'image_list_masonry.html'),
}


# 정렬 함수
def initialize_sorted_images():
    global ref_shuffled_images
    images = [
        f for f in os.listdir(REF_IMAGE_DIR)
        if os.path.isfile(os.path.join(REF_IMAGE_DIR, f))
           and not f.lower().endswith(EXCLUDE_SUFFIXES)
    ]
    images.sort(key=lambda x: x.lower())  # 이름순 정렬
    ref_shuffled_images = images


# 셔플 함수
def initialize_shuffle_images():
    global ref_shuffled_images
    images = [
        f for f in os.listdir(REF_IMAGE_DIR)
        if os.path.isfile(os.path.join(REF_IMAGE_DIR, f))
           and not f.lower().endswith(EXCLUDE_SUFFIXES)
    ]
    random.seed(time.time())
    random.shuffle(images)
    ref_shuffled_images = images


# 최초에는 정렬
initialize_sorted_images()


def safe_mtime(path):
    try:
        return os.path.getmtime(path)  # 수정시간 (초 단위)
    except FileNotFoundError:
        print(f"[WARN] File missing: {path}")
        return 0  # 또는 float('-inf')


def get_images(start, count, page, dir, image_arr=None):
    if dir == REF_IMAGE_DIR:
        images = ref_shuffled_images

        if start >= len(images) and len(images) > 0:
            start = max(0, start - LIMIT_PAGE_NUM)
            page = max(1, page - 1)

        if image_arr is not None:
            image_arr[:] = images

    else:
        full_paths = []

        for root, dirs, files in os.walk(dir):
            dirs[:] = [d for d in dirs if d != 'thumb']
            for f in files:
                if f.lower().endswith(EXCLUDE_SUFFIXES):
                    continue

                full_path = os.path.join(root, f)

                if os.path.isfile(full_path):
                    full_paths.append(full_path)

        # 수정시간 오름차순
        full_paths.sort(key=lambda x: os.path.getmtime(x))

        # dir 기준 상대경로로 변환
        images = [
            os.path.relpath(path, dir).replace("\\", "/")
            for path in full_paths
        ]

        if start >= len(images) and len(images) > 0:
            start = max(0, start - LIMIT_PAGE_NUM)
            page = max(1, page - 1)

        if image_arr is not None:
            image_arr[:] = images

    return images[start:start + count], page

def get_subdir_and_reels_images(start, limit, page, parent_dir, image_arr):
    pairs = []  # (rel_path, mtime)
    # subdir: 각 인스타그램 계정 폴더
    for subdir in os.listdir(parent_dir):
        subdir_path = os.path.join(parent_dir, subdir)
        if not os.path.isdir(subdir_path):
            continue
        # 1. subdir 바로 아래 파일
        for f in os.listdir(subdir_path):
            file_path = os.path.join(subdir_path, f)
            if os.path.isfile(file_path) and not f.lower().endswith(EXCLUDE_SUFFIXES):
                pairs.append((f"{subdir}/{f}", safe_mtime(file_path)))
        # 2. reels 서브디렉토리
        reels_path = os.path.join(subdir_path, "reels")
        if os.path.isdir(reels_path):
            for f in os.listdir(reels_path):
                file_path = os.path.join(reels_path, f)
                if os.path.isfile(file_path) and not f.lower().endswith(EXCLUDE_SUFFIXES):
                    pairs.append((f"{subdir}/reels/{f}", safe_mtime(file_path)))
        # 3. images 서브디렉토리
        images_path = os.path.join(subdir_path, "images")
        if os.path.isdir(images_path):
            for f in os.listdir(images_path):
                file_path = os.path.join(images_path, f)
                if os.path.isfile(file_path) and not f.lower().endswith(EXCLUDE_SUFFIXES):
                    pairs.append((f"{subdir}/images/{f}", safe_mtime(file_path)))

    pairs.sort(key=lambda x: x[1], reverse=True)  # mtime 내림차순 (최신 먼저)
    images = [rel for rel, _ in pairs]

    if start >= len(images) and len(images) > 0:
        start = max(0, start - LIMIT_PAGE_NUM)
        page = max(1, page - 1)

    image_arr[:] = images

    return images[start:start + limit], page


def get_reverse_images(start, count, dir):
    images = sorted(
        [f for f in os.listdir(dir) if not f.lower().endswith(EXCLUDE_SUFFIXES)],
        reverse=True
    )
    return images[start:start + count]


def fetch_images(start, limit, page, dir_path, image_arr, source_type=None):
    if source_type == "ig":
        return get_subdir_and_reels_images(start, limit, page, dir_path, image_arr)
    elif source_type == None:
        return get_images(start, limit, page, dir_path, image_arr)
    else:
        raise ValueError("Unknown source_type")


# 첫 페이지가 아니면 이미지 배열을 재사용
def get_image_page(start, limit, page, target_dir, image_arr, html, source_type=None):
    if page != 1:
        images = image_arr[start:start + limit]
    else:
        images, page = fetch_images(start, limit, page, target_dir, image_arr, source_type)

    if len(images) == 0:
        page = page - 1
        start = (page - 1) * limit
        images = image_arr[start:start + limit]

    images_length = len(image_arr)
    template_html = html

    return images, page, start, images_length, template_html


def warm_up_image_caches():
    for cfg in DIR_CONFIG.values():
        try:
            fetch_images(0, LIMIT_PAGE_NUM, 1, cfg.base_dir, cfg.image_arr, cfg.source_type)
        except Exception as e:
            print(f"[WARN] 캐시 워밍업 실패 ({cfg.base_dir}): {e}")


def resolve_dir_page(dir: str, page: int):
    cfg = DIR_CONFIG.get(dir)
    if cfg is None:
        return None
    start = (page - 1) * LIMIT_PAGE_NUM
    images, page, start, images_length, template_html = get_image_page(
        start, LIMIT_PAGE_NUM, page, cfg.base_dir, cfg.image_arr, cfg.template, cfg.source_type
    )
    return images, page, start, images_length, template_html


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


def clean_filename(filename):
    # Windows에서 허용되지 않는 문자(: * ? " < > | / \)를 _로 변경
    return re.sub(r'[<>:"/\\|?*]', '_', filename)




def safe_path_join(base_dir, rel_path):
    rel_path = unquote(rel_path).strip()
    base = os.path.realpath(base_dir)
    target = os.path.realpath(os.path.join(base, rel_path))
    # base 자신이거나 base 하위 경로만 허용 (심볼릭 링크 우회 차단)
    if target != base and not target.startswith(base + os.sep):
        raise ValueError(f"경로 탈출 감지: {rel_path}")
    return target


def delete_images_task(images_to_delete, dir):
    for image in images_to_delete:
        try:
            if dir == 'image2':
                dir_part  = os.path.dirname(image)
                file_part = os.path.basename(image)
                clean_file_part = clean_filename(unquote(file_part).strip())
                safe_path = safe_path_join(IMAGE_DIR2, os.path.join(dir_part, clean_file_part))
            elif dir in DIR_CONFIG:
                safe_path = safe_path_join(DIR_CONFIG[dir].base_dir, image)
            else:
                continue  # 알 수 없는 dir

            if not os.path.exists(safe_path):
                # 이미 지워졌거나 잘못된 이름
                # print(f"[WARN] not found: {safe_path}")
                continue

            send2trash(safe_path)

        except FileNotFoundError:
            print(f"[WARN] not found (caught): {image}")
        except Exception as e:
            # 다른 문제(권한, path traversal 등)
            print(f"[ERROR] delete failed: {image} -> {e}")


###################### image ########################

@image_bp.route('/pages', methods=['GET'])
@login_required
def image_list():
    # ?title=video-call&dir=temp
    # if current_user.username == settings['GUEST_USERNAME']:

    template_html = 'image_list.html'
    dir = request.args.get('dir')
    selected_dir = request.args.get('selected_dir')
    # print('selected_dir', selected_dir)
    if selected_dir in ("None", "null", "undefined", ""):
        selected_dir = None
    subdir_list = []
    images = []
    images_length = 0
    page = int(request.args.get('page', 1))
    start = (page - 1) * LIMIT_PAGE_NUM

    # 게스트
    if (hasattr(current_user, 'username') and current_user.username == settings['GUEST_USERNAME']) or dir == 'temp' or dir == 'trip':
        # template_html = 'image_list.html'
        template_html = 'image_list_masonry.html' # 개발중
        subdir_list = sorted([d for d in os.listdir(TEMP_IMAGE_DIR) if os.path.isdir(os.path.join(TEMP_IMAGE_DIR, d))])

        # 선택된 title 값 가져오기 (없다면 첫 번째 값 자동 선택)
        if not selected_dir or selected_dir not in subdir_list:
            # selected_dir = subdir_list[0] if subdir_list else ''  # 첫 번째 항목 자동 선택
            selected_dir = subdir_list[0] if subdir_list else TEMP_IMAGE_DIR  # 첫 번째 항목 자동 선택

        target_dir = os.path.join(TEMP_IMAGE_DIR, selected_dir)
        if selected_dir == 'video-call':
            all_files = sorted(
                [f for f in os.listdir(target_dir) if not f.lower().endswith(EXCLUDE_SUFFIXES)],
                reverse=True
            )
            images = all_files[start:start + LIMIT_PAGE_NUM]
            images_length = len(all_files)
        else:
            tmp_arr = []
            images, page = get_images(start, LIMIT_PAGE_NUM, page, target_dir, tmp_arr)
            images_length = len(tmp_arr)
        dir = 'temp'

    # elif dir == 'trip':
    #     images, page = get_images(start, LIMIT_PAGE_NUM, page, TRIP_IMAGE_DIR)
    #     images_length = count_non_zip_files(TRIP_IMAGE_DIR)
    #     template_html = 'trip_image_list.html'


    # 공통 기능 : 캐시 배열 슬라이싱 (풀스캔은 /fetch 에서만)
    elif dir in DIR_CONFIG:
        cfg = DIR_CONFIG[dir]
        images = cfg.image_arr[start:start + LIMIT_PAGE_NUM]
        if len(images) == 0:
            page = page - 1
            start = (page - 1) * LIMIT_PAGE_NUM
            images = cfg.image_arr[start:start + LIMIT_PAGE_NUM]
        images_length = len(cfg.image_arr)
        template_html = cfg.template

    elif dir == 'refine':
        images, page, start, images_length, template_html = get_image_page(
            start, LIMIT_PAGE_NUM, page, REF_IMAGE_DIR, refined_image_arr, 'image_list.html'
        )

        isSlide = request.args.get('slide', '')
        if isSlide == 'y':
            images, page = get_images(0, images_length, page, REF_IMAGE_DIR)
            return jsonify({"slide_show_images": images})

    elif dir == 'stock':
        market = request.args.get('market') or ''
        return redirect(url_for("image.stock-graph-list", market=market, page=page))
    else:
        template_html = 'image_list.html'

    total_pages = (images_length + LIMIT_PAGE_NUM-1) // LIMIT_PAGE_NUM

    return render_template(template_html, images=images, page=page,
                           total_pages=total_pages, images_length=images_length, dir=dir,
                           selected_dir=selected_dir, subdir_list=subdir_list, version=int(time.time()))


@image_bp.route('/fetch', methods=['GET'])
@login_required
def fetch_image_list():
    template_html = 'image_list_masonry.html'
    dir = request.args.get('dir')
    selected_dir = request.args.get('selected_dir')
    if selected_dir in ("None", "null", "undefined", ""):
        selected_dir = None
    subdir_list = []
    images = []
    images_length = 0
    page = int(request.args.get('page', 1))
    start = (page - 1) * LIMIT_PAGE_NUM

    # 공통 기능 : 첫번째 페이지에서만 풀 스캔
    if dir in DIR_CONFIG:
        images, page, start, images_length, template_html = resolve_dir_page(dir, page)

    total_pages = (images_length + LIMIT_PAGE_NUM-1) // LIMIT_PAGE_NUM

    return render_template(template_html, images=images, page=page,
                           total_pages=total_pages, images_length=images_length, dir=dir,
                           selected_dir=selected_dir, subdir_list=subdir_list, version=int(time.time()))


@image_bp.route('/move-image', methods=['POST'], endpoint='move-image')
@login_required
def move_image():
    payload = request.get_json(silent=True) or {}
    # imagepath의 값에 따라 src_path 결정
    imagepath = payload.get('imagepath')
    subpath = payload.get('subpath', '')
    filename = payload.get('filename')

    if not imagepath:
        return jsonify({'status': 'error', 'message': 'imagepath is required'}), 400

    if not filename:
        return jsonify({'status': 'error', 'message': 'filename is required'}), 400

    filename = urllib.parse.unquote(filename)

    filename = os.path.join(
        os.path.dirname(filename),
        clean_filename(os.path.basename(filename))
    )
    dest_path = os.path.join(
        MOVE_DIR,
        clean_filename(os.path.basename(filename))
    )

    ref_dest_path = os.path.join(
        REF_IMAGE_DIR,
        clean_filename(os.path.basename(filename))
    )

    name_without_ext = os.path.splitext(filename)[0]

    # send2trash(os.path.join(IMAGE_DIR2, new_path)) # 휴지통으로 보낸다

    if imagepath in DIR_CONFIG:
        cfg = DIR_CONFIG[imagepath]
        src_path = os.path.join(cfg.base_dir, filename)
        thumb_dir = os.path.join(cfg.base_dir, "thumb")
        if imagepath == "move":
            dest_path = ref_dest_path
    elif imagepath == "refine":
        src_path = os.path.join(REF_IMAGE_DIR, filename)
        thumb_dir = os.path.join(REF_IMAGE_DIR, "thumb")
    elif imagepath == "trip":
        src_path = os.path.join(TRIP_IMAGE_DIR, filename)
        thumb_dir = os.path.join(TRIP_IMAGE_DIR, "thumb")
    elif imagepath == "temp":
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
    # images_to_delete = request.form.getlist('images[]')
    dir = request.args.get('dir')
    data = request.get_json()
    # 'account/p/{파일명}'
    images_to_delete = data.get("images", [])

    batch_runner.scheduler.add_job(
        delete_images_task,
        trigger='date',
        run_date=datetime.now(),
        args=[images_to_delete, dir],
        executor='io',
        id=f"delete_images_{time.time_ns()}",
        replace_existing=False
    )

    # 루프가 끝난 뒤 한 번에 삭제(모든 중복 제거, in-place 갱신으로 참조 유지)
    to_delete = set(images_to_delete)
    if dir in DIR_CONFIG:
        arr = DIR_CONFIG[dir].image_arr
        if arr:
            arr[:] = [p for p in arr if p not in to_delete]
    elif dir == 'refine' and refined_image_arr:
        refined_image_arr[:] = [p for p in refined_image_arr if p not in to_delete]

    page = int(data.get("page", 1))
    # if dir == 'image2':
    #     global ig_image_arr
    #     ig_image_arr = ig_image_arr[LIMIT_PAGE_NUM:]
    #     total_pages = (len(ig_image_arr) + LIMIT_PAGE_NUM-1) // LIMIT_PAGE_NUM
    #
    #     return render_template('image_list.html', images=ig_image_arr[:LIMIT_PAGE_NUM], page=page, title=None,
    #                            total_pages=total_pages, images_length=len(ig_image_arr), dir=dir,
    #                            selected_dir=None, dir_list=[], version=int(time.time()))
    # else:
    #     return redirect(url_for('image.image_list', page=page, dir=dir))

    # return redirect(url_for('image.image_list', page=page, dir=dir))
    # return jsonify(redirect=url_for('image.image_list', page=page, dir=dir)), 200
    return jsonify({"redirect": url_for('image.image_list', page=page, dir=dir)}), 200 # 명시적 표기








@image_bp.route('/images')
@login_required
def get_image():
    filename = request.args.get('filename')
    filename = urllib.parse.unquote_plus(filename)
    dir = request.args.get('dir')
    selected_dir = request.args.get('selected_dir', '')

    market = request.args.get('market') or ''
    directory = DIRECTORY_MAP.get(market.lower())


    if dir in DIR_CONFIG:
        base_dir = DIR_CONFIG[dir].base_dir
    elif dir == 'refine':
        base_dir = REF_IMAGE_DIR
    elif dir == 'trip':
        base_dir = TRIP_IMAGE_DIR
    elif dir == 'temp':
        base_dir = TEMP_IMAGE_DIR
        if selected_dir:
            base_dir = os.path.join(TEMP_IMAGE_DIR, selected_dir)
    elif dir == 'stock':
        if directory is not None:
            return send_from_directory(directory, filename)  # 없으면 함수가 404를 응답함
        else:
            abort(404)  # 유효하지 않은 market 값에 대해 404 에러 반환
    else:
        abort(400, 'Invalid dir')

    # thumb 서브디렉토리에 동일 이름 .webp 있으면 우선 반환
    thumb_dir = os.path.join(base_dir, 'thumb')
    if not os.path.isdir(thumb_dir):
        # raise FileNotFoundError(f"thumb_dir이 존재하지 않습니다: {thumb_dir}")
        return send_from_directory(base_dir, filename)

    name_without_ext, _ = os.path.splitext(filename)
    webp_path = os.path.join(thumb_dir, name_without_ext + '.webp')
    if os.path.exists(webp_path):
        return send_from_directory(thumb_dir, name_without_ext + '.webp')

    return send_from_directory(base_dir, filename)

@image_bp.route('/shuffle/ref-images', methods=['POST'], endpoint='shuffle/ref-images')
@login_required
def shuffle_image():
    dir = request.args.get('dir')
    page = int(request.args.get('page', 1))

    initialize_shuffle_images()

    # return jsonify({'status': 'success'})
    return jsonify({"redirect": url_for('image.image_list', page=page, dir=dir)}), 200 # 명시적 표기


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
    return render_template(
        # 'stock_graph_list.html',
        'image_list.html',
        dir='stock', images=images, page=page, total_pages=total_pages, market=market,
        images_length = images_length,
        version=int(time.time())
    )

@image_bp.route('/stock-graphs/<market>/<filename>', endpoint='stock-graphs')
@login_required
def get_stock_graph(market, filename):
    directory = DIRECTORY_MAP.get(market.lower())

    if market.lower() == 'interest':
    # if market.lower() == 'interest' or market.lower() == 'kospil':
        # directory = DIRECTORY_MAP.get('interest')
        # URL 인코딩된 파일명 대응
        filename = unquote(filename)

        match = re.match(r"^(\d{4})(\d{2})(\d{2})", filename)
        if not match:
            abort(404)

        year, month, day = match.groups()
        target_dir = os.path.join(directory, year, month, day)
    else:
        target_dir = directory

    if target_dir is not None:
        return send_from_directory(target_dir, filename)
    else:
        abort(404)  # 유효하지 않은 market 값에 대해 404 에러 반환

@image_bp.route('/move-stock-image/<market>/<path:filename>', methods=['POST'], endpoint='move-stock-image')
@login_required
def move_stock_image(market, filename):
    # filename = unquote(filename)  # URL 디코딩 처리
    directory = DIRECTORY_MAP.get(market.lower())
    filename = unquote(filename)

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

