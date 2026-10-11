"""음성 분석 — 통화/회의 녹음을 올리면 받아쓰기·화자분리·요약을 거쳐 마크다운으로 보여준다.

분석 자체는 tools/audio_analysis/worker.py 를 venv_audio(Python 3.12, torch/whisper/pyannote) 로 서브프로세스
실행한다 — 이 앱의 venv(3.8)에는 그 패키지들이 설치되지 않는다. GPU 하나를 쓰므로 작업은 한 번에 하나씩 순서대로.

작업 디렉토리: data/audio_analysis/<job_id>/
  job.json      업로드 메타 (원본 파일명, 화자 수, 업로드 사용자)
  input.<ext>   원본 오디오
  status.json   워커가 갱신하는 진행 상태 (stage: queued/running/done/error)
  result.md     최종 결과
  worker.log    워커 stdout/stderr
"""
import io
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from flask import Blueprint, render_template, request, jsonify, abort, send_file
from flask_login import login_required, current_user

audio = Blueprint('audio', __name__)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_DIR = os.path.join(ROOT_DIR, 'data', 'audio_analysis')
AUDIO_PYTHON = os.path.join(ROOT_DIR, 'venv_audio', 'Scripts', 'python.exe')
WORKER_SCRIPT = os.path.join(ROOT_DIR, 'tools', 'audio_analysis', 'worker.py')

AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.wav', '.aac', '.amr', '.3gp', '.ogg', '.opus', '.flac', '.wma', '.webm', '.mp4'}
JOB_ID_RE = re.compile(r'^[0-9a-f]{32}$')
DICTIONARY_DIR = os.path.join(JOBS_DIR, 'dictionary')
MAX_SPEAKERS = 10

_queue = queue.Queue()  # type: queue.Queue
_worker_lock = threading.Lock()
_worker_thread = None  # type: Optional[threading.Thread]
_running = {}  # type: Dict[str, subprocess.Popen]


# 사용자별 분리: 작업은 올린 사람만 보고(목록·결과·재생·다운로드·재분석·삭제), 단어장도 사용자별이다.
# 통화 녹음은 민감하다 — 게스트(nh824)에게 열면서 서로의 녹음·단어장(이름 목록)이 보이지 않게 했다 (2026-10-12).
def _owns(job_id: str) -> bool:
    return _read_json(os.path.join(JOBS_DIR, job_id, 'job.json')).get('user') == current_user.get_id()


def _job_dir(job_id: str) -> str:
    """남의 작업이면 존재 여부도 드러내지 않게 404."""
    if not JOB_ID_RE.match(job_id or ''):
        abort(404)
    path = os.path.join(JOBS_DIR, job_id)
    if not os.path.isdir(path) or not _owns(job_id):
        abort(404)
    return path


def dictionary_path(user_id: str) -> str:
    """사용자별 단어장 — 워커(tools/audio_analysis/worker.py load_vocabulary)도 같은 규칙으로 찾는다."""
    return os.path.join(DICTIONARY_DIR, re.sub(r'[^A-Za-z0-9_.-]', '_', user_id or 'unknown') + '.json')


# status.json 은 워커(별도 프로세스)가 쓰고 페이지 폴링이 2초마다 읽는다. 윈도우에선 누가 열고 있는 파일을
# os.replace 로 덮으면 WinError 5, 교체 순간에 열면 PermissionError 가 난다 — 둘 다 잠깐 기다렸다 다시 한다.
_IO_RETRIES = 40  # 대기 0.01·0.02·…·최대 0.1초씩 늘려 총 약 3.5초


def _read_json(path: str) -> Dict:
    for i in range(_IO_RETRIES):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (PermissionError, ValueError):  # ValueError: 아래 직접 쓰기 도중을 읽음
            time.sleep(min(0.01 * (i + 1), 0.1))
        except OSError:
            return {}
    return {}


