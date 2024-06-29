import hashlib
import os
import random
import subprocess
import time
from hashlib import md5

from flask import Blueprint, request, jsonify, send_file, render_template, redirect, url_for, Response, abort
from flask_login import login_required

from config import settings

video = Blueprint('video', __name__)


@video.route('/select_directory', methods=['POST'])
@login_required
def select_directory():
    directory = request.form.get('directory')
    return redirect(url_for('video.video_player', directory=directory))

@video.route('/video_player/<directory>')
@login_required
def video_player(directory):
    return render_template('video.html', directory=directory)

@video.route('/videos', methods=['GET'])
@login_required
def get_videos():
    directory = request.args.get('directory')
    video_directory = settings['VIDEO_DIRECTORY' + directory]  # 딕셔너리 접근 방식으로 수정
    videos = []
    for root, dirs, files in os.walk(video_directory):
        for file in files:
            if file.endswith(('.mp4', '.avi', '.mkv', 'ts')):
                rel_dir = os.path.relpath(root, video_directory)
                rel_file = os.path.join(rel_dir, file)
                videos.append(rel_file)

    random.seed(time.time())
    random.shuffle(videos)
    return jsonify(videos)

@video.route('/video/<path:filename>', methods=['GET'])
@login_required
def get_video(filename):
    directory = request.args.get('directory')
    video_directory = settings['VIDEO_DIRECTORY' + directory]  # 딕셔너리 접근 방식으로 수정
    return send_file(os.path.join(video_directory, filename))

@video.route('/delete/<path:filename>', methods=['DELETE'])
@login_required
def delete_video(filename):
    directory = request.args.get('directory')
    video_directory = settings['VIDEO_DIRECTORY' + directory]  # 딕셔너리 접근 방식으로 수정
    file_path = os.path.join(video_directory, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return '', 204
    return '', 404