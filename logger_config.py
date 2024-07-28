import logging

'''
127.0.0.1로 시작하는 로그 제거 필터링

class NoHTTPRequestLogFilter(logging.Filter):
    def filter(self, record):
        return not record.getMessage().startswith('127.0.0.1')

# 모든 로그 핸들러에 대해 필터 적용
for handler in app.logger.handlers:
    handler.addFilter(NoHTTPRequestLogFilter())
'''

# Create a logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('### %(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 전역 로거  (웹요청이 아닌 파이썬 내부 로그를 출력) - root
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(formatter)

# Create a file handler for logging
file_handler = logging.FileHandler('logs/app.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)




# APScheduler 로거
logging.getLogger('apscheduler.executors.default').setLevel(logging.WARNING)

# Flask가 내부적으로 사용하는 Werkzeug 서버 (app.run())
# Werkzeug 로거    --- app.run()
logging.getLogger('werkzeug').setLevel(logging.INFO)

# Waitress 로거    --- serve()
waitress_logger = logging.getLogger('waitress')
# Waitress 로그를 root로 전파하지 않음
# waitress_logger.propagate = False # 전파하지 않으면 file에 로그가 남지 않는다

if not waitress_logger.handlers:  # 핸들러가 없다면 추가
    waitress_logger.addHandler(console_handler)
    waitress_logger.setLevel(logging.INFO)