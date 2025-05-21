import psycopg
from typing import Optional

from app.repository.users.UserDTO import UserDTO
from config.db_connect import conn


# dict 반환: psycopg3는 row_factory로 처리

def find_user_by_login_id(username: str) -> Optional["UserDTO"]:
    # row_factory를 dict로 설정
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute("SELECT * FROM users WHERE username = %s;", (username,))
        row = cur.fetchone()
    if row:
        return UserDTO(**row)
    return None

def insert_user(user: "UserDTO") -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (login_id, email, password, role, is_active) VALUES (%s, %s, %s, %s, %s) RETURNING id;",
            (user.login_id, user.email, user.password, user.role, user.is_active)
        )
        user_id = cur.fetchone()[0]
        conn.commit()
    return user_id

def update_user_password(login_id: str, new_password: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET password = %s WHERE login_id = %s;",
            (new_password, login_id)
        )
        conn.commit()
