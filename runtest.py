"""
import logging
from flask import Flask, request


# ✅ 로그 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger(__name__)

def create_app():
    app = Flask(__name__)

    @app.route('/')
    def index():
        logger.info(f"접속: {request.remote_addr} - {request.method} {request.path}") # 접속: 127.0.0.1 - GET /
        return '✅ Waitress 서버가 실행 중입니다!'

    return app
"""


# 0: werkzeug, 1: waitress
select_server = 0


if __name__ == '__main__':
    if select_server == 0: # werkzeug
        from app import create_app # Flask

        # ✅ 앱 인스턴스
        app = create_app()
        app.run(debug=False, host='127.0.0.1', port=8090,)

    if select_server == 1: # waitress 서버
        from waitress import serve
        from utils.wsgi_midleware import RequestLoggingMiddleware, logger
        from app import create_app

        app = create_app()
        app.wsgi_app = RequestLoggingMiddleware(app.wsgi_app)
        serve(app, host='127.0.0.1', port=8090, threads=12)


