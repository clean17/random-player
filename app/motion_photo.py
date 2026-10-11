# -*- coding: utf-8 -*-
"""갤럭시 모션포토 → 브라우저에서 재생할 수 있는 mp4 (2026-10-11).

갤럭시 모션포토는 JPEG 한 파일 안에 짧은 영상(약 3초)이 같이 들어 있다:
    [JPEG 본문][게인맵 JPEG][...'MotionPhoto_Data'][MP4][SEF 트레일러(...'SEFT')]
XMP 에 GCamera:MotionPhoto="1" 과 Container:Directory 의 video/mp4 Item:Length 가 적혀 있다
(구글 Motion Photo v1 포맷 — 픽셀도 같은 XMP 를 쓰지만 MP4 가 파일 맨 끝에 붙고 SEF 가 없다).

- 판별: JPEG 세그먼트를 따라가 XMP(APP1)만 읽는다(_read_xmp). 2026-10-11 F:\\merci_server_file_dir 의
  JPG 12,684장 전수 확인: 'MotionPhoto_Data' 가 있는 파일과 XMP MotionPhoto="1" 파일이 정확히 일치했다.
- 내장 영상은 HEVC(1440x1080 등)라 HEVC 하드웨어 디코딩이 없는 PC 크롬에선 검은 화면이 된다.
  그래서 처음 요청될 때 H.264 + AAC(원본 해상도, 소리 포함) mp4 로 한 번 변환해 thumb/<이름>.motion-av.mp4 에 둔다.
  (처음엔 무음(-an)으로 thumb/<이름>.motion.mp4 에 만들었다 — 2026-10-11 소리 포함으로 바꾸면서 캐시 이름을 바꿔
  옛 무음 캐시를 쓰지 않게 했고, 브라우저 캐시는 프론트 URL 의 av=1 로 피한다(static/js/image.js motionVideoUrl).)
  thumb/ 는 갤러리 목록·썸네일 생성에서 이미 제외되는 폴더라 별도 예외 처리가 필요 없다.
"""
import os
import re
import subprocess
import threading
from typing import Dict, Optional, Tuple

_HEAD_BYTES = 256 * 1024
_XMP_MOTION = re.compile(rb'(?:Camera:MotionPhoto|Camera:MicroVideo)\s*=\s*"1"|Camera:MotionPhoto>1<')
_XMP_NS = b'http://ns.adobe.com/xap/1.0/\x00'
_SEF_MARKER = b'MotionPhoto_Data'
_MOTION_EXTS = ('.jpg', '.jpeg')
MOTION_SUFFIX = '.motion-av.mp4'            # 소리 포함 캐시
OLD_MOTION_SUFFIXES = ('.motion.mp4',)      # 무음 시절 캐시 — 사진 삭제 때 같이 지운다
_FFMPEG_TIMEOUT_SEC = 60

# (경로) -> ((mtime, size), 모션포토 여부). 페이지마다 같은 파일을 다시 읽지 않도록.
_detect_cache = {}  # type: Dict[str, Tuple[Tuple[float, int], bool]]
_build_locks = {}  # type: Dict[str, threading.Lock]
_build_locks_guard = threading.Lock()


def is_motion_photo(path):
    # type: (str) -> bool
    if not path.lower().endswith(_MOTION_EXTS):
        return False
    try:
        st = os.stat(path)
    except OSError:
        return False
    key = (st.st_mtime, st.st_size)
    hit = _detect_cache.get(path)
    if hit and hit[0] == key:
        return hit[1]
    try:
        xmp = _read_xmp(path)
        result = bool(xmp and _XMP_MOTION.search(xmp))
    except OSError:
        result = False
    _detect_cache[path] = (key, result)
    return result


def _read_xmp(path):
    # type: (str) -> Optional[bytes]
    """JPEG 세그먼트 헤더만 따라가 XMP(APP1) 본문만 읽는다. 갤러리 한 페이지가 수백 장이라
    파일마다 앞 256KB 를 통째로 읽지 않으려고(EXIF 썸네일 때문에 XMP 가 ~95KB 뒤에 있다)."""
    with open(path, 'rb') as f:
        if f.read(2) != b'\xff\xd8':
            return None
        while True:
            hdr = f.read(4)
            if len(hdr) < 4 or hdr[0] != 0xFF:
                return None
            marker = hdr[1]
            if marker == 0xDA or marker == 0xD9:   # SOS / EOI — 메타데이터 끝
                return None
            seg_len = int.from_bytes(hdr[2:4], 'big') - 2
            if seg_len < 0:
                return None
            if marker == 0xE1:
                body = f.read(seg_len)
                if body.startswith(_XMP_NS):
                    return body
            else:
                f.seek(seg_len, 1)


