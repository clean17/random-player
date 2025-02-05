import logging
import io
import os
import re
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler

# stdout과 stderr 인코딩을 강제로 UTF-8로 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# sys.stdout.reconfigure(encoding='utf-8')
# sys.stderr.reconfigure(encoding='utf-8')

# sys.stdout과 sys.stderr를 UTF-8로 설정
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')


class ColorFormatter(logging.Formatter):
    """모든 ANSI 색상 코드 제거"""

    ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def format(self, record):
        log_message = super().format(record)
        return self.ANSI_ESCAPE_RE.sub('', log_message)  # ANSI 색상 코드 제거


def setup_logging():
    """
    로그 설정을 초기화하는 함수
    """
    # 로그 디렉토리 생성
    os.makedirs("logs", exist_ok=True)

    # 1️⃣ 로거 설정
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 2️⃣ 로그 포맷 설정
    formatter = logging.Formatter("### %(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # 3️⃣ 콘솔 핸들러 (터미널 출력)
    console_handler = logging.StreamHandler(sys.stdout) # 설정하지 않으면 sys.stderr(표준 에러 스트림)에 로그를 출력, error.log
    console_handler.setLevel(logging.DEBUG)  # 콘솔에서는 DEBUG부터 출력
    console_handler.setFormatter(formatter)

    # 4️⃣ 파일 핸들러 (날짜별 자동 로그 파일 관리)
    today_str = datetime.now().strftime("%y%m%d") # 오늘 날짜를 YYMMDD 형식으로 변환
    log_filename = f"logs/app_{today_str}.log"
    # file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler = TimedRotatingFileHandler(log_filename, when="midnight", interval=1, encoding="utf-8", backupCount=7)
    file_handler.setLevel(logging.INFO)  # 파일에는 INFO부터 저장
    # file_handler.setFormatter(formatter)
    console_formatter = ColorFormatter("### %(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(console_formatter)

    # 5️⃣ 핸들러를 로거에 추가
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    # 6️⃣ 특정 모듈의 로그 레벨 조정

    # logging.getLogger("werkzeug").setLevel(logging.INFO)  # Flask 기본 서버 로그
    werkzeug_logger = logging.getLogger("werkzeug")
    werkzeug_logger.setLevel(logging.INFO)

    # logging.getLogger("waitress").setLevel(logging.INFO)  # Waitress 로그
    waitress_logger = logging.getLogger('waitress')
    waitress_logger.setLevel(logging.INFO)
    # Waitress 로그를 root로 전파하지 않음 > file에 로그가 남지 않는다
    # waitress_logger.propagate = False

    if not waitress_logger.handlers:  # 핸들러가 없다면 추가
        waitress_logger.addHandler(console_handler)

    return logger

'''
Flask 내장 서버 - 코드 수정 시 자동 재시작, 부하처리 오류복구 기능 부족, threaded=True으로 멀티스레드 보장되지는 않는다, 개발용
Waitress 서버 - Python WSGI 서버, Waitress는 워커(프로세스)와 스레드 설정을 통해 병렬 처리를 훨씬 더 세밀하게 제어, IO 바운드 작업에서 성능을 극대화 >> 대규모 트래픽과 안정성

구분	        werkzeug	                        waitress
설명	        Flask의 기본 개발 서버	            WSGI 프로덕션 서버
용도	        개발 환경에서 테스트용 서버 실행	    프로덕션에서 안정적인 애플리케이션 실행
비동기 지원	    단일 스레드 (기본) / 멀티 스레드 가능	멀티 스레드 지원 (기본적으로 멀티 스레드)
성능	        낮음 (개발용)	                    높음 (프로덕션용)
배포 방식	    flask run 또는 app.run() 사용	    waitress-serve 명령어 사용
운영체제 지원	모든 OS	                            Windows, Linux, macOS
WSGI 표준	    WSGI 서버이지만 개발용	            완전한 WSGI 프로덕션 서버
'''
