# image.py
import os
import re
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, send_from_directory, abort, g, \
    send_file
from flask_login import login_required, current_user
from send2trash import send2trash
from jinja2 import Environment
from config.config import settings
import random
import time
import io
import json
import logging
import functools
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
    'refine': DirConfig(REF_IMAGE_DIR, refined_image_arr, 'image_list_masonry.html'),
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
    refined_image_arr[:] = images


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
            # thumb: 썸네일 / origin: 자르기 전 원본 백업(crop-image) — 둘 다 갤러리 목록에 넣지 않는다
            dirs[:] = [d for d in dirs if d not in ('thumb', 'origin')]
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

            # 썸네일(thumb/<상대경로 확장자 뺌>.webp)도 같이 휴지통으로 — 원본이 이미 없어도 남은 썸네일은 정리한다.
            # move-image(원본 이동)가 하는 것과 같은 처리이고, utils/image_thumbs.py 가 만드는 경로와 같다.
            thumb_base = IMAGE_DIR2 if dir == 'image2' else DIR_CONFIG[dir].base_dir
            rel = os.path.relpath(safe_path, os.path.realpath(thumb_base)).replace('\\', '/')
            # normpath: send2trash(Windows)는 '\'와 '/'가 섞인 경로(IG 하위 폴더)를 거부한다(WinError -2147024809).
            webp_file = os.path.normpath(os.path.join(thumb_base, 'thumb', os.path.splitext(rel)[0] + '.webp'))
            if os.path.exists(webp_file):
                try:
                    send2trash(webp_file)
                except Exception as e:
                    print(f"[WARN] thumb delete failed: {webp_file} -> {e}")

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

# ── 느린 요청 계측 ────────────────────────────────────────────────────────────
# 간헐적으로 10초 걸리는 /image/move-image 의 원인을 가리기 위한 로그(2026-10-02). 핸들러 안에서 걸린
# 시간이 임계값(기본 1초)을 넘으면 단계별 시간과 함께 app 로그에 남긴다. 이 로그가 안 찍혔는데 화면에서
# 느렸다면 지연은 핸들러 밖(대기열·GIL·nginx·네트워크)이다 — 반대로 찍혔다면 steps 에 병목 단계가 나온다.
_slow_log = logging.getLogger('image.slow')


def _ensure_slow_log_handlers():
    # 앱 로그(config/logger_config.py)는 로거마다 핸들러를 직접 붙이고 root 로 전파하지 않는 구조다. 게다가
    # 기본 로거에는 NO_LOGS_URLS 필터가 걸려 있어 '/image/move-image' 가 들어간 메시지는 통째로 사라진다.
    # 그래서 필터가 없는 'waitress.queue' 로거가 쓰는 핸들러(콘솔+파일 큐)를 첫 사용 시 그대로 빌려 쓴다.
    if _slow_log.handlers:
        return
    borrowed = logging.getLogger('waitress.queue').handlers
    if borrowed:
        for h in borrowed:
            _slow_log.addHandler(h)
        _slow_log.setLevel(logging.INFO)
        _slow_log.propagate = False


class _timed:
    """with _timed('trash'): ... — 단계 시간을 g.steps 에 기록한다."""
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        self.t = time.perf_counter()

    def __exit__(self, *exc):
        steps = getattr(g, 'steps', None)
        if steps is None:
            steps = g.steps = {}
        steps[self.name] = round(time.perf_counter() - self.t, 3)


