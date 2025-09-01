import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def fetch_url_preview_by_selenium(url):
    try:
        options = Options()
        # options.add_argument("--headless")  # 창 없이 실행
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        # options.add_argument("--window-size=1280,800")  # (필수는 아님)

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

        # 안전한 이미지 추출
        raw = get_meta('og:image') or get_meta('twitter:image') or get_meta('image')
        print('raw', raw)
        image_url = None
        if raw:
            if raw.startswith('//'):
                image_url = 'https:' + raw
            else:
                image_url = urljoin(driver.current_url, raw)  # 상대경로/스킴 상대 모두 처리

        return {
            'title': soup.title.string if soup.title else '',
            'description': get_meta('og:description') or get_meta('description'),
            'image': image_url,
            'url': url
        }
    except Exception as e:
        return None
    finally:
        if driver:
            driver.quit()

go_url = 'https://m.fmkorea.com/best/8405944051'
go_url = 'https://www.coupang.com/vp/products/7638852473?itemId=20291196156&vendorItemId=87174513955&src=1191000&spec=10999999&addtag=400&ctag=7638852473&lptag=CFM30565187&itime=20250902031308&pageType=PRODUCT&pageValue=7638852473&wPcid=17567503881607839402249&wRef=&wTime=20250902031308&redirect=landing&mcid=bd4671289bcf42abb18d4d59e507008e&sharesource=sharebutton&style=&isshortened=Y&settlement=N'
go2_url = 'https://link.coupang.com/a/cuXjoF'
result = fetch_url_preview_by_selenium(go_url)
print(result)