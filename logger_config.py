import logging
import logging.handlers
import queue
from threading import Thread
import io
import os
import re
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from concurrent_log_handler import ConcurrentRotatingFileHandler
from concurrent_log_handler import ConcurrentTimedRotatingFileHandler
import werkzeug
from werkzeug.serving import WSGIRequestHandler
import time
import threading

# sys.stdout과 sys.stderr를 UTF-8로 설정 (reconfigure: python 3.7부터 지원, hasattr: 3.6이하 안전하게)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

NO_LOGS_URLS = ["/image/images", "/video/videos/", "/static/", "/func/chat/save-file", "/func/logs/stream", "/video/temp-video/"]
HIDE_DETAIL_URLS = ["/image/move_image/image/", "/video/delete/"]

class WerkzeugLogFilter(logging.Filter):
    DATE_PATTERN = re.compile(r'\[\d{2}/[A-Za-z]{3}/\d{4} \d{2}:\d{2}:\d{2}\] ')

    def filter(self, record):
        record.msg = self.DATE_PATTERN.sub('', record.getMessage()).strip()
        record.args = ()  # 기존 args 제거 (포맷팅 오류 방지)
        return True

class ColorFormatter(logging.Formatter):
    """모든 ANSI 색상 코드 제거, log파일 색상정보 문자 제거용"""

    ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def format(self, record):
        log_message = super().format(record)
        return self.ANSI_ESCAPE_RE.sub('', log_message)  # ANSI 색상 코드 제거

class NoLogsFilter(logging.Filter):
    """ 특정 URL 패턴을 포함하는 로그를 필터링 """

    def __init__(self, patterns):
        super().__init__()
        if not isinstance(patterns, list):  # 리스트인지 확인
            raise TypeError(f"patterns should be a list, got {type(patterns)} instead.")
        self.patterns = patterns

    def filter(self, record):
        log_message = record.getMessage()
        if not isinstance(log_message, str):  # 로그 메시지가 문자열인지 확인
            return True
        return not any(pattern in log_message for pattern in self.patterns)

class HideDetailURLFilter(logging.Filter):
    """ 특정 URL 패턴 이후의 세부 정보를 숨기는 로그 필터 """

    def __init__(self, patterns):
        super().__init__()
        if not isinstance(patterns, list):  # 리스트인지 확인
            raise TypeError(f"patterns should be a list, got {type(patterns)} instead.")
        self.patterns = patterns

    def filter(self, record):
        log_message = record.getMessage()
        if not isinstance(log_message, str):  # 로그 메시지가 문자열인지 확인
            return True

        for pattern in self.patterns:
#             log_message = log_message.replace(pattern, pattern.rstrip('/') + '/[HIDDEN]')
            log_message = re.sub(f"{re.escape(pattern)}.*", pattern.rstrip('/') + '/[HIDDEN]', log_message)


        record.msg = log_message
        record.args = ()  # 기존 args 제거 (포맷팅 오류 방지)
        return True

log_dir = "logs"
current_date_str = None
file_handler = None
root_logger = None
listener = None
log_queue = queue.Queue()
formatting = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

def get_log_filename():
    today_str = datetime.now().strftime("%y%m%d") # 오늘 날짜를 YYMMDD 형식으로
    return f"logs/app_{today_str}.log"

def setup_logging():
    # 로그 디렉토리 생성
    os.makedirs("logs", exist_ok=True)

    global root_logger, file_handler, listener, log_queue, formatting

    # 기본 로거 설정
    root_logger = logging.getLogger() # root
    root_logger.setLevel(logging.INFO)

    werkzeug_logger = logging.getLogger("werkzeug") # Flask 기본 서버 로그
    waitress_logger = logging.getLogger("waitress") # Waitress 로그

    # 로그 포맷 설정
    formatter = logging.Formatter(formatting)

    # 콘솔 핸들러 정의 (터미널 출력)
    console_handler = logging.StreamHandler(sys.stdout) # 설정하지 않으면 sys.stderr(표준 에러 스트림)에 로그를 출력, error.log
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(WerkzeugLogFilter())

    # 파일 핸들러 (날짜별 자동 로그 파일 관리)
    log_filename = get_log_filename()
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    # file_handler = TimedRotatingFileHandler(log_filename, when="midnight", interval=1, encoding="utf-8", backupCount=7) # 시간 기준으로 회전, 단일 프로세스
    # file_handler = ConcurrentRotatingFileHandler(log_filename, maxBytes=5*1024*1024, encoding="utf-8", backupCount=7) # 크기 기준으로 회전, 동시성 지원
    # file_handler = ConcurrentTimedRotatingFileHandler(log_filename, when="midnight", interval=1, backupCount=7, encoding="utf-8", delay=False) # 시간 기준, 동시성
    file_handler.setLevel(logging.INFO)  # 파일에는 INFO부터 저장
    file_handler.setFormatter(ColorFormatter(formatting))
    file_handler.addFilter(WerkzeugLogFilter())

    """ 비동기 로깅 구현 > 멀티스레드/멀티프로세스 환경에서 로그 기록을 효율적으로 수행 """
    # 로그 메시지를 저장할 큐 생성
    # QueueHandler 생성 후 로거에 추가 (모든 로그를 큐로 보냄)
    queue_handler = logging.handlers.QueueHandler(log_queue)
    werkzeug_logger.addHandler(queue_handler)
    waitress_logger.addHandler(queue_handler) # root로거에 큐 핸들러를 추가하지 않으면 '.propagate = False' 를  설정할 필요가 없다
    # QueueListener: 백그라운드에서 로그 처리 (큐에서 로그 메시지를 하나씩 꺼내어 file_handler를 통해 파일에 기록)
    listener = logging.handlers.QueueListener(log_queue, file_handler)
    listener.start()

    # Flask 서버가 실행될 때 기본 요청 로그를 새 포맷으로 변경
    werkzeug_logger.addHandler(console_handler) # 기본 로깅 형태를 변경
    werkzeug_logger.setLevel(logging.INFO)
    werkzeug_logger.propagate = False # root로 전파하지 않는다
    werkzeug_logger.addFilter(NoLogsFilter(NO_LOGS_URLS))
    werkzeug_logger.addFilter(HideDetailURLFilter(HIDE_DETAIL_URLS))

    waitress_logger.addHandler(console_handler)
    waitress_logger.setLevel(logging.INFO)
    waitress_logger.propagate = False
    waitress_logger.addFilter(NoLogsFilter(NO_LOGS_URLS))
    waitress_logger.addFilter(HideDetailURLFilter(HIDE_DETAIL_URLS))

    return waitress_logger

def check_logger():
    global file_handler, current_date_str, listener, log_queue, formatting

    # 날짜 문자열
    new_date_str = datetime.now().strftime('%Y%m%d')

    # 날짜가 바뀌었으면 교체
    if new_date_str != current_date_str:
        if file_handler:
            file_handler.close()

        log_filename = get_log_filename()
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setLevel(logging.INFO)  # 파일에는 INFO부터 저장
        file_handler.setFormatter(ColorFormatter(formatting))
        file_handler.addFilter(WerkzeugLogFilter())

        if listener is not None:
            listener.stop()
        listener = logging.handlers.QueueListener(log_queue, file_handler)
        listener.start()

        current_date_str = new_date_str

# 백그라운드에서 날짜 변경 감지
def log_monitor():
    time.sleep(60)
    while True:
        check_logger()
        time.sleep(60)  # 매 60초마다 체크

# 로그 감시 쓰레드 시작
threading.Thread(target=log_monitor, daemon=True).start()

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
