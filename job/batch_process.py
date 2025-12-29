import subprocess


def renew_kiwoom_token_job():
    print('    ############################### renew_kiwoom_token ###############################')
    # # 명령어 조합
    # # Windows에서는 여러 명령을 &&로 연결하여 한 줄에 실행 가능
    # # venv 활성화 후 바로 실행
    # script_dir = r'C:\my-project\random-player'
    # venv_activate = r'venv\Scripts\activate'
    # py_script = r'python utils\renew_kiwoom_token.py'
    #
    # # 전체 명령어 (venv 활성화 → 스크립트 실행)
    # # 주의: activate.bat는 cmd에서만 인식, powershell은 다름
    # cmd = f'cmd /c "cd /d {script_dir} && {venv_activate} && {py_script} && exit"'
    #
    # # subprocess 실행 (새로운 프로세스)
    # process = subprocess.Popen(
    #     [venv_python, py_script],
    #     # creationflags=subprocess.CREATE_NEW_CONSOLE,   # 새 콘솔창에서 실행!
    #     stdout=subprocess.PIPE,
    #     stderr=subprocess.PIPE,
    #     text=True,
    #     shell=True,   # &&, cd, activate.bat 같은 셸 내장/배치 기능을 쓰려면 필요
    #     encoding="cp949",
    #     errors="ignore"   # 디코딩 안되는 문자 무시
    # )

    venv_python = r"C:\my-project\random-player\venv\Scripts\python.exe"
    py_script = r"C:\my-project\random-player\utils\renew_kiwoom_token.py"

    # subprocess 실행 (새로운 프로세스), subprocess.Popen()은 어느 스레드에서 호출하든 OS에 “새 프로세스 생성”을 요청
    process = subprocess.Popen(
        [venv_python, "-u", "-X", "utf8", py_script],  #  UTF-8 강제하면 이모지 출력 가능 // -u 붙여서 자식 파이썬을 unbuffered로 실행 > 출력이 PIPE를 타지 않고 버퍼에 쌓이지 않아 바로 출력됨
        cwd=r"C:\my-project\random-player",   # 자식 프로세스의 현재 작업 디렉토리(working directory) 를 지정
        stdout=subprocess.PIPE,               # 주석하면 자식 프로세스의 출력이 “파이프로 캡처되지 않고” 그냥 기본 출력 스트림으로 흘러간다
        stderr=subprocess.STDOUT,             # stderr도 stdout으로 합치기(편함)
        text=True,
        encoding="utf-8",                     # 부모도 UTF-8로 읽기
        errors="replace",                     # ignore 대신 replace 추천(문제 보이게)
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="")   # 실시간 콘솔 출력

    process.wait()
    if process.returncode != 0:
        print("returncode =", process.returncode)


def run_crawl_ai_image():
    print('    ############################### run_crawl_ai_image ###############################')
    venv_python = r"C:\my-project\random-player\venv\Scripts\python.exe"
    # py_script = r"C:\my-project\random-player\utils\scrap_ai_by_playwright.py"
    py_script = r"C:\my-project\random-player\utils\scrap_ai_by_playwright_async.py"

    # subprocess 실행 (새로운 프로세스)
    process = subprocess.Popen(
        [venv_python, "-u", "-X", "utf8", py_script],  #  UTF-8 강제하면 이모지 출력 가능
        cwd=r"C:\my-project\random-player",   # 자식 프로세스의 현재 작업 디렉토리(working directory) 를 지정
        stdout=subprocess.PIPE,               # 주석하면 자식 프로세스의 출력이 “파이프로 캡처되지 않고” 그냥 기본 출력 스트림으로 흘러간다
        stderr=subprocess.STDOUT,             # stderr도 stdout으로 합치기(편함)
        text=True,
        encoding="utf-8",                     # 부모도 UTF-8로 읽기
        errors="replace",                     # ignore 대신 replace 추천(문제 보이게)
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="")   # 실시간 콘솔 출력

    process.wait()
    print("returncode =", process.returncode)

