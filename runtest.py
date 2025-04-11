import logging
from flask import Flask, request
from waitress import serve
from config.logger_config import get_active_loggers

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
        logger.info(f"접속: {request.remote_addr} - {request.method} {request.path}")
        return '✅ Waitress 서버가 실행 중입니다!'

    @app.route('/log-test')
    def log_test():
        logger.info("📘 /log-test 요청됨")
        return '로그 찍혔습니다!'

    return app

# ✅ 앱 인스턴스
app = create_app()

if __name__ == '__main__':
    active_loggers = get_active_loggers()
    for name, logger in active_loggers.items():
        if name == "waitress":
            print('waitress')
        if name == "werkzeug":
            print('werkzeug')

    logger.info("🚀 Waitress 서버 시작 (http://0.0.0.0:8090)")
    serve(
        app,
        host='0.0.0.0',
        port=8090,
        threads=6,
        max_request_body_size=1024 * 1024 * 1024 * 50
    )
