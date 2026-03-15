from flask import Blueprint, render_template, jsonify, request, send_file, send_from_directory, session, url_for, redirect, Response, stream_with_context
import ctypes
from flask_login import login_required
import zipfile
import os
import io
import json
from app.image import get_images
from app.image import LIMIT_PAGE_NUM
from app.repository.chats.ChatDTO import ChatDTO
from app.repository.chats.ChatPreviewDTO import ChatPreviewDTO
from app.repository.chats.chats import insert_chat, get_chats_count, find_chats_by_offset, chats_to_line_list, \
    find_chat_room_by_roomname, update_chat_room, insert_chat_url_preview, find_chat_url_preview, \
    find_chat_indices_by_keyword, fetch_context_by_center
from app.repository.scrap_posts.ScrapPostDTO import ScrapPostDTO
from app.repository.scrap_posts.scrap_posts import insert_scrap_post, find_scrap_post
from app.repository.users.users import find_user_by_username
from job.batch_process import run_crawl_ai_image
from job.buy_lotto import async_buy_lotto
from utils.common import open_folder
from utils.fetch_url_preview import fetch_url_preview_by_selenium
from job.compress_file import compress_directory, compress_directory_to_zip
import multiprocessing
import time
from flask_socketio import SocketIO
from datetime import datetime
from config.config import settings
import asyncio

from utils.wsgi_midleware import logger
from filelock import FileLock, Timeout
import random

func = Blueprint('func', __name__)

socketio = SocketIO() # __init__ 으로 전달

LOG_DIR = "logs/app"
DATA_DIR = "data"
MEMO_FILE = 'memo.txt'
CHAT_FILE = 'chat.txt'
STATE_FILE = 'data.json'
MEMO_FILE_PATH = os.path.join(DATA_DIR, MEMO_FILE)
CHAT_FILE_PATH = os.path.join(DATA_DIR, CHAT_FILE)
CHAT_STATE_FILE_PATH = os.path.join(DATA_DIR, STATE_FILE)
TEMP_IMAGE_DIR = settings['TEMP_IMAGE_DIR']
MAX_FETCH_MESSAGE_SIZE = 100
UNC_DIR = settings['UNC_DIR']
VIDEO_DIRECTORY7 = settings['VIDEO_DIRECTORY7']


# Windows API 상수
SHERB_NOCONFIRMATION = 0x00000001  # 사용자 확인 대화 상자를 표시하지 않음
SHERB_NOPROGRESSUI = 0x00000002   # 진행 UI를 표시하지 않음
SHERB_NOSOUND = 0x00000004        # 소리를 재생하지 않음




################################# IMAGE #####################################

def check_recycle_bin():
    """휴지통 상태 확인"""
    try:
        # SHQueryRecycleBinW 구조체 초기화
        class SHQUERYRBINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("i64Size", ctypes.c_longlong),
                ("i64NumItems", ctypes.c_longlong),
            ]

        rbinfo = SHQUERYRBINFO()
        rbinfo.cbSize = ctypes.sizeof(SHQUERYRBINFO)

        # 휴지통 상태 확인
        result = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(rbinfo))
        if result != 0:
            return {"status": "error", "message": f"휴지통 상태를 확인하는 데 실패했습니다. 오류 코드: {result}"}

        return {
            "is_empty": rbinfo.i64NumItems == 0,
            "size": rbinfo.i64Size,
            "items": rbinfo.i64NumItems
        }
    except Exception as e:
        return {"status": "error", "message": f"휴지통 상태 확인 중 예외가 발생했습니다: {e}"}

def empty_recycle_bin():
    """휴지통 비우기"""
    try:
        # 휴지통 상태 확인
        status = check_recycle_bin()
        if status.get("is_empty", False):
            return {"status": "info", "message": "휴지통이 이미 비워져 있습니다."}

        # 휴지통 비우기
        result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
        if result == 0:
            return {"status": "success", "message": "휴지통이 성공적으로 비워졌습니다."}
        else:
            return {"status": "error", "message": f"휴지통을 비우는 데 실패했습니다. 오류 코드: {result}"}
    except Exception as e:
        return {"status": "error", "message": f"예기치 않은 오류가 발생했습니다: {e}"}

