import os
import signal
import subprocess
from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from flask_login import login_required
from config import settings
from task_manager import tasks, Task, current_date

m_ffmpeg = Blueprint('ffmpeg', __name__, template_folder='templates')

@m_ffmpeg.route('/ffmpeg')
@login_required
def ffmpeg():
    return render_template('ffmpeg.html')

@m_ffmpeg.route('/run_batch', methods=['POST'])
@login_required
def run_batch():
    keyword = request.form['keyword']
    url = request.form['clipboard_content']
    current_date_str = current_date()
    file_pattern = f"{settings['WORK_DIRECTORY']}/{current_date_str}{keyword}_*.ts"

    cmd = f"cmd /c \"f:/m/ff.bat {keyword} {url}\""
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
    tasks.append(Task(process.pid, file_pattern))

    return redirect(url_for('ffmpeg.status'))

@m_ffmpeg.route('/status')
@login_required
def status():
    return render_template('status.html', tasks=tasks)

@m_ffmpeg.route('/kill_task/<int:pid>', methods=['POST'])
@login_required
def kill_task(pid):
    os.kill(pid, signal.SIGTERM)
    for task in tasks:
        if task.pid == pid:
            tasks.remove(task)
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
            'last_modified_time': task.last_modified_time.strftime('%Y-%m-%d %H:%M:%S') if task.last_modified_time else 'N/A'
        })
    return jsonify(task_list)
