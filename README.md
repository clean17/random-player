### 1. 가상환경 세팅
```bash
$ python -m venv venv
```
### 2. 가상환경 활성화
```bash
$ source venv/bin/activate 

$ source venv/Scripts/activate  # windows
```

### 2.5 다운받았을 경우 패키지 설치
```bash
$ pip freeze > requirements.txt # push

$ pip install -r requirements.txt # pull
```

### 3. flask 설치
```bash
$ pip install flask
```
### 4. 기타 디렉토리 생성
```bash
$ mkdir templates static
```
### 5. 애플리케이션 실행
```bash
python app.py
```

### 사용 방법
`config.ini` 파일을 생성 후 내부에 디렉토리를 지정한다
```
[settings]
video_directory = C:/[dirPath]
```

### encodeURIComponent
JavaScript의 내장 함수로 URI의 특정 구성 요소를 인코딩하여 안전하게 전달한다<br>
의미를 가지는 일부문자를 이스케이프한다

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