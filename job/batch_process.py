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
        [venv_python, py_script],
        cwd=r"C:\my-project\random-player",   # 자식 프로세스의 현재 작업 디렉토리(working directory) 를 지정
        stdout=subprocess.PIPE,               # 주석하면 자식 프로세스의 출력이 “파이프로 캡처되지 않고” 그냥 기본 출력 스트림으로 흘러간다
        stderr=subprocess.STDOUT,             # stderr도 stdout으로 합치기(편함)
        text=True,
        encoding="cp949",
        errors="ignore",                      # 디코딩 안되는 문자 무시
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="")   # 실시간 콘솔 출력

    process.wait()
    print("returncode =", process.returncode)


def run_crawl_ai_image():
    print('    ############################### run_crawl_image ###############################')
    # # 명령어 조합
    # # Windows에서는 여러 명령을 &&로 연결하여 한 줄에 실행 가능
    # # venv 활성화 후 바로 실행
    # script_dir = r'C:\my-project\random-player'
    # venv_activate = r'venv\Scripts\activate'
    # py_script = r'python utils\crawl_image_by_playwright.py'
    #
    # # 전체 명령어 (venv 활성화 → 스크립트 실행)
    # # 주의: activate.bat는 cmd에서만 인식, powershell은 다름
    # cmd = f'cmd /c "cd /d {script_dir} && {venv_activate} && {py_script} && exit"'

    venv_python = r"C:\my-project\random-player\venv\Scripts\python.exe"
    py_script = r"C:\my-project\random-player\utils\crawl_image_by_playwright.py"

    # subprocess 실행
    process = subprocess.Popen(
        [venv_python, py_script],
        cwd=r"C:\my-project\random-player",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="cp949",
        errors="ignore"
    )
    stdout, stderr = process.communicate(timeout=60)


'''
cd /d C:\my-project\AutoSales.py
venv\Scripts\activate
python multi_kor_stocks.py
'''
def predict_stock_graph(stock):
    print(f'    ############################### predict_stock_graph : {stock} ###############################')
    script_dir = r'C:\my-project\AutoSales.py'
    venv_activate = r'venv\Scripts\activate'
    if stock == 'kospi':
        py_script = r'python multi_kor_stocks.py'
    if stock == 'nasdaq':
        py_script = r'python new_nasdaq_multi.py'

    # 전체 명령어 (venv 활성화 → 스크립트 실행)
    # 주의: activate.bat는 cmd에서만 인식, powershell은 다름
    cmd = f'cmd /c "cd /d {script_dir} && {venv_activate} && {py_script} && exit"'

    # subprocess 실행
    process = subprocess.Popen(
        cmd,
        # stdout=subprocess.PIPE, # 버퍼가 꽉 차서 죽는다 ? > 서브프로세스(=실행된 명령)의 표준출력(stdout)이 '파이썬 부모 프로세스'로 파이프로 전달
        # stderr=subprocess.PIPE,
        text=True,
        shell=True,
        encoding='utf-8',
        errors="ignore" # 디코딩 안되는 문자 무시
    )
    # stdout, stderr = process.communicate(timeout=60) # 버퍼를 읽어줘야 죽지 않는다
    # print("STDOUT:", stdout)
    # print("STDERR:", stderr)

def find_stocks():
    script_dir = r'C:\my-project\AutoSales.py'
    venv_activate = r'venv\Scripts\activate'
    py_script = r'python 2_finding_stocks_with_increased_volume.py'

    cmd = f'cmd /c "cd /d {script_dir} && {venv_activate} && {py_script} && exit"'

    # subprocess 실행
    process = subprocess.Popen(
        cmd,
        text=True,
        shell=True,
        encoding='utf-8',
        errors="ignore" # 디코딩 안되는 문자 무시
    )

def find_low_stocks():
    script_dir = r'C:\my-project\AutoSales.py'
    venv_activate = r'venv\Scripts\activate'
    py_script = r'python 4_find_low_point.py'

    cmd = f'cmd /c "cd /d {script_dir} && {venv_activate} && {py_script} && exit"'

    # subprocess 실행
    process = subprocess.Popen(
        cmd,
        text=True,
        shell=True,
        encoding='utf-8',
        errors="ignore" # 디코딩 안되는 문자 무시
    )

def update_interest_stocks():
    # script_dir = r'C:\my-project\AutoSales.py'
    # venv_activate = r'venv\Scripts\activate'
    # py_script = r'python 1_periodically_update_today_interest_stocks.py'
    #
    # cmd = f'cmd /c "cd /d {script_dir} && {venv_activate} && {py_script} && exit"'
    #
    # # subprocess 실행
    # process = subprocess.Popen(
    #     cmd,
    #     text=True,
    #     shell=True,
    #     encoding='utf-8',
    #     errors="ignore" # 디코딩 안되는 문자 무시
    # )

    venv_python = r"C:\my-project\AutoSales.py\venv\Scripts\python.exe"
    py_script = r"C:\my-project\AutoSales.py\1_periodically_update_today_interest_stocks.py"

    # subprocess 실행 (새로운 프로세스)
    process = subprocess.Popen(
        [venv_python, py_script],
        cwd=r"C:\my-project\random-player",   # 자식 프로세스의 현재 작업 디렉토리(working directory) 를 지정
        stdout=subprocess.PIPE,               # 주석하면 자식 프로세스의 출력이 “파이프로 캡처되지 않고” 그냥 기본 출력 스트림으로 흘러간다
        stderr=subprocess.STDOUT,             # stderr도 stdout으로 합치기(편함)
        text=True,
        encoding="cp949",
        errors="ignore",                      # 디코딩 안되는 문자 무시
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="")   # 실시간 콘솔 출력

    process.wait()
    print("returncode =", process.returncode)

