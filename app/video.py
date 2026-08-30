import os
import json
import random
import subprocess
import threading
import time, gc
import cv2
import re
from send2trash import send2trash, TrashPermissionError
from flask import Blueprint, request, jsonify, send_file, render_template, redirect, url_for, Response, abort, \
    current_app, send_from_directory
from flask_login import login_required
# from werkzeug.utils import secure_filename
from urllib.parse import quote

from config.config import settings

video = Blueprint('video', __name__)

# 영상별 오디오 싱크 오프셋 저장 — { "<dir>": { "<filename>": offset, ... }, ... }
SYNC_OFFSET_FILE = os.path.join(os.path.dirname(__file__), 'video_sync_offsets.json')
_sync_offset_lock = threading.Lock()


def _load_sync_offsets():
    if not os.path.exists(SYNC_OFFSET_FILE):
        return {}
    try:
        with open(SYNC_OFFSET_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, ValueError):
        return {}


def _save_sync_offsets(data):
    tmp_path = SYNC_OFFSET_FILE + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp_path, SYNC_OFFSET_FILE)  # 쓰다가 죽어도 원본 파일이 깨지지 않도록 원자적 교체

# ── 좋아요 = 파일을 그 디렉터리의 'like' 하위 폴더로 실제 이동시키는 방식 ────────────
# 목록의 진실은 JSON이 아니라 "파일이 like 폴더 안에 있는가"다.
#   - Liked   : <VIDEO_DIRECTORYn>/like/**
#   - Unliked : <VIDEO_DIRECTORYn>/** 에서 like 폴더만 제외
LIKE_DIR_NAME = 'like'

# 하트를 누른 순간 바로 옮기지 않고 예약해두는 이유:
# 그 영상은 지금 재생 중이라 (a) Windows에서 파일이 잠겨 있어 이동이 실패하고(WinError 32),
# (b) 성공하더라도 브라우저가 뒤이어 요청할 range가 404가 되어 재생이 끊긴다.
# 그래서 의사만 기록해두고, 그 영상에서 넘어갈 때(/like/flush)나 목록을 새로 받을 때 실제로 옮긴다.
#   { "<dir>": { "pending": { "<현재 상대경로>": true(=like로) / false(=원위치로) },
#                "origin":  { "like/a.mp4": "원래 상대경로" } } }
LIKE_STATE_FILE = os.path.join(os.path.dirname(__file__), 'video_like_state.json')
_like_state_lock = threading.Lock()

# 폴더 방식으로 바꾸기 전에 쓰던 기록 — /like/migrate에서 한 번 옮겨줄 때만 읽는다
LIKED_VIDEOS_FILE = os.path.join(os.path.dirname(__file__), 'liked_videos.json')
_liked_videos_lock = threading.Lock()


def _load_json_file(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (IOError, ValueError):
        return {}


def _save_json_file(path, data):
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp_path, path)  # 쓰다가 죽어도 원본 파일이 깨지지 않도록 원자적 교체


def _load_like_state():
    return _load_json_file(LIKE_STATE_FILE)


def _save_like_state(data):
    _save_json_file(LIKE_STATE_FILE, data)


def _load_liked_videos():
    return _load_json_file(LIKED_VIDEOS_FILE)


def _save_liked_videos(data):
    _save_json_file(LIKED_VIDEOS_FILE, data)


def _video_root(directory):
    if directory is None:
        return None
    return settings.get('VIDEO_DIRECTORY' + str(directory))


def _to_rel(video_directory, abs_path):
    """목록(get_videos)이 만들어내는 상대경로 표기와 똑같은 문자열을 만든다.
    루트 파일은 './a.mp4', like 폴더 파일은 'like/a.mp4' — 표기가 어긋나면
    video_sync_offsets.json 키와 클라이언트의 currentVideo가 서로 안 맞는다."""
    rel_dir = os.path.relpath(os.path.dirname(abs_path), video_directory)
    return os.path.join(rel_dir, os.path.basename(abs_path)).replace(os.path.sep, '/')


def _to_abs(video_directory, rel):
    return os.path.join(video_directory, rel.replace('/', os.path.sep))


