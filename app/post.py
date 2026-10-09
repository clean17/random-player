from flask import Blueprint, render_template, session, Flask, send_from_directory, request, redirect, url_for, jsonify
from flask_login import login_required, current_user

from app.repository.posts.PostDTO import PostDTO
from app.repository.posts.posts import find_post, find_post_list, get_posts_count, insert_post, update_post, delete_post
from app.repository.posts.post_marks import find_pinned_posts, find_bookmarked_posts, find_marked_post_ids, get_post_marks, set_post_pinned, set_post_bookmarked
from app.repository.users.users import find_user_by_username
from config.config import settings
import time
from bs4 import BeautifulSoup


posts = Blueprint('posts', __name__)

SEARCH_TYPES = {'all', 'title', 'content', 'author'}

@posts.route('/')
@login_required
def post_list():
    page = int(request.args.get('page', 1))
    search = request.args.get('search', '').strip()
    search_type = request.args.get('type', 'all')
    if search_type not in SEARCH_TYPES:
        search_type = 'all'
    per_page = 10
    total = get_posts_count(search=search or None, search_type=search_type)
    page_posts = find_post_list(page, per_page, search=search or None, search_type=search_type)
    for post in page_posts:
        soup = BeautifulSoup(post.content, "html.parser")
        first_img = soup.find("img")
        if first_img:
            post.thumbnail = first_img["src"]
        else:
            post.thumbnail = '/static/no-image.png'

    max_page = (total - 1) // per_page + 1 if total else 1

    user = find_user_by_username(current_user.get_id())
    # 목록 각 행의 공지/즐겨찾기 배지용 (모든 페이지·검색 결과)
    pinned_ids, bookmarked_ids = find_marked_post_ids([post.id for post in page_posts], user.id)

    # 상단 공지/즐겨찾기 영역은 첫 페이지의 일반 목록에서만 노출 (검색 결과·2페이지 이후엔 방해만 됨)
    pinned_posts, bookmarked_posts = [], []
    if page == 1 and not search:
        pinned_posts = find_pinned_posts()
        bookmarked_posts = find_bookmarked_posts(user.id)

    return render_template(
        "posts/post_list.html"
        , posts=page_posts
        , pinned_posts=pinned_posts
        , bookmarked_posts=bookmarked_posts
        , pinned_ids=pinned_ids
        , bookmarked_ids=bookmarked_ids
        , page=page
        , max_page=max_page
        , total=total
        , search=search
        , search_type=search_type
        , version=int(time.time())
    )

@posts.route('/<string:post_id>')
@login_required
def view_post(post_id):
    post = find_post(post_id)
    user = find_user_by_username(current_user.get_id()) # current_user.get_id(): 사용자 ID

    if not post:
        return "존재하지 않는 게시글", 404
    is_pinned, is_bookmarked = get_post_marks(post.id, user.id)
    return render_template(
        "posts/view_post.html"
        , post=post
        , user=user
        , is_admin=user.role == 'ADMIN'
        , is_pinned=is_pinned
        , is_bookmarked=is_bookmarked
        , version=int(time.time())
    )

def _mark_on_from_request() -> bool:
    data = request.get_json(silent=True) or {}
    return bool(data.get('on'))

@posts.route('/<string:post_id>/pin', methods=['POST'])
@login_required
def pin_post(post_id):
    post = find_post(post_id)
    user = find_user_by_username(current_user.get_id())

    if not post:
        return jsonify({"result": "false", "comment": "존재하지 않는 게시글"}), 404
    if user.role != 'ADMIN':
        return jsonify({"result": "false", "comment": "권한이 없습니다"}), 403

    on = _mark_on_from_request()
    set_post_pinned(post.id, user.id, on)
    return jsonify({"result": "true", "on": on}), 200

@posts.route('/<string:post_id>/bookmark', methods=['POST'])
@login_required
def bookmark_post(post_id):
    post = find_post(post_id)
    user = find_user_by_username(current_user.get_id())

    if not post:
        return jsonify({"result": "false", "comment": "존재하지 않는 게시글"}), 404

    on = _mark_on_from_request()
    set_post_bookmarked(post.id, user.id, on)
    return jsonify({"result": "true", "on": on}), 200

@posts.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    user = find_user_by_username(current_user.get_id())

    if request.method == 'POST':
        post = PostDTO(user_id=user.id, title=request.form['title'], content=request.form['content'])
        post_id = insert_post(post)
        return redirect(url_for('posts.post_list'))
    return render_template(
        "posts/edit_post.html"
        , user=user
        , type='C'
        , version=int(time.time())
    )

@posts.route('/<string:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = find_post(post_id)
    user = find_user_by_username(current_user.get_id()) # current_user.get_id(): 사용자 ID

    if not post:
        return jsonify(
            {
                "result": "false",
                "comment": "존재하지 않는 게시글"
            }
        ), 404

    if post.user_id != user.id:
        return jsonify(
            {
                "result": "false",
                "comment": "권한이 없습니다"
            }
        ), 403

    if request.method == 'POST':
        user = find_user_by_username(current_user.get_id())
        post = PostDTO(user_id=user.id, title=request.form['title'], content=request.form['content'], public_id=post_id)
        post_id = update_post(post)
        return redirect(url_for('posts.view_post', post_id=post_id))
    return render_template(
        "posts/edit_post.html"
        , post=post
        , type='U'
        , post_id=post_id
        , version=int(time.time())
    )

@posts.route('/<string:post_id>/del', methods=['POST'])
@login_required
def delete_posts(post_id):
    post = find_post(post_id)
    user = find_user_by_username(current_user.get_id()) # current_user.get_id(): 사용자 ID

    if not post:
        return jsonify(
            {
                "result": "false",
                "comment": "존재하지 않는 게시글"
            }
        ), 404

    if post.user_id != user.id:
        return jsonify(
            {
                "result": "false",
                "comment": "권한이 없습니다"
            }
        ), 403

    delete_post(post)

    return jsonify(
        {
            "result": "true",
            "comment": "삭제되었습니다."
        }
    ), 200


