### 1. 가상환경 세팅
```bash
$ python -m venv venv
```
### 2. 가상환경 활성화
```bash
$ source venv/bin/activate 

$ source venv/Scripts/activate  # windows (git bash)

$ venv\Scripts\activate.bat     # cmd (windows terminal)
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
### nginx 서버
`https://nginx.org/en/download.html` 에서 zip 파일을 다운받고 푼다 <br>
`nginx.exe` 파일이 있는 위치에서 아래 명령어로 실행
```bash
start nginx
```
아래 명령어로 종료
```bash
nginx -s quit
```
아래 명령어로 재시작
```bash
nginx -s reload
```
절대 경로로 실행(git bash)
```bash
C:/nginx/nginx-1.26.2/nginx.exe &
C:/nginx/nginx-1.26.2/nginx.exe -s quit
C:/nginx/nginx-1.26.2/nginx.exe -s reload
```
실행 결과 <br>

![img.png](app/static/readme/img.png)
- Nginx와 Flask 연동 <br>
  Flask 애플리케이션이 8090 포트에서 실행중이라면
```bash
waitress-serve --port=80 run:app
```
- nginx 설정 수정 (`/conf/nginx.conf`) <br>
80 포트를 내부서버 8090으로 연결
```bash
server {
    listen 80;
    server_name localhost;

    location / {
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
### ssl 적용

생성한 `cert.pem`, `key.pem`을 `conf`디렉토리의 `ssl`디렉토리에 넣는다<br>
```bash
server {
    listen 443 ssl;  # 443 포트에서 SSL을 사용
    server_name yourdomain.com;  # 또는 localhost

    ssl_certificate     ssl/cert.pem;   # 인증서 파일 경로
    ssl_certificate_key ssl/key.pem;    # 키 파일 경로
    
    ssl_session_cache    shared:SSL:1m;
    ssl_session_timeout  5m;

    ssl_protocols       TLSv1 TLSv1.1 TLSv1.2;  # SSL 프로토콜 (최신 TLS 버전을 사용하는 것이 좋음)
    ssl_prefer_server_ciphers  on;
    ssl_ciphers         HIGH:!aNULL:!MD5;       # 보안 설정

    location / {
        try_files $uri $uri/ =404;
        root   html;
        index  index.html index.htm;
        proxy_pass http://127.0.0.1:8090;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

```

### 작업 스케줄러

작업 스케줄러 > 작업 만들기

![img_3.png](app/static/readme/img_3.png)

트리거 > 새로 만들기

![img_5.png](app/static/readme/img_5.png)

동작 > 새로 만들기

![img_1.png](app/static/readme/img_1.png) <br>
스크립트 `"C:\Program Files\Git\bin\bash.exe"` <br>
인수 `-c "cd /c/nginx/nginx-1.26.2 && ./nginx.exe &"`

마찬가지로 python 서버 자동 시작<br>

스크립트 `wt.exe
`<br>
인수 `new-tab -p "Command Prompt" -d C:\my-project\random-player cmd /k "venv\Scripts\activate && python run.py"`

### nginx 재기동
```bash
cd /c/nginx/nginx-1.26.2
# graceful 종료
./nginx.exe -s quit
# 즉시 종료
./nginx.exe -s stop
# 기동 (백그라운드)
start ./nginx.exe
# 재기동 
./nginx.exe -s reload
```
작업스케줄러를 통해 실행되었다면 직접 제거 후 재기동한다
```bash
# Nginx 프로세스를 확인
tasklist | findstr nginx
# Nginx 프로세스를 강제 종료
taskkill /F /IM nginx.exe
# pid 파일 삭제
cd ..\..\nginx\nginx-1.26.2\logs
del nginx.pid
```
### 병렬 작업 비교
![img_6.png](app/static/readme/img_6.png)
![img_11.png](app/static/readme/img_11.png)
### 멀티스레드, 멀티프로세스, asyncio I/O 처리 관점
![img_7.png](app/static/readme/img_7.png)
![img_8.png](app/static/readme/img_8.png)
![img_9.png](app/static/readme/img_9.png)
![img_10.png](app/static/readme/img_10.png)

## Redis 설치
Redis를 Windows 서비스로 설치
```cmd
redis-server --service-install redis.windows.conf --loglevel verbose
```
이미 설치가 되어 있는 경우 삭제 후 서비스 설치
```cmd
taskkill /f /im redis-server.exe
```
서비스 실행
```cmd
redis-server --service-start
```
서비스 동작 확인
```cmd
C:\Redis>sc query redis

SERVICE_NAME: redis
        종류               : 10  WIN32_OWN_PROCESS
        상태               : 4  RUNNING
                                (STOPPABLE, NOT_PAUSABLE, ACCEPTS_PRESHUTDOWN)
        WIN32_EXIT_CODE    : 0  (0x0)
        SERVICE_EXIT_CODE  : 0  (0x0)
        검사점             : 0x0
        WAIT_HINT          : 0x0
```
`redis-cli.exe` 실행 후 테스트
```cmd
127.0.0.1:6379> ping
PONG
```

## PostgreSQL 도입
도커에 설치하기 위해 먼저 Docker Desktop을 실행 후 이미지 다운로드
```bash
docker pull postgres
```
다운받은 이미지로 컨테이너 실행
```bash
docker run --name mypg -e POSTGRES_PASSWORD=dlsdn317! -p 5432:5432 -d postgres
```
Docker Desktop이 실행되면 자동으로 컨테이너 실행
```bash
docker run --name mypg -e POSTGRES_PASSWORD=dlsdn317! -p 5432:5432 -d --restart unless-stopped postgres
또는
docker update --restart unless-stopped mypg
```
bash로 진입
```bash
docker exec -it mypg /bin/bash
```
dbeaver로 간단한 연결<br>
![img.png](app/static/readme/img_12.png)
bash에서 psql로 PostgreSQL 접속
```bash
psql -U postgres
```
```sql
CREATE USER chick WITH PASSWORD 'password';
CREATE DATABASE mydb OWNER myuser;
```
데이터베이스 접속
```sql
\c mydb chick

\dt : 현재 DB의 테이블 목록 보기

\du : 유저 목록 보기

\q : psql 종료
```
문법 차이
```sql
ALTER TABLE users ADD login_attempt NUMERIC(1,0);
ALTER TABLE users ALTER COLUMN password TYPE VARCHAR(256);
ALTER TABLE users RENAME COLUMN login_id TO username;

SELECT conname FROM pg_constraint WHERE conrelid = 'chats'::regclass;
ALTER TABLE chats DROP CONSTRAINT chats_message_key;

SELECT setval('chats_id_seq', (SELECT MAX(id) FROM chats));
```

파이썬에서 db 연결
```bash
pip install psycopg-binary
```
(설치가 안되는 이슈가 있으면 윈도우에 PostgreSql을 설치하고 Path 에 bin 경로 추가 필요)