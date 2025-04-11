import logging
from flask import Flask, request
from waitress import serve
from app import create_app
from utils.wsgi_midleware import RequestLoggingMiddleware, HopByHopHeaderFilter, ReverseProxied, logger

"""
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

# ✅ 앱 인스턴스
app = create_app()

if __name__ == '__main__':
    logger.info("🚀 Waitress 서버 시작 (http://127.0.0.1:8090)")

    serve(
        app,
        host='0.0.0.0',
        port=8090,
    )
