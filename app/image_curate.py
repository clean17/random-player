"""refine(야짤2024) 정리 화면 — /image/curate/  (2026-11-02)

refine 이미지 중 취향과 먼/점수 낮은 이미지를 골라 보관함(refine/_review/)으로 옮긴다.
**최종 삭제는 없다(사용자 결정)** — 보관함으로 옮기기만 하고, 보관함에서 언제든 refine 으로 되돌릴 수 있다.

탭
  후보    종합 점수 하위(gif 제외). 기본값 '유지' — 뺄 이미지만 눌러 '제거'로 바꾸고 확정한다(2026-11-02 변경).
          판정은 labels.json 에 쌓이고, 쌓인 판정으로 취향 모델(tools/image_curate/scoring.py)을 학습해 다음 후보를 고른다.
  중복    근접중복 그룹(CLIP 유사도 ≥ 0.97). 기본값 '유지' — 별로인 것만 눌러 '제거'.
          중복 정리는 '둘 중 덜 나은 쪽'이라 취향 학습에는 쓰지 않는다(src='dup').
  임시 보관함  _review/ 목록(후보·중복 탭에서 제거한 이미지가 먼저 오는 곳). 마지막으로 검토해서
          보관함(_archive/)으로 넘기거나 refine 으로 복원 — 복원한 이미지는 '유지' 판정으로 바뀐다.
  보관함  _archive/ 목록(2026-11-03 추가). 임시 보관함에서 넘기는 것은 판정·학습을 바꾸지 않는다 —
          학습은 후보 탭에서 유지/제거를 가를 때(+복원)만. 여기서도 refine 으로 복원할 수 있다.

점수의 근거(임베딩·미적 점수)는 tools/image_curate/embed.py 가 별도 venv(venv_imgml, GPU)에서 계산한 캐시를
numpy 로만 읽는다. 캐시에 없는 파일은 건너뛴다.

갱신 흐름(2026-11-02)
  임베딩  화면을 열 때·자르기 저장 후·확정 후 embed.py 를 **별도 프로세스**로 띄운다(_kick_embed). 바뀐/새 파일만
          계산한다(파일명·크기·mtime 비교 — 자르기는 mtime 을 유지하지만 크기가 바뀐다). torch/CLIP 은 이 서버
          프로세스(자동매매 동거)에 올리지 않는다. 한 번에 하나만 돌고, 도는 중 요청이 오면 끝난 뒤 한 번 더 돈다.
  점수    _compute 가 (임베딩 캐시 mtime, labels.json mtime, refine 목록)이 바뀌면 전체를 다시 계산한다 —
          확정하면 판정이 늘어 취향 모델을 다시 학습하고 전체 순위를 새로 매긴다. 확정 뒤 화면은 임베딩 갱신이
          끝나기를 기다렸다가(/api/embed/status) 후보를 다시 받는다.

2026-11-03
  - embed.py 다음에 features.py(인물·얼굴 영역 CLIP)도 이어서 돌린다. 취향 모델 입력이 전체+인물+얼굴로 바뀌었다
    (근거: tools/image_curate/scoring.py 모듈 설명). 둘 다 바뀐 파일만 계산 — 몇 장이면 합쳐 20~30초.
  - 갤러리에서 move → refine 으로 옮기거나 refine 갤러리에서 자르면 app/image.py 가 schedule_embed() 를 부른다.
    마지막 요청 후 EMBED_DEBOUNCE 초 뒤에 한 번만 돈다.
"""
import os
import shutil
import subprocess
import threading
import time
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from config.config import settings

from app import image as image_mod
from app.image import IMAGE_DIR2, REF_IMAGE_DIR, safe_path_join, _carry_crop_origin
from app.motion_photo import MOTION_SUFFIX, OLD_MOTION_SUFFIXES
from tools.image_curate import scoring
from tools.image_curate.common import (CACHE_PATH, FEAT_PATH, LABELS_BACKUP_KEEP, LABELS_PATH, PROJECT_ROOT,
                                       ARCHIVE_SUBDIR, REVIEW_SUBDIR, SCREEN_FEAT_PATH, TRASH_DIR,
                                       list_images_recursive, backup_file, base_name, list_images, load_cache,
                                       load_feat)

curate_bp = Blueprint('curate', __name__)
log = logging.getLogger(__name__)


@curate_bp.before_request
def _super_only():
    """메인 화면 Image 메뉴(index.html)와 같은 기준 — SUPER 계정만. 파일을 옮기는 화면이라 다른 계정은 막는다."""
    if not current_user.is_authenticated:
        return None   # 각 라우트의 login_required 가 로그인 화면으로 보낸다
    if current_user.get_id() != settings['SUPER_USERNAME']:
        return jsonify({'error': 'forbidden'}), 403
    return None