def _log_slow(threshold=1.0):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                total = time.perf_counter() - t
                if total > threshold:
                    _ensure_slow_log_handlers()
                    _slow_log.warning('[느린요청] %s %.1fs 단계=%s ip=%s', request.path, total,
                                      getattr(g, 'steps', {}), request.remote_addr)
        return wrapper
    return deco


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
    search = request.args.get('search', '').strip()
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
        source_arr = cfg.image_arr
        if search:
            source_arr = [f for f in source_arr if f.replace('\\', '/').startswith(search)]
        images = source_arr[start:start + LIMIT_PAGE_NUM]
        if len(images) == 0 and page > 1:
            page = page - 1
            start = (page - 1) * LIMIT_PAGE_NUM
            images = source_arr[start:start + LIMIT_PAGE_NUM]
        images_length = len(source_arr)
        template_html = cfg.template

        if dir == 'refine' and request.args.get('slide') == 'y':
            slide_images, _ = get_images(0, images_length, page, REF_IMAGE_DIR)
            return jsonify({"slide_show_images": slide_images})

    elif dir == 'stock':
        market = request.args.get('market') or ''
        return redirect(url_for("image.stock-graph-list", market=market, page=page))
    else:
        template_html = 'image_list.html'

    total_pages = (images_length + LIMIT_PAGE_NUM-1) // LIMIT_PAGE_NUM

    return render_template(template_html, images=images, page=page,
                           total_pages=total_pages, images_length=images_length, dir=dir,
                           selected_dir=selected_dir, subdir_list=subdir_list,
                           search=search, version=int(time.time()))


@image_bp.route('/fetch', methods=['GET'])
@login_required
def fetch_image_list():
    template_html = 'image_list_masonry.html'
    dir = request.args.get('dir')
    selected_dir = request.args.get('selected_dir')
    if selected_dir in ("None", "null", "undefined", ""):
        selected_dir = None
    search = request.args.get('search', '').strip()
    subdir_list = []
    images = []
    images_length = 0
    page = int(request.args.get('page', 1))
    start = (page - 1) * LIMIT_PAGE_NUM

    # 공통 기능 : 첫번째 페이지에서만 풀 스캔
    if dir in DIR_CONFIG:
        resolve_dir_page(dir, page)
        if search:
            pass  # 검색 필터는 /pages에서 처리

    return redirect(url_for('image.image_list', dir=dir, page=page,
                            selected_dir=selected_dir, search=search or None))


@image_bp.route('/move-image', methods=['POST'], endpoint='move-image')
@login_required
@_log_slow()
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

    # filename의 os.path.dirname 부분은 clean_filename을 거치지 않으므로(하위 폴더 구조 보존 목적),
    # 실제 파일 경로는 반드시 safe_path_join으로 base_dir 밖 탈출 여부를 검증한다.
    try:
        if imagepath in DIR_CONFIG:
            cfg = DIR_CONFIG[imagepath]
            src_path = safe_path_join(cfg.base_dir, filename)
            thumb_dir = os.path.join(cfg.base_dir, "thumb")
            if imagepath == "move":
                dest_path = ref_dest_path
        elif imagepath == "refine":
            src_path = safe_path_join(REF_IMAGE_DIR, filename)
            thumb_dir = os.path.join(REF_IMAGE_DIR, "thumb")
        elif imagepath == "trip":
            src_path = safe_path_join(TRIP_IMAGE_DIR, filename)
            thumb_dir = os.path.join(TRIP_IMAGE_DIR, "thumb")
        elif imagepath == "temp":
            dest_path = os.path.join(DEL_TEMP_IMAGE_DIR, filename)
            src_path = safe_path_join(TEMP_IMAGE_DIR, os.path.join(subpath, filename))
            thumb_dir = os.path.join(TEMP_IMAGE_DIR, subpath, "thumb")
        else:
            return jsonify({'status': 'error', 'message': 'Invalid imagepath'}), 400

        webp_file = safe_path_join(thumb_dir, name_without_ext + ".webp")
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid filename'}), 400

    # 존재하면 휴지통으로 이동
    with _timed('thumb_trash'):
        if os.path.exists(webp_file):
            send2trash(webp_file)

    # print('src_path', src_path)
    with _timed('src_exists'):
        src_exists = os.path.exists(src_path)
    if src_exists:
        # os.rename(src_path, dest_path) # OS ERROR : 다른 드라이브로 이동시킬 수 없다, shutil 사용을 권장
        with _timed('move'):
            shutil.move(src_path, dest_path) # src_path > dest_path 이동

        raw_filename = urllib.parse.unquote(payload.get('filename', ''))
        if imagepath in DIR_CONFIG:
            arr = DIR_CONFIG[imagepath].image_arr
            arr[:] = [p for p in arr if p != raw_filename]

        return jsonify({'status': 'success'})
    else:
        return jsonify({'status': 'error', 'message': 'File not found'}), 404



