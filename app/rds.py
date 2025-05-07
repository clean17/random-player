import redis
from flask import Blueprint, request, jsonify, send_file, render_template, redirect, url_for, Response, abort
from flask_login import login_required

rds = Blueprint('rds', __name__)

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

r.set('user:123:status', 'active')
r.set('task:running', 'true')

@rds.route('/test', methods=['get'])
@login_required
def get_redis_test():
    status = r.get('task:running')
    return jsonify({'task_running': status})

@rds.route('/last-read-chat-id', methods=['GET', 'POST'], endpoint='last-read-chat-id')
@login_required
def last_read_chat_id():
    username = request.args.get('username') if request.method == 'GET' else request.get_json().get('username')
    key = f"user:{username}:lastReadChatId"

    if request.method == 'POST':
        chatId = request.get_json().get('lastReadChatId')
        r.set(key, chatId)
        return jsonify({'result': 'success'})
    else:
        chatId = r.get(key)
        return jsonify({'username': username, 'last_read_chat_id': chatId})

@rds.route('/last-chat-id', methods=['GET', 'POST'], endpoint='last-chat-id')
@login_required
def handle_last_chat_id():
    key = "chat:lastChatId"

    if request.method == 'POST':
        data = request.get_json()
        chatId = data.get('lastChatId')
        r.set(key, chatId)
        return jsonify({'result': 'success'})

    elif request.method == 'GET':
        chatId = r.get(key)
        return jsonify({'last_chat_id': chatId})
