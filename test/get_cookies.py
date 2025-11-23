import http.cookiejar
import urllib.request

# 파일 경로 지정
file_path = 'D:\cookies.txt'

# 쿠키 저장을 위한 객체 생성
cookie_jar = http.cookiejar.MozillaCookieJar(file_path)

# 쿠키 핸들러를 이용한 opener 생성
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

# 웹 페이지 접속
response = opener.open('https://www.naver.com/')

# 쿠키를 파일로 저장
cookie_jar.save(ignore_discard=True, ignore_expires=True)