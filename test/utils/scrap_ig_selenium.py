from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time

# --- 로그인 정보 ---
USERNAME = "fkaus015"   # 인스타 로그인 계정
PASSWORD = ""   # 비밀번호
TARGET_ACCOUNT = ""  # 스크랩할 계정

# --- 크롬 옵션 설정 ---
options = Options()
options.add_argument("--start-maximized")
# options.add_argument("--window-size=900,600")
options.add_argument("--disable-blink-features=AutomationControlled")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# --- 인스타그램 로그인 ---
driver.get("https://www.instagram.com/")
time.sleep(2)

# 아이디, 비밀번호 입력
driver.find_element(By.NAME, "username").send_keys(USERNAME)
driver.find_element(By.NAME, "password").send_keys(PASSWORD)
driver.find_element(By.NAME, "password").send_keys(Keys.RETURN)
time.sleep(5)

# --- 계정 검색 ---
search_url = f"https://www.instagram.com/{TARGET_ACCOUNT}/"
driver.get(search_url)
time.sleep(3)

# --- 스크롤 내려가며 게시물 로드 ---
SCROLL_PAUSE = 3
last_height = driver.execute_script("return document.body.scrollHeight")

post_links = set()

while True:
    # 현재 화면의 게시물 링크 수집
    anchors = driver.find_elements(By.TAG_NAME, "a")
    for a in anchors:
        href = a.get_attribute("href")
        if "/p/" in href or "/reel/" in href:  # 게시글/릴스 URL
            post_links.add(href)

    # 스크롤 내리기
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(SCROLL_PAUSE)

    new_height = driver.execute_script("return document.body.scrollHeight")
    if new_height == last_height:
        break
    last_height = new_height

print(f"총 {len(post_links)}개 게시글/릴스 링크 수집 완료")

# --- 각 게시글 접속해서 이미지/영상 src 추출 ---
media_urls = []

for link in list(post_links)[:10]:  # 테스트용: 처음 10개만
    driver.get(link)
    time.sleep(5)
    imgs = driver.find_elements(By.TAG_NAME, "img")
    videos = driver.find_elements(By.TAG_NAME, "video")

    for img in imgs:
        media_urls.append(img.get_attribute("src"))
    for v in videos:
        media_urls.append(v.get_attribute("src"))

print("수집된 미디어:", media_urls)

driver.quit()
