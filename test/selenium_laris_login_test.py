from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException

URL = 'http://192.168.60.101:8080/'
USER = 'laris_system'
PW   = '!Pass9900'

opts = Options()
# opts.add_argument('--headless=new')  # 먼저 눈으로 확인하고 나중에 켜세요
opts.add_argument('--window-size=1920,1080')   # headless 시 권장
opts.add_argument('--start-maximized')
opts.add_experimental_option("detach", True)

driver = webdriver.Chrome(options=opts)
wait = WebDriverWait(driver, 15)

driver.get(URL)

# 폼 요소 대기
wait.until(EC.presence_of_element_located((By.ID, 'txtUsername')))
wait.until(EC.presence_of_element_located((By.ID, 'txtPassword')))
wait.until(EC.presence_of_element_located((By.ID, 'btnLogin')))

driver.find_element(By.ID, 'txtUsername').clear()
driver.find_element(By.ID, 'txtUsername').send_keys(USER)
pwd = driver.find_element(By.ID, 'txtPassword')
pwd.clear()
pwd.send_keys(PW)

# 1) 오버레이가 있으면 사라질 때까지 대기
overlay = (By.CSS_SELECTOR, 'div.blockUI.blockOverlay')
try:
    # 오버레이가 잠깐 떴다가 사라지는 패턴 대비
    WebDriverWait(driver, 10).until(EC.invisibility_of_element_located(overlay))
except TimeoutException:
    pass  # 없어도 됨

# 2) 버튼을 화면 중앙으로 스크롤
btn = wait.until(EC.element_to_be_clickable((By.ID, 'btnLogin')))
driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)

# 3) 일반 클릭 → 가로막히면 JS 클릭 → 그래도 안되면 Enter 키
try:
    btn.click()
except ElementClickInterceptedException:
    try:
        driver.execute_script("arguments[0].click();", btn)
    except Exception:
        pwd.send_keys(Keys.ENTER)  # 폼 submit이 연결되어 있으면 Enter로도 로그인됨

# (선택) 로그인 완료의 신호가 되는 요소/URL/타이틀로 대기
wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
print("title:", driver.title)
