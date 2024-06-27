# ffmpeg.py
import os
import signal
import subprocess

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required

from config import settings
from task_manager import TaskManager

m_ffmpeg = Blueprint('ffmpeg', __name__, template_folder='templates')

task_manager = TaskManager(settings['WORK_DIRECTORY'])
@m_ffmpeg.route('/ffmpeg')
@login_required
def ffmpeg():
    return render_template('ffmpeg.html')

@m_ffmpeg.route('/run_batch', methods=['POST'])
@login_required
def run_batch():
    keyword = request.form.get('keyword')
    clipboard_content = request.form.get('clipboard_content').replace('\r\n', '\n')
    print(clipboard_content)
    if keyword and clipboard_content:
        command = f'{settings.FFMPEG_SCRIPT_PATH} {keyword} "{clipboard_content}"'
        try:
            print("Executing command:", command)
            pid = task_manager.start_task(command, keyword)
            flash(f'Command executed with PID: {pid}', 'success')
        except subprocess.CalledProcessError as e:
            flash(f'Error executing command: {e}', 'danger')
        except UnicodeDecodeError as e:
            flash(f'Encoding error: {e}', 'danger')
        except IndexError as e:
            flash(f'Index error: {e}', 'danger')
    else:
        flash('Keyword and clipboard content are required', 'warning')
    return redirect(url_for('ffmpeg.ffmpeg'))

@m_ffmpeg.route('/check_status')
@login_required
def check_status():
    tasks = task_manager.get_running_tasks()
    print(tasks)
    return render_template('check_status.html', tasks=tasks)

@m_ffmpeg.route('/stop_task/<int:pid>', methods=['POST'])
@login_required
def stop_task(pid):
    task_manager.stop_task(pid)
    return redirect(url_for('ffmpeg.check_status'))
@m_ffmpeg.route('/task_status')
@login_required
def task_status():
    tasks = task_manager.get_running_tasks()
    task_status = [{'pid': task['process'].pid, 'running': task['process'].poll() is None, 'keyword': task['info']['keyword'], 'thumbnail': task['info'].get('thumbnail')} for task in tasks]
    return jsonify(task_status)

@m_ffmpeg.route('/kill_task/<int:pid>', methods=['POST'])
@login_required
def kill_task(pid):
    try:
        os.kill(pid, signal.SIGTERM)
        return redirect(url_for('ffmpeg.check_status'))
    except Exception as e:
        return str(e)