# ── 이미지 자르기(dir=move) ──────────────────────────────────────────────────
# 갤러리에서 영역을 골라 3:4 비율로 잘라 **같은 파일명으로 덮어쓴다**(2026-10-02, 사용자 요청).
#  - 원본은 <base_dir>/origin/<상대경로> 에 1회만 백업한다(이미 있으면 그게 최초 원본이라 덮지 않는다).
#    origin/ 은 갤러리 목록(get_images)과 썸네일 생성(utils/image_thumbs.py)에서 제외된다.
#  - 리샘플: 확대는 BICUBIC + 넓고 약한 언샤프(부드럽되 선명도는 유지), 축소는 LANCZOS 만(_render_crop 참고).
#  - 포맷은 확장자 그대로: PNG 는 무손실, JPG 는 품질 95·크로마 서브샘플링 없음, WEBP 는 품질 95.
#  - 원본의 수정시각을 유지한다(move 갤러리는 수정시각 순 정렬이라, 바꾸면 편집한 이미지가 맨 뒤로 튄다).
#    그래서 브라우저 캐시(1일) 회피용 버전값은 수정시각이 아니라 '편집한 시각'을 따로 기록해 쓴다(img_v).
#  - 저장 즉시 썸네일(thumb/<이름>.webp)도 새로 만든다.
CROP_RATIO = (3, 4)            # 1440x1920 = 3:4 (최대공약수 480). 2026-10-02 53:72(1060x1440)에서 변경
CROP_DIRS = ('move',)
CROP_MAX_UNIT = 2000           # 출력 최대 6000 x 8000
_CROP_FORMATS = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.jfif': 'JPEG', '.png': 'PNG', '.webp': 'WEBP'}
_EDIT_VER_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              'logs', 'image_edits', 'versions.json')


