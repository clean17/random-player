import psycopg
import os
from datetime import datetime

from config.db_connect import conn

DATA_DIR = "data"
CHAT_FILE = 'chat.txt'
CHAT_FILE_PATH = os.path.join(DATA_DIR, CHAT_FILE)

def parse_line(line, line_num):
    # 라인 분리 및 공백 제거
    parts = [x.strip() for x in line.strip().split('|')]
    if len(parts) != 4:
        print('4개 아님', line_num)
        return None  # 잘못된 라인 skip
    id_, create_at, user_id, message = parts
    # create_at 파싱 (예시: 250520151539 → 2025-05-20 15:13:39)
    create_at_fmt = create_at[:12]
    dt = datetime.strptime(create_at_fmt, "%y%m%d%H%M%S")
    u_id = None
    if user_id == 'nh824':
        u_id = 2
    elif user_id == 'fkaus14':
        u_id = 1
    else:
        u_id = 3
    return {
        "id": int(line_num),
        "created_at": dt,
        "user_id": u_id,
        "message": message
    }

def insert_chats_from_file(filename, conn):
    with open(filename, encoding="utf-8") as f, conn.cursor() as cur:
        line_num = 0;
        for line in f:
            line_num += 1
            if not line.strip():
                continue  # 빈 줄 skip
            try:
                data = parse_line(line, line_num)
                if data is None:
                    print("형식 오류:", line)
                    continue
                cur.execute(
                    "INSERT INTO chats (id, created_at, user_id, message) VALUES (%s, %s, %s, %s);",
                    (data["id"], data["created_at"], data["user_id"], data["message"])
                )
            except Exception as e:
                print(f"ERROR ({line_num}): {e} -> {line.strip()}")
                conn.rollback()
                continue
        print(line_num)
        conn.commit()

if __name__ == "__main__":
    insert_chats_from_file(CHAT_FILE_PATH, conn)
    conn.close()