DEFAULT_N = 100
_lock = threading.Lock()          # 이동·판정 기록은 한 번에 하나만
_state_cache = {'key': None, 'val': None}


# ── 판정 기록 ───────────────────────────────────────────────────────────────
def _load_labels() -> Dict[str, Dict]:
    try:
        with open(LABELS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_labels(labels: Dict[str, Dict]) -> None:
    os.makedirs(os.path.dirname(LABELS_PATH), exist_ok=True)
    tmp = LABELS_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(labels, f, ensure_ascii=False, indent=0)
    os.replace(tmp, LABELS_PATH)
    backup_file(LABELS_PATH, LABELS_BACKUP_KEEP)   # F:\image_curate_backup — common.py 참고


def _mtime(p: str) -> float:
    try:
        return os.path.getmtime(p)
    except OSError:
        return 0.0


# ── 임베딩 갱신(embed.py 를 별도 프로세스로) ───────────────────────────────────
_EMBED_PY = os.path.join(PROJECT_ROOT, 'venv_imgml', 'Scripts', 'python.exe')
_EMBED_SCRIPTS = [os.path.join(PROJECT_ROOT, 'tools', 'image_curate', n) for n in ('embed.py', 'features.py')]
_EMBED_LOG = os.path.join(os.path.dirname(LABELS_PATH), 'embed.log')
_EMBED_TIMEOUT = 3600
EMBED_DEBOUNCE = 60   # 갤러리 이동·자르기 후 이 시간(초) 동안 추가 요청이 없으면 실행
_embed_lock = threading.Lock()
_gpu_lock = threading.Lock()      # GPU 를 쓰는 하위 프로세스는 한 번에 하나(refine 갱신 / image2 1차 분류)
_embed = {'running': False, 'again': False, 'rc': None, 'error': None, 'started': None, 'ended': None}
_debounce = {'timer': None}


def _cache_ver() -> float:
    """화면이 '캐시가 바뀌었나'를 판단하는 값 — 두 캐시 중 늦게 바뀐 시각."""
    return max(_mtime(CACHE_PATH), _mtime(FEAT_PATH))


def schedule_embed(delay: float = EMBED_DEBOUNCE) -> None:
    """갤러리(app/image.py)용 — 한 장씩 연달아 옮기므로 마지막 요청 후 delay 초 뒤에 한 번만 돈다.
    실패해도 갤러리 동작에는 영향 없다."""
    try:
        with _embed_lock:
            t = _debounce['timer']
            if t is not None:
                t.cancel()
            t = threading.Timer(delay, _kick_embed)
            t.daemon = True
            t.name = 'curate-embed-debounce'
            _debounce['timer'] = t
            t.start()
    except Exception as e:  # noqa: BLE001
        log.warning('curate schedule_embed failed: %s', e)


def _kick_embed() -> bool:
    """embed.py → features.py 실행을 요청한다. 이미 도는 중이면 끝난 뒤 한 번 더 돌도록 표시만 한다. venv_imgml 이 없으면 False."""
    if not os.path.isfile(_EMBED_PY):
        _embed['error'] = 'venv_imgml 없음'
        return False
    with _embed_lock:
        if _embed['running']:
            _embed['again'] = True
            return True
        _embed['running'], _embed['again'] = True, False
    threading.Thread(target=_embed_worker, name='curate-embed', daemon=True).start()
    return True


def _embed_worker() -> None:
    while True:
        _embed['started'], rc, err = time.time(), None, None
        try:
            os.makedirs(os.path.dirname(_EMBED_LOG), exist_ok=True)
            if os.path.exists(_EMBED_LOG) and os.path.getsize(_EMBED_LOG) > 2 * 1024 * 1024:
                os.replace(_EMBED_LOG, _EMBED_LOG + '.1')       # 로그가 커지면 한 세대만 남긴다
            with open(_EMBED_LOG, 'a', encoding='utf-8') as lf:
                for script in _EMBED_SCRIPTS:      # features.py 는 embed.py 와 독립 — 앞이 실패해도 돈다
                    sname = os.path.basename(script)
                    lf.write('\n=== %s %s\n' % (datetime.now().isoformat(timespec='seconds'), sname))
                    lf.flush()
                    try:
                        with _gpu_lock:     # image2 1차 분류 계산과 GPU(8GB)를 동시에 쓰지 않는다
                            p = subprocess.run(
                                [_EMBED_PY, script, '--dir', REF_IMAGE_DIR], cwd=PROJECT_ROOT,
                                stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                env=dict(os.environ, PYTHONIOENCODING='utf-8'), timeout=_EMBED_TIMEOUT,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                        if p.returncode != 0 and err is None:
                            rc = p.returncode
                            err = '%s 종료코드 %s (logs/image_curate/embed.log)' % (sname, p.returncode)
                    except Exception as e:  # noqa: BLE001
                        if err is None:
                            err = '%s: %s: %s' % (sname, type(e).__name__, e)
                if rc is None and err is None:
                    rc = 0
        except Exception as e:  # noqa: BLE001 — 실패해도 정리 화면은 기존 캐시로 계속 동작
            err = '%s: %s' % (type(e).__name__, e)
        if err:
            log.warning('curate embed failed: %s', err)
        with _embed_lock:
            _embed['rc'], _embed['error'], _embed['ended'] = rc, err, time.time()
            if _embed['again']:
                _embed['again'] = False
                continue
            _embed['running'] = False
            return


# ── 점수 계산(캐시) ─────────────────────────────────────────────────────────
def _compute() -> Dict:
    """현재 refine 최상위 이미지 기준 점수. 캐시·판정·refine 목록이 그대로면 재사용한다."""
    files = list_images(REF_IMAGE_DIR)
    names_now = [f[0] for f in files]
    key = (_mtime(CACHE_PATH), _mtime(FEAT_PATH), _mtime(LABELS_PATH), len(names_now), hash(tuple(names_now)))
    if _state_cache['key'] == key:
        return _state_cache['val']

    c = load_cache()
    if c is None:
        raise RuntimeError('임베딩 캐시 없음 — venv_imgml/Scripts/python.exe tools/image_curate/embed.py 먼저 실행')
    all_bases = [base_name(str(n)) for n in c['names']]
    idx_by_base = {b: i for i, b in enumerate(all_bases)}
    E_all = scoring.normalize(c['emb'])
    X_all = scoring.model_input(E_all, load_feat(), all_bases)   # 취향 모델 입력: 전체+인물+얼굴(2026-11-03)
    aes_all = c['aes'].astype(np.float64)

    cur = [n for n in names_now if n in idx_by_base]          # 캐시에 없는 새 파일은 빠진다
    missing = len(names_now) - len(cur)
    ci = np.array([idx_by_base[n] for n in cur], dtype=int)
    E, aes = E_all[ci], aes_all[ci]
    sc = scoring.base_scores(E, aes)

    # 취향 모델: 후보 탭 판정만(중복 탭 판정은 제외). 학습 풀 = 현재 refine + 보관함으로 간 제거 판정
    labels = _load_labels()
    cur_set = set(cur)
    rm = [n for n, v in labels.items() if v.get('label') == 'remove' and v.get('src') == 'candidate'
          and n in idx_by_base and n not in cur_set]
    pool_idx = np.concatenate([ci, np.array([idx_by_base[n] for n in rm], dtype=int)])
    y = np.zeros(len(pool_idx), dtype=int)
    y[len(ci):] = 1
    keep_mask = np.array([labels.get(n, {}).get('label') == 'keep' for n in cur] + [False] * len(rm))
    model_prob = None
    clf = scoring.train_model(X_all[pool_idx], y, keep_mask)
    if clf is not None:
        model_prob = clf.predict_proba(X_all[ci])[:, 1]
    final = scoring.final_scores(sc['combined'], model_prob)

    val = {'names': cur, 'aes': aes, 'sc': sc, 'model': model_prob, 'final': final,
           'labels': labels, 'missing': missing,
           'n_remove': len(rm), 'n_keep': int(keep_mask.sum()),
           # image2 1차 분류(_screen_result)가 같은 모델을 읽기만 한다
           'clf': clf, 'X_cur': X_all[ci], 'keep_cur': keep_mask[:len(ci)]}
    _state_cache['key'], _state_cache['val'] = key, val
    return val


def _item(st: Dict, i: int) -> Dict:
    m = st['model']
    return {'name': st['names'][i], 'aes': round(float(st['aes'][i]), 2),
            'sim': round(float(st['sc']['knn_sim'][i]), 3),
            'score': round(float(st['final'][i]), 3),
            'model': None if m is None else round(float(m[i]), 3),
            # 자른 이미지의 캐시 회피값(편집 시각) — 갤러리(img_v)와 같은 값. 없으면 None
            'v': image_mod.img_v('refine', st['names'][i])}


# ── 파일 이동 ───────────────────────────────────────────────────────────────
def _move_one(name: str, src_sub: str, dst_sub: str) -> Optional[str]:
    """refine/<src_sub>/<name> → refine/<dst_sub>/<name>. sub: '' = refine 최상위, REVIEW_SUBDIR(임시 보관함),
    ARCHIVE_SUBDIR(보관함). 같은 볼륨이라 이름만 바뀐다. 실패 사유를 돌려준다(None=성공).
    썸네일·자르기 원본 백업(origin/)·자르기 기록도 같이 옮긴다(갤러리 간 이동 move_image 와 같은 규칙)."""
    name = os.path.basename(name)
    src_rel = (src_sub + '/' if src_sub else '') + name
    dst_rel = (dst_sub + '/' if dst_sub else '') + name
    try:
        src = safe_path_join(REF_IMAGE_DIR, src_rel)
        dst = safe_path_join(REF_IMAGE_DIR, dst_rel)
    except ValueError:
        return 'invalid'
    if not os.path.isfile(src):
        return 'missing'
    if os.path.exists(dst):
        return 'exists'
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.replace(src, dst)
    except OSError:
        shutil.move(src, dst)

    from utils.image_thumbs import move_thumb
    move_thumb(src, REF_IMAGE_DIR, dst, REF_IMAGE_DIR)
    # 모션포토 영상 캐시는 원본에서 다시 만들 수 있으니 지운다(move_image 와 같음)
    stem = os.path.splitext(src_rel)[0]
    for sfx in (MOTION_SUFFIX,) + tuple(OLD_MOTION_SUFFIXES):
        p = os.path.join(REF_IMAGE_DIR, 'thumb', stem + sfx)
        if os.path.exists(p):
            os.remove(p)
    try:
        _carry_crop_origin('refine', src_rel, 'refine', dst_rel)
    except OSError as e:
        log.warning('curate: crop origin carry failed %s -> %s: %s', src_rel, dst_rel, e)

    # refine 갤러리의 메모리 목록(셔플/원본 순서)도 맞춘다
    for arr in (image_mod.refined_image_arr, image_mod.ref_shuffled_images, image_mod.ref_original_images):
        if arr is None:      # 서버 시작 직후 refine 을 한 번도 안 열었으면 ref_shuffled_images 는 None
            continue
        if not src_sub:
            arr[:] = [p for p in arr if p != name]
        elif not dst_sub and name not in arr:
            arr.append(name)
    return None


def _move_many(names: List[str], src_sub: str, dst_sub: str) -> Tuple[List[str], Dict[str, str]]:
    ok, fail = [], {}
    for n in names:
        try:
            r = _move_one(n, src_sub, dst_sub)
        except Exception as e:  # noqa: BLE001 — 한 장 실패로 나머지를 멈추지 않는다
            r = '%s: %s' % (type(e).__name__, e)
        if r is None:
            ok.append(os.path.basename(n))
        else:
            fail[n] = r
    return ok, fail


def _purge_one(name: str, dest: str) -> Optional[str]:
    """refine/_review/<name> → dest/<name> (다른 볼륨 F: 이라 복사 후 삭제). 자르기 원본 백업(origin/_review/<name>)은
    dest/origin/<name> 으로, 썸네일·모션 캐시는 지운다(다시 만들 수 있다). 실패 사유를 돌려준다(None=성공)."""
    name = os.path.basename(name)
    rel = REVIEW_SUBDIR + '/' + name
    try:
        src = safe_path_join(REF_IMAGE_DIR, rel)
    except ValueError:
        return 'invalid'
    if not os.path.isfile(src):
        return 'missing'
    dst = os.path.join(dest, name)
    if os.path.exists(dst):
        return 'exists'
    os.makedirs(dest, exist_ok=True)
    shutil.move(src, dst)

    bk = image_mod._origin_path('refine', rel)
    if os.path.isfile(bk):
        os.makedirs(os.path.join(dest, 'origin'), exist_ok=True)
        shutil.move(bk, os.path.join(dest, 'origin', name))
    from utils.image_thumbs import thumb_path
    stem = os.path.splitext(rel)[0]
    for p in [thumb_path(REF_IMAGE_DIR, rel)] + [os.path.join(REF_IMAGE_DIR, 'thumb', stem + s)
                                               for s in (MOTION_SUFFIX,) + tuple(OLD_MOTION_SUFFIXES)]:
        if os.path.exists(p):
            os.remove(p)
    key = 'refine/' + rel
    if image_mod._crop_history.pop(key, None) is not None:
        image_mod._save_crop_history()
    if image_mod._edit_versions.pop(key, None) is not None:
        image_mod._save_edit_versions()
    return None


# ── 라우트 ─────────────────────────────────────────────────────────────────
@curate_bp.route('/', methods=['GET'])
@login_required
def page():
    return render_template('image_curate.html', version=int(time.time()))


@curate_bp.route('/api/candidates', methods=['GET'])
@login_required
def api_candidates():
    n = max(10, min(int(request.args.get('n', DEFAULT_N)), 500))
    try:
        st = _compute()
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 503
    labels = st['labels']
    order = np.argsort(-st['final'])
    out = []
    for i in order:
        nm = st['names'][i]
        if nm.lower().endswith('.gif'):          # 2026-11-02 사용자: 후보에서 gif 제외
            continue
        if labels.get(nm, {}).get('label') == 'keep':
            continue
        out.append(_item(st, int(i)))
        if len(out) >= n:
            break
    return jsonify({'items': out, 'model': st['model'] is not None,
                    'n_remove': st['n_remove'], 'n_keep': st['n_keep'],
                    'total': len(st['names']), 'missing': st['missing'], 'cache_ver': _cache_ver()})


@curate_bp.route('/api/embed', methods=['POST'])
@login_required
def api_embed():
    """임베딩 갱신 요청(화면 열 때·자르기 저장 후). 바로 돌아오고, 진행은 /api/embed/status 로 본다."""
    return jsonify({'started': _kick_embed(), 'error': _embed['error']})


@curate_bp.route('/api/embed/status', methods=['GET'])
@login_required
def api_embed_status():
    return jsonify({'running': _embed['running'], 'error': _embed['error'], 'cache_ver': _cache_ver()})


@curate_bp.route('/api/dups', methods=['GET'])
@login_required
def api_dups():
    try:
        st = _compute()
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 503
    groups = scoring.dup_groups(st['sc']['pairs'], len(st['names']))
    out = [sorted([_item(st, i) for i in g], key=lambda x: -x['aes']) for g in groups]
    return jsonify({'groups': out, 'thr': scoring.DUP_THR})


_SUBS = {'review': REVIEW_SUBDIR, 'archive': ARCHIVE_SUBDIR}


@curate_bp.route('/api/review', methods=['GET'])
@login_required
def api_review():
    """?where=review(임시 보관함, 기본) | archive(보관함)"""
    sub = _SUBS.get(request.args.get('where', 'review'))
    if sub is None:
        return jsonify({'error': 'invalid where'}), 400
    rv = os.path.join(REF_IMAGE_DIR, sub)
    labels = _load_labels()
    items = []
    if os.path.isdir(rv):
        for n, _s, _m in list_images(rv):
            lb = labels.get(n, {})
            items.append({'name': n, 'src': lb.get('src', ''), 'ts': lb.get('ts', '')})
    items.sort(key=lambda x: x['ts'], reverse=True)
    return jsonify({'items': items})


@curate_bp.route('/api/purge-dups', methods=['POST'])
@login_required
def api_purge_dups():
    """보관함 중 '중복 정리'로 들어온(src=dup) 이미지를 TRASH_DIR/dup_<시각>/ 으로 옮긴다(2026-11-03 사용자 요청).
    중복 판정은 취향 학습에 쓰지 않으므로 판정 기록에 purged 만 남기고, 임베딩·특징 캐시에서도 빠진다
    (embed.py/features.py 는 파일이 없어진 판정 이미지 중 src=dup 은 남기지 않는다)."""
    with _lock:
        labels = _load_labels()
        rv = os.path.join(REF_IMAGE_DIR, REVIEW_SUBDIR)
        present = set(n for n, _s, _m in list_images(rv)) if os.path.isdir(rv) else set()
        names = [n for n in present if labels.get(n, {}).get('src') == 'dup' and labels[n].get('label') == 'remove']
        if not names:
            return jsonify({'moved': 0, 'fail': {}, 'dest': None})
        dest = os.path.join(TRASH_DIR, 'dup_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
        try:
            os.makedirs(dest, exist_ok=True)
        except OSError as e:
            return jsonify({'error': '보관 폴더를 만들 수 없음(%s): %s' % (TRASH_DIR, e)}), 500
        ok, fail = [], {}
        for n in names:
            try:
                r = _purge_one(n, dest)
            except Exception as e:  # noqa: BLE001 — 한 장 실패로 나머지를 멈추지 않는다
                r = '%s: %s' % (type(e).__name__, e)
            if r is None:
                ok.append(n)
            else:
                fail[n] = r
        ts = datetime.now().isoformat(timespec='seconds')
        for n in ok:
            labels[n]['purged'] = ts
        if ok:
            _save_labels(labels)
    log.info('curate purge-dups: %d moved to %s, %d failed', len(ok), dest, len(fail))
    if ok:
        _kick_embed()       # 캐시에서 빼기
    return jsonify({'moved': len(ok), 'fail': fail, 'dest': dest})


@curate_bp.route('/api/apply', methods=['POST'])
@login_required
def api_apply():
    """{remove: [...], keep: [...], src: 'candidate'|'dup'} — remove 는 보관함으로 옮기고 판정을 기록한다."""
    data = request.get_json(silent=True) or {}
    src = data.get('src')
    if src not in ('candidate', 'dup'):
        return jsonify({'error': 'invalid src'}), 400
    remove = [os.path.basename(x) for x in (data.get('remove') or [])]
    keep = [os.path.basename(x) for x in (data.get('keep') or [])] if src == 'candidate' else []
    ts = datetime.now().isoformat(timespec='seconds')
    with _lock:
        ok, fail = _move_many(remove, '', REVIEW_SUBDIR)
        labels = _load_labels()
        for n in ok:
            labels[n] = {'label': 'remove', 'src': src, 'ts': ts}
        for n in keep:
            labels[n] = {'label': 'keep', 'src': src, 'ts': ts}
        _save_labels(labels)
    log.info('curate apply src=%s moved=%d keep=%d fail=%d', src, len(ok), len(keep), len(fail))
    _kick_embed()   # 옮긴 파일 이름(_review/) 반영 + 그새 자른/새 이미지 계산. 화면은 끝나길 기다렸다가 후보를 다시 받는다
    return jsonify({'moved': len(ok), 'kept': len(keep), 'fail': fail})


@curate_bp.route('/api/restore', methods=['POST'])
@login_required
def api_restore():
    """{names, from: review|archive} 임시 보관함/보관함 → refine. 복원한 이미지는 '유지' 판정으로 바꾼다
    (잘못 뺀 것이므로 취향 학습에도 유지 신호)."""
    data = request.get_json(silent=True) or {}
    names = [os.path.basename(x) for x in (data.get('names') or [])]
    sub = _SUBS.get(data.get('from') or 'review')
    if sub is None:
        return jsonify({'error': 'invalid from'}), 400
    ts = datetime.now().isoformat(timespec='seconds')
    with _lock:
        ok, fail = _move_many(names, sub, '')
        labels = _load_labels()
        for n in ok:
            labels[n] = {'label': 'keep', 'src': 'restore', 'ts': ts}
        _save_labels(labels)
    log.info('curate restore from=%s moved=%d fail=%d', sub, len(ok), len(fail))
    _kick_embed()
    return jsonify({'restored': len(ok), 'fail': fail})


@curate_bp.route('/api/archive', methods=['POST'])
@login_required
def api_archive():
    """{names} 임시 보관함 → 보관함(마지막 검토 끝, 2026-11-03 사용자 요청). **판정·학습은 바꾸지 않는다** —
    학습은 후보 탭에서 유지/제거를 가를 때만 한다. 판정 기록에 archived 시각만 남긴다."""
    data = request.get_json(silent=True) or {}
    names = [os.path.basename(x) for x in (data.get('names') or [])]
    ts = datetime.now().isoformat(timespec='seconds')
    with _lock:
        ok, fail = _move_many(names, REVIEW_SUBDIR, ARCHIVE_SUBDIR)
        labels = _load_labels()
        changed = False
        for n in ok:
            if n in labels:
                labels[n]['archived'] = ts
                changed = True
        if changed:
            _save_labels(labels)
    log.info('curate archive moved=%d fail=%d', len(ok), len(fail))
    _kick_embed()   # 캐시 안 파일 이름(_review/ → _archive/)만 바뀐다 — 다시 계산하지는 않는다
    return jsonify({'moved': len(ok), 'fail': fail})


# ── image2 1차 분류 (2026-11-03, 모델은 읽기만) ─────────────────────────────────
# 사용자 요청: 지금 취향 모델로 dir=image2(인스타 계정별 폴더)를 1차로 걸러, 통과한 것은 갤러리 ☰ 메뉴 버튼으로
# move 로 옮기고(이동은 화면이 기존 /image/move-image 를 그대로 부른다) 나머지는 사용자가 직접 본다.
# **모델은 사용만 한다** — 판정 기록·학습·refine 캐시는 건드리지 않는다.
# 특징은 features.py --recursive --out image2_feat.npz 로 따로 계산한다(바뀐/새 파일만, 처음 1회 약 30분).
# 통과 = 둘 다 만족
#   (1) 취향 모델의 '제거될 확률' ≤ refine 에서 사용자가 '유지'로 판정한 이미지들의 SCREEN_P_Q 분위
#   (2) refine 과 닮음: refine 에서 가장 비슷한 10장과의 평균 유사도 ≥ refine 이미지끼리 잰 같은 값의 SCREEN_SIM_Q 분위
#       — 취향 모델은 refine(이미 한 번 고른 이미지) 안에서만 학습해 사람 없는 사진·남자·글자 같은 종류는 본 적이
#         없다. 그런 이미지는 확률이 엉뚱하게 낮게 나올 수 있어 (2)로 거른다.
SCREEN_DIRS = {'image2': IMAGE_DIR2}
SCREEN_P_Q = 0.5
SCREEN_SIM_Q = 0.05
_SCREEN_LOG = os.path.join(os.path.dirname(LABELS_PATH), 'screen.log')
_screen_lock = threading.Lock()
# 계산(features.py) → 분류(_screen_result)까지 한 스레드에서 끝내고 결과를 'result' 에 둔다 — 분류 계산이 image2
# 목록 읽기(WSL 9P) 때문에 수십 초 걸려, 화면 요청 안에서 하면 프록시 시간 초과로 끊길 수 있다(2026-11-03).
_screen = {'running': False, 'error': None, 'started': None, 'ended': None, 'phase': '', 'result': None}
_screen_move = {'running': False, 'total': 0, 'moved': 0, 'fail': [], 'error': None}
_screen_cache = {'key': None, 'val': None}


def _kick_screen() -> bool:
    if not os.path.isfile(_EMBED_PY):
        _screen['error'] = 'venv_imgml 없음'
        return False
    with _screen_lock:
        if _screen['running'] or _screen_move['running']:
            return True
        _screen['running'], _screen['error'], _screen['result'] = True, None, None
        _screen['phase'] = ''
    threading.Thread(target=_screen_worker, name='curate-screen', daemon=True).start()
    return True


def _screen_worker() -> None:
    _screen['started'], err = time.time(), None
    try:
        os.makedirs(os.path.dirname(_SCREEN_LOG), exist_ok=True)
        with open(_SCREEN_LOG, 'w', encoding='utf-8') as lf:     # 진행 표시용 — 매번 새로 쓴다
            with _gpu_lock:
                p = subprocess.run(
                    [_EMBED_PY, _EMBED_SCRIPTS[1], '--dir', IMAGE_DIR2, '--recursive', '--out', SCREEN_FEAT_PATH],
                    cwd=PROJECT_ROOT, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                    env=dict(os.environ, PYTHONIOENCODING='utf-8'), timeout=4 * 3600,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if p.returncode != 0:
            err = 'features.py 종료코드 %s (logs/image_curate/screen.log)' % p.returncode
        else:
            _screen['phase'] = '취향 모델로 분류 중… (image2 목록 읽기 포함 1분 안팎)'
            _screen['result'] = _screen_result()
    except Exception as e:  # noqa: BLE001
        err = '%s: %s' % (type(e).__name__, e)
    if err:
        log.warning('curate screen failed: %s', err)
    with _screen_lock:
        _screen['running'], _screen['error'], _screen['ended'] = False, err, time.time()


def _screen_move_worker(names: List[str]) -> None:
    """통과분을 image2 → move 로 옮긴다. 갤러리의 이동 버튼과 같은 처리(app/image.py move_image_core)."""
    from app.image import move_image_core   # image.py 가 이 모듈을 지연 import 하므로 여기서도 지연
    try:
        for n in names:
            try:
                body, code = move_image_core({'imagepath': 'image2', 'subpath': '', 'filename': n})
                ok = code == 200 and body.get('status') == 'success'
                msg = '' if ok else '%s %s' % (code, body.get('message', ''))
            except Exception as e:  # noqa: BLE001
                ok, msg = False, '%s: %s' % (type(e).__name__, e)
            if ok:
                _screen_move['moved'] += 1
            else:
                _screen_move['fail'].append('%s — %s' % (n, msg))
                log.warning('curate screen move failed: %s — %s', n, msg)
    except Exception as e:  # noqa: BLE001
        _screen_move['error'] = '%s: %s' % (type(e).__name__, e)
    finally:
        _screen['result'] = None   # 목록이 바뀌었으니 다음엔 다시 분류
        _screen_move['running'] = False


def _screen_progress() -> str:
    """screen.log 마지막 진행 줄('  123/4567  60s ...')."""
    try:
        with open(_SCREEN_LOG, 'r', encoding='utf-8', errors='replace') as f:
            lines = [ln.strip() for ln in f.readlines()[-20:] if ln.strip()]
    except OSError:
        return ''
    for ln in reversed(lines):
        if '/' in ln.split(' ')[0] or ln.startswith('재사용'):
            return ln
    return lines[-1] if lines else ''


def _screen_result() -> Dict:
    st = _compute()
    if st.get('clf') is None:
        raise RuntimeError('취향 모델이 아직 없음 — 정리 화면에서 판정을 먼저 쌓아야 함')
    if not os.path.exists(SCREEN_FEAT_PATH):
        raise RuntimeError('image2 특징이 아직 없음 — 계산을 먼저 실행')
    files = list_images_recursive(IMAGE_DIR2)
    names_now = [f[0] for f in files]
    key = (_mtime(SCREEN_FEAT_PATH), _state_cache['key'], len(names_now), hash(tuple(names_now)))
    if _screen_cache['key'] == key:
        return _screen_cache['val']
    with np.load(SCREEN_FEAT_PATH, allow_pickle=False) as z:
        feat = {k: z[k] for k in ('names', 'sizes', 'emb', 'emb_person', 'emb_face')}
    fi = {str(n): i for i, n in enumerate(feat['names'])}
    size_now = {f[0]: f[1] for f in files}
    names = [n for n in names_now if n in fi and int(feat['sizes'][fi[n]]) == size_now[n]]   # 계산 후 바뀐 파일 제외
    out = {'total': len(names_now), 'scored': len(names), 'missing': len(names_now) - len(names),
           'pass': [], 'thr_p': None, 'thr_sim': None}
    if names:
        X2 = scoring.feat_rows(feat, np.array([fi[n] for n in names], dtype=int))
        clf, Xr = st['clf'], st['X_cur']
        p2 = clf.predict_proba(X2)[:, 1]
        thr_p = float(np.quantile(clf.predict_proba(Xr[st['keep_cur']])[:, 1], SCREEN_P_Q))
        d = Xr.shape[1] // 3
        R = Xr[:, :d]
        thr_sim = float(np.quantile(scoring.knn_sim_to(R, R, exclude_self=True), SCREEN_SIM_Q))
        sim2 = scoring.knn_sim_to(X2[:, :d], R)
        ok = (p2 <= thr_p) & (sim2 >= thr_sim)
        out.update(thr_p=round(thr_p, 4), thr_sim=round(thr_sim, 4),
                   n_low_sim=int((sim2 < thr_sim).sum()), n_high_p=int((p2 > thr_p).sum()),
                   **{'pass': [n for n, k in zip(names, ok) if k]})
    _screen_cache['key'], _screen_cache['val'] = key, out
    return out


@curate_bp.route('/api/screen', methods=['GET'])
@login_required
def api_screen():
    """?dir=image2 → 계산 중이면 {running, progress}, 끝났으면 1차 분류 결과(통과 목록 = image2 기준 상대경로)."""
    if request.args.get('dir') not in SCREEN_DIRS:
        return jsonify({'error': 'invalid dir'}), 400
    if _screen['running']:
        return jsonify({'running': True, 'progress': _screen['phase'] or _screen_progress()})
    if _screen['error']:
        return jsonify({'running': False, 'error': _screen['error']}), 500
    r = _screen['result']
    if r is None:
        return jsonify({'running': False, 'error': '분류 결과 없음 — 다시 실행하세요'}), 409
    return jsonify(dict({k: v for k, v in r.items() if k != 'pass'}, running=False, n_pass=len(r['pass'])))


@curate_bp.route('/api/screen/move', methods=['GET', 'POST'])
@login_required
def api_screen_move():
    """POST: 직전 분류의 통과분을 백그라운드로 move 로 옮긴다. GET: 진행 상황."""
    if request.method == 'POST':
        with _screen_lock:
            r = _screen['result']
            if _screen['running'] or _screen_move['running']:
                return jsonify({'error': '이미 실행 중'}), 409
            if not r or not r['pass']:
                return jsonify({'error': '옮길 통과 이미지 없음 — 분류를 다시 실행하세요'}), 409
            names = list(r['pass'])
            _screen_move.update(running=True, total=len(names), moved=0, fail=[], error=None)
        threading.Thread(target=_screen_move_worker, args=(names,), name='curate-screen-move', daemon=True).start()
    return jsonify(dict(_screen_move, fail=_screen_move['fail'][:50], n_fail=len(_screen_move['fail'])))


@curate_bp.route('/api/screen/run', methods=['POST'])
@login_required
def api_screen_run():
    """image2 특징 계산(바뀐/새 파일만)을 백그라운드로 시작한다."""
    if (request.get_json(silent=True) or {}).get('dir') not in SCREEN_DIRS:
        return jsonify({'error': 'invalid dir'}), 400
    if not _kick_screen():
        return jsonify({'error': _screen['error']}), 503
    return jsonify({'running': True})
