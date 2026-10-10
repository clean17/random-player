# -*- coding: utf-8 -*-
"""파일 본문 전송을 nginx 에 넘긴다 (X-Accel-Redirect, 2026-10-10).

왜: waitress 는 send_file 응답의 본문을 이벤트 루프 스레드 1개가 파일을 읽어가며 보낸다
(waitress/task.py 의 write_soon → channel._flush_some). 갤러리 파일 대부분이 \\\\wsl.localhost\\...
(Docker Desktop 볼륨)라 읽기 한 번이 멈추면 그동안 모든 응답이 같이 멈춰, 스크롤 중 이미지 15개가
한꺼번에 pending 되는 증상이 났다.

어떻게: Flask 는 로그인 확인·파일 결정만 하고 본문 없이 X-Accel-Redirect 헤더로 "이 파일을 보내라"고만
답한다. nginx 가 그 헤더를 보고 internal location 으로 내부 이동해 파일을 직접 보낸다. Range(206)·
If-None-Match/If-Modified-Since(304)·ETag 는 nginx 가 처리한다. Cache-Control·Content-Type 은 여기서
준 값이 그대로 나간다(nginx 가 파일 확장자로 다시 정하지 않는다 — 그래서 mimetype 을 직접 넣는다).

nginx.conf(443 server)와 짝:
    location /_files/igdata/ { internal; alias "//wsl.localhost/.../igdata/_data/"; }   ← settings['UNC_DIR']
    location /_files/temp/   { internal; alias "F:/merci_server_file_dir/"; }           ← settings['TEMP_IMAGE_DIR']
    location / { ... proxy_set_header X-Accel-Enabled 1; }
_ACCEL_ROOTS 를 바꾸면 nginx.conf 도 같이 바꿔야 한다.

X-Accel-Enabled 헤더가 없는 요청(nginx 를 안 거친 개발 서버 직접 접속 등)이나 위 루트 밖의 파일
(G:\\, X:\\ 영상 폴더, 주식 그래프 등)은 지금까지처럼 send_file 로 보낸다.
"""
import mimetypes
import os
from urllib.parse import quote

from flask import Response, abort, request, send_file
from werkzeug.security import safe_join

from config.config import settings

_ACCEL_ROOTS = [
    (settings['UNC_DIR'], '/_files/igdata/'),
    (settings['TEMP_IMAGE_DIR'], '/_files/temp/'),
]
_ROOTS_NORM = [(os.path.normcase(os.path.abspath(root)), prefix) for root, prefix in _ACCEL_ROOTS]

# Python 3.8 mimetypes 는 .webp 를 모른다
_EXTRA_TYPES = {'.webp': 'image/webp'}


def _accel_uri(path):
    """파일 경로 → nginx internal URI. 루트 밖이면 None."""
    full = os.path.abspath(path)
    norm = os.path.normcase(full)
    for root, prefix in _ROOTS_NORM:
        if norm.startswith(root + os.sep):
            # 대소문자는 원래 경로 그대로 쓴다(도커 볼륨은 대소문자를 구분할 수 있다)
            rel = full[len(root) + 1:].replace('\\', '/')
            # 한글·공백·#·%·?·+ 는 인코딩해야 nginx 가 파일명을 제대로 찾는다(헤더는 latin-1 만 허용)
            return prefix + quote(rel, safe='/')
    return None


def _mimetype(path):
    ext = os.path.splitext(path)[1].lower()
    return mimetypes.guess_type(path)[0] or _EXTRA_TYPES.get(ext) or 'application/octet-stream'


def send_file_accel(path, max_age=None, private=False, mimetype=None):
    """send_file(path, conditional=True, max_age=...) 대체. private=True 면 공용(프록시) 캐시를 막는다."""
    uri = _accel_uri(path) if request.headers.get('X-Accel-Enabled') == '1' else None
    if uri is None:
        resp = send_file(path, mimetype=mimetype, conditional=True, max_age=max_age)
    else:
        resp = Response(status=200, mimetype=mimetype or _mimetype(path))
        resp.headers['X-Accel-Redirect'] = uri
        # werkzeug send_file 과 같은 캐시 헤더: max_age 없으면 no-cache(조건부 재검증), 있으면 public + max-age
        if max_age:
            resp.cache_control.public = True
            resp.cache_control.max_age = max_age
        else:
            resp.cache_control.no_cache = True
    if private:
        resp.cache_control.public = None
        resp.cache_control.private = True
    return resp


def send_from_directory_accel(directory, filename, max_age=None, private=False):
    """send_from_directory 대체 — 경로 검증(safe_join)과 없는 파일 404 는 send_from_directory 와 같다."""
    path = safe_join(os.fspath(directory), os.fspath(filename))
    if path is None or not os.path.isfile(path):
        abort(404)
    return send_file_accel(path, max_age=max_age, private=private)
