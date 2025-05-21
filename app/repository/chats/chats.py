import psycopg
from typing import Optional

from app.repository.chats.ChatDTO import ChatDTO
from config.db_connect import conn
from typing import List

def get_chats_by_offset(offset: int, limit: int) -> List["ChatDTO"]:
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

def get_chats_count() -> int:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            "select count(1) from chats;"
        )
        row = cur.fetchone()
    return row['count']

def chats_to_line_list(chat_list):
    line_list = []
    for c in chat_list:
        # created_at을 원하는 형식(예: yymmddHHMMSS)으로 변환
        create_at_str = c.created_at.strftime("%y%m%d%H%M%S")
        # id가 None일 수 있으니 str() 처리
        line = f"{c.id} | {create_at_str} | {c.username} | {c.message}\n"
        line_list.append(line)
    return line_list


def insert_chat(chat: "ChatDTO") -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chats (created_at, user_id, message) VALUES (%s, %s, %s) RETURNING id;",
            (chat.created_at, chat.user_id, chat.message)
        )
        chat_id = cur.fetchone()[0]
        conn.commit()
    return chat_id


