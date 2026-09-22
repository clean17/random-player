from config.logger_config import setup_logging
from werkzeug.middleware.proxy_fix import ProxyFix
from urllib.parse import unquote
from http.cookies import SimpleCookie
from config.config import settings

logger = setup_logging()
SUPER_USERNAME = settings['SUPER_USERNAME']

# 요청 로깅 미들웨어
class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app
        self.logger = logger

    def __call__(self, environ, start_response):
        # client_ip = environ.get("REMOTE_ADDR", "-")
        client_ip = (
                environ.get("HTTP_X_CLIENT_IP") or
                environ.get("HTTP_X_REAL_IP") or
                environ.get("REMOTE_ADDR", "-")
        ) # 프록시 전의 ip
        method = environ.get("REQUEST_METHOD")
        # 2026-09-23: PATH_INFO는 WSGI 스펙(PEP 3333)상 실제 요청 경로 바이트(UTF-8)를
        # latin-1로 디코딩한 문자열로 온다 — 한글 파일명이 섞인 경로(예: 관심종목 그래프
        # 이미지 /image/lgbm-stocks/...)가 로그에 mojibake(ì¼ì´ì¸ 류)로 찍히던 원인.
        # 실제 라우팅/파일서빙은 werkzeug가 내부적으로 알아서 복원해서 정상 동작하고
        # (200 응답), 이 로그 한 줄만 안 고쳐진 상태였다. latin-1로 되돌린 뒤 utf-8로
        # 다시 디코딩하면 원래 문자열이 복원된다 — ASCII만 있는 경로는 latin-1/utf-8에서
        # 바이트가 동일해 왕복해도 값이 안 바뀐다(기존 로그에 영향 없음). errors='replace'는
        # 혹시 경로 바이트가 UTF-8이 아닌 요청이 와도(스캐너 등) 로깅 자체가 죽지 않게 한다.
        path = environ.get("PATH_INFO")
        if path:
            try:
                path = path.encode('latin-1').decode('utf-8', errors='replace')
            except UnicodeEncodeError:
                pass   # 이미 정상 유니코드 문자열이면(latin-1 범위 밖 문자 포함) 그대로 둔다
        query_string = environ.get("QUERY_STRING", "")
        decoded_query = unquote(query_string)
        full_path = f"{path}?{decoded_query}" if decoded_query else path
        protocol = environ.get("SERVER_PROTOCOL", "-")

        # 🔹 1) 쿠키 파싱
        cookie_header = environ.get("HTTP_COOKIE", "")
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header)
        except Exception:
            cookie = SimpleCookie()

        # 🔹 2) remember_username 꺼내기 (없으면 '-')
        username = "-"
        if "username" in cookie:
            username = cookie["username"].value or "-"

        status_code = None

        # start_response를 감싸는 내부 함수를 정의합니다.
        def custom_start_response(status, response_headers, exc_info=None):
            nonlocal status_code
            # status는 예: "200 OK" 형태이므로, 공백을 기준으로 나누어 상태 코드만 추출합니다.
            status_code = status.split()[0]
            return start_response(status, response_headers, exc_info)

        # 원래 WSGI 애플리케이션을 custom_start_response를 사용해 호출합니다.
        result = self.app(environ, custom_start_response)

        # self.logger.info('%s - - "%s %s %s" %s ', client_ip, method, path, protocol, status_code)
        if username != SUPER_USERNAME:
            self.logger.info('%s - - %s "%s %s %s" %s', client_ip, username, method, full_path, protocol, status_code)

        return result

'''
Hop-by-Hop: HTTP/1.1 프로토콜에서 사용하는 헤더, 프록시나 게이트웨이 등을 거칠 때 제거되어야 하는 헤더
프록시나 게이트웨이를 통과하는 동안 다른 연결로 전달되지 않아야 한다

Connection, Keep-Alive, ...

서버-애플리케이션 인터페이스에서 사용하면 안된다
Hop-by-Hop 헤더를 제거하는 미들웨어
'''
class HopByHopHeaderFilter(object):
    hop_by_hop_headers = {
        'connection',
        'keep-alive',
        'proxy-authenticate',
        'proxy-authorization',
        'te',
        'trailer',
        'transfer-encoding',
        'upgrade',
    }
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        def custom_start_response(status, headers, exc_info=None):
            filtered_headers = [(key, value) for key, value in headers if key.lower() not in self.hop_by_hop_headers]
            return start_response(status, filtered_headers, exc_info)
        return self.app(environ, custom_start_response)

# nginx(ssl)를 추가하고 나서 아래 설정을 추가하면 /get_tasks의 _external=True가 https:// 로 이미지 경로를 생성한다
class ReverseProxied:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ['wsgi.url_scheme'] = 'https'  # HTTPS로 설정
        return self.app(environ, start_response)