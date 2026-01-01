import os
import subprocess
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, send_from_directory
from flask_login import login_required
from flask_cors import cross_origin
from config.config import settings
from utils.ffmpeg.ffmpeg_handle_task_manager import tasks, Task, current_date, terminate_task
import shutil

m_ffmpeg = Blueprint('ffmpeg', __name__, template_folder='templates')

@m_ffmpeg.route('/ffmpeg')
@login_required
def ffmpeg():
    return render_template('ffmpeg.html')

@m_ffmpeg.route('/run-batch', methods=['POST'], endpoint='run-batch')
@login_required
def run_batch():
    keyword = request.form['keyword']
    url = request.form['clipboard_content'].replace('\r\n', '').replace('\n', '').strip()
    current_date_str = current_date()
    file_pattern = f"{settings['WORK_DIRECTORY']}/{current_date_str}{keyword}_*.ts"

    cmd = f'cmd /c "{settings["FFMPEG_SCRIPT_PATH"]} {keyword} "{url}" && exit"'
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True, encoding='utf-8')
    '''
    shell=True 새로운 셸
    capture_output=True 표준 출력,오류 캡쳐
    stdout=subprocess.PIPE 파이프로 캡쳐 (capture_output=True 의 기본값)
    '''
    tasks.append(Task(process.pid, file_pattern, settings['WORK_DIRECTORY'], url))

    return redirect(url_for('ffmpeg.status'))

@m_ffmpeg.route('/status')
@login_required
def status():
    free_space_gb = get_drive_free_space('F:')
    return render_template('status.html', tasks=tasks, free_space_gb=free_space_gb)

@m_ffmpeg.route('/get-free-size')
@login_required
def get_free_size():
    free_space_gb = get_drive_free_space('F:')
    return jsonify(free_space_gb)

@m_ffmpeg.route('/kill-task/<int:pid>', methods=['POST'], endpoint='kill-task')
@login_required
def kill_task(pid):
    terminate_task(pid)
    return redirect(url_for('ffmpeg.status'))

@m_ffmpeg.route('/get-tasks', methods=['GET'])
@login_required
def get_tasks():
    task_list = []
    for task in tasks:
        # thumbnail_url = url_for('ffmpeg.thumbnail', filename=os.path.basename(task.thumbnail_path), _external=True) if task.thumbnail_path else None
        # scheme을 붙일 필요가 없다..  src가 알아서 찾을테니
        thumbnail_url = url_for('ffmpeg.thumbnail', filename=os.path.basename(task.thumbnail_path)) if task.thumbnail_path else None
        # thumbnail_url = url_for('ffmpeg.thumbnail', filename=quote(os.path.basename(task.thumbnail_path))) if task.thumbnail_path else None
        # if thumbnail_url:
        #     thumbnail_url = 'https://merci-seoul.iptime.org' + thumbnail_url
        # print(thumbnail_url)

        task_list.append({
            'pid': task.pid,
            'file_name': task.file_name,
            'last_modified_time': task.last_modified_time,
            'thumbnail_path': thumbnail_url,
            'thumbnail_update_time': task.thumbnail_update_time,
            'url': task.url,
        })
    return jsonify(task_list)

@m_ffmpeg.route('/thumbnails/<path:filename>')
@cross_origin() # allowed CORS
def thumbnail(filename):
    response = send_from_directory(settings['WORK_DIRECTORY'], filename)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = 'Thu, 01 Jan 1970 00:00:00 GMT'
    return response


def get_drive_free_space(drive):
    total, used, free = shutil.disk_usage(drive)
    free_gb = free / (1024 ** 3)  # Convert bytes to GB
    return free_gb