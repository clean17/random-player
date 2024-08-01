import os
import random
import subprocess
import time
import cv2
import re
from send2trash import send2trash, TrashPermissionError
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

                rel_file = rel_file.replace(os.path.sep, '/')
                videos.append(rel_file)

    # print('############### video_list ###############')
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
    video_directory = settings.get('VIDEO_DIRECTORY' + directory)  # 딕셔너리 접근 방식으로 수정
    if not video_directory:
        return '', 404
    
    file_path = os.path.join(video_directory, filename)
    if os.path.exists(file_path):
        normalized_path = os.path.normpath(file_path)
        try:
            send2trash(normalized_path) # 휴지통
        except OSError as e:
            print(f"Error: {e}")
        except TrashPermissionError as e:
            print(f"Permission Error: {e}")

        print(f"[ {filename} ] is successfully deleted")
        # os.remove(file_path)
        return '', 204
    return '', 404



###################################################


def get_video_codec(file_path):
    video = cv2.VideoCapture(file_path)
    if not video.isOpened():
        return None
    codec = int(video.get(cv2.CAP_PROP_FOURCC))
    video.release()
    return codec

def generate_ffmpeg_command(input_path, start_time, output_codec='libx264'):
    command = [
        'ffmpeg',
        '-ss', str(start_time),  # 시작 시간
        '-i', input_path,  # 입력 파일
        '-c:v', output_codec,  # 비디오 코덱
        '-preset', 'ultrafast',  # 인코딩 속도 (품질 감소)
        '-c:a', 'aac',  # 오디오 코덱
        '-f', 'mp4',
        '-movflags', '+frag_keyframe+empty_moov+faststart',  # 실시간 스트리밍을 위한 설정
        'pipe:1'  # 표준 출력으로 데이터를 전송
    ]

    return command


@video.route('/stream/<path:filename>', methods=['GET'])
def video_stream(filename):
    print('############### stream ###################')
    directory = request.args.get('directory')
    video_directory = settings['VIDEO_DIRECTORY' + directory]
    file_path = os.path.join(video_directory, filename)

    if not os.path.exists(file_path):
        abort(404)

    # 영상 코덱 확인 및 FFmpeg 명령 구성
    codec = get_video_codec(file_path)
    output_codec = 'libx264' if codec == cv2.VideoWriter_fourcc(*'hvc1') else 'copy'
    start_time = 0
    start_byte = 0  # 시작 바이트 초기화

    # 범위 요청 처리
    range_header = request.headers.get('Range', None)
    if range_header:
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if match:
            start_byte = int(match.group(1))
            start_time = start_byte / 1000  # FFmpeg 시간 설정 (초 단위)

    start_time = start_byte / 1000
    command = generate_ffmpeg_command(file_path, start_time, output_codec)

    # FFmpeg 프로세스 시작
    def generate():
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=-1)
        try:
            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    break
                yield chunk
        finally:
            process.kill()

    # 파일 크기 및 응답 헤더 설정
    file_size = os.path.getsize(file_path)
    content_length = file_size - start_byte
    headers = {
        'Content-Type': 'video/mp4',
        'Content-Length': str(content_length),
        'Content-Range': f'bytes {start_byte}-{file_size-1}/{file_size}',
        'Accept-Ranges': 'bytes',
        'Connection': 'close',
    }

    return Response(generate(), status=206 if range_header else 200, headers=headers)
