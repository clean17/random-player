# -*- coding: utf-8 -*-
"""갤러리 썸네일 증분 생성 — <base_dir>/thumb/<상대경로(확장자 뺌)>.webp, 가로 640px.

왜: /image/images(app/image.py get_image)는 thumb/ 에 같은 이름의 .webp 가 있으면 그걸 보내고
없으면 원본을 보낸다. 썸네일이 없으면 원본이 그대로 나가 느리다(utils/image_thumbs_dryrun.py 결과:
대상 약 24,500장, 원본 14GB → 썸네일 약 2.3GB).

증분 동작(스케줄러로 매일 돌려도 안전):
  - 썸네일이 이미 있고 원본보다 새로우면 건너뛴다(원본이 바뀌었으면 다시 만든다).
  - 만들 필요가 없다고 판단한 파일(이미 작음 / 애니메이션 / 썸네일이 원본보다 큼 / 열기 실패)은
    logs/job/image_thumbs_skip_<폴더이름>.json 에 (mtime, size, 사유)로 기억해 다음 실행에서 파일을 다시 열지 않는다.
    원본이 바뀌면(mtime/size 불일치) 다시 판단한다.
  - 같은 폴더에서 이름이 같고 확장자만 다른 파일(a.jpg / a.png)은 thumb/a.webp 하나로 충돌해
    서로 다른 그림이 뒤바뀌어 보이므로 둘 다 썸네일을 만들지 않고, 이미 있던 충돌 썸네일은 지운다.
  - 최근 10분 안에 수정된 파일은 아직 쓰는 중일 수 있어 다음 실행으로 미룬다.
  - 쓰기는 임시 파일(.webp.tmp)에 쓴 뒤 os.replace 로 교체해, 중간에 끊겨도 깨진 webp 를 서버가 보내지 않는다.
  - max_seconds 를 넘기면 남은 것은 다음 실행으로 미룬다(첫 실행은 수만 장이라 며칠에 걸쳐도 된다).
  - 영상(mp4/webm 등)과 애니메이션 gif/webp 는 만들지 않는다 — thumb 이 있으면 서버가 그걸 우선
    보내므로 첫 프레임 정지 이미지가 나가 애니메이션이 깨진다.

사용:
    스케줄러: job/batch_runner.py 의 image_thumbs_daily (매일 05:00, cpu 프로세스 풀)
    수동(venv 필수):  PYTHONIOENCODING=utf-8 venv/Scripts/python.exe utils/image_thumbs.py [--only move] [--dry-run]
    쓰기 없이 규모만 보려면 utils/image_thumbs_dryrun.py (표본 변환으로 용량·시간 추정)
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PIL import Image, ImageOps

Image.MAX_IMAGE_PIXELS = 250_000_000   # 초대형 이미지도 열어 보되, 그 이상은 실패로 기록

THUMB_WIDTH = 640
QUALITY = 80
SMALL_BYTES = 100 * 1024       # 파일이 이 크기 이하면 가로와 무관하게 썸네일 불필요(원본을 그대로 보낸다)
RECENT_SEC = 600               # 이 시간 안에 수정된 파일은 다음 실행으로 미룬다

IMG_EXT = {'.jpg', '.jpeg', '.jfif', '.png', '.webp', '.bmp', '.gif'}
VIDEO_EXT = {'.mp4', '.webm', '.mov', '.mkv', '.avi'}
EXCLUDE_EXT = {'.zip', '.ini', '.identifier'}   # app/image.py EXCLUDE_SUFFIXES 와 같은 의미

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_PATH = os.path.join(_PROJECT_ROOT, 'logs', 'job', 'image_thumbs.log')


def _log(msg: str) -> None:
    line = f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} [image_thumbs] {msg}'
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        with open(_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def thumb_path(base: str, rel: str) -> str:
    """app/image.py get_image 가 찾는 경로와 같다: <base>/thumb/<rel 확장자 뺌>.webp"""
    return os.path.join(base, 'thumb', os.path.splitext(rel)[0] + '.webp')


VIDEO_THUMB_SUBDIR = 'video_poster'   # 영상 썸네일은 thumb/ 아래 이 하위 폴더에 둔다


def video_thumb_path(base: str, rel: str) -> str:
    """영상 썸네일 경로: <base>/thumb/video_poster/<rel 확장자 뺌>.webp
    이미지 썸네일(thumb_path)과 폴더를 나눈 이유 — 같은 폴더의 a.jpg 와 a.mp4 가 thumb/a.webp 하나로 충돌해
    get_image 가 이미지 자리에 영상 프레임을 보내는 걸 막는다. thumb/ 아래라 이미지 스캔(scan_images)은 건너뛴다."""
    return os.path.join(base, 'thumb', VIDEO_THUMB_SUBDIR, os.path.splitext(rel)[0] + '.webp')


def probe(path: str) -> Tuple[int, int, bool, Optional[str]]:
    """헤더만 열어 (가로, 세로, 애니메이션 여부, 오류). 오류가 있으면 앞의 값은 의미 없다."""
    try:
        with Image.open(path) as im:
            return im.width, im.height, bool(getattr(im, 'is_animated', False)), None
    except Exception as e:   # noqa: BLE001 — 손상 파일 등은 기록만 한다
        return 0, 0, False, f'{type(e).__name__}: {e}'[:120]


def make_thumb(path: str, width: int = THUMB_WIDTH, quality: int = QUALITY) -> bytes:
    """원본을 가로 width 로 줄인 webp 바이트(원본이 더 좁으면 축소 없이 재압축만)."""
    with Image.open(path) as im:
        if im.format == 'JPEG':
            im.draft('RGB', (width, max(1, round(im.height * width / max(im.width, 1)))))   # 디코딩 가속
        im = ImageOps.exif_transpose(im)
        if im.width > width:
            im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
        has_alpha = im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info)
        im = im.convert('RGBA' if has_alpha else 'RGB')
        buf = io.BytesIO()
        im.save(buf, 'WEBP', quality=quality, method=4)
        return buf.getvalue()


def make_video_thumb(src: str, dst: str, seeks: Tuple[float, ...] = (1.0, 0), width: int = THUMB_WIDTH,
                     timeout: int = 20) -> bool:
    """영상 한 프레임 → 가로 width webp(dst). ffmpeg 로 JPEG 한 장만 뽑고, 리사이즈·webp 변환은 make_thumb 이 한다.
    seeks: 앞에서부터 시도할 초 — 영상이 더 짧으면 프레임이 안 나오므로 다음 값(보통 0)으로 한 번 더 시도한다.
    중간 JPEG 는 -q:v 2 (재압축 열화 최소화), 쓰기는 임시 파일에 쓴 뒤 os.replace 로 교체한다."""
    frame = dst + '.frame.jpg'
    tmp = dst + '.tmp'
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        for ss in seeks:
            try:
                subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(ss), '-i', src,
                                '-frames:v', '1', '-q:v', '2', frame],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
            except Exception as e:   # noqa: BLE001 — 타임아웃·ffmpeg 없음
                _log(f'영상 프레임 추출 실패: {src} -> {e}')
                return False
            if os.path.exists(frame) and os.path.getsize(frame) > 0:
                break
        else:
            return False
        data = make_thumb(frame, width)
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, dst)
        return True
    except Exception as e:   # noqa: BLE001
        _log(f'영상 썸네일 변환 실패: {src} -> {type(e).__name__}: {e}')
        return False
    finally:
        for p in (frame, tmp):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass


def scan_images(base: str) -> List[Tuple[str, str, float, int]]:
    """(경로, 상대경로('/' 구분), mtime, 크기) 목록. thumb·origin(자르기 전 원본 백업) 폴더, 영상,
    제외 확장자는 건너뛴다."""
    out = []
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d.lower() not in ('thumb', 'origin')]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in IMG_EXT:
                continue
            p = os.path.join(root, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append((p, os.path.relpath(p, base).replace('\\', '/'), st.st_mtime, st.st_size))
    return out


def _write_atomic(tp: str, data: bytes) -> None:
    """임시 파일에 쓴 뒤 os.replace — 중간에 끊겨도 깨진 webp 를 서버가 보내지 않는다.
    임시 파일 이름에 pid·스레드를 넣어 배치(05:00)와 스크랩 직후 호출이 같은 파일을 동시에 써도 서로 덮지 않는다."""
    os.makedirs(os.path.dirname(tp), exist_ok=True)
    tmp = f'{tp}.{os.getpid()}.{threading.get_ident()}.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, tp)


def _is_fresh(tp: str, src: str) -> bool:
    """썸네일이 있고 원본보다 새로우면(수정시각 기준) 다시 만들 필요가 없다 — 배치(process_dir)의 '최신' 판정과 같다."""
    try:
        return os.path.getmtime(tp) >= os.path.getmtime(src)
    except OSError:
        return False


def move_thumb(src_path: str, src_base: str, dst_path: str, dst_base: str) -> str:
    """파일을 옮긴 뒤(dst_path 에 이미 있어야 한다) 썸네일도 따라 옮긴다 — 다시 만드는 것보다 훨씬 싸다.
    src_path 는 이미 없어도 된다(경로 계산에만 쓴다). 이미지는 thumb_path, 영상은 video_thumb_path 를 옮긴다.
    · 원래 썸네일이 있고 옮긴 파일보다 새로우면 → dst 쪽 같은 이름 썸네일을 지우고 옮긴다. 반환 'moved'
    · 없거나 낡았으면 → 낡은 건 지우고 dst 에서 ensure_thumb 로 만든다(작은 파일 등은 만들지 않는다). 'made'|'skip'|'fail'
    dst 에 있던 같은 이름 썸네일은 항상 지운다 — 새 파일의 것이 아니라 이전 파일의 잔재이기 때문이다."""
    try:
        ext = os.path.splitext(dst_path)[1].lower()
        if ext in VIDEO_EXT:
            tp_fn = video_thumb_path
        elif ext in IMG_EXT:
            tp_fn = thumb_path
        else:
            return 'skip'
        src_rel = os.path.relpath(src_path, src_base).replace('\\', '/')
        dst_rel = os.path.relpath(dst_path, dst_base).replace('\\', '/')
        src_tp, dst_tp = tp_fn(src_base, src_rel), tp_fn(dst_base, dst_rel)
        if os.path.exists(dst_tp):
            os.remove(dst_tp)
        if os.path.exists(src_tp):
            if _is_fresh(src_tp, dst_path):
                os.makedirs(os.path.dirname(dst_tp), exist_ok=True)
                shutil.move(src_tp, dst_tp)   # 같은 볼륨이면 이름만 바뀌고, 다른 볼륨이면 복사 후 삭제
                return 'moved'
            os.remove(src_tp)
        return ensure_thumb(dst_path, dst_base)
    except Exception as e:   # noqa: BLE001
        _log(f'move_thumb 실패 {src_path} -> {dst_path} — {type(e).__name__}: {e}'[:300])
        return 'fail'


def ensure_thumb(path: str, base: str, width: int = THUMB_WIDTH) -> str:
    """파일 하나의 썸네일을 바로 만든다(스크랩·업로드 직후 호출용). base = 갤러리 기준 폴더(IMAGE_DIR 등) —
    썸네일 경로가 base 기준 상대경로로 정해지므로(<base>/thumb/<rel>.webp) 계정 하위 폴더 파일도 갤러리가 찾는 자리에 생긴다.
    이미지는 thumb_path, 영상은 video_thumb_path 에 만들고 규칙은 배치(process_dir)와 같다.
    반환: 'made' | 'skip' | 'fail'. 예외를 던지지 않는다(썸네일 실패가 다운로드를 깨면 안 된다)."""
    try:
        rel = os.path.relpath(path, base).replace('\\', '/')
        if rel.startswith('..'):
            _log(f'ensure_thumb: base 밖의 파일이라 건너뜀 — {path}')
            return 'fail'
        ext = os.path.splitext(path)[1].lower()
        if ext in VIDEO_EXT:
            vtp = video_thumb_path(base, rel)
            if _is_fresh(vtp, path):
                return 'skip'
            return 'made' if make_video_thumb(path, vtp, width=width) else 'fail'
        if ext not in IMG_EXT:
            return 'skip'
        size = os.path.getsize(path)
        if size <= SMALL_BYTES:
            return 'skip'
        if _is_fresh(thumb_path(base, rel), path):
            return 'skip'
        _, _, animated, err = probe(path)
        if err:
            _log(f'ensure_thumb: 이미지 열기 실패 {rel} — {err}')
            return 'fail'
        if animated:
            return 'skip'
        data = make_thumb(path, width)
        if len(data) >= size:
            return 'skip'
        _write_atomic(thumb_path(base, rel), data)
        return 'made'
    except Exception as e:   # noqa: BLE001
        _log(f'ensure_thumb 실패 {path} — {type(e).__name__}: {e}'[:300])
        return 'fail'


def _skip_path(name: str) -> str:
    # ⚠️ 이미지 폴더(thumb 포함) 안에 두지 않는다 — IG 갤러리(get_subdir_and_reels_images)는 base 바로 아래의
    # 모든 하위 폴더를 계정 폴더로 보고 그 안의 파일을 목록에 올려서, thumb/.skip.json 이 깨진 이미지 칸으로 뜬다.
    return os.path.join(_PROJECT_ROOT, 'logs', 'job', f'image_thumbs_skip_{name}.json')


def _load_skip(name: str) -> Dict[str, list]:
    try:
        with open(_skip_path(name), 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_skip(name: str, state: Dict[str, list]) -> None:
    path = _skip_path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, path)


def _convert_one(item, base: str, width: int, deadline: float, dry_run: bool):
    """한 장 처리. (rel, 결과, 값) — 결과: made | skip(사유) | fail | deferred."""
    path, rel, mtime, size = item
    if time.time() > deadline:
        return rel, 'deferred', None
    _, _, animated, err = probe(path)
    if err:
        return rel, 'fail', err
    if animated:
        return rel, 'skip', 'animated'
    if size <= SMALL_BYTES:
        return rel, 'skip', 'small'
    if dry_run:
        return rel, 'made', 0
    try:
        data = make_thumb(path, width)
    except Exception as e:   # noqa: BLE001
        return rel, 'fail', f'{type(e).__name__}: {e}'[:120]
    if len(data) >= size:
        return rel, 'skip', 'larger'   # 원본이 더 작으면 원본을 그대로 보내는 편이 낫다
    _write_atomic(thumb_path(base, rel), data)
    return rel, 'made', len(data)


def process_dir(name: str, base: str, width: int = THUMB_WIDTH, workers: int = 3,
                deadline: float = float('inf'), dry_run: bool = False) -> Dict[str, int]:
    stats = {'files': 0, 'up_to_date': 0, 'made': 0, 'made_bytes': 0, 'orig_bytes': 0, 'skip_known': 0,
             'skip_small': 0, 'skip_animated': 0, 'skip_larger': 0, 'collide': 0, 'collide_removed': 0,
             'recent': 0, 'fail': 0, 'deferred': 0}
    if not os.path.isdir(base):
        _log(f'{name}: 폴더를 열 수 없어 건너뜀 — {base}')
        return stats

    items = scan_images(base)
    stats['files'] = len(items)

    # 이름 충돌: 같은 폴더·같은 이름(확장자만 다름)은 thumb/<이름>.webp 하나로 합쳐진다
    groups: Dict[Tuple[str, str], int] = {}
    for _, rel, _, _ in items:
        key = (os.path.dirname(rel).lower(), os.path.splitext(os.path.basename(rel))[0].lower())
        groups[key] = groups.get(key, 0) + 1

    state = _load_skip(name)
    live = {rel for _, rel, _, _ in items}
    new_state = {k: v for k, v in state.items() if k in live}   # 사라진 파일의 기록은 정리
    now = time.time()
    todo = []

    for item in items:
        path, rel, mtime, size = item
        key = (os.path.dirname(rel).lower(), os.path.splitext(os.path.basename(rel))[0].lower())
        tp = thumb_path(base, rel)
        if groups[key] > 1:
            stats['collide'] += 1
            if os.path.exists(tp):          # 충돌이 생기기 전에 만든 썸네일은 누구 것인지 알 수 없다
                if not dry_run:
                    try:
                        os.remove(tp)
                        stats['collide_removed'] += 1
                    except OSError:
                        pass
            continue
        try:
            tmt = os.stat(tp).st_mtime
        except OSError:
            tmt = None
        if tmt is not None and tmt >= mtime:
            stats['up_to_date'] += 1
            continue
        rec = new_state.get(rel)
        if rec and abs(rec[0] - mtime) < 1e-6 and rec[1] == size:
            stats['skip_known'] += 1
            continue
        if now - mtime < RECENT_SEC:
            stats['recent'] += 1
            continue
        todo.append(item)

    if todo:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            results = list(pool.map(lambda it: _convert_one(it, base, width, deadline, dry_run), todo))
        meta = {it[1]: it for it in todo}
        for rel, res, val in results:
            _, _, mtime, size = meta[rel]
            if res == 'made':
                stats['made'] += 1
                stats['made_bytes'] += val
                stats['orig_bytes'] += size
            elif res == 'skip':
                stats['skip_' + val] += 1
                new_state[rel] = [mtime, size, val]
            elif res == 'fail':
                stats['fail'] += 1
                new_state[rel] = [mtime, size, 'fail: ' + str(val)]
                _log(f'{name}: 변환 실패 {rel} — {val}')
            else:
                stats['deferred'] += 1

    if not dry_run and new_state != state:
        try:
            _save_skip(name, new_state)
        except OSError as e:
            _log(f'{name}: skip 기록 저장 실패 — {e}')
    return stats


def run_image_thumbs_job(dirs: Optional[Dict[str, str]] = None, width: int = THUMB_WIDTH, workers: int = 3,
                         max_seconds: float = 2 * 3600, dry_run: bool = False) -> Dict[str, Dict[str, int]]:
    """스케줄러/CLI 공용 진입점. dirs = {이름: base_dir}. None 이면 settings 에서 읽는다(CLI 용)."""
    if dirs is None:
        sys.path.insert(0, _PROJECT_ROOT)
        from config.config import settings
        keys = {'image': 'IMAGE_DIR', 'image2': 'IMAGE_DIR2', 'cos': 'COS_DIR', 'move': 'MOVE_DIR',
                'refine': 'REF_IMAGE_DIR'}
        dirs = {n: settings.get(k) for n, k in keys.items()}
    dirs = {n: p for n, p in dirs.items() if p}

    t0 = time.time()
    deadline = t0 + max_seconds
    _log(f'시작 width={width} workers={workers} 제한 {max_seconds / 60:.0f}분 dry_run={dry_run} 폴더 {list(dirs)}')
    total: Dict[str, Dict[str, int]] = {}
    for name, base in dirs.items():
        s = process_dir(name, base, width, workers, deadline, dry_run)
        total[name] = s
        _log(f'{name}: 파일 {s["files"]:,} | 최신 {s["up_to_date"]:,} | 생성 {s["made"]:,} '
             f'(원본 {s["orig_bytes"] / 1048576:,.0f}MB → {s["made_bytes"] / 1048576:,.0f}MB) | '
             f'제외 기록 {s["skip_known"]:,} / 신규 제외 작음 {s["skip_small"]:,}·애니 {s["skip_animated"]:,}·'
             f'원본이작음 {s["skip_larger"]:,} | 이름충돌 {s["collide"]:,}(썸네일 삭제 {s["collide_removed"]:,}) | '
             f'작성중 {s["recent"]:,} | 실패 {s["fail"]:,} | 시간초과 이월 {s["deferred"]:,}')
    deferred = sum(s['deferred'] for s in total.values())
    _log(f'종료 {time.time() - t0:.0f}초' + (f' — 시간 제한으로 {deferred:,}장은 다음 실행으로 이월' if deferred else ''))
    return total


def main():
    ap = argparse.ArgumentParser(description='갤러리 썸네일 증분 생성')
    ap.add_argument('--only', default='', help='쉼표 구분: image,image2,cos,move,refine')
    ap.add_argument('--width', type=int, default=THUMB_WIDTH)
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--max-minutes', type=float, default=120)
    ap.add_argument('--dry-run', action='store_true', help='쓰기 없이 분류만(용량 추정 없음)')
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:   # noqa: BLE001
        pass
    only = {x.strip() for x in args.only.split(',') if x.strip()}
    dirs = None
    if only:
        sys.path.insert(0, _PROJECT_ROOT)
        from config.config import settings
        keys = {'image': 'IMAGE_DIR', 'image2': 'IMAGE_DIR2', 'cos': 'COS_DIR', 'move': 'MOVE_DIR',
                'refine': 'REF_IMAGE_DIR'}
        dirs = {n: settings.get(k) for n, k in keys.items() if n in only}
    run_image_thumbs_job(dirs, args.width, args.workers, args.max_minutes * 60, args.dry_run)


if __name__ == '__main__':
    main()