@func.route('/empty-trash-bin', methods=['POST'])
@login_required
def handle_empty_recycle_bin():
    """휴지통 비우기 요청 처리"""
    result = empty_recycle_bin()
    return jsonify(result)

@func.route('/download-zip/page', methods=['GET'])
@login_required
def download_page_zip():
    try:
        target_directory = request.args.get('dir')
        title_directory = request.args.get('title')
        page = int(request.args.get('page', 1))

        if not target_directory:
            return jsonify({"error": "Directory path not provided"}), 400

        if target_directory == 'temp':
            target_directory = os.path.join(TEMP_IMAGE_DIR, title_directory)

        if not os.path.exists(target_directory) or not os.path.isdir(target_directory):
            return jsonify({"error": "Invalid or non-existent directory path"}), 400

        start = (page - 1) * LIMIT_PAGE_NUM
        images, page = get_images(start, LIMIT_PAGE_NUM, target_directory, page)

        if not images:
            return jsonify({"error": "No files found for the specified page"}), 404

        # ZIP 파일 이름 설정
        zip_filename = "files.zip"

        # 메모리에 ZIP 파일 생성
        zip_stream = io.BytesIO()
        with zipfile.ZipFile(zip_stream, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # for root, dirs, files in os.walk(target_directory): # 해당 디렉토리 모든 파일 압축
            #     for file in files:
            #         file_path = os.path.join(root, file)
            #         arcname = os.path.relpath(file_path, target_directory)  # 상대 경로로 추가
            #         zipf.write(file_path, arcname)
            for image in images: # 선택된 배열만 압축
                file_path = os.path.join(target_directory, image)
                zipf.write(file_path, image)  # 파일 이름만 추가 (상대 경로)

        # 스트림의 시작 위치로 이동
        zip_stream.seek(0)

        # 클라이언트에게 ZIP 파일 반환
        return send_file(
            zip_stream,
            as_attachment=True,
            download_name=zip_filename,
            mimetype='application/zip'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@func.route('/download-zip/all', methods=['GET'])
@login_required
def download_all_zip():
    directory = request.args.get('dir')
    title_directory = request.args.get('title')

    if not directory:
        return jsonify({"error": "Missing 'dir' parameter"}), 400

    if directory == 'temp':
        directory = os.path.join(TEMP_IMAGE_DIR, title_directory)
        print('download_all_zip - directory', directory)

    zip_filename = f"compressed_{os.path.basename(directory)}_.zip"
    zip_filepath = os.path.join(directory, zip_filename)

    # ZIP 파일이 없으면 생성
    if not os.path.isfile(zip_filepath):
        compress_directory(directory)

    # 파일 다운로드
    return send_from_directory(directory, zip_filename, as_attachment=True)

@func.route('/compress-zip', methods=['GET'])
@login_required
def compress_now():
    process = multiprocessing.Process(target=compress_directory_to_zip)
    process.start()
    return jsonify({"status": "Compression started"}), 202


################################# LOG ######################################

def get_log_filename(date=None):
    """주어진 날짜(yyMMdd)의 로그 파일 경로 반환. 날짜가 없으면 오늘 날짜 사용"""
    if date is None:
        date = datetime.now().strftime("%y%m%d")
    month_str = datetime.now().strftime("%y%m")
    return os.path.join(LOG_DIR, f"{month_str}/app_{date}.log")

@func.route("/logs/view")
@login_required
def get_log_viewer():
    """로그 뷰어 HTML 페이지 제공"""
    return render_template("log_viewer.html", version=int(time.time()))

@func.route("/logs")
@login_required
def get_latest_logs():
    """최신 로그 파일 가져오기"""
    return get_logs_by_date(datetime.now().strftime("%y%m%d"))

@func.route("/logs/<date>")
@login_required
def get_logs_by_date(date):
    """특정 날짜의 로그 파일 가져오기"""
    log_file = get_log_filename(date)  # 클라이언트 요청 날짜의 로그 파일 읽기
    if not os.path.exists(log_file):
        return jsonify({"error": f"{date} 로그 파일이 없습니다."}), 404

    def generate():
        with open(log_file, encoding='utf-8') as f:
            for line in f:
                yield line

    return Response(generate(), mimetype="text/plain")

    # try:
    #     with open(log_file, "r", encoding="utf-8") as f:
    #         logs = f.readlines()
    # except PermissionError:
    #     return jsonify({"error": "로그 파일을 현재 사용할 수 없습니다. 잠시 후 다시 시도하세요."}), 503
    # except Exception as e:
    #     return jsonify({"error": f"로그 파일을 읽는 중 오류 발생: {e}"}), 500

    # return jsonify({"logs": logs})

@func.route("/logs/stream")
def stream_logs():
    """SSE를 사용하여 실시간 로그 스트리밍"""
    def generate():
        log_file = get_log_filename()
        last_position = os.path.getsize(log_file)  # 시작 시점: 파일 맨 끝

        # 연결 직후 한 번은 무조건 데이터 전송 (브라우저가 onopen 판단 가능하도록)
        yield "data: 연결됨\n\n"

        while True:
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    f.seek(last_position)

                    line = f.readline()
                    if line:
                        yield f"data: {line.strip()}\n\n"
                        last_position = f.tell()
                    else:
                        # 주석 형태(:로 시작)의 SSE 이벤트는 클라이언트에 표시되진 않지만 연결을 유지
                        # SSE 연결이 죽었는지 판단하려면 최소한의 유효 응답이라도 주기적으로 받아야 한다
                        yield ": keep-alive\n\n"
                        # 너무 빠르면 CPU 100% 될 수 있으니 적절 조절
                        time.sleep(0.3)

            except Exception as e:
                yield f"data: 오류: {e}\n\n"
                time.sleep(1)

    return Response(stream_with_context(generate()), content_type="text/event-stream")

'''
def tail_log_file():
    """실시간 로그를 WebSocket으로 전송하는 함수"""
    log_file = get_log_filename()

    last_position = 0  # 마지막으로 읽은 파일 위치 저장

    while True:
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                f.seek(last_position)  # 마지막 읽은 위치로 이동

                while True:
                    line = f.readline()
                    if not line:
                        break  # 새로운 내용이 없으면 반복문 탈출

                    socketio.emit("log_update", {"log": line})  # 프론트로 로그 전송
                    last_position = f.tell()  # 읽은 위치 저장

            time.sleep(1)  # 새로운 로그가 없으면 잠시 대기

        except Exception as e:
            print(f"로그 파일 읽기 오류: {e}")
            time.sleep(1)  # 오류 발생 시 재시도


@socketio.on("connect")
def handle_connect():
    """클라이언트가 WebSocket에 연결될 때 실행"""
    socketio.start_background_task(tail_log_file)  # 백그라운드에서 로그 모니터링 시작
'''


################################# Chat ######################################

# 로그 파일에서 가장 최근 N개의 메시지 가져오기
def get_last_n_lines(filepath, n):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return lines[-n:]  # 가장 마지막 N개 줄 반환
    except FileNotFoundError:
        return []  # 파일이 없으면 빈 리스트 반환

def get_last_n_lines(filepath, start, end):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total = len(lines)

        # 역방향 슬라이싱을 위한 시작/끝 계산
        slice_end = total - start
        slice_start = max(0, total - end)

        return lines[slice_start:slice_end]

    except FileNotFoundError:
        return []

def normalize_ip(ip_address):
    if ip_address.startswith("::ffff:"):
        return ip_address[7:]  # 앞에 "::ffff:" 빼버림
    return ip_address

# 인코딩 가능한지 확인하고 처리 > 처리 못하면 '?' 대체
def sanitize_text(text):
    return text.encode('utf-8', errors='replace').decode('utf-8')


@func.route("/chat")
@login_required
def get_chat_ui():
    if "_user_id" not in session:
        return redirect(url_for('auth.logout'))  # 로그인 안 되어 있으면 로그인 페이지로 이동

    return render_template("chat_ui.html", username=session["_user_id"], maxFetchMessageSize = MAX_FETCH_MESSAGE_SIZE, version=int(time.time()))

@func.route("/api/chat/save-file", methods=["POST"])
# @login_required 추가하면 안된다.. 외부 API 역할을 한다
def save_chat_message():
    data = request.json
    # client_ip = request.headers.get('X-Client-IP') or request.remote_addr
    # client_ip = normalize_ip(client_ip)
    # print(f"✅ 클린 IP 주소: {client_ip}")

    # if not data['timestamp']:
    #     now = datetime.now()
    #     data['timestamp'] = now.strftime("%y%m%d%H%M%S")

    # if not data['username']:
    #     data['username'] = 'error'

    # try:
    #     with open(CHAT_FILE_PATH, "r", encoding="utf-8") as f:
    #         line_count = sum(1 for _ in f)
    # except FileNotFoundError:
    #     line_count = 0  # 파일이 없으면 0부터 시작
    #
    # next_line_number = line_count + 1

    sanitized_message = sanitize_text(data['message'])

    # 아래는 파일에 저장하는 코드
    # log_entry = f"{next_line_number} | {data['timestamp']} | {data['username']} | {sanitized_message}"
    # with open(CHAT_FILE_PATH, "a", encoding="utf-8", errors='replace') as log_file: # errors='replace'; 인코딩할 수 없는 문자를 자동으로 '?'로 대체
    #     log_file.write(log_entry + "\n")

    username = (data.get('username') or '').strip()
    fetch_user = find_user_by_username(username)
    chat_room = find_chat_room_by_roomname(data['roomname'])
    chat = ChatDTO(created_at=str(datetime.now()), user_id=fetch_user.id, message=sanitized_message, chat_room_id=chat_room.id)
    inserted_id = insert_chat(chat)
    chat.last_chat_id = inserted_id
    last_chat_id = update_chat_room(chat)
    update_last_chat_id_in_state(inserted_id)

    resp = jsonify({"status": "success", "inserted_id": inserted_id})
    # return {"status": "success", "inserted_id": inserted_id}, 200

    # username이 있으면 쿠키로 내려보내기
    if username:
        resp.set_cookie(
            "username",
            username,
            max_age=60 * 60 * 24 * 30,  # 30일 유지
            path="/",
            httponly=True,  # JS에서 안 쓸 거면 True
            samesite="Lax"
        )

    return resp

# 비동기로 추가 채팅 로그 요청 API
@func.route("/chat/load-more-chat", methods=["POST"])
@login_required
def load_more_logs():
    offset = int(request.json.get("offset", 0))  # 클라이언트가 요청한 로그 시작점
    # all_lines = get_last_n_lines(CHAT_FILE_PATH, 0, 1000)  # 최대 로그 유지
    all_chat_count = get_chats_count()

    # offset 0 =>  950 ~ 1000 라인
    # offset 1 =>  900 ~ 950 라인...
    # start = max(0, len(all_lines) - offset - MAX_FETCH_MESSAGE_SIZE)
    # end = len(all_lines) - offset

    # if (end > 0):
    #     return jsonify({"logs": all_lines[start:end]})
    # else:
    #     return jsonify({"logs": []})

    sql_offset = min(offset, all_chat_count)
    chat_list = find_chats_by_offset(sql_offset, MAX_FETCH_MESSAGE_SIZE)
    # return jsonify({"logs": all_lines[start:end]})
    return jsonify({"logs": chats_to_line_list(chat_list)})

# 검색 인덱스 구하기 (전역/전체 검색)
@func.route("/chat/search", methods=["POST"])
@login_required
def search_chat():
    q = (request.json.get("q") or "").strip()
    if not q:
        return jsonify({"count": 0, "hits": []})

    # 구현 방식 예시:
    # - DB에 fulltext/like로 전체에서 매칭되는 "행 인덱스" 리스트를 반환
    hits = find_chat_indices_by_keyword(q)  # 오름차순 인덱스
    return jsonify({"count": len(hits), "hits": hits})


# 중심 인덱스를 기준으로 위/아래 컨텍스트 슬라이스 가져오기
@func.route("/chat/fetch-context", methods=["POST"])
@login_required
def fetch_context():
    payload = request.get_json(force=True) or {}
    # center 또는 center_id 둘 다 지원
    center_id = payload.get("center")
    if center_id is None:
        center_id = payload.get("center_id")
    try:
        center_id = int(center_id)
    except (TypeError, ValueError):
        return jsonify({"error": "center (id) is required"}), 400

    before = int(payload.get("before", 25))
    after  = int(payload.get("after", 25))

    rows = fetch_context_by_center(center_id, before, after)

    # id 범위(클라이언트가 스크롤 이어붙일 때 참고용)
    start_id = rows[0][0] if rows else None   # c.*의 첫 컬럼이 id라고 가정
    end_id   = rows[-1][0] if rows else None

    return jsonify({
        "logs": chats_to_line_list(rows),  # "chatId|timestamp|username|msg" 형태
        "start_id": start_id,
        "end_id": end_id,
        "center_id": center_id,
        "count": len(rows)
    })



################################# Memo ######################################
@func.route('/memo', methods=['GET', 'POST'])
@login_required
def memo():
    if request.method == 'POST':
        # textarea의 내용 가져오기
        content = request.form.get('memo_content', '')
        # 줄바꿈 문자 통일 (\r\n -> \n)
        content = content.replace('\r\n', '\n')
        # 파일에 내용 저장
        with open(MEMO_FILE_PATH, 'w', encoding='utf-8') as f:
            f.write(content)
    else:
        # GET 요청 시 기존 메모 내용 읽기
        if os.path.exists(MEMO_FILE_PATH):
            with open(MEMO_FILE_PATH, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = ''
    return render_template('memo.html', content=content, version=int(time.time()))

################################# HLS ######################################

@func.route('/get-hls', methods=['GET'])
@login_required
def get_hls():
    return render_template('hls/test_hls.html')


################################# Call ######################################

@func.route('/video-call', methods=['GET'])
@login_required
def get_video_call():
    return render_template('video_call.html', username=session["_user_id"], version=int(time.time()))

@func.route('/video-call/window', methods=['GET'])
@login_required
def get_video_call_window():
    return render_template('video_call.html', username=session["_user_id"], windowFlag=1, version=int(time.time()))

################################# LOTTO ####################################

@func.route("/buy/lotto-test")
@login_required
def test_lotto():
    asyncio.run(async_buy_lotto())  # 코루틴 실행
    return {"status": "success", "message": "로또 구매 완료!!"}


@func.route("/crawl-ai", methods=['GET'], endpoint='crawl-ai')
@login_required
def crawl_ai():
    run_crawl_ai_image()
    return {"status": "success", "message": "크롤링 시작!!"}


################################# STATE ####################################


DEFAULT_STATE = {
    "chats": {"last_chat_id": 0},
    "users": {},
    "ai_scheduler_uri": None
}
LOCK_PATH = CHAT_STATE_FILE_PATH + ".lock"

# JSON 상태 불러오기
def load_state():
    lock = FileLock(LOCK_PATH, timeout=2)
    try:
        with lock:
            if not os.path.exists(CHAT_STATE_FILE_PATH):
                logger.warning("⚠️ 상태 파일 없음. 기본값 반환.")
                return DEFAULT_STATE

            if os.path.getsize(CHAT_STATE_FILE_PATH) == 0:
                logger.warning("⚠️ 상태 파일 비어 있음. 기본값 반환.")
                return DEFAULT_STATE

            with open(CHAT_STATE_FILE_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Timeout:
        logger.error("❌ 상태 파일 읽기 락 획득 실패 (2초 타임아웃)")
        return DEFAULT_STATE
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON 파싱 실패: {e}")
        return DEFAULT_STATE
    except Exception as e:
        logger.error(f"❌ 상태 로드 중 기타 예외: {e}")
        return DEFAULT_STATE

# JSON 상태 저장하기
def save_state(state: dict):
    lock = FileLock(LOCK_PATH, timeout=2)
    tmp_path = CHAT_STATE_FILE_PATH + ".tmp"

    try:
        with lock:
            try:
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as write_err:
                logger.error(f"❌ 임시 파일 쓰기 실패: {write_err}")
                return

            if os.path.exists(tmp_path):
                try:
                    os.replace(tmp_path, CHAT_STATE_FILE_PATH)
                    # logger.info("✅ 상태 파일 저장 완료")
                except Exception as replace_err:
                    logger.error(f"❌ 상태 파일 교체 실패: {replace_err}")
            else:
                logger.error(f"❌ 임시 파일 누락: {tmp_path} – 저장 스킵됨")

    except Timeout:
        logger.warning("🔒 상태 저장 락 획득 실패 (2초 대기 후 포기)")

def update_last_chat_id_in_state(chat_id):
    if chat_id is None:
        return jsonify({'error': 'lastChatId is required'}), 400
    state = load_state()
    state.setdefault("chats", {})["last_chat_id"] = chat_id
    save_state(state)
    return {'result': 'success'}

# ✅ 사용자별 last_read_chat_id 관리
@func.route('/last-read-chat-id', methods=['GET', 'POST'], endpoint='last-read-chat-id')
@login_required
def last_read_chat_id():
    state = load_state()
    username = request.args.get('username') if request.method == 'GET' else request.get_json().get('username')

    if not username:
        return jsonify({'error': 'username is required'}), 400

    if request.method == 'POST': # 유저가 읽은 채팅 ID 갱신 요청
        chat_id = request.get_json().get('lastReadChatId')
        if chat_id is None:
            return jsonify({'error': 'lastReadChatId is required'}), 400
        state.setdefault("users", {}).setdefault(username, {})["last_read_chat_id"] = chat_id
        save_state(state)
        return jsonify({'result': 'success'})

    else:  # GET
        chat_id = state.get("users", {}).get(username, {}).get("last_read_chat_id", 0)
        return jsonify({'username': username, 'last_read_chat_id': chat_id})

# ✅ 전체 마지막 채팅 ID 관리
@func.route('/last-chat-id', methods=['GET'], endpoint='last-chat-id')
@login_required
def handle_last_chat_id():
    state = load_state()

    # if request.method == 'POST':
    #     chat_id = request.get_json().get('lastChatId')
    #     return jsonify(update_last_chat_id_in_state(chat_id))
    #
    # elif request.method == 'GET':
    #     chat_id = state.get("chats", {}).get("last_chat_id", 0)
    #     return jsonify({'last_chat_id': chat_id})

    chat_id = state.get("chats", {}).get("last_chat_id", 0)
    return jsonify({'last_chat_id': chat_id})


################################# PREVIEW ####################################

@func.route('/api/url-preview', methods=['POST'])
def render_preview():
    data = request.get_json()
    url = data.get('url')
    chat_id = data.get('chat_id')
    # return fetch_url_preview(url)

    # chat_id 로 검색한 결과가 없으면 데이터 fetch
    result = find_chat_url_preview(url)
    if not result:
        result = fetch_url_preview_by_selenium(url)
        preview = ChatPreviewDTO(
            created_at=str(datetime.now()),
            chat_id=chat_id,
            origin_url=url,
            thumbnail_url = result.get('image'),
            title = result.get('title'),
            description = result.get('description'),
        )
        insert_chat_url_preview(preview)
        result = preview

    if not result:
        # result가 여전히 None이라면 안전하게 처리 (예: 로그/예외/기본값 등)
       raise Exception("미리보기 데이터가 존재하지 않습니다.")

    return jsonify(result)


################################# SCRAP ####################################
@func.route('/scrap-posts', methods=['POST'])
def insert_scrap_posts():
    data = request.get_json()
    account = data.get('account')
    post_urls = data.get('post_urls')
    type = data.get('type')

    scrap = ScrapPostDTO(
        account=account,
        post_urls=post_urls,
        type=type,
    )

    try:
        insert_scrap_post(scrap)
    except Exception as e:
        # 오류 발생시 JSON 반환
        print(e)
        return {
            "status": "error",
            "message": str(e)
        }, 500

    return {"status": "success", "result": "200"}, 200

@func.route('/scrap-posts', methods=['GET'])
def find_scrap_posts_func():
    post_urls = request.args.get("urls")  # ?urls=... 값을 가져옴
    return jsonify({"result": find_scrap_post(post_urls)})

@func.route("/docker-file/", methods=['GET'])
@login_required
def open_file_explorer_docker():
    open_folder(UNC_DIR)
    return jsonify({"result": "success"})

@func.route("/g-tr/", methods=['GET'])
@login_required
def open_file_explorer_tr():
    open_folder(VIDEO_DIRECTORY7)
    return jsonify({"result": "success"})


# test axios timeout
@func.route('/settimeout', methods=['POST'])
def test_settimeout():
    delay = random.uniform(2.78, 2.99)
    time.sleep(delay)
    return "ok";

@func.route('/ping', methods=['GET'])
def pingpong():
    return "pong";