def _is_in_like_dir(rel):
    return (rel or '').replace('\\', '/').split('/')[0].lower() == LIKE_DIR_NAME


def _unique_path(path):
    """서로 다른 하위 폴더에 같은 파일명이 있으면 like 폴더에서 충돌한다 — 덮어쓰지 말고 번호를 붙인다."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 2
    while os.path.exists('%s (%d)%s' % (base, i, ext)):
        i += 1
    return '%s (%d)%s' % (base, i, ext)


def _move_with_backoff(src, dst, attempts=5, base=0.2):
    """재생 중이라 잠겨 있으면(WinError 32/33) 핸들이 풀릴 때까지 지수 백오프로 재시도한다.
    try_trash_with_backoff()와 같은 방식. 끝내 실패하면 False — 예약을 남겨두고 다음에 다시 시도한다."""
    for i in range(attempts):
        try:
            os.rename(src, dst)
            return True
        except OSError as e:
            if getattr(e, 'winerror', None) in (5, 32, 33) or isinstance(e, PermissionError):
                if i == attempts - 1:
                    return False
                gc.collect()                 # 참조 정리(잠재적 핸들 해제 유도)
                time.sleep(base * (2 ** i))  # 0.2s, 0.4s, 0.8s, ...
                continue
            raise
    return False


def _rename_sync_offset(directory, old_rel, new_rel):
    """파일이 옮겨지면 video_sync_offsets.json의 키도 같이 따라가야 저장해둔 싱크 값을 안 잃는다."""
    if old_rel == new_rel:
        return
    with _sync_offset_lock:
        all_offsets = _load_sync_offsets()
        dir_offsets = all_offsets.get(str(directory))
        if not dir_offsets or old_rel not in dir_offsets:
            return
        dir_offsets[new_rel] = dir_offsets.pop(old_rel)
        _save_sync_offsets(all_offsets)


def _prune_dir_state(state, key):
    dir_state = state.get(key) or {}
    if not dir_state.get('pending'):
        dir_state.pop('pending', None)
    if not dir_state.get('origin'):
        dir_state.pop('origin', None)
    if not dir_state:
        state.pop(key, None)


def _flush_pending_moves(directory, attempts=5):
    """예약된 이동을 실제로 수행한다. 잠겨서 못 옮긴 건 예약에 남겨 다음 기회에 다시 시도한다."""
    video_directory = _video_root(directory)
    if not video_directory:
        return {'moved': 0, 'deferred': 0, 'moves': {}}

    key = str(directory)
    moved = 0
    deferred = 0
    moves = {}   # {옮기기 전 상대경로: 옮긴 뒤 상대경로} — 클라이언트가 들고 있는 경로를 갱신하는 데 쓴다
    with _like_state_lock:
        state = _load_like_state()
        dir_state = state.get(key) or {}
        pending = dict(dir_state.get('pending') or {})
        if not pending:
            return {'moved': 0, 'deferred': 0, 'moves': {}}
        origin = dict(dir_state.get('origin') or {})

        for rel, want_like in list(pending.items()):
            src = _to_abs(video_directory, rel)
            if not os.path.exists(src):
                pending.pop(rel, None)  # 그새 삭제됐거나 이미 옮겨진 파일
                continue

            if want_like:
                like_dir = os.path.join(video_directory, LIKE_DIR_NAME)
                try:
                    if not os.path.isdir(like_dir):
                        os.makedirs(like_dir)
                except OSError as e:
                    print('[video] like 폴더 생성 실패: %s' % e)
                    deferred += 1
                    continue
                dst = _unique_path(os.path.join(like_dir, os.path.basename(src)))
            else:
                back = origin.get(rel)  # 좋아요 누르기 전 위치를 기억해뒀으면 그리로 되돌린다
                dst = None
                if back:
                    candidate = _to_abs(video_directory, back)
                    parent = os.path.dirname(candidate)
                    if os.path.isdir(parent):
                        dst = candidate
                    else:
                        try:
                            os.makedirs(parent)
                            dst = candidate
                        except OSError:
                            dst = None
                if dst is None:
                    dst = os.path.join(video_directory, os.path.basename(src))
                dst = _unique_path(dst)

            try:
                ok = _move_with_backoff(src, dst, attempts=attempts)
            except OSError as e:
                print('[video] like 이동 실패(%s): %s' % (rel, e))
                ok = False

            if not ok:
                deferred += 1
                continue

            new_rel = _to_rel(video_directory, dst)
            moves[rel] = new_rel
            _rename_sync_offset(key, rel, new_rel)
            if want_like:
                origin[new_rel] = rel   # 나중에 하트를 풀면 여기로 되돌린다
            else:
                origin.pop(rel, None)
            pending.pop(rel, None)
            moved += 1

        dir_state['pending'] = pending
        dir_state['origin'] = origin
        state[key] = dir_state
        _prune_dir_state(state, key)
        _save_like_state(state)

    return {'moved': moved, 'deferred': deferred, 'moves': moves}


def _list_video_files(video_directory, liked_param):
    """liked_param: 'true'=like 폴더 안, 'false'=like 폴더 제외한 나머지, None=전체"""
    like_root = os.path.join(video_directory, LIKE_DIR_NAME)
    want_liked = (liked_param or '').lower() == 'true'

    if want_liked:
        if not os.path.isdir(like_root):
            return []
        walk_root = like_root
    else:
        walk_root = video_directory

    exclude_like = (liked_param is not None) and not want_liked
    videos = []
    for root, dirs, files in os.walk(walk_root):
        if exclude_like and os.path.abspath(root) == os.path.abspath(video_directory):
            # like 폴더는 '안 누른 영상' 목록에서 빼고, 그 아래로 내려가지도 않는다
            dirs[:] = [d for d in dirs if d.lower() != LIKE_DIR_NAME]
        for file in files:
            if file.lower().endswith(('.mp4', '.avi', '.mkv', '.ts', '.mov')):
                rel_dir = os.path.relpath(root, video_directory)
                rel_file = os.path.join(rel_dir, file)
                videos.append(rel_file.replace(os.path.sep, '/'))
    return videos

# 설정
TEMP_IMAGE_DIR = settings['TEMP_IMAGE_DIR']
IMAGE_DIR = settings['IMAGE_DIR']
IMAGE_DIR2 = settings['IMAGE_DIR2']
MOVE_DIR = settings['MOVE_DIR']
REF_IMAGE_DIR = settings['REF_IMAGE_DIR']
COS_DIR = settings['COS_DIR']

WIN_SHARING_VIOLATION = -2144927705  # 0x80270027



@video.route('/select-directory', methods=['POST'], endpoint='select-directory')
@login_required
def select_directory():
    directory = request.form.get('directory')
    return redirect(url_for('video.video_player', directory=directory))

@video.route('/video-player/<directory>')
@login_required
def video_player(directory):
    return render_template('video.html', directory=directory, version=int(time.time()))

@video.route('/videos', methods=['GET'])
@login_required
def get_videos():
    directory = request.args.get('dir')
    liked_param = request.args.get('liked')  # 'true' / 'false' / 없음(전체)
    video_directory = _video_root(directory)
    if not video_directory:
        abort(404)

    # 목록을 만들기 전에 밀린 이동부터 처리한다 — 안 그러면 방금 하트한 영상이 아직 제자리에 있어
    # 'Unliked' 목록에 다시 섞여 나온다. 재생 중이라 잠긴 파일까지 기다리진 않고(attempts=1)
    # 넘어간다 — 그건 /like/flush가 다시 맡는다.
    _flush_pending_moves(directory, attempts=1)

    videos = _list_video_files(video_directory, liked_param)

    # print('############### video_list ###############')
    random.seed(time.time())
    random.shuffle(videos)
    return jsonify(videos)

@video.route('/liked-videos', methods=['GET'])
@login_required
def get_liked_videos():
    """하트 버튼 표시용 — like 폴더에 들어있는 영상 + 아직 못 옮긴 예약분까지 합쳐서 돌려준다."""
    directory = request.args.get('dir')
    video_directory = _video_root(directory)
    if not video_directory:
        return jsonify([])

    liked = set(_list_video_files(video_directory, 'true'))
    with _like_state_lock:
        state = _load_like_state()
        pending = (state.get(str(directory)) or {}).get('pending') or {}
    for rel, want_like in pending.items():
        if want_like:
            liked.add(rel)      # 아직 제자리에 있지만 하트는 켜져 있어야 한다
        else:
            liked.discard(rel)  # 아직 like 폴더에 있지만 하트는 꺼져 있어야 한다
    return jsonify(sorted(liked))

@video.route('/like', methods=['POST'])
@login_required
def set_liked_video():
    """하트 토글 — 실제 파일 이동은 예약만 하고, 그 영상에서 넘어갈 때(/like/flush) 수행한다.
    지금 재생 중인 파일을 그 자리에서 옮기면 스트림이 끊기고 Windows에선 잠겨서 실패한다."""
    data = request.get_json(silent=True) or {}
    directory = data.get('dir')
    filename = data.get('filename')
    liked = bool(data.get('liked'))
    if not directory or not filename:
        return '', 400
    if not _video_root(directory):
        return '', 404

    key = str(directory)
    with _like_state_lock:
        state = _load_like_state()
        dir_state = state.setdefault(key, {})
        pending = dir_state.setdefault('pending', {})
        # 이미 like 폴더 안에 있는 파일을 또 하트하는 등, 원하는 상태가 지금 위치와 같으면
        # 예약할 게 없다 (하트를 두 번 눌러 원위치로 돌아온 경우도 여기서 예약이 취소된다)
        if liked == _is_in_like_dir(filename):
            pending.pop(filename, None)
        else:
            pending[filename] = liked
        _prune_dir_state(state, key)
        _save_like_state(state)
    return '', 204

@video.route('/like/flush', methods=['POST'])
@login_required
def flush_liked_videos():
    """예약된 이동을 실제로 수행한다. 클라이언트가 그 영상에서 넘어갈 때/페이지를 벗어날 때 호출한다."""
    data = request.get_json(silent=True) or {}
    directory = data.get('dir') or request.args.get('dir')
    if not directory:
        return '', 400
    if not _video_root(directory):
        return '', 404
    return jsonify(_flush_pending_moves(directory))

@video.route('/like/migrate', methods=['POST'])
@login_required
def migrate_liked_videos():
    """폴더 방식으로 바꾸기 전 liked_videos.json에 쌓여 있던 좋아요를 실제 like 폴더로 옮긴다.
    파일을 대량으로 움직이는 작업이라 자동 실행하지 않는다 — 직접 호출할 때만 동작한다.
    dir 없이 부르면 기록에 있는 모든 디렉터리를 처리한다."""
    data = request.get_json(silent=True) or {}
    only_dir = data.get('dir') or request.args.get('dir')

    with _liked_videos_lock:
        legacy = _load_liked_videos()

    result = {}
    for key in list(legacy.keys()):
        if only_dir and str(only_dir) != str(key):
            continue
        video_directory = _video_root(key)
        if not video_directory:
            result[key] = {'skipped': 'unknown directory'}
            continue

        queued = 0
        missing = 0
        with _like_state_lock:
            state = _load_like_state()
            dir_state = state.setdefault(str(key), {})
            pending = dir_state.setdefault('pending', {})
            for rel in legacy.get(key) or []:
                if _is_in_like_dir(rel):
                    continue  # 이미 like 폴더
                if not os.path.exists(_to_abs(video_directory, rel)):
                    missing += 1
                    continue
                pending[rel] = True
                queued += 1
            _prune_dir_state(state, str(key))
            _save_like_state(state)

        moved = _flush_pending_moves(key)
        result[key] = {'queued': queued, 'missing': missing,
                       'moved': moved['moved'], 'deferred': moved['deferred']}

        # 옮긴 만큼 legacy 기록에서 제거 (다시 실행해도 중복 이동되지 않도록)
        with _liked_videos_lock:
            legacy_now = _load_liked_videos()
            video_directory = _video_root(key)
            remain = [rel for rel in (legacy_now.get(key) or [])
                      if os.path.exists(_to_abs(video_directory, rel)) and not _is_in_like_dir(rel)]
            if remain:
                legacy_now[key] = remain
            else:
                legacy_now.pop(key, None)
            _save_liked_videos(legacy_now)

    return jsonify(result)

@video.route('/sync-offsets', methods=['GET'])
@login_required
def get_sync_offsets():
    directory = request.args.get('dir')
    with _sync_offset_lock:
        all_offsets = _load_sync_offsets()
    return jsonify(all_offsets.get(directory, {}))

@video.route('/sync-offset', methods=['POST'])
@login_required
def set_sync_offset():
    data = request.get_json(silent=True) or {}
    directory = data.get('dir')
    filename = data.get('filename')
    offset = data.get('offset')
    if not directory or not filename:
        return '', 400

    with _sync_offset_lock:
        all_offsets = _load_sync_offsets()
        dir_offsets = all_offsets.setdefault(directory, {})
        if not offset:  # 0(기본값) 또는 누락이면 저장해둘 필요 없음
            dir_offsets.pop(filename, None)
        else:
            dir_offsets[filename] = offset
        if not dir_offsets:
            all_offsets.pop(directory, None)
        _save_sync_offsets(all_offsets)
    return '', 204

@video.route('/videos/<path:filepath>', methods=['GET'])
@login_required
def get_video(filepath):
    # basename() : ../../test.mp4 >> test.mp4 .. 경로 traversal 방지
    file_dir = os.path.dirname(filepath)
    filename = os.path.basename(filepath)
    directory = request.args.get('dir')

    key = 'VIDEO_DIRECTORY' + directory
    if key not in settings:
        abort(404)

    video_directory = settings[key]  # 딕셔너리 접근 방식으로 수정
    full_path = os.path.join(video_directory, file_dir, filename)

    if not os.path.exists(full_path):
        print(f"[video] not found: {full_path}")
        abort(404)

    try:
        return send_file(full_path, conditional=True)
    except FileNotFoundError:
        # os.path.exists() 확인과 send_file() 내부 open() 사이의 TOCTOU 레이스 — 경로가
        # \\wsl.localhost\...(Docker Desktop 볼륨)라 네트워크 순단이나 삭제 버튼과의 경합으로
        # 그 짧은 틈에 파일이 사라질 수 있다. 그대로 두면 500으로 죽으므로 404로 처리한다.
        print(f"[video] disappeared before send_file: {full_path}")
        abort(404)


# 이미지 리스트, 채팅 페이지에서 임시로 사용할 엔드포인트
@video.route('/temp-video/<path:filename>', methods=['GET'])
@login_required
def get_temp_video(filename):
    filename = filename.replace("\\", "/")

    dir_type = request.args.get('dir')
    selected_dir = request.args.get('selected_dir')

    if dir_type == 'temp':
        base_dir = TEMP_IMAGE_DIR
        if selected_dir:
            base_dir = os.path.join(TEMP_IMAGE_DIR, selected_dir)
    elif dir_type == 'image2':
        base_dir = IMAGE_DIR2
    elif dir_type == 'image':
        base_dir = IMAGE_DIR
    elif dir_type == 'move':
        base_dir = MOVE_DIR
    elif dir_type == 'refine':
        base_dir = REF_IMAGE_DIR
    elif dir_type == 'cos':
        base_dir = COS_DIR
    else:
        abort(400)

    # send_file보다 send_from_directory사용하는게 안전
    return send_from_directory(
        base_dir,
        filename,
        conditional=True  # 영상의 필요한 구간만
    )


def try_trash_with_backoff(path, attempts=5, base=0.2):
    for i in range(attempts):
        try:
            send2trash(path)
            return True
        except OSError as e:
            if getattr(e, "winerror", None) == WIN_SHARING_VIOLATION:
                gc.collect()                # 참조 정리(잠재적 핸들 해제 유도)
                time.sleep(base * (2 ** i)) # 지수 백오프: 0.2s, 0.4s, 0.8s, ...
                continue                    # 다음 반복에서 재시도
            raise                           # 다른 오류면 즉시 전파
    return False

@video.route('/delete/<path:filename>', methods=['POST'])
@login_required
def delete_video(filename):
    directory = request.args.get('dir')
    video_directory = settings.get('VIDEO_DIRECTORY' + directory)  # 딕셔너리 접근 방식으로 수정
    if not video_directory:
        return '', 404
    
    file_path = os.path.join(video_directory, filename)
    if os.path.exists(file_path):
        normalized_path = os.path.normpath(file_path)
        try:
            # send2trash(normalized_path) # 휴지통
            try_trash_with_backoff(normalized_path)
        except OSError as e:
            print(f"Error: {e}") # 0x80270027은 “그 파일/폴더 지금 누가 쓰는 중이라 휴지통 이동 못 함” 이라는 뜻
        except TrashPermissionError as e:
            print(f"Permission Error: {e}")

        # 지워진 영상의 예약/원위치 기록도 같이 정리 (안 하면 없는 파일을 계속 옮기려 든다)
        key = str(directory)
        with _like_state_lock:
            state = _load_like_state()
            dir_state = state.get(key) or {}
            changed = False
            if filename in (dir_state.get('pending') or {}):
                dir_state['pending'].pop(filename, None)
                changed = True
            if filename in (dir_state.get('origin') or {}):
                dir_state['origin'].pop(filename, None)
                changed = True
            if changed:
                state[key] = dir_state
                _prune_dir_state(state, key)
                _save_like_state(state)

        # print(f"[ {filename} ] is successfully deleted")
        # os.remove(file_path)
        return '', 204
    return '', 404



###################################################


def get_video_codec(file_path):
    video = cv2.VideoCapture(file_path)
    if not video.isOpened():
        return None
    codec = int(video.get(cv2.CAP_PROP_FOURCC))
    video.release()
    return codec


# 바이트 Range를 ffmpeg -ss 탐색 시간으로 정확히 환산하려면 이 파일의 실제 재생시간(초)이
# 필요하다. ffprobe로 컨테이너의 format duration을 직접 읽는다(cv2의 프레임수/fps 계산보다
# mkv 등에서 더 신뢰할 수 있다).
def get_video_duration_seconds(file_path):
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5
        )
        duration = float(result.stdout.strip())
        return duration if duration > 0 else None
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


# HEVC(H.265)는 mp4 컨테이너 안에서 hvc1/hev1 두 태그 중 하나로 표기되지만, OpenCV의
# CAP_PROP_FOURCC는 그 박스 태그가 아니라 FFmpeg 내부 코덱 이름을 그대로(소문자 'hevc') 반환한다
# — ffprobe로 실제 문제 파일들(진지 커플 펠라.SVP.mp4, ktds775 시오리.SVP.mkv)을 열어 codec_tag_string은
# hev1/[0][0][0][0]으로 제각각이었지만 cv2로 읽으면 항상 b'hevc'였다. hvc1/hev1만 체크하던 이전
# 버전은 이 때문에 전혀 안 걸렸다. 크롬은 HEVC를 하드웨어 디코드로만 지원해서(소프트웨어 폴백
# 없음) 이게 간헐적으로 실패하면 에러 없이 소리만 나오고 화면만 까맣게 굳는다 — SVP(프레임 보간)
# 도구로 인코딩된 파일들에서 특히 자주 나왔다.
def _is_hevc_codec(codec):
    hevc_fourccs = (
        cv2.VideoWriter_fourcc(*'hvc1'),
        cv2.VideoWriter_fourcc(*'hev1'),
        cv2.VideoWriter_fourcc(*'hevc'),
        cv2.VideoWriter_fourcc(*'HEVC'),
    )
    return codec in hevc_fourccs


def generate_ffmpeg_command(input_path, start_time, output_codec='libx264'):
    command = [
        'ffmpeg',
        '-ss', str(start_time),  # 시작 시간
        '-i', input_path,  # 입력 파일
        '-c:v', output_codec,  # 비디오 코덱
        '-preset', 'ultrafast',  # 인코딩 속도 (품질 감소)
        '-c:a', 'aac',  # 오디오 코덱
        '-f', 'mp4',
        '-movflags', '+frag_keyframe+empty_moov+faststart',  # 실시간 스트리밍을 위한 설정
        'pipe:1'  # 표준 출력으로 데이터를 전송
    ]

    return command


# 크롬 <video>는 Matroska(.mkv) 컨테이너를 디먹싱하지 못한다 — 코덱 자체는 멀쩡해도 컨테이너를
# 못 읽어서 화면만 까맣게 나오고(오디오 트랙만 별도 경로로 재생되는 경우가 있어 소리는 남) 콘솔에
# 에러도 안 남는 증상으로 나타난다(OS/드라이버 상태에 따라 간헐적으로만 재현되기도 한다). 그래서
# ffmpeg로 mp4 컨테이너로 감싸서(코덱은 그대로 복사 — HEVC만 예외적으로 h264로 재인코딩) 내보낸다.
def stream_video_transcoded(file_path):
    codec = get_video_codec(file_path)
    output_codec = 'libx264' if _is_hevc_codec(codec) else 'copy'

    # Range의 시작 바이트를 실제 탐색 시간(초)으로 바꾼다. 예전엔 /1000로 나눴는데 이건 실제
    # 비트레이트와 무관한 근사치라 파일 끝부분을 찌르는 probe 요청에서 수만 초짜리 말도 안 되는
    # 값이 나와 ffmpeg가 거기서 멈췄다(응답 없음의 원인). 그렇다고 Range를 아예 무시하고 항상
    # 0부터 재생하면(그 다음 시도) 탐색바를 눌러도 항상 처음으로 되돌아가고, 매 요청마다 ffmpeg가
    # 통째로 재시작되는 문제가 생겼다. 이 파일의 실제 재생시간(ffprobe)과 파일 크기의 비율로
    # 바이트→초를 정확히 환산하면 두 문제 다 해결된다(대체로 일정한 비트레이트라는 가정 하에).
    start_time = 0
    range_header = request.headers.get('Range', None)
    if range_header:
        match = re.search(r'bytes=(\d+)-', range_header)
        if match:
            start_byte = int(match.group(1))
            if start_byte > 0:
                duration = get_video_duration_seconds(file_path)
                file_size = os.path.getsize(file_path)
                if duration and file_size:
                    start_time = start_byte * duration / file_size

    command = generate_ffmpeg_command(file_path, start_time, output_codec)

    # FFmpeg 프로세스 시작 — stderr는 어디서도 안 읽으므로 PIPE로 열면 ffmpeg가 경고/로그를
    # 충분히 많이 써서 OS 파이프 버퍼가 차는 순간 거기서 멈추고, 그러면 stdout도 같이 막혀
    # 아래 read()가 영원히 블록된다(응답이 아예 안 오는 원인이었다). 안 읽을 거면 버려야 한다.
    def generate():
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=-1)
        try:
            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    break
                yield chunk
        finally:
            process.kill()

    # 실시간으로 트랜스코딩되는 스트림이라 최종 출력 바이트 크기를 미리 알 수 없다 — 원본
    # 파일 크기 기준으로 Content-Length/Content-Range를 계산해서 붙이면(예전 코드) 실제 ffmpeg
    # 출력 크기와 달라, 브라우저가 스트림 도중 "약속한 길이와 다르다"(ERR_CONTENT_LENGTH_MISMATCH)
    # 며 응답을 통째로 버리고 계속 재요청하는 원인이었다. 길이를 모른다고 정직하게 200 + 청크
    # 전송(Content-Length 생략)으로 내보낸다.
    headers = {
        'Content-Type': 'video/mp4',
        'Cache-Control': 'no-store',
    }

    return Response(generate(), status=200, headers=headers)


@video.route('/stream/<path:filename>', methods=['GET'])
def video_stream(filename):
    print('############### stream ###################')
    directory = request.args.get('dir')
    video_directory = settings['VIDEO_DIRECTORY' + directory]
    file_path = os.path.join(video_directory, filename)

    if not os.path.exists(file_path):
        abort(404)

    return stream_video_transcoded(file_path)
