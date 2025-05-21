import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def fetch_url_preview_by_selenium(url):
    try:
        options = Options()
        options.add_argument("--headless")  # 창 없이 실행
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1280,800")  # (필수는 아님)

        driver = webdriver.Chrome(options=options)
        driver.get(url)

        # try:
        #     # og:image 또는 og:description이 DOM에 생성될 때까지 최대 N초 대기
        #     WebDriverWait(driver, 10).until(
        #         lambda d: d.find_element(By.XPATH, '//meta[@property="og:image"]')
        #     )
        # except Exception:
        #     pass  # 못 찾으면 그냥 넘어감

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # response = requests.get(url, timeout=10)
        # soup = BeautifulSoup(response.text, 'html.parser')

        def get_meta(property_name):
            tag = soup.find('meta', attrs={'property': property_name}) or \
                  soup.find('meta', attrs={'name': property_name})
            return tag['content'] if tag and 'content' in tag.attrs else None

        return {
            'title': soup.title.string if soup.title else '',
            'description': get_meta('og:description') or get_meta('description'),
            'image': get_meta('og:image'),
            'url': url
        }
    except Exception as e:
        return None

go_url = 'https://m.fmkorea.com/best/8405944051'
go2_url = 'https://link.coupang.com/a/cuXjoF'
result = fetch_url_preview(go_url)
print(result)