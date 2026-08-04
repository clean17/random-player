# from fastapi import FastAPI
# import firebase_admin
# from firebase_admin import credentials, messaging
#
# app = FastAPI()
#
# # Firebase 초기화
# cred = credentials.Certificate("serviceAccountKey.json")
# firebase_admin.initialize_app(cred)
#
# @app.post("/send")
# def send_push(token: str):
#     message = messaging.Message(
#         token=token,
#         notification=messaging.Notification(
#             title="새 메시지",
#             body="누군가 메시지를 보냈습니다"
#         )
#     )
#
#     response = messaging.send(message)
#
#     return {
#         "success": True,
#         "message_id": response
#     }





# from flask import Blueprint, render_template, jsonify, request, send_file, send_from_directory, session, url_for, redirect, Response, stream_with_context
# import ctypes
# from flask_login import login_required
# import zipfile
# import os
# import io
# import json
# from app.image import get_images
# from app.image import LIMIT_PAGE_NUM
# from app.repository.chats.ChatDTO import ChatDTO
# from app.repository.chats.ChatPreviewDTO import ChatPreviewDTO
# from app.repository.chats.chats import insert_chat, get_chats_count, find_chats_by_offset, chats_to_line_list, \
#     find_chat_room_by_roomname, update_chat_room, insert_chat_url_preview, find_chat_url_preview, \
#     find_chat_indices_by_keyword, fetch_context_by_center
# from app.repository.scrap_posts.ScrapPostDTO import ScrapPostDTO
# from app.repository.scrap_posts.scrap_posts import insert_scrap_post, find_scrap_post
# from app.repository.users.users import find_user_by_username
# from job.batch_process import run_crawl_ai_image
# from job.buy_lotto import async_buy_lotto
# from utils.common import open_folder
# from utils.fetch_url_preview import fetch_url_preview_by_selenium
# from job.compress_file import compress_directory, compress_directory_to_zip
# import multiprocessing
# import time
# from flask_socketio import SocketIO
# from datetime import datetime
# from config.config import settings
# import asyncio
#
# from utils.wsgi_midleware import logger
# from filelock import FileLock, Timeout
# import random
#
# func = Blueprint('func', __name__)
#
# socketio = SocketIO() # __init__ 으로 전달
#
# LOG_DIR = "logs/app"
# DATA_DIR = "data"
# MEMO_FILE = 'memo.txt'
# CHAT_FILE = 'chat.txt'
# STATE_FILE = 'data.json'
# MEMO_FILE_PATH = os.path.join(DATA_DIR, MEMO_FILE)
# CHAT_FILE_PATH = os.path.join(DATA_DIR, CHAT_FILE)
# CHAT_STATE_FILE_PATH = os.path.join(DATA_DIR, STATE_FILE)
# TEMP_IMAGE_DIR = settings['TEMP_IMAGE_DIR']
# MAX_FETCH_MESSAGE_SIZE = 100
# UNC_DIR = settings['UNC_DIR']
# VIDEO_DIRECTORY7 = settings['VIDEO_DIRECTORY7']
#
#
# # Windows API 상수
# SHERB_NOCONFIRMATION = 0x00000001  # 사용자 확인 대화 상자를 표시하지 않음
# SHERB_NOPROGRESSUI = 0x00000002   # 진행 UI를 표시하지 않음
# SHERB_NOSOUND = 0x00000004        # 소리를 재생하지 않음
#
#
# ################################# Chat ######################################
#
# # 로그 파일에서 가장 최근 N개의 메시지 가져오기
# def get_last_n_lines(filepath, n):
#     try:
#         with open(filepath, "r", encoding="utf-8") as f:
#             lines = f.readlines()
#         return lines[-n:]  # 가장 마지막 N개 줄 반환
#     except FileNotFoundError:
#         return []  # 파일이 없으면 빈 리스트 반환
#
# def get_last_n_lines(filepath, start, end):
#     try:
#         with open(filepath, "r", encoding="utf-8") as f:
#             lines = f.readlines()
#
#         total = len(lines)
#
#         # 역방향 슬라이싱을 위한 시작/끝 계산
#         slice_end = total - start
#         slice_start = max(0, total - end)
#
#         return lines[slice_start:slice_end]
#
#     except FileNotFoundError:
#         return []
#
# def normalize_ip(ip_address):
#     if ip_address.startswith("::ffff:"):
#         return ip_address[7:]  # 앞에 "::ffff:" 빼버림
#     return ip_address
#
# # 인코딩 가능한지 확인하고 처리 > 처리 못하면 '?' 대체
# def sanitize_text(text):
#     return text.encode('utf-8', errors='replace').decode('utf-8')
#
#
# @func.route("/chat")
# @login_required
# def get_chat_ui():
#     if "_user_id" not in session:
#         return redirect(url_for('auth.logout'))  # 로그인 안 되어 있으면 로그인 페이지로 이동
#
#     return render_template("chat_ui.html", username=session["_user_id"], maxFetchMessageSize = MAX_FETCH_MESSAGE_SIZE, version=int(time.time()))
#
# @func.route("/api/chat/save-file", methods=["POST"])
# # @login_required 추가하면 안된다.. 외부 API 역할을 한다
# def save_chat_message():
#     data = request.json
#     # client_ip = request.headers.get('X-Client-IP') or request.remote_addr
#     # client_ip = normalize_ip(client_ip)
#     # print(f"✅ 클린 IP 주소: {client_ip}")
#
#     # if not data['timestamp']:
#     #     now = datetime.now()
#     #     data['timestamp'] = now.strftime("%y%m%d%H%M%S")
#
#     # if not data['username']:
#     #     data['username'] = 'error'
#
#     # try:
#     #     with open(CHAT_FILE_PATH, "r", encoding="utf-8") as f:
#     #         line_count = sum(1 for _ in f)
#     # except FileNotFoundError:
#     #     line_count = 0  # 파일이 없으면 0부터 시작
#     #
#     # next_line_number = line_count + 1
#
#     sanitized_message = sanitize_text(data['message'])
#
#     # 아래는 파일에 저장하는 코드
#     # log_entry = f"{next_line_number} | {data['timestamp']} | {data['username']} | {sanitized_message}"
#     # with open(CHAT_FILE_PATH, "a", encoding="utf-8", errors='replace') as log_file: # errors='replace'; 인코딩할 수 없는 문자를 자동으로 '?'로 대체
#     #     log_file.write(log_entry + "\n")
#
#     username = (data.get('username') or '').strip()
#     fetch_user = find_user_by_username(username)
#     chat_room = find_chat_room_by_roomname(data['roomname'])
#     chat = ChatDTO(created_at=str(datetime.now()), user_id=fetch_user.id, message=sanitized_message, chat_room_id=chat_room.id)
#     inserted_id = insert_chat(chat)
#     chat.last_chat_id = inserted_id
#     last_chat_id = update_chat_room(chat)
#     update_last_chat_id_in_state(inserted_id)
#
#     resp = jsonify({"status": "success", "inserted_id": inserted_id})
#     # return {"status": "success", "inserted_id": inserted_id}, 200
#
#     # username이 있으면 쿠키로 내려보내기
#     if username:
#         resp.set_cookie(
#             "username",
#             username,
#             max_age=60 * 60 * 24 * 30,  # 30일 유지
#             path="/",
#             httponly=True,  # JS에서 안 쓸 거면 True
#             samesite="Lax"
#         )
#
#     return resp
#
# # 비동기로 추가 채팅 로그 요청 API
# @func.route("/chat/load-more-chat", methods=["POST"])
# @login_required
# def load_more_logs():
#     offset = int(request.json.get("offset", 0))  # 클라이언트가 요청한 로그 시작점
#     # all_lines = get_last_n_lines(CHAT_FILE_PATH, 0, 1000)  # 최대 로그 유지
#     all_chat_count = get_chats_count()
#
#     # offset 0 =>  950 ~ 1000 라인
#     # offset 1 =>  900 ~ 950 라인...
#     # start = max(0, len(all_lines) - offset - MAX_FETCH_MESSAGE_SIZE)
#     # end = len(all_lines) - offset
#
#     # if (end > 0):
#     #     return jsonify({"logs": all_lines[start:end]})
#     # else:
#     #     return jsonify({"logs": []})
#
#     sql_offset = min(offset, all_chat_count)
#     chat_list = find_chats_by_offset(sql_offset, MAX_FETCH_MESSAGE_SIZE)
#     # return jsonify({"logs": all_lines[start:end]})
#     return jsonify({"logs": chats_to_line_list(chat_list)})
#
# # 검색 인덱스 구하기 (전역/전체 검색)
# @func.route("/chat/search", methods=["POST"])
# @login_required
# def search_chat():
#     q = (request.json.get("q") or "").strip()
#     if not q:
#         return jsonify({"count": 0, "hits": []})
#
#     # 구현 방식 예시:
#     # - DB에 fulltext/like로 전체에서 매칭되는 "행 인덱스" 리스트를 반환
#     hits = find_chat_indices_by_keyword(q)  # 오름차순 인덱스
#     return jsonify({"count": len(hits), "hits": hits})
#
#
# # 중심 인덱스를 기준으로 위/아래 컨텍스트 슬라이스 가져오기
# @func.route("/chat/fetch-context", methods=["POST"])
# @login_required
# def fetch_context():
#     payload = request.get_json(force=True) or {}
#     # center 또는 center_id 둘 다 지원
#     center_id = payload.get("center")
#     if center_id is None:
#         center_id = payload.get("center_id")
#     try:
#         center_id = int(center_id)
#     except (TypeError, ValueError):
#         return jsonify({"error": "center (id) is required"}), 400
#
#     before = int(payload.get("before", 25))
#     after  = int(payload.get("after", 25))
#
#     rows = fetch_context_by_center(center_id, before, after)
#
#     # id 범위(클라이언트가 스크롤 이어붙일 때 참고용)
#     start_id = rows[0][0] if rows else None   # c.*의 첫 컬럼이 id라고 가정
#     end_id   = rows[-1][0] if rows else None
#
#     return jsonify({
#         "logs": chats_to_line_list(rows),  # "chatId|timestamp|username|msg" 형태
#         "start_id": start_id,
#         "end_id": end_id,
#         "center_id": center_id,
#         "count": len(rows)
#     })
#
#
#
#
#
#
# ################################# STATE ####################################
#
#
# DEFAULT_STATE = {
#     "chats": {"last_chat_id": 0},
#     "users": {},
#     "ai_scheduler_uri": None
# }
# LOCK_PATH = CHAT_STATE_FILE_PATH + ".lock"
#
# # JSON 상태 불러오기
# def load_state():
#     lock = FileLock(LOCK_PATH, timeout=2)
#     try:
#         with lock:
#             if not os.path.exists(CHAT_STATE_FILE_PATH):
#                 logger.warning("⚠️ 상태 파일 없음. 기본값 반환.")
#                 return DEFAULT_STATE
#
#             if os.path.getsize(CHAT_STATE_FILE_PATH) == 0:
#                 logger.warning("⚠️ 상태 파일 비어 있음. 기본값 반환.")
#                 return DEFAULT_STATE
#
#             with open(CHAT_STATE_FILE_PATH, 'r', encoding='utf-8') as f:
#                 return json.load(f)
#     except Timeout:
#         logger.error("❌ 상태 파일 읽기 락 획득 실패 (2초 타임아웃)")
#         return DEFAULT_STATE
#     except json.JSONDecodeError as e:
#         logger.error(f"❌ JSON 파싱 실패: {e}")
#         return DEFAULT_STATE
#     except Exception as e:
#         logger.error(f"❌ 상태 로드 중 기타 예외: {e}")
#         return DEFAULT_STATE
#
# # JSON 상태 저장하기
# def save_state(state: dict):
#     lock = FileLock(LOCK_PATH, timeout=2)
#     tmp_path = CHAT_STATE_FILE_PATH + ".tmp"
#
#     try:
#         with lock:
#             try:
#                 with open(tmp_path, 'w', encoding='utf-8') as f:
#                     json.dump(state, f, ensure_ascii=False, indent=2)
#                     f.flush()
#                     os.fsync(f.fileno())
#             except Exception as write_err:
#                 logger.error(f"❌ 임시 파일 쓰기 실패: {write_err}")
#                 return
#
#             if os.path.exists(tmp_path):
#                 try:
#                     os.replace(tmp_path, CHAT_STATE_FILE_PATH)
#                     # logger.info("✅ 상태 파일 저장 완료")
#                 except Exception as replace_err:
#                     logger.error(f"❌ 상태 파일 교체 실패: {replace_err}")
#             else:
#                 logger.error(f"❌ 임시 파일 누락: {tmp_path} – 저장 스킵됨")
#
#     except Timeout:
#         logger.warning("🔒 상태 저장 락 획득 실패 (2초 대기 후 포기)")
#
# def update_last_chat_id_in_state(chat_id):
#     if chat_id is None:
#         return jsonify({'error': 'lastChatId is required'}), 400
#     state = load_state()
#     state.setdefault("chats", {})["last_chat_id"] = chat_id
#     save_state(state)
#     return {'result': 'success'}
#
# # ✅ 사용자별 last_read_chat_id 관리
# @func.route('/last-read-chat-id', methods=['GET', 'POST'], endpoint='last-read-chat-id')
# @login_required
# def last_read_chat_id():
#     state = load_state()
#     username = request.args.get('username') if request.method == 'GET' else request.get_json().get('username')
#
#     if not username:
#         return jsonify({'error': 'username is required'}), 400
#
#     if request.method == 'POST': # 유저가 읽은 채팅 ID 갱신 요청
#         chat_id = request.get_json().get('lastReadChatId')
#         if chat_id is None:
#             return jsonify({'error': 'lastReadChatId is required'}), 400
#         state.setdefault("users", {}).setdefault(username, {})["last_read_chat_id"] = chat_id
#         save_state(state)
#         return jsonify({'result': 'success'})
#
#     else:  # GET
#         chat_id = state.get("users", {}).get(username, {}).get("last_read_chat_id", 0)
#         return jsonify({'username': username, 'last_read_chat_id': chat_id})
#
# # ✅ 전체 마지막 채팅 ID 관리
# @func.route('/last-chat-id', methods=['GET'], endpoint='last-chat-id')
# @login_required
# def handle_last_chat_id():
#     state = load_state()
#
#     # if request.method == 'POST':
#     #     chat_id = request.get_json().get('lastChatId')
#     #     return jsonify(update_last_chat_id_in_state(chat_id))
#     #
#     # elif request.method == 'GET':
#     #     chat_id = state.get("chats", {}).get("last_chat_id", 0)
#     #     return jsonify({'last_chat_id': chat_id})
#
#     chat_id = state.get("chats", {}).get("last_chat_id", 0)
#     return jsonify({'last_chat_id': chat_id})
#
#