def run_crawl_ig_image():
    print('    ############################### run_crawl_ig_image ###############################')
    venv_python = r"C:\my-project\random-player\venv\Scripts\python.exe"
    # py_script = r"C:\my-project\random-player\utils\scrap_ai_by_playwright.py"
    py_script = r"C:\my-project\random-player\utils\scrap_ig_playwrigit.py"

    # subprocess 실행 (새로운 프로세스)
    process = subprocess.Popen(
        [venv_python, "-u", "-X", "utf8", py_script],  #  UTF-8 강제하면 이모지 출력 가능
        cwd=r"C:\my-project\random-player",   # 자식 프로세스의 현재 작업 디렉토리(working directory) 를 지정
        stdout=subprocess.PIPE,               # 주석하면 자식 프로세스의 출력이 “파이프로 캡처되지 않고” 그냥 기본 출력 스트림으로 흘러간다
        stderr=subprocess.STDOUT,             # stderr도 stdout으로 합치기(편함)
        text=True,
        encoding="utf-8",                     # 부모도 UTF-8로 읽기
        errors="replace",                     # ignore 대신 replace 추천(문제 보이게)
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="")   # 실시간 콘솔 출력

    process.wait()
    print("returncode =", process.returncode)


'''
cd /d C:\my-project\AutoSales.py
venv\Scripts\activate
python multi_kor_stocks.py
'''
def predict_stock_graph(stock):
    print(f'    ############################### predict_stock_graph : {stock} ###############################')
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    if stock == 'kospi':
        py_script = r"C:\my-project\AutoSales.py\multi_kor_stocks.py"
    if stock == 'nasdaq':
        py_script = r"C:\my-project\AutoSales.py\new_nasdaq_multi.py"

    # subprocess 실행 (새로운 프로세스)
    process = subprocess.Popen(
        [venv_python, "-u", "-X", "utf8", py_script],  #  UTF-8 강제하면 이모지 출력 가능
        cwd=r"C:\my-project\AutoSales.py",   # 자식 프로세스의 현재 작업 디렉토리(working directory) 를 지정
        stdout=subprocess.PIPE,               # 주석하면 자식 프로세스의 출력이 “파이프로 캡처되지 않고” 그냥 기본 출력 스트림으로 흘러간다
        stderr=subprocess.STDOUT,             # stderr도 stdout으로 합치기(편함)
        text=True,
        encoding="utf-8",                     # 부모도 UTF-8로 읽기
        errors="replace",                     # ignore 대신 replace 추천(문제 보이게)
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="")   # 실시간 콘솔 출력

    process.wait()
    print("returncode =", process.returncode)


def update_interest_stocks():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\1_periodically_update_today_interest_stocks.py"

    # subprocess 실행 (새로운 프로세스)
    process = subprocess.Popen(
        [venv_python, "-u", "-X", "utf8", py_script],  #  UTF-8 강제하면 이모지 출력 가능
        cwd=r"C:\my-project\AutoSales.py",   # 자식 프로세스의 현재 작업 디렉토리(working directory) 를 지정
        stdout=subprocess.PIPE,               # 주석하면 자식 프로세스의 출력이 “파이프로 캡처되지 않고” 그냥 기본 출력 스트림으로 흘러간다
        stderr=subprocess.STDOUT,             # stderr도 stdout으로 합치기(편함)
        text=True,
        encoding="utf-8",                     # 부모도 UTF-8로 읽기
        errors="replace",                     # ignore 대신 replace 추천(문제 보이게)
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="")   # 실시간 콘솔 출력

    process.wait()
    if process.returncode != 0:
        print("returncode =", process.returncode)


def find_stocks():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\2_finding_stocks_with_increased_volume.py"

    # subprocess 실행 (새로운 프로세스)
    process = subprocess.Popen(
        [venv_python, "-u", "-X", "utf8", py_script],  #  UTF-8 강제하면 이모지 출력 가능
        cwd=r"C:\my-project\AutoSales.py",   # 자식 프로세스의 현재 작업 디렉토리(working directory) 를 지정
        stdout=subprocess.PIPE,               # 주석하면 자식 프로세스의 출력이 “파이프로 캡처되지 않고” 그냥 기본 출력 스트림으로 흘러간다
        stderr=subprocess.STDOUT,             # stderr도 stdout으로 합치기(편함)
        text=True,
        encoding="utf-8",                     # 부모도 UTF-8로 읽기
        errors="replace",                     # ignore 대신 replace 추천(문제 보이게)
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="")   # 실시간 콘솔 출력

    process.wait()
    print("find_stocks_returncode =", process.returncode)


