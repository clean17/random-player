import psycopg

from app.repository.scrap_posts.ScrapPostDTO import ScrapPostDTO
from config.db_connect import conn, db_transaction
from typing import List

@db_transaction
def insert_scrap_post(post: "ScrapPostDTO", conn=None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO scrap_posts (created_at, account, post_urls, type) VALUES (now(), %s, %s, %s) RETURNING id;",
            (post.account, post.post_urls, post.type)
        )
        chat_id = cur.fetchone()[0]
        return chat_id

@db_transaction
def find_scrap_post(post_urls: str, conn=None) -> List["ScrapPostDTO"]:
    pattern = f"%{post_urls}%"
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            "SELECT * FROM scrap_posts "
            "WHERE post_urls LIKE %s;",
            (pattern,) # 한 개짜리 튜플은 (값, )처럼 반드시 콤마가 있어야 한다
        )
        row = cur.fetchone()
        if row:
            return ScrapPostDTO(**row)
        return None