def _embedded_video_bytes(data):
    # type: (bytes) -> Optional[bytes]
    """모션포토 원본 바이트에서 내장 MP4 부분만 잘라낸다."""
    m = re.search(rb'Item:Mime="video/mp4"[^>]*?Item:Length="(\d+)"', data[:_HEAD_BYTES]) \
        or re.search(rb'Item:Length="(\d+)"[^>]*?Item:Mime="video/mp4"', data[:_HEAD_BYTES])
    length = int(m.group(1)) if m else 0

    # 1) 삼성: 'MotionPhoto_Data' 바로 뒤가 MP4, 그 뒤엔 SEF 트레일러가 붙는다
    pos = data.rfind(_SEF_MARKER)
    if pos != -1:
        start = pos + len(_SEF_MARKER)
        if data[start + 4:start + 8] == b'ftyp':
            return data[start:start + length] if length else data[start:]

    # 2) 구글 포맷(픽셀 등): MP4 가 파일 맨 끝 Item:Length 바이트
    if length and length < len(data):
        start = len(data) - length
        if data[start + 4:start + 8] == b'ftyp':
            return data[start:]

    # 3) 메타데이터가 어긋난 경우: JPEG 끝 이후 첫 'ftyp' 박스
    idx = data.find(b'ftypmp4', data.find(b'\xff\xd9'))
    if idx == -1:
        idx = data.find(b'ftypisom', data.find(b'\xff\xd9'))
    if idx >= 4:
        return data[idx - 4:]
    return None


def motion_video_path(src_path):
    # type: (str) -> str
    folder, name = os.path.split(src_path)
    return os.path.join(folder, 'thumb', os.path.splitext(name)[0] + MOTION_SUFFIX)


def _lock_for(path):
    # type: (str) -> threading.Lock
    with _build_locks_guard:
        lock = _build_locks.get(path)
        if lock is None:
            lock = _build_locks[path] = threading.Lock()
        return lock


def ensure_motion_video(src_path):
    # type: (str) -> Optional[str]
    """모션포토면 재생용 mp4 경로를 돌려준다(없으면 만든다). 모션포토가 아니거나 실패하면 None."""
    out = motion_video_path(src_path)
    try:
        if os.path.getmtime(out) >= os.path.getmtime(src_path):
            return out
    except OSError:
        pass
    if not is_motion_photo(src_path):
        return None

    with _lock_for(out):
        # 같은 파일을 동시에 요청한 다른 스레드가 먼저 만들었으면 그대로 쓴다
        if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(src_path):
            return out
        with open(src_path, 'rb') as f:
            data = f.read()
        video = _embedded_video_bytes(data)
        if not video:
            return None

        os.makedirs(os.path.dirname(out), exist_ok=True)
        raw = out + '.src.tmp'
        tmp = out + '.tmp.mp4'
        try:
            with open(raw, 'wb') as f:
                f.write(video)
            cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', raw,
                   '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                   '-c:a', 'aac', '-b:a', '128k',   # 소리 유지(2026-10-11 사용자 요청). 오디오 없는 영상이면 영상만 나온다
                   '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',   # yuv420p 는 짝수 크기만 허용
                   '-pix_fmt', 'yuv420p', '-movflags', '+faststart', tmp]
            r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               timeout=_FFMPEG_TIMEOUT_SEC,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if r.returncode != 0 or not os.path.exists(tmp):
                print(f'[WARN] motion photo transcode failed: {src_path}: '
                      f'{r.stderr.decode("utf-8", "replace")[:300]}')
                return None
            os.replace(tmp, out)
            return out
        except (OSError, subprocess.SubprocessError) as e:
            print(f'[WARN] motion photo extract failed: {src_path}: {e}')
            return None
        finally:
            for p in (raw, tmp):
                try:
                    os.remove(p)
                except OSError:
                    pass