def find_low_stocks():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\4_find_low_point.py"

    # subprocess 실행 (새로운 프로세스)
    process = subprocess.Popen(
        [venv_python, "-u", "-X", "utf8", py_script],  #  UTF-8 강제하면 이모지 출력 가능
        cwd=r"C:\my-project\AutoSales.py",   # 자식 프로세스의 현재 작업 디렉토리(working directory) 를 지정
        stdout=subprocess.PIPE,               # 주석하면 자식 프로세스의 출력이 “파이프로 캡처되지 않고” 그냥 기본 출력 스트림으로 흘러간다
        stderr=subprocess.STDOUT,             # stderr도 stdout으로 합치기(편함)
        text=True,
        encoding="utf-8",                     # 부모도 UTF-8로 읽기
        errors="replace",                     # ignore 대신 replace 추천(문제 보이게)
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="")   # 실시간 콘솔 출력

    process.wait()
    print("returncode =", process.returncode)


def update_stocks_daily():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\update_kor_stocks_periodically.py"

    # subprocess 실행 (새로운 프로세스)
    process = subprocess.Popen(
        [venv_python, "-u", "-X", "utf8", py_script],  #  UTF-8 강제하면 이모지 출력 가능
        cwd=r"C:\my-project\AutoSales.py",   # 자식 프로세스의 현재 작업 디렉토리(working directory) 를 지정
        stdout=subprocess.PIPE,               # 주석하면 자식 프로세스의 출력이 “파이프로 캡처되지 않고” 그냥 기본 출력 스트림으로 흘러간다
        stderr=subprocess.STDOUT,             # stderr도 stdout으로 합치기(편함)
        text=True,
        encoding="utf-8",                     # 부모도 UTF-8로 읽기
        errors="replace",                     # ignore 대신 replace 추천(문제 보이게)
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="")   # 실시간 콘솔 출력

    process.wait()
    print("returncode =", process.returncode)


def update_stock_data_daily():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\10_update_stock_data.py"

    # subprocess 실행 (새로운 프로세스)
    process = subprocess.Popen(
        [venv_python, "-u", "-X", "utf8", py_script],  #  UTF-8 강제하면 이모지 출력 가능
        cwd=r"C:\my-project\AutoSales.py",   # 자식 프로세스의 현재 작업 디렉토리(working directory) 를 지정
        stdout=subprocess.PIPE,               # 주석하면 자식 프로세스의 출력이 “파이프로 캡처되지 않고” 그냥 기본 출력 스트림으로 흘러간다
        stderr=subprocess.STDOUT,             # stderr도 stdout으로 합치기(편함)
        text=True,
        encoding="utf-8",                     # 부모도 UTF-8로 읽기
        errors="replace",                     # ignore 대신 replace 추천(문제 보이게)
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="")   # 실시간 콘솔 출력

    process.wait()
    print("returncode =", process.returncode)


def update_summary_stock_graph_daily():
    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\5_generate_interest_stocks_graph.py"

    # subprocess 실행 (새로운 프로세스)
    process = subprocess.Popen(
        [venv_python, "-u", "-X", "utf8", py_script],  #  UTF-8 강제하면 이모지 출력 가능
        cwd=r"C:\my-project\AutoSales.py",   # 자식 프로세스의 현재 작업 디렉토리(working directory) 를 지정
        stdout=subprocess.PIPE,               # 주석하면 자식 프로세스의 출력이 “파이프로 캡처되지 않고” 그냥 기본 출력 스트림으로 흘러간다
        stderr=subprocess.STDOUT,             # stderr도 stdout으로 합치기(편함)
        text=True,
        encoding="utf-8",                     # 부모도 UTF-8로 읽기
        errors="replace",                     # ignore 대신 replace 추천(문제 보이게)
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="")   # 실시간 콘솔 출력

    process.wait()
    print("returncode =", process.returncode)
