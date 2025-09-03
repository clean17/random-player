import re
import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urljoin

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_BG_URL_RE = re.compile(r'url\((["\']?)(.+?)\1\)', re.I)



def resolve_url(url: str, timeout: int = 10, max_hops: int = 10) -> str:
    """
    경유(짧은) URL을 최종 URL로 해석해 반환.
    - 3xx Location 따라가기
    - HEAD 막히면 GET로 대체
    - HTML의 <meta http-equiv="refresh" content="0;url=..."> 도 인식
    실패 시 원본 url 반환
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    })

    current = url
    visited = set()

    for _ in range(max_hops):
        if current in visited:
            break
        visited.add(current)

        # 1) HEAD로 가볍게 시도 (일부 사이트는 405/403/4xx 가능)
        try:
            r = s.head(current, allow_redirects=False, timeout=timeout)
            status = r.status_code
        except Exception:
            r = None
            status = None

        def _follow(loc):
            nonlocal current
            nxt = urljoin(current, loc.strip())
            current = nxt

        if r is not None and 300 <= status < 400 and "Location" in r.headers:
            # Location 헤더 리다이렉트
            _follow(r.headers["Location"])
            continue

        # 2) GET으로 한 번 더 확인 (allow_redirects=False → 우리가 직접 처리)
        try:
            r = s.get(current, allow_redirects=False, timeout=timeout)
            status = r.status_code
        except Exception:
            break

        if 300 <= status < 400 and "Location" in r.headers:
            _follow(r.headers["Location"])
            continue

        # 3) HTML meta refresh 처리
        ctype = r.headers.get("Content-Type", "")
        if "text/html" in ctype and r.text:
            soup = BeautifulSoup(r.text, "html.parser")
            meta = soup.find("meta", attrs={"http-equiv": re.compile(r"refresh", re.I)})
            if meta and meta.get("content"):
                m = re.search(r"url\s*=\s*([^;]+)", meta["content"], flags=re.I)
                if m:
                    _follow(m.group(1))
                    continue

        # 여기까지 오면 더 이상 리다이렉트 없음 → current가 최종
        return r.url or current

    return current  # hop 초과/예외 시 현재 값 반환



def find_business1_src(driver, timeout=8):
    """
    #business_1 요소 '자체'의 소스를 반환.
    - 우선순위: src, data-src, data-lazy-src, data-original, data-ks-lazyload, data-img
    - 없으면 style의 background-image url(...)
    - 메인 문서에서 먼저 찾고 없으면 모든 iframe을 순회.
    - 하위 <img>는 보지 않음.
    """
    src_attrs = ('src', 'data-src', 'data-lazy-src', 'data-original', 'data-ks-lazyload', 'data-img')

    def _from_elem(elem, base_url):
        # 속성 우선
        for attr in src_attrs:
            raw = elem.get_attribute(attr)
            if raw:
                return urljoin(base_url, raw)
        # style background-image
        style = elem.get_attribute('style') or ''
        m = _BG_URL_RE.search(style)
        if m:
            return urljoin(base_url, m.group(2))
        return None

    def _pick_here(drv):
        try:
            root = WebDriverWait(drv, 2).until(
                EC.presence_of_element_located((By.ID, "business_1"))
            )
        except Exception:
            return None
        return _from_elem(root, drv.current_url)

    # 1) 현재 문서
    val = _pick_here(driver)
    if val:
        return val

    # 2) 모든 iframe 순회
    frames = driver.find_elements(By.CSS_SELECTOR, 'iframe')
    for f in frames:
        try:
            driver.switch_to.frame(f)
            val = _pick_here(driver)
            if val:
                return val
        except Exception:
            pass
        finally:
            driver.switch_to.default_content()

    return None


def fetch_url_preview_by_selenium(url):
    driver = None
    try:
        final_url = resolve_url(url)  # ★ 리다이렉트 미리 풀기
        print('final_url', final_url)
        opts  = Options()
        # opts.add_argument("--headless=new")  # 창 없이 실행
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--window-size=1280,800")  # headless에선 꼭 지정
        opts.add_argument("--log-level=3")  # 0=INFO… 3=ERROR;  크롬 자체 로그 레벨 하향
        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(15)  # 완전 로드까지 쵀대 15초 대기
        driver.get(final_url)

        # DOM 최소 준비 대기 (interactive/complete); Explicit Wait (명시적 대기), 최대 8초 동안
        # WebDriverWait(driver, 8).until(
        #     lambda d: d.execute_script("return document.readyState") in ("interactive", "complete")
        # )

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        def get_meta(property_name):
            tag = soup.find('meta', attrs={'property': property_name}) or \
                  soup.find('meta', attrs={'name': property_name})
            return tag['content'] if tag and 'content' in tag.attrs else None


        # ❷ naver.me일 때 business_1 우선
        if url.startswith("https://naver.me/"):
            image_url = find_business1_src(driver)
        else:
            image_url = None

        if not image_url:
            # 안전한 이미지 추출
            raw = get_meta('og:image') or get_meta('twitter:image') or get_meta('image')
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
        print("fetch_url_preview_by_selenium_v1 error:", repr(e))
        # 실패해도 일단 구조는 유지
        return {
            'title': 'err',
            'description': None,
            'image': None,
            'origin_url': url,
        }
    finally:
        if driver:
            driver.quit()

go1_url = 'https://m.fmkorea.com/best/8405944051'
go2_url = 'https://link.coupang.com/a/cuXjoF'
go3_url = 'https://naver.me/xCB70lbu'
# result = fetch_url_preview_by_selenium(go3_url)
# print(result)