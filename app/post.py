from flask import Blueprint, render_template, session, Flask, send_from_directory, request, redirect, url_for, jsonify, abort
from flask_login import login_required, current_user
from werkzeug.security import safe_join
from urllib.parse import quote
from datetime import datetime
import os
import uuid

from app.accel import send_file_accel, guess_mimetype, POST_FILE_DIR
from app.image import clean_filename, IMAGE_CACHE_SECONDS

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


# ── 게시글 첨부파일(영상·일반 파일) ─────────────────────────────────────────────
# 편집 화면에서 붙여넣은 파일(static/js/post_attach.js). 이미지는 기존대로 /upload(갤러리 temp)로 가고,
# 그 외 파일은 갤러리와 섞이지 않게 별도 폴더 <POST_FILE_DIR>/<YYYYMM>/<uuid>__<원래이름> 에 둔다.
# 확장자 제한은 없다 — 대신 서빙할 때 영상·오디오·이미지(svg 제외)만 inline 으로 열고 나머지는 항상
# 다운로드(attachment)로 보낸다. html/svg 를 브라우저가 열어 스크립트가 실행되는 것을 막기 위해서다.
_POST_FILE_SEP = '__'


def _post_file_kind(mimetype):
    if mimetype.startswith('video/'):
        return 'video'
    if mimetype.startswith('audio/'):
        return 'audio'
    if mimetype.startswith('image/') and mimetype != 'image/svg+xml':
        return 'image'
    return 'file'


@posts.route('/files', methods=['POST'])
@login_required
def upload_post_files():
    files = request.files.getlist('files[]')
    if not files:
        return jsonify({"error": "No file uploaded"}), 400

    sub = datetime.now().strftime('%Y%m')
    target_dir = os.path.join(POST_FILE_DIR, sub)
    os.makedirs(target_dir, exist_ok=True)

    saved = []
    for f in files:
        if not f or not f.filename:
            continue
        # 클라이언트가 보낸 이름은 신뢰하지 않는다 — 경로·금지문자 제거, 경로 길이(260자) 때문에 앞부분만
        original = clean_filename(os.path.basename(f.filename)).strip() or 'file'
        name, ext = os.path.splitext(original)
        original = name[:80] + ext.lower()[:20]
        stored = f"{uuid.uuid4().hex}{_POST_FILE_SEP}{original}"
        path = os.path.join(target_dir, stored)
        f.save(path)

        mimetype = guess_mimetype(original)
        saved.append({
            "name": original,
            "size": os.path.getsize(path),
            "type": mimetype,
            "kind": _post_file_kind(mimetype),
            "url": f"/posts/files/{sub}/{quote(stored)}",
        })
    return jsonify({"status": "success", "files": saved})


@posts.route('/files/<path:rel>', methods=['GET'])
@login_required
def get_post_file(rel):
    path = safe_join(POST_FILE_DIR, rel)
    if path is None or not os.path.isfile(path):
        abort(404)
    stored = os.path.basename(path)
    original = stored.split(_POST_FILE_SEP, 1)[1] if _POST_FILE_SEP in stored else stored
    mimetype = guess_mimetype(original)
    if _post_file_kind(mimetype) == 'file':
        mimetype = 'application/octet-stream'   # html 등은 타입부터 실행 불가로 — attachment·nosniff 와 함께 이중 방어
    inline = _post_file_kind(mimetype) != 'file' and request.args.get('download') != '1'

    # 본문은 nginx 가 보낸다(app/accel.py) — 큰 영상도 waitress I/O 스레드를 붙잡지 않는다
    resp = send_file_accel(path, max_age=IMAGE_CACHE_SECONDS, private=True, mimetype=mimetype)
    # RFC 5987(filename*) 로 한글 파일명도 그대로 저장되게 한다
    resp.headers['Content-Disposition'] = "%s; filename*=UTF-8''%s" % (
        'inline' if inline else 'attachment', quote(original))
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


