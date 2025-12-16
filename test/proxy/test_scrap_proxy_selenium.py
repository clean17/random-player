import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


# ─────────────────────────────────────────────
# 1. 타겟 URL 및 동작 파라미터
# ─────────────────────────────────────────────
URL = "https://m.blog.naver.com/PostView.naver?blogId=mojjustice&logNo=224100395324"
URL = "https://mojjustice.tistory.com/8710890"

HEADLESS = False
SCROLL_PAUSE = 0.1      # 한 번 스크롤 후 대기 시간 (초)
MAX_SCROLLS = 3000      # 최대 스크롤 횟수 (너무 크면 오래 걸릴 수 있음)


import logging

log = logging.getLogger(__name__)

def scroll_to_bottom(driver, blog):
    """
    Python 3.8 + Selenium용 스크롤 함수
    - driver: selenium webdriver
    - blog: "naver" 등
    """
    while True:
        driver.execute_script("window.scrollBy(0, 80);")
        time.sleep(0.1)

        new_height = int(driver.execute_script("return window.scrollY + window.innerHeight;"))
        total_height = int(driver.execute_script("return document.body.scrollHeight;"))

        if new_height >= total_height:
            break

        if blog == "naver":
            is_visible = driver.execute_script(
                "var el = document.getElementById('post_writer');"
                "if (!el) return false;"
                "var rect = el.getBoundingClientRect();"
                "return (rect.bottom > 0 && rect.top < window.innerHeight);"
            )

            if is_visible is True:
                log.info("[INFO] id='post_writer' 요소가 화면에 표시되었습니다. 스크롤을 중단합니다.")
                break

    time.sleep(1.0)



def main():
    # ─────────────────────────────────────────
    # 2. Chrome 옵션 + SOCKS5/HTTP 프록시 설정
    # ─────────────────────────────────────────
    chrome_options = Options()
    if HEADLESS:
        # 크롬 최근 버전에서는 --headless=new 권장
        chrome_options.add_argument("--headless=new")

    # 프록시 설정 (Playwright의 proxy와 동일하게)
    chrome_options.add_argument("--proxy-server=http://127.0.0.1:8899")
    # chrome_options.add_argument("--proxy-server=http://192.168.60.101:3128")

    # 필요하다면 User-Agent, 언어 등도 여기서 추가
    # chrome_options.add_argument("user-agent=...")

    # chromedriver가 PATH에 있어야 함
    driver = webdriver.Chrome(options=chrome_options)

    try:
        # ─────────────────────────────────────
        # 3. 페이지 이동
        # ─────────────────────────────────────
        print(f"[goto] {URL}")
        driver.set_page_load_timeout(60)
        driver.get(URL)

        # ─────────────────────────────────────
        # 4. 아래까지 스크롤해서 전체 컨텐츠 로드 유도
        # ─────────────────────────────────────
        # auto_scroll_page(driver)
        scroll_to_bottom(driver, None)

        # ─────────────────────────────────────
        # 5. 전체 HTML 가져와서 파일 저장
        # ─────────────────────────────────────
        html = driver.page_source

        # out_dir = Path(__file__).resolve().parent / "output"
        out_dir = Path(__file__).resolve().parent
        # out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "naver_m_blog_selenium.html"

        out_path.write_text(html, encoding="utf-8")
        print(f"✅ 전체 HTML 저장 완료: {out_path}")

    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    main()
