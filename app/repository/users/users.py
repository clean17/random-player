import psycopg
from typing import Optional

from app.repository.users.UserDTO import UserDTO
from config.db_connect import db_transaction



# dict 반환: psycopg3는 row_factory로 처리

@db_transaction
def find_user_by_username(username: str, conn=None) -> Optional["UserDTO"]:
    # row_factory를 dict로 설정
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute("SELECT * FROM users WHERE username = %s;", (username,))
        row = cur.fetchone()
    if row:
        return UserDTO(**row)
    return None

@db_transaction
def insert_user(user: "UserDTO", conn=None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (username, email, password, role, is_active) VALUES (%s, %s, %s, %s, %s) RETURNING id;",
            (user.username, user.email, user.password, user.role, user.is_active)
        )
        user_id = cur.fetchone()[0]
    return user_id

@db_transaction
def update_user_password(username: str, new_password: str, conn=None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET password = %s, updated_at = now() WHERE username = %s;",
            (new_password, username)
        )

@db_transaction
def update_user_login_attempt(username: str, login_attempt: str, conn=None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET login_attempt = %s, updated_at = now() WHERE username = %s;",
            (login_attempt, username)
        )

@db_transaction
def update_user_is_lockout(username: str, is_lockout: str, conn=None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET is_lockout = %s, updated_at = now() WHERE username = %s;",
            (is_lockout, username)
        )

@db_transaction
def update_user_lockout_time(username: str, lockout_time=None, conn=None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET lockout_time = %s, updated_at = now() WHERE username = %s;",
            (lockout_time, username)
        )
