from flask import Blueprint, render_template, session, Flask, send_from_directory, request, redirect, url_for
from flask_login import login_required, current_user

from app.repository.posts.PostDTO import PostDTO
from app.repository.posts.posts import find_post, find_post_list, get_posts_count, insert_post, update_post
from app.repository.users.users import find_user_by_username
from config.config import settings
import time

posts = Blueprint('posts', __name__)

@posts.route('/')
@login_required
def post_list():
    page = int(request.args.get('page', 1))
    per_page = 10
    total = get_posts_count()
    page_posts = find_post_list(page, per_page)
    max_page = (total - 1) // per_page + 1
    return render_template(
        "posts/post_list.html"
        , posts=page_posts
        , page=page
        , max_page=max_page
        , version=int(time.time())
    )

@posts.route('/<int:post_id>')
@login_required
def view_post(post_id):
    post = find_post(post_id)
    if not post:
        return "존재하지 않는 게시글", 404
    return render_template("posts/view_post.html", post=post)

@posts.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    user = find_user_by_username(current_user.get_id())

    if request.method == 'POST':
        post = PostDTO(user_id=user.id, title=request.form['title'], content=request.form['content'])
        post_id = insert_post(post)
        return redirect(url_for('posts.post_list'))
    return render_template(
        "posts/create_post.html"
        , realname=user.realname
    )

@posts.route('/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = find_post(post_id)
    if not post:
        return "존재하지 않는 게시글", 404
    if request.method == 'POST':
        user = find_user_by_username(current_user.get_id())
        post = PostDTO(user_id=user.id, title=request.form['title'], content=request.form['content'], id=post_id)
        post_id = update_post(post)
        return redirect(url_for('posts.view_post', post_id=post_id))
    return render_template("posts/edit_post.html", post=post, post_id=post_id)
