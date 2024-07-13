### 1. 가상환경 세팅
```bash
$ python -m venv venv
```
### 2. 가상환경 활성화
```bash
$ source venv/bin/activate 

$ source venv/Scripts/activate  # windows

$ venv\Scripts\activate.bat     # cmd
```

### 2-1. push 전 requirements.txt 생성
```bash
$ pip freeze > requirements.txt
```
### 2-2. pull 후 가상환경에 패키지 설치
```bash
$ pip install -r requirements.txt
```

### 3. 애플리케이션 실행
```bash
python run.py
```

### 가상환경 제거
```bash
rmdir /s /q venv # cmd
```
### pip upgrade
```bash
python -m pip install --upgrade pip
```

### 버전차이로 문제가 되는 패키지 재설치
```bash
pip uninstall ffmpeg-python
pip install ffmpeg-python
```

### 사용 방법
`config.ini` 파일을 생성 후 내부에 디렉토리를 지정한다
```
[settings]
secret_key = 
username = 
password = 

[directories]
video_directory1 =
video_directory2 = 
ffmpeg_directory = 

[paths]
ffmpeg_script_path = 
work_directory = 
```

### encodeURIComponent
JavaScript의 내장 함수로 URI의 특정 구성 요소를 인코딩하여 안전하게 전달한다<br>
의미를 가지는 일부문자를 이스케이프한다
```js
`/video/video/${encodeURIComponent(currentVideo)}?directory=${directory}`
```

### 인증서 생성
```bash
$ openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
```
```bash
Generating a RSA private key
................................................++++
........................................................................................++++
writing new private key to 'key.pem'
-----
You are about to be asked to enter information that will be incorporated
into your certificate request.
What you are about to enter is what is called a Distinguished Name or a DN.
There are quite a few fields but you can leave some blank
For some fields there will be a default value,
If you enter '.', the field will be left blank.
-----
Country Name (2 letter code) [AU]:
State or Province Name (full name) [Some-State]:
Locality Name (eg, city) []:
Organization Name (eg, company) [Internet Widgits Pty Ltd]:
Organizational Unit Name (eg, section) []:
Common Name (e.g. server FQDN or YOUR name) []:
Email Address []:
```