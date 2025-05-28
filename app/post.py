from flask import Blueprint, render_template, session, Flask, send_from_directory, request, redirect, url_for
from flask_login import login_required
from config.config import settings
import time

posts = Blueprint('posts', __name__)

posts1 = [
    {"id": 1, "title": "첫 번째 게시글 제목", "author": "홍길동", "content": "이곳은 게시글의 내용 일부가 표시됩니다...", "date": "2024-05-26"},
    {"id": 2, "title": "두 번째 게시글", "author": "김영희", "content": "내용 미리보기...", "date": "2024-05-25"},
]


def get_post(post_id):
    return next((p for p in posts1 if p["id"] == post_id), None)

@posts.route('/')
@login_required
def post_list():
    page = int(request.args.get('page', 1))
    per_page = 10
    total = len(posts1)
    start = (page - 1) * per_page
    end = start + per_page
    page_posts = posts1[start:end]
    max_page = (total - 1) // per_page + 1
    return render_template("posts/post_list.html"
                           , posts=page_posts
                           , page=page
                           , max_page=max_page
                           , username=session["_user_id"]
                           , version=int(time.time())
                           )

@posts.route('/<int:post_id>')
@login_required
def view_post(post_id):
    post = get_post(post_id)
    if not post:
        return "존재하지 않는 게시글", 404
    return render_template("posts/view_post.html", post=post)

@posts.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        new_id = max(p["id"] for p in posts1) + 1 if posts1 else 1
        posts1.append({
            "id": new_id,
            "title": request.form['title'],
            "author": request.form['author'],
            "content": request.form['content'],
            "date": "2024-05-26"
        })
        return redirect(url_for('posts.post_list'))
    return render_template("posts/create_post.html")

@posts.route('/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = get_post(post_id)
    if not post:
        return "존재하지 않는 게시글", 404
    if request.method == 'POST':
        post['title'] = request.form['title']
        post['author'] = request.form['author']
        post['content'] = request.form['content']
        return redirect(url_for('posts.view_post', post_id=post_id))
    return render_template("posts/edit_post.html", post=post, post_id=post_id)