def _load_edit_versions():
    try:
        with open(_EDIT_VER_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


_edit_versions = _load_edit_versions()

# 마지막으로 확정한 틀(최초 원본 기준 좌표)과 출력 단위. '원본으로 되돌리기' 때 같은 틀을 다시 씌우는 데 쓴다.
# 두 번 이상 자른 경우에도 최초 원본(origin/) 좌표로 환산해 저장하므로, 되돌린 원본 위에 정확히 같은 영역이 잡힌다.
_CROP_HIST_PATH = os.path.join(os.path.dirname(_EDIT_VER_PATH), 'crop_history.json')
try:
    with open(_CROP_HIST_PATH, 'r', encoding='utf-8') as _f:
        _crop_history = json.load(_f)
except (OSError, ValueError):
    _crop_history = {}


def _save_crop_history():
    try:
        os.makedirs(os.path.dirname(_CROP_HIST_PATH), exist_ok=True)
        with open(_CROP_HIST_PATH + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(_crop_history, f, ensure_ascii=False)
        os.replace(_CROP_HIST_PATH + '.tmp', _CROP_HIST_PATH)
    except OSError as e:
        print(f'[WARN] crop history save failed: {e}')


def _origin_box(key, used_box, cur_size, had_backup):
    """이번 틀(used_box, 지금 파일 좌표)을 최초 원본 좌표로 환산. 지금 파일이 이미 한 번 잘린 결과면
    (had_backup) 직전 기록(원본에서 어떤 영역을 어떤 크기로 만들었는지)으로 거꾸로 환산한다. 모르면 None."""
    x, y, w, h = used_box
    if not had_backup:
        return [x, y, w, h]
    prev = _crop_history.get(key)
    if not prev or list(prev.get('out') or []) != list(cur_size):
        return None                       # 직전 결과 크기와 다르면(기록 없음/다른 경로로 바뀜) 환산 불가
    px, py, pw, ph = prev['box']
    sx, sy = pw / cur_size[0], ph / cur_size[1]
    return [px + x * sx, py + y * sy, w * sx, h * sy]


@image_bp.app_template_global('img_v')
def img_v(dir, filename):
    """편집된 이미지만 캐시 회피용 버전값(편집 시각). 편집 안 된 이미지는 None → url_for 가 v 를 빼고 만든다."""
    return _edit_versions.get(f'{dir}/{filename}')


def _soften_jaggies(img):
    """확대 결과의 계단현상(원본 픽셀·JPG 블록이 커진 경계)을 경계 보존 블러(양방향 필터)로 완화한다.
    평평한 곳과 경계 주변의 들쭉날쭉함만 고르게 하고 뚜렷한 경계는 남긴다. 2026-10-03 사용자 요청(D안):
    move 실사진 2배 확대 비교에서 Bicubic 만 쓴 것보다 계단이 줄고 질감은 대부분 유지, 1080x1440 기준 약 40ms.
    색 거리만 보는 필터라 RGB/BGR 순서와 무관하고, 투명도(알파)는 건드리지 않는다."""
    import numpy as np
    import cv2
    from PIL import Image
    if img.mode == 'RGBA':
        rgb, alpha = img.convert('RGB'), img.getchannel('A')
    else:
        rgb, alpha = img.convert('RGB'), None
    out = Image.fromarray(cv2.bilateralFilter(np.asarray(rgb), 7, 25, 7))
    if alpha is not None:
        out.putalpha(alpha)
    return out


def _render_crop(src_path, box, out_w, out_h):
    """원본(EXIF 회전 반영)에서 box=(x, y, w, h)를 잘라 (out_w, out_h)로 리샘플한 PIL 이미지."""
    from PIL import Image, ImageOps
    with Image.open(src_path) as im:
        im = ImageOps.exif_transpose(im)
        W, H = im.size
        x, y, w, h = box
        w = max(1, min(int(round(w)), W))
        h = max(1, min(int(round(h)), H))
        x = max(0, min(int(round(x)), W - w))
        y = max(0, min(int(round(y)), H - h))
        if im.mode not in ('RGB', 'RGBA'):
            has_alpha = im.mode in ('LA', 'PA') or (im.mode == 'P' and 'transparency' in im.info)
            im = im.convert('RGBA' if has_alpha else 'RGB')
        region = im.crop((x, y, x + w, y + h))
        if out_w > w:
            # 확대: BICUBIC 만, 선명화 없음(2026-10-03 사용자 요청). LANCZOS 는 확대 시 경계에 밝고 어두운 띠(링잉)를
            # 만들어 날카롭게 보인다. 경과: LANCZOS+UnsharpMask(1.0,50%) → BICUBIC+UnsharpMask(1.6) 20→15→12→9→5% → 없음.
            # move 실사진 8장 기준 날카로움(처음 방식=100%): 지금 66% / 5% 언샤프 68% / BILINEAR 53%(확연히 흐림).
            out = _soften_jaggies(region.resize((out_w, out_h), Image.BICUBIC))
        else:
            # 축소: LANCZOS 만으로 충분히 선명하다 — 추가 선명화는 과해진다
            out = region.resize((out_w, out_h), Image.LANCZOS)
        icc = im.info.get('icc_profile')
    return out, icc, (x, y, w, h), (W, H)


def _save_image(img, path, fmt, icc=None):
    kw = {}
    if icc:
        kw['icc_profile'] = icc
    if fmt == 'JPEG':
        img.convert('RGB').save(path, 'JPEG', quality=95, subsampling=0, optimize=True, **kw)
    elif fmt == 'PNG':
        # 무손실(압축 수준은 크기·속도만 바꾼다). 2026-10-03 optimize=True → compress_level=6 → 3:
        # move 실제 PNG 1080x1440 기준 저장 2,251ms → 196ms, 파일 +8% (자르기 확정이 매번 2~3초 걸리던 원인)
        img.save(path, 'PNG', compress_level=3, **kw)
    else:
        img.save(path, 'WEBP', quality=95, method=6, **kw)


@image_bp.route('/crop-image', methods=['POST'], endpoint='crop-image')
@login_required
@_log_slow()
def crop_image():
    """payload: dir, filename, box{x,y,w,h}(원본 픽셀, EXIF 회전 반영 후 좌표), unit(출력 = CROP_RATIO 각 항 × unit),
    preview(true면 결과 이미지만 돌려주고 파일은 건드리지 않는다)."""
    if hasattr(current_user, 'username') and current_user.username == settings['GUEST_USERNAME']:
        return jsonify({'status': 'error', 'message': 'forbidden'}), 403
    p = request.get_json(silent=True) or {}
    dir_ = p.get('dir')
    filename = urllib.parse.unquote(p.get('filename') or '')
    if dir_ not in CROP_DIRS or not filename:
        return jsonify({'status': 'error', 'message': 'invalid dir/filename'}), 400
    base = DIR_CONFIG[dir_].base_dir
    try:
        src = safe_path_join(base, filename)
        b = p.get('box') or {}
        box = (float(b['x']), float(b['y']), float(b['w']), float(b['h']))
        unit = int(p.get('unit'))
    except (ValueError, KeyError, TypeError):
        return jsonify({'status': 'error', 'message': 'invalid parameters'}), 400
    fmt = _CROP_FORMATS.get(os.path.splitext(src)[1].lower())
    if fmt is None or not os.path.isfile(src):
        return jsonify({'status': 'error', 'message': 'unsupported or missing file'}), 400
    unit = max(1, min(unit, CROP_MAX_UNIT))
    out_w, out_h = CROP_RATIO[0] * unit, CROP_RATIO[1] * unit

    with _timed('render'):
        img, icc, used_box, orig_size = _render_crop(src, box, out_w, out_h)

    if p.get('preview'):
        buf = io.BytesIO()
        _save_image(img, buf, fmt, icc)
        buf.seek(0)
        resp = send_file(buf, mimetype={'JPEG': 'image/jpeg', 'PNG': 'image/png'}.get(fmt, 'image/webp'))
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    rel = os.path.relpath(src, os.path.realpath(base)).replace(os.sep, '/')
    st = os.stat(src)
    with _timed('backup'):
        backup = os.path.normpath(os.path.join(base, 'origin', rel))
        had_backup = os.path.exists(backup)
        if not had_backup:                    # 최초 원본만 보관(두 번째 편집부터는 이미 있는 백업을 유지)
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            shutil.copy2(src, backup)
    with _timed('save'):
        tmp = src + '.croptmp'
        _save_image(img, tmp, fmt, icc)
        # Windows 는 다른 요청이 그 파일을 읽는 중(열린 핸들)이면 교체를 거부한다 — 잠깐 재시도하고,
        # 그래도 안 되면 원본은 그대로 두고 오류를 돌려준다.
        for attempt in range(5):
            try:
                os.replace(tmp, src)
                break
            except PermissionError:
                if attempt == 4:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    return jsonify({'status': 'error', 'message': '파일이 사용 중이라 저장하지 못했어요. 잠시 후 다시 시도해 주세요'}), 409
                time.sleep(0.3)
        os.utime(src, (st.st_atime, st.st_mtime))   # 원본 수정시각 유지 → 갤러리 순서 그대로
    with _timed('thumb'):
        _rebuild_thumb(base, rel, src)
    hist_key = f'{dir_}/{filename}'
    obox = _origin_box(hist_key, used_box, orig_size, had_backup)
    if obox is None:
        _crop_history.pop(hist_key, None)
    else:
        _crop_history[hist_key] = {'box': [round(v, 2) for v in obox], 'unit': unit, 'out': [out_w, out_h]}
    _save_crop_history()
    ver = _bump_edit_version(dir_, filename)
    return jsonify({'status': 'success', 'v': ver, 'size': [out_w, out_h], 'box': list(used_box),
                    'original_size': list(orig_size), 'has_origin': True})


def _rebuild_thumb(base, rel, src):
    """편집/복원 직후 썸네일을 다시 만든다. utils/image_thumbs.py 와 같은 규칙: 이미 작으면(가로 800 이하 +
    200KB 이하) 썸네일 없이 원본을 그대로 보내고, 썸네일이 원본보다 커지면 만들지 않는다."""
    from utils.image_thumbs import make_thumb, probe, thumb_path, THUMB_WIDTH, SMALL_BYTES
    tp = os.path.normpath(thumb_path(base, rel))
    size = os.path.getsize(src)
    width = probe(src)[0]
    data = None if (width <= THUMB_WIDTH and size <= SMALL_BYTES) else make_thumb(src)
    if data is None or len(data) >= size:
        if os.path.exists(tp):
            os.remove(tp)
        return
    os.makedirs(os.path.dirname(tp), exist_ok=True)
    with open(tp + '.tmp', 'wb') as f:
        f.write(data)
    os.replace(tp + '.tmp', tp)


def _bump_edit_version(dir_, filename):
    """캐시 회피용 버전값(편집/복원 시각)을 기록하고 돌려준다.
    밀리초 단위 + 같은 파일은 항상 이전 값보다 크게 — 초 단위였을 때 확정과 되돌리기가 같은 1초 안에 일어나면
    버전값이 같아져, 브라우저가 되돌린 원본 대신 방금 받은 잘린 이미지를 캐시에서 그대로 보여줬다(틀이 엉뚱하게 튐)."""
    key = f'{dir_}/{filename}'
    ver = max(int(time.time() * 1000), int(_edit_versions.get(key) or 0) + 1)
    _edit_versions[key] = ver
    try:
        os.makedirs(os.path.dirname(_EDIT_VER_PATH), exist_ok=True)
        with open(_EDIT_VER_PATH + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(_edit_versions, f, ensure_ascii=False)
        os.replace(_EDIT_VER_PATH + '.tmp', _EDIT_VER_PATH)
    except OSError as e:
        print(f'[WARN] edit version save failed: {e}')
    return ver


def _crop_paths(dir_, filename):
    """(base, src, rel, backup) — 잘못된 dir/경로면 ValueError."""
    if dir_ not in CROP_DIRS or not filename:
        raise ValueError('invalid dir/filename')
    base = DIR_CONFIG[dir_].base_dir
    src = safe_path_join(base, filename)
    rel = os.path.relpath(src, os.path.realpath(base)).replace(os.sep, '/')
    backup = os.path.normpath(os.path.join(base, 'origin', rel))
    return base, src, rel, backup


@image_bp.route('/crop-info', methods=['GET'], endpoint='crop-info')
@login_required
def crop_info():
    """편집 창이 '원본으로 되돌리기' 버튼을 보일지 정하는 용도 — origin/ 에 백업이 있는지."""
    try:
        _, _, _, backup = _crop_paths(request.args.get('dir'), urllib.parse.unquote(request.args.get('filename') or ''))
    except ValueError:
        return jsonify({'status': 'error', 'message': 'invalid dir/filename'}), 400
    return jsonify({'status': 'success', 'has_origin': os.path.isfile(backup)})


@image_bp.route('/crop-restore', methods=['POST'], endpoint='crop-restore')
@login_required
@_log_slow()
def crop_restore():
    """origin/ 의 백업을 원래 자리로 되돌린다(백업 파일을 그대로 옮기므로 내용·수정시각 모두 최초 원본).
    되돌린 뒤에는 백업이 없어지고, 다시 자르면 그때 새로 백업된다."""
    if hasattr(current_user, 'username') and current_user.username == settings['GUEST_USERNAME']:
        return jsonify({'status': 'error', 'message': 'forbidden'}), 403
    p = request.get_json(silent=True) or {}
    dir_ = p.get('dir')
    filename = urllib.parse.unquote(p.get('filename') or '')
    try:
        base, src, rel, backup = _crop_paths(dir_, filename)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'invalid dir/filename'}), 400
    if not os.path.isfile(backup):
        return jsonify({'status': 'error', 'message': '되돌릴 원본 백업이 없어요'}), 404
    with _timed('restore'):
        for attempt in range(5):           # 다른 요청이 파일을 읽는 중이면 Windows 가 교체를 거부한다
            try:
                os.replace(backup, src)
                break
            except PermissionError:
                if attempt == 4:
                    return jsonify({'status': 'error', 'message': '파일이 사용 중이라 되돌리지 못했어요. 잠시 후 다시 시도해 주세요'}), 409
                time.sleep(0.3)
    with _timed('thumb'):
        _rebuild_thumb(base, rel, src)
    ver = _bump_edit_version(dir_, filename)
    # 마지막 확정 틀(원본 좌표)을 돌려줘서 편집 창이 같은 틀을 다시 씌우게 한다. 원본으로 돌아갔으니 기록은 지운다
    # (다음 확정은 원본에서 새로 시작 → 그때 다시 기록된다).
    last = _crop_history.pop(f'{dir_}/{filename}', None)
    _save_crop_history()
    return jsonify({'status': 'success', 'v': ver, 'has_origin': False,
                    'last_crop': {'box': last['box'], 'unit': last['unit']} if last else None})


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

    search = (data.get("search") or "").strip()
    page = int(data.get("page", 1))
    if search:
        page = 1
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
    return jsonify({"redirect": url_for('image.image_list', page=page, dir=dir, search=search or None)}), 200 # 명시적 표기








IMAGE_CACHE_SECONDS = 60 * 60 * 24   # 갤러리 이미지 브라우저 캐시(1일) — 같은 이미지를 다시 볼 때 재요청을 줄인다


def _send_cached(directory, filename):
    """send_from_directory + 브라우저 캐시. 로그인이 필요한 이미지라 공용(프록시) 캐시는 막고 private으로만 둔다.
    ETag/Last-Modified는 그대로라 만료 후에는 304로 재검증된다."""
    resp = send_from_directory(directory, filename, max_age=IMAGE_CACHE_SECONDS)
    resp.cache_control.public = None
    resp.cache_control.private = True
    return resp


@image_bp.route('/images')
@login_required
@_log_slow()
def get_image():
    filename = request.args.get('filename')
    filename = urllib.parse.unquote_plus(filename)
    dir = request.args.get('dir')
    selected_dir = request.args.get('selected_dir', '')
    original = request.args.get('original', '') in ('1', 'true')

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
            return _send_cached(directory, filename)  # 없으면 함수가 404를 응답함
        else:
            abort(404)  # 유효하지 않은 market 값에 대해 404 에러 반환
    else:
        abort(400, 'Invalid dir')

    if original:
        # 원본 요청 시 썸네일을 건너뛰고 원본 파일을 바로 반환
        return _send_cached(base_dir, filename)

    # thumb 서브디렉토리에 동일 이름 .webp 있으면 우선 반환
    thumb_dir = os.path.join(base_dir, 'thumb')
    if not os.path.isdir(thumb_dir):
        # raise FileNotFoundError(f"thumb_dir이 존재하지 않습니다: {thumb_dir}")
        return _send_cached(base_dir, filename)

    name_without_ext, _ = os.path.splitext(filename)
    webp_path = os.path.join(thumb_dir, name_without_ext + '.webp')
    if os.path.exists(webp_path):
        return _send_cached(thumb_dir, name_without_ext + '.webp')

    return _send_cached(base_dir, filename)

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

    try:
        src_path = safe_path_join(directory, filename)
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Invalid filename'}), 400
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


# ── 예측종목(LightGBM) ──────────────────────────────────────────────────────
# job/multi_kor_stocks_lgbm.py, job/multi_us_stocks_lgbm.py (AutoSales.py) 결과.
# 시장당 폴더 1개(F:\lgbm_stocks, F:\lgbm_stocks_us)에 파일이 그대로 쌓인다 — 위 kospi/nasdaq와
# 같은 방식. 날짜 조회는 폴더가 아니라 파일명 앞의 YYYYMMDD를 파싱해서 한다.
# [2026-09-21] kr_watch = 트랙 B(관찰 목록). ⚠️ 매수 신호가 아니다 —
# AutoSales.py의 job/multi_kor_stocks_lgbm.py는 매수 신호(트랙 A)가 0건인 날에만
# raw 상위 2개를 이 폴더에 넣는다. 실측 실행 건당 -0.79%로 사면 평균적으로 손해다.
# 사이드카 json의 "track" 필드가 "alert"/"watch"로 구분되므로 화면에서 반드시 구분해 렌더할 것.
LGBM_DIR_MAP = {
    'kr': r'F:\lgbm_stocks',
    'us': r'F:\lgbm_stocks_us',
    'kr_watch': r'F:\lgbm_stocks_watch',
}
LGBM_FILENAME_DATE_RE = re.compile(r'^(\d{8})')


def _lgbm_available_dates(directory):
    if not os.path.isdir(directory):
        return []
    dates = set()
    for name in os.listdir(directory):
        m = LGBM_FILENAME_DATE_RE.match(name)
        if m:
            dates.add(m.group(1))
    return sorted(dates, reverse=True)


@image_bp.route('/lgbm-stocks/<market>', methods=['GET'], endpoint='lgbm-stock-list')
@login_required
def lgbm_stock_list(market):
    market = market.lower()
    directory = LGBM_DIR_MAP.get(market)
    if directory is None:
        abort(404)

    dates = _lgbm_available_dates(directory)
    date_str = request.args.get('date') or (dates[0] if dates else datetime.today().strftime('%Y%m%d'))
    if not re.fullmatch(r'\d{8}', date_str):
        abort(400)

    page = int(request.args.get('page', 1))
    start = (page - 1) * LIMIT_PAGE_NUM

    if os.path.isdir(directory):
        all_names = [f for f in os.listdir(directory) if f.startswith(date_str)
                     and os.path.isfile(os.path.join(directory, f))]
        images_length = len(all_names)
        # get_stock_graphs()는 디렉터리 전체를 대상으로 정렬하므로, 이 날짜 파일만 걸러낸
        # 리스트는 직접 정렬한다 — 확률(파일명의 %) 내림차순.
        def _proba_key(filename):
            m = re.search(r'\[\s*([-+]?\d+\.\d+)%\s*\]', filename)
            return -float(m.group(1)) if m else 0.0
        all_names.sort(key=_proba_key)
        images = all_names[start:start + LIMIT_PAGE_NUM]
    else:
        images, images_length = [], 0
    total_pages = max(1, (images_length + LIMIT_PAGE_NUM - 1) // LIMIT_PAGE_NUM)

    return render_template(
        'lgbm_stock_list.html',
        market=market, date=date_str, dates=dates,
        images=images, page=page, total_pages=total_pages,
        images_length=images_length,
        version=int(time.time()),
    )


@image_bp.route('/lgbm-stocks/<market>/<filename>', endpoint='lgbm-stock-graph')
@login_required
def get_lgbm_stock_graph(market, filename):
    market = market.lower()
    directory = LGBM_DIR_MAP.get(market)
    if directory is None:
        abort(404)
    return send_from_directory(directory, filename)

