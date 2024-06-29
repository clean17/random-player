import os
import signal
import subprocess
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, send_from_directory
from flask_login import login_required
from config import settings
from task_manager import tasks, Task, current_date, save_tasks_to_file

m_ffmpeg = Blueprint('ffmpeg', __name__, template_folder='templates')

@m_ffmpeg.route('/ffmpeg')
@login_required
def ffmpeg():
    return render_template('ffmpeg.html')

@m_ffmpeg.route('/run_batch', methods=['POST'])
@login_required
def run_batch():
    keyword = request.form['keyword']
    url = request.form['clipboard_content'].replace('\r\n', '').replace('\n', '')
    current_date_str = current_date()
    file_pattern = f"{settings['WORK_DIRECTORY']}/{current_date_str}{keyword}_*.ts"

    cmd = f"cmd /c \"{settings['FFMPEG_SCRIPT_PATH']} {keyword} \"{url}\"\""
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True, encoding='utf-8')
    tasks.append(Task(process.pid, file_pattern, settings['WORK_DIRECTORY']))
    save_tasks_to_file()

    return redirect(url_for('ffmpeg.status'))

@m_ffmpeg.route('/status')
@login_required
def status():
    return render_template('status.html', tasks=tasks)

@m_ffmpeg.route('/kill_task/<int:pid>', methods=['POST'])
@login_required
def kill_task(pid):
    for task in tasks:
        if task.pid == pid:
            Task.terminate(pid)
            tasks.remove(task)
            save_tasks_to_file()
            break
    return redirect(url_for('ffmpeg.status'))

@m_ffmpeg.route('/get_tasks', methods=['GET'])
@login_required
def get_tasks():
    task_list = []
    for task in tasks:
        task_list.append({
            'pid': task.pid,
            'file_name': task.file_name,
            'last_modified_time': task.last_modified_time,
            'thumbnail_path': url_for('ffmpeg.thumbnail', filename=os.path.basename(task.thumbnail_path)) if task.thumbnail_path else None
        })
    return jsonify(task_list)

@m_ffmpeg.route('/thumbnails/<path:filename>')
@login_required
def thumbnail(filename):
    return send_from_directory(settings['WORK_DIRECTORY'], filename)
