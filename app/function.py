from flask import Blueprint, render_template, jsonify, request, send_file, send_from_directory, session, url_for, redirect, Response, stream_with_context
import ctypes
from flask_login import login_required
import zipfile
import os
import io
import json
from app.image import get_images
from app.image import LIMIT_PAGE_NUM
from utils.compress_file import compress_directory, compress_directory_to_zip
import multiprocessing
import time
from flask_socketio import SocketIO
from datetime import datetime
from utils.lotto_schedule import async_buy_lotto
from config.config import settings
import asyncio

func = Blueprint('func', __name__)

socketio = SocketIO() # __init__ 으로 전달

LOG_DIR = "logs"
DATA_DIR = "data"
MEMO_FILE = 'memo.txt'
CHAT_FILE = 'chat.txt'
MEMO_FILE_PATH = os.path.join(DATA_DIR, MEMO_FILE)
CHAT_FILE_PATH = os.path.join(DATA_DIR, CHAT_FILE)
TEMP_IMAGE_DIR = settings['TEMP_IMAGE_DIR']
MAX_FETCH_MESSAGE_SIZE = 50



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
        images = get_images(start, LIMIT_PAGE_NUM, target_directory)

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
    return os.path.join(LOG_DIR, f"app_{date}.log")

@func.route("/logs/view")
@login_required
def get_log_viewer():
    """로그 뷰어 HTML 페이지 제공"""
    return render_template("log_viewer.html")

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

        while True:
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    f.seek(last_position)

                    line = f.readline()
                    if line:
                        yield f"data: {line.strip()}\n\n"
                        last_position = f.tell()
                    else:
                        # 빠른 polling (0.1초) → 너무 빠르면 CPU 100% 될 수 있으니 적절 조절
                        time.sleep(0.1)

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

    if not data['timestamp']:
        now = datetime.now()
        data['timestamp'] = now.strftime("%y%m%d%H%M%S")

    if not data['username']:
        data['username'] = 'error'

    try:
        with open(CHAT_FILE_PATH, "r", encoding="utf-8") as f:
            line_count = sum(1 for _ in f)
    except FileNotFoundError:
        line_count = 0  # 파일이 없으면 0부터 시작

    next_line_number = line_count + 1

    log_entry = f"{next_line_number} | {data['timestamp']} | {data['username']} | {data['message']}"
    with open(CHAT_FILE_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(log_entry + "\n")
    return {"status": "success"}, 200

# 비동기로 추가 채팅 로그 요청 API
@func.route("/chat/load-more-chat", methods=["POST"])
@login_required
def load_more_logs():
    offset = int(request.json.get("offset", 0))  # 클라이언트가 요청한 로그 시작점
    all_lines = get_last_n_lines(CHAT_FILE_PATH, 0, 1000)  # 최대 로그 유지

    # offset 0 =>  950 ~ 1000 라인
    # offset 1 =>  900 ~ 950 라인...
    start = max(0, len(all_lines) - offset - MAX_FETCH_MESSAGE_SIZE)
    end = len(all_lines) - offset

    if (end > 0):
        return jsonify({"logs": all_lines[start:end]})
    else:
        return jsonify({"logs": []})


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
    return render_template('memo.html', content=content)

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

################################# STATE ####################################


STATE_FILE = 'data.json'

# JSON 상태 불러오기
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "chats": {"last_chat_id": 0},
        "users": {},
        "ai_scheduler_uri": None
    }

# JSON 상태 저장하기
def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=4, ensure_ascii=False)

# ✅ 사용자별 last_read_chat_id 관리
@func.route('/last-read-chat-id', methods=['GET', 'POST'], endpoint='last-read-chat-id')
@login_required
def last_read_chat_id():
    state = load_state()
    username = request.args.get('username') if request.method == 'GET' else request.get_json().get('username')

    if not username:
        return jsonify({'error': 'username is required'}), 400

    if request.method == 'POST':
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
@func.route('/last-chat-id', methods=['GET', 'POST'], endpoint='last-chat-id')
@login_required
def handle_last_chat_id():
    state = load_state()

    if request.method == 'POST':
        chat_id = request.get_json().get('lastChatId')
        if chat_id is None:
            return jsonify({'error': 'lastChatId is required'}), 400
        state.setdefault("chats", {})["last_chat_id"] = chat_id
        save_state(state)
        return jsonify({'result': 'success'})

    elif request.method == 'GET':
        chat_id = state.get("chats", {}).get("last_chat_id", 0)
        return jsonify({'last_chat_id': chat_id})

