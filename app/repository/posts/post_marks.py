import psycopg

from app.repository.posts.PostDTO import PostDTO
from config.db_connect import db_transaction
from typing import List, Set, Tuple

# 공지(post_pins) / 개인 즐겨찾기(post_bookmarks). 스키마: schema_pins_bookmarks.sql

_LIST_SELECT = (
    "SELECT p.id, p.public_id, p.user_id, p.title, "
    "TO_CHAR(p.updated_at, 'YYYY-MM-DD HH24:MI') as updated_at, u.realname FROM posts p "
    "JOIN users u ON u.id = p.user_id "
)

@db_transaction
def find_pinned_posts(limit: int = 5, conn=None) -> List["PostDTO"]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            _LIST_SELECT + "JOIN post_pins pp ON pp.post_id = p.id "
            "ORDER BY pp.pinned_at DESC LIMIT %s;",
            (limit,)
        )
        return [PostDTO(**row) for row in cur.fetchall()]

@db_transaction
def find_bookmarked_posts(user_id: int, limit: int = 30, conn=None) -> List["PostDTO"]:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(
            _LIST_SELECT + "JOIN post_bookmarks pb ON pb.post_id = p.id "
            "WHERE pb.user_id = %s ORDER BY pb.created_at DESC LIMIT %s;",
            (user_id, limit)
        )
        return [PostDTO(**row) for row in cur.fetchall()]

@db_transaction
def get_post_marks(post_id: int, user_id: int, conn=None) -> Tuple[bool, bool]:
    """(공지 여부, 이 사용자의 즐겨찾기 여부)"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM post_pins WHERE post_id = %s), "
            "EXISTS(SELECT 1 FROM post_bookmarks WHERE post_id = %s AND user_id = %s);",
            (post_id, post_id, user_id)
        )
        pinned, bookmarked = cur.fetchone()
        return bool(pinned), bool(bookmarked)

@db_transaction
def find_marked_post_ids(post_ids: List[int], user_id: int, conn=None) -> Tuple[Set[int], Set[int]]:
    """목록 한 페이지 분량 post_ids 중 (공지인 id, 이 사용자가 즐겨찾기한 id)"""
    if not post_ids:
        return set(), set()
    with conn.cursor() as cur:
        cur.execute("SELECT post_id FROM post_pins WHERE post_id = ANY(%s);", (post_ids,))
        pinned = {row[0] for row in cur.fetchall()}
        cur.execute(
            "SELECT post_id FROM post_bookmarks WHERE user_id = %s AND post_id = ANY(%s);",
            (user_id, post_ids)
        )
        bookmarked = {row[0] for row in cur.fetchall()}
    return pinned, bookmarked

@db_transaction
def set_post_pinned(post_id: int, user_id: int, pinned: bool, conn=None) -> None:
    with conn.cursor() as cur:
        if pinned:
            cur.execute(
                "INSERT INTO post_pins (post_id, pinned_by) VALUES (%s, %s) ON CONFLICT (post_id) DO NOTHING;",
                (post_id, user_id)
            )
        else:
            cur.execute("DELETE FROM post_pins WHERE post_id = %s;", (post_id,))

@db_transaction
def set_post_bookmarked(post_id: int, user_id: int, bookmarked: bool, conn=None) -> None:
    with conn.cursor() as cur:
        if bookmarked:
            cur.execute(
                "INSERT INTO post_bookmarks (user_id, post_id) VALUES (%s, %s) ON CONFLICT (user_id, post_id) DO NOTHING;",
                (user_id, post_id)
            )
        else:
            cur.execute("DELETE FROM post_bookmarks WHERE user_id = %s AND post_id = %s;", (user_id, post_id))
