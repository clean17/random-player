import psycopg

from app.repository.chats.ChatDTO import ChatDTO
from app.repository.chats.ChatRoomDTO import ChatRoomDTO
from app.repository.chats.ChatPreviewDTO import ChatPreviewDTO
from config.db_connect import conn, db_transaction
from typing import List

@db_transaction
def find_chats_by_offset(offset: int, limit: int, conn=None) -> List["ChatDTO"]:
    chats = []
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            "SELECT A.* FROM"
            "(SELECT c.*, u.username FROM chats c "
            "JOIN users u on c.user_id = u.id "
            "ORDER BY c.id DESC OFFSET %s LIMIT %s) A "
            "ORDER BY A.id ASC;",
            (offset, limit)
        )
        rows = cur.fetchall()
        for row in rows:
            chats.append(ChatDTO(**row))
    return chats

@db_transaction
def find_chat_room_by_roomname(roomname: str, conn=None) -> List["ChatRoomDTO"]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            "SELECT * FROM chat_rooms WHERE room_name = %s;",
            (roomname,) # 한 개짜리 튜플은 (값, )처럼 반드시 콤마가 있어야 한다
        )
        row = cur.fetchone()
        if row:
            return ChatRoomDTO(**row)
        return None

@db_transaction
def get_chats_count(conn=None) -> int:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            "select count(1) from chats;"
        )
        row = cur.fetchone()
    return row['count']

@db_transaction
def insert_chat(chat: "ChatDTO", conn=None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chats (created_at, user_id, message, chat_room_id) VALUES (%s, %s, %s, %s) RETURNING id;",
            (chat.created_at, chat.user_id, chat.message, chat.chat_room_id)
        )
        chat_id = cur.fetchone()[0]
        return chat_id

@db_transaction
def update_chat_room(chat: "ChatDTO", conn=None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE chat_rooms SET last_chat_id = %s, updated_at = now() WHERE id = %s RETURNING last_chat_id;",
            (chat.last_chat_id, chat.chat_room_id)
        )
        last_chat_id = cur.fetchone()[0]
        return last_chat_id

# 기존 채팅 스크립트 구조로 변경해주는 함수
def chats_to_line_list(chat_list):
    line_list = []
    for c in chat_list:
        # created_at을 원하는 형식(예: yymmddHHMMSS)으로 변환
        create_at_str = c.created_at.strftime("%y%m%d%H%M%S")
        # id가 None일 수 있으니 str() 처리
        line = f"{c.id} | {create_at_str} | {c.username} | {c.message} | {c.chat_room_id}\n"
        line_list.append(line)
    return line_list

@db_transaction
def find_chat_url_preview(chat_id: str, conn=None) -> List["ChatPreviewDTO"]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            "SELECT * FROM chats_preview WHERE chat_id = %s;",
            (chat_id,) # 한 개짜리 튜플은 (값, )처럼 반드시 콤마가 있어야 한다
        )
        row = cur.fetchone()
        if row:
            return ChatPreviewDTO(**row)
        return None

@db_transaction
def insert_chat_url_preview(chat: "ChatPreviewDTO", conn=None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chats_preview (chat_id, origin_url, thumbnail_url, title, description, created_at) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;",
            (chat.chat_id, chat.origin_url, chat.thumbnail_url, chat.title, chat.description, chat.created_at)
        )
        chat_id = cur.fetchone()[0]
        return chat_id

# @db_transaction
# def find_temp_chat_by_username():
#     with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
#         cur.execute("SELECT * FROM users WHERE username = %s;", (username,))
#         row = cur.fetchone()
#     if row:
#         return UserDTO(**row)
#     return None
#
# @db_transaction
# def insert_temp_chat():
#     pass
#
# @db_transaction
# def update_temp_chat():
#     pass