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