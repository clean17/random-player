from flask import Blueprint, render_template, session, Flask, send_from_directory, redirect, request, jsonify
from flask_login import login_required

from app.repository.users.users import find_user_by_username, update_user_login_attempt, update_user_is_lockout, \
    update_user_lockout_time

api = Blueprint('api', __name__)



# @api.route('/')
# @login_required
# def admin_dashboard():
#     user = session.get('principal')
#     if not user or user['role'] != 'ADMIN':
#         return redirect('/login')
#     return render_template('/admin/admin_dashboard.html')
#
#
# @api.route('/search-user', methods=['GET', 'POST'], endpoint='search-user')
# @login_required
# def search_user():
#     # 관리자 권한 체크
#     user = session.get('principal')
#     if not user or user['role'] != 'ADMIN':
#         return redirect('/loginForm')
#     search_id = request.form.get('username')
#     found_user = None
#     if search_id:
#         found_user = find_user_by_username(search_id)
#     return render_template('/admin/admin_search.html', found_user=found_user)
#
#
# def reset_login_attempts_and_lockout(username):
#     update_user_login_attempt(username, 0)
#     update_user_is_lockout(username, False)
#     update_user_lockout_time(username, None)
#     return jsonify({"success": "true"})
#
#
# @api.route('/reset-user-session/<username>', methods=['POST'], endpoint='reset-user-session')
# @login_required
# def reset_user_session(username):
#     # DB에서 해당 유저의 시도횟수/락아웃필드 초기화
#     reset_login_attempts_and_lockout(username)
#     return "해당 유저의 세션(시도횟수/락아웃) 초기화 완료!"