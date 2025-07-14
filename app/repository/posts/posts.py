import psycopg

from app.repository.posts.PostDTO import PostDTO
from config.db_connect import conn, db_transaction
from typing import List

@db_transaction
def insert_post(post: "PostDTO", conn=None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO posts (user_id, type, title, content, created_at, updated_at) VALUES (%s, %s, %s, %s, now(), now()) RETURNING id;",
            (post.user_id, None, post.title, post.content)
        )
        chat_id = cur.fetchone()[0]
        return chat_id

@db_transaction
def update_post(post: "PostDTO", conn=None) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE posts SET user_id = %s, title = %s, content = %s, updated_at = now() WHERE id = %s RETURNING id;",
            (post.user_id, post.title, post.content, post.id)
        )
        post_id = cur.fetchone()[0]
        return post_id

@db_transaction
def find_post(post_id: str, conn=None) -> List["PostDTO"]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            "SELECT p.*, TO_CHAR(p.updated_at, 'YYYY-MM-DD HH24:MI') as updated_at, u.realname FROM posts p "
            "JOIN users u ON u.id = p.user_id "
            "WHERE p.id = %s ;",
            (post_id,) # 한 개짜리 튜플은 (값, )처럼 반드시 콤마가 있어야 한다
        )
        row = cur.fetchone()
        if row:
            return PostDTO(**row)
        return None

@db_transaction
def find_post_list(offset: int, limit: int, conn=None) -> List["PostDTO"]:
    posts = []
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            "SELECT p.*, TO_CHAR(p.updated_at, 'YYYY-MM-DD HH24:MI') as updated_at, u.realname FROM posts p "
            "JOIN USERS u on u.id = p.user_id "
            "ORDER BY p.id DESC OFFSET %s LIMIT %s;",
            ((offset-1)*10, limit)
        )
        rows = cur.fetchall()
        for row in rows:
            posts.append(PostDTO(**row))
    return posts

@db_transaction
def get_posts_count(conn=None) -> int:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            "select count(1) from posts;"
        )
        row = cur.fetchone()
    return row['count']