def _write_json(path: str, data: Dict):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    for i in range(_IO_RETRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(min(0.01 * (i + 1), 0.1))
    # 계속 막히면 원자적 교체를 포기하고 직접 덮어쓴다 — 읽기용으로 열린 파일도 쓰기는 허용된다
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    try:
        os.remove(tmp)
    except OSError:
        pass


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _job_summary(job_id: str) -> Dict:
    path = os.path.join(JOBS_DIR, job_id)
    meta = _read_json(os.path.join(path, 'job.json'))
    status = _read_json(os.path.join(path, 'status.json'))
    return {
        'id': job_id,
        'filename': meta.get('filename', ''),
        'created_at': meta.get('created_at', ''),
        'num_speakers': meta.get('num_speakers', 0),
        'stage': status.get('stage', 'queued'),
        'progress': status.get('progress', 0),
        'message': status.get('message', ''),
        'duration': status.get('duration'),
        'speakers': status.get('speakers'),
        'summarized': status.get('summarized'),
        'finished_at': status.get('finished_at'),
        'title': status.get('title') or '',            # 분석이 붙인 제목 — 이전 회의 고르기 목록에 쓴다
        'previous_job': meta.get('previous_job') or '',
    }


def _valid_previous(prev_id: Optional[str], job_id: str) -> Optional[str]:
    """이전 회의로 지정할 수 있는 작업인지 — 본인 것이고, 분석이 끝났고, 자기 자신이 아닐 것."""
    if not prev_id or prev_id == job_id or not JOB_ID_RE.match(prev_id) or not _owns(prev_id):
        return None
    return prev_id if _read_json(os.path.join(JOBS_DIR, prev_id, 'status.json')).get('stage') == 'done' else None


# ─────────────────────────── 작업 큐 ───────────────────────────

def _worker_env() -> Dict[str, str]:
    env = dict(os.environ)
    env['PYTHONIOENCODING'] = 'utf-8'
    # HF_TOKEN / AUDIO_* 는 .env 에 두면 서버 재시작 없이도 다음 작업부터 반영된다
    try:
        from dotenv import dotenv_values
        for k, v in dotenv_values(os.path.join(ROOT_DIR, '.env')).items():
            if v and (k in ('HF_TOKEN', 'HUGGINGFACE_TOKEN') or k.startswith('AUDIO_')):
                env[k] = v
    except Exception:
        pass
    return env


def _run_job(job_id: str):
    path = os.path.join(JOBS_DIR, job_id)
    meta = _read_json(os.path.join(path, 'job.json'))
    if not meta:  # 대기 중에 삭제됨
        return
    status_path = os.path.join(path, 'status.json')
    _write_json(status_path, {'stage': 'running', 'progress': 0, 'message': '분석 시작', 'started_at': _now()})

    cmd = [AUDIO_PYTHON, WORKER_SCRIPT,
           '--input', os.path.join(path, meta['input']),
           '--outdir', path,
           '--title', os.path.splitext(meta.get('filename', ''))[0] or '음성 분석',
           '--num-speakers', str(meta.get('num_speakers') or 0)]
    try:
        # 로그 핸들까지 닫은 뒤에 _running 에서 빼야 delete_job 의 rmtree 가 윈도우 파일 잠금에 안 걸린다
        with open(os.path.join(path, 'worker.log'), 'w', encoding='utf-8') as log:
            proc = subprocess.Popen(cmd, cwd=ROOT_DIR, env=_worker_env(), stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            _running[job_id] = proc
            code = proc.wait()
    finally:
        _running.pop(job_id, None)

    if os.path.isdir(path) and _read_json(status_path).get('stage') not in ('done', 'error'):
        # 워커가 상태를 남기지 못하고 죽음 (import 실패, 강제 종료 등)
        _write_json(status_path, {'stage': 'error', 'progress': 0, 'finished_at': _now(),
                                  'message': '워커 비정상 종료 (exit {}) — worker.log 확인'.format(code)})


def _worker_loop():
    while True:
        job_id = _queue.get()
        try:
            _run_job(job_id)
        except Exception as e:
            print('### audio analysis job {} failed: {}'.format(job_id, e))
            # 상태를 안 바꾸면 '대기'로 영영 남는다 — 오류로 바꿔야 화면에 재시도 버튼이 뜬다
            try:
                if os.path.isdir(os.path.join(JOBS_DIR, job_id)):
                    _write_json(os.path.join(JOBS_DIR, job_id, 'status.json'),
                                {'stage': 'error', 'progress': 0, 'finished_at': _now(),
                                 'message': '작업 실행 실패: {}'.format(e)})
            except Exception:
                pass
        finally:
            _queue.task_done()


def _ensure_worker():
    """첫 사용 시 큐 스레드를 띄우고, 서버 재시작 전에 대기/진행 중이던 작업을 정리한다."""
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None:
            return
        os.makedirs(JOBS_DIR, exist_ok=True)
        pending = []
        for job_id in os.listdir(JOBS_DIR):
            if not JOB_ID_RE.match(job_id):
                continue
            info = _job_summary(job_id)
            if info['stage'] == 'queued':
                pending.append((info['created_at'], job_id))
            elif info['stage'] == 'running':
                _write_json(os.path.join(JOBS_DIR, job_id, 'status.json'),
                            {'stage': 'error', 'progress': info['progress'], 'finished_at': _now(),
                             'message': '서버 재시작으로 중단됨 — 다시 실행하세요'})
        for _, job_id in sorted(pending):
            _queue.put(job_id)
        _worker_thread = threading.Thread(target=_worker_loop, daemon=True, name='audio_analysis_worker')
        _worker_thread.start()


# ─────────────────────────── 라우트 ───────────────────────────

@audio.route('/', methods=['GET'])
@login_required
def get_audio_page():
    _ensure_worker()
    ready = os.path.exists(AUDIO_PYTHON) and os.path.exists(WORKER_SCRIPT)
    return render_template('audio_analysis.html', ready=ready, max_speakers=MAX_SPEAKERS, version=int(time.time()))


@audio.route('/upload', methods=['POST'])
@login_required
def upload_audio():
    _ensure_worker()
    if not os.path.exists(AUDIO_PYTHON):
        return jsonify({'error': '분석 환경(venv_audio)이 설치되지 않았습니다'}), 500

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': '파일이 없습니다'}), 400
    filename = os.path.basename(file.filename.replace('\\', '/'))
    ext = os.path.splitext(filename)[1].lower()
    if ext not in AUDIO_EXTENSIONS:
        return jsonify({'error': '지원하지 않는 형식입니다: {}'.format(ext or filename)}), 400

    try:
        num_speakers = int(request.form.get('num_speakers') or 0)
    except ValueError:
        num_speakers = 0
    num_speakers = max(0, min(num_speakers, MAX_SPEAKERS))
    hotwords = _split_words(request.form.get('hotwords', ''))
    previous_job = _valid_previous(request.form.get('previous_job'), '') or ''

    job_id = uuid.uuid4().hex
    path = os.path.join(JOBS_DIR, job_id)
    os.makedirs(path)
    file.save(os.path.join(path, 'input' + ext))
    _write_json(os.path.join(path, 'status.json'), {'stage': 'queued', 'progress': 0, 'message': '대기 중'})
    _write_json(os.path.join(path, 'job.json'), {
        'id': job_id, 'filename': filename, 'input': 'input' + ext, 'num_speakers': num_speakers,
        'hotwords': hotwords, 'previous_job': previous_job, 'user': current_user.get_id(), 'created_at': _now(),
    })
    _queue.put(job_id)
    return jsonify(_job_summary(job_id))


def _split_words(text: str) -> List[str]:
    """쉼표·줄바꿈으로 구분한 단어 목록 (중복 제거, 순서 유지)."""
    out = []  # type: List[str]
    for w in re.split(r'[,\n]', text or ''):
        w = w.strip()
        if w and w not in out:
            out.append(w[:40])
    return out[:100]


@audio.route('/dictionary', methods=['GET'])
@login_required
def get_dictionary():
    """단어장 — hotwords: 받아쓰기 힌트(이름·회사·부서·용어), corrections: 받아쓴 뒤 치환할 교정 규칙.
    워커가 data/audio_analysis/dictionary/<user>.json 을 직접 읽는다."""
    data = _read_json(dictionary_path(current_user.get_id()))
    return jsonify({'hotwords': data.get('hotwords') or [], 'corrections': data.get('corrections') or []})


@audio.route('/dictionary', methods=['POST'])
@login_required
def save_dictionary():
    body = request.get_json(silent=True) or {}
    corrections = []
    # '틀린 말 => 바른 말' 한 줄에 하나
    for line in str(body.get('corrections') or '').splitlines():
        if '=>' not in line:
            continue
        wrong, right = line.split('=>', 1)
        wrong, right = wrong.strip(), right.strip()
        if wrong and wrong != right:
            corrections.append({'from': wrong[:80], 'to': right[:80]})
    data = {'hotwords': _split_words(str(body.get('hotwords') or '')), 'corrections': corrections[:200],
            'updated_at': _now(), 'updated_by': current_user.get_id()}
    os.makedirs(DICTIONARY_DIR, exist_ok=True)
    _write_json(dictionary_path(current_user.get_id()), data)
    return jsonify(data)


@audio.route('/jobs', methods=['GET'])
@login_required
def list_jobs():
    if not os.path.isdir(JOBS_DIR):
        return jsonify([])
    jobs = [_job_summary(j) for j in os.listdir(JOBS_DIR) if JOB_ID_RE.match(j) and _owns(j)]  # type: List[Dict]
    jobs.sort(key=lambda j: j['created_at'], reverse=True)
    return jsonify(jobs)


@audio.route('/jobs/<job_id>', methods=['GET'])
@login_required
def get_job(job_id):
    path = _job_dir(job_id)
    info = _job_summary(job_id)
    md_path = os.path.join(path, 'result.md')
    if info['stage'] == 'done' and os.path.exists(md_path):
        with open(md_path, 'r', encoding='utf-8') as f:
            info['markdown'] = f.read()
        # 키워드·주제·타임라인·회의록 화면용 구조화 결과 (예전 작업엔 없다 — 화면은 markdown 으로 대체 표시)
        analysis = _read_json(os.path.join(path, 'analysis.json'))
        if analysis:
            info['result'] = analysis
        info['has_audio'] = bool(_read_json(os.path.join(path, 'job.json')).get('input'))
    return jsonify(info)


@audio.route('/jobs/<job_id>/md', methods=['GET'])
@login_required
def download_md(job_id):
    """?kind=minutes 면 회의록만, 아니면 전체 결과(요약+회의록+대화록)."""
    path = _job_dir(job_id)
    minutes = request.args.get('kind') == 'minutes'
    md_path = os.path.join(path, 'minutes.md' if minutes else 'result.md')
    if not os.path.exists(md_path):
        abort(404)
    name = os.path.splitext(_read_json(os.path.join(path, 'job.json')).get('filename') or job_id)[0]
    if minutes:
        name += '_회의록'
    # 경로로 send_file 하면 응답이 끝날 때까지 파일 핸들이 열려 있어 그 사이 삭제(rmtree)가 윈도우에서 실패한다
    with open(md_path, 'rb') as f:
        data = io.BytesIO(f.read())
    return send_file(data, as_attachment=True, download_name=name + '.md', mimetype='text/markdown')


@audio.route('/jobs/<job_id>/audio', methods=['GET'])
@login_required
def stream_audio(job_id):
    """대화록에서 시각을 누르면 그 지점부터 재생 — conditional=True 로 Range 요청(구간 탐색)을 지원한다."""
    path = _job_dir(job_id)
    meta = _read_json(os.path.join(path, 'job.json'))
    src = os.path.join(path, meta.get('input') or '')
    if not meta.get('input') or not os.path.isfile(src):
        abort(404)
    # 윈도우 mimetypes 는 m4a 를 모르거나 audio/x-m4a 로 준다 — 브라우저가 확실히 재생하는 타입으로
    mime = {'.m4a': 'audio/mp4', '.mp4': 'audio/mp4', '.aac': 'audio/aac', '.mp3': 'audio/mpeg', '.wav': 'audio/wav',
            '.ogg': 'audio/ogg', '.opus': 'audio/ogg', '.webm': 'audio/webm', '.flac': 'audio/flac'}
    return send_file(src, conditional=True, mimetype=mime.get(os.path.splitext(src)[1].lower()))


@audio.route('/jobs/<job_id>/log', methods=['GET'])
@login_required
def get_job_log(job_id):
    log_path = os.path.join(_job_dir(job_id), 'worker.log')
    if not os.path.exists(log_path):
        return jsonify({'log': ''})
    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        return jsonify({'log': f.read()[-20000:]})


@audio.route('/jobs/<job_id>/retry', methods=['POST'])
@login_required
def retry_job(job_id):
    _ensure_worker()
    path = _job_dir(job_id)
    if _job_summary(job_id)['stage'] not in ('error', 'done'):
        return jsonify({'error': '대기 중이거나 진행 중인 작업입니다'}), 400
    # 화자 수·이전 회의를 바꿔 재분석 — 받아쓰기는 워커가 캐시를 재사용하고 화자분리·요약만 다시 한다
    body = request.get_json(silent=True) or {}
    meta_path = os.path.join(path, 'job.json')
    meta = _read_json(meta_path)
    num = body.get('num_speakers', request.form.get('num_speakers'))
    if num is not None:
        try:
            meta['num_speakers'] = max(0, min(int(num), MAX_SPEAKERS))
        except (TypeError, ValueError):
            return jsonify({'error': '화자 수가 올바르지 않습니다'}), 400
    if 'previous_job' in body:
        prev = _valid_previous(body.get('previous_job'), job_id)
        if prev is None and body.get('previous_job'):
            return jsonify({'error': '이전 회의로 고를 수 없는 작업입니다 (본인의 완료된 작업만)'}), 400
        meta['previous_job'] = prev or ''
    if meta:
        _write_json(meta_path, meta)
    _write_json(os.path.join(path, 'status.json'), {'stage': 'queued', 'progress': 0, 'message': '대기 중'})
    _queue.put(job_id)
    return jsonify(_job_summary(job_id))


# nginx 가 GET/POST 외 메서드를 막는다(limit_except GET POST) — DELETE 대신 POST
@audio.route('/jobs/<job_id>/delete', methods=['POST'])
@login_required
def delete_job(job_id):
    path = _job_dir(job_id)
    proc = _running.get(job_id)
    if proc is not None:
        proc.kill()
        deadline = time.time() + 10
        while job_id in _running and time.time() < deadline:
            time.sleep(0.2)
    shutil.rmtree(path, ignore_errors=True)
    if os.path.exists(path):
        return jsonify({'error': '일부 파일을 삭제하지 못했습니다 (사용 중) — 잠시 후 다시 시도하세요'}), 500
    return jsonify({'ok': True})
