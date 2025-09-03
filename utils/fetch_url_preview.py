import re
import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urljoin

from io import BytesIO
import re, requests
from PIL import Image

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_BG_URL_RE = re.compile(r'url\((["\']?)(.+?)\1\)', re.I)

_INT = re.compile(r'^\s*(\d+)\s*$')

def _to_int(v):
    if v is None: return None
    if isinstance(v, int): return v
    m = _INT.match(str(v)); return int(m.group(1)) if m else None

def _get_meta(soup, name):
    tag = soup.find('meta', attrs={'property': name}) or soup.find('meta', attrs={'name': name})
    return tag['content'] if tag and 'content' in tag.attrs else None

def _parse_srcset(srcset):
    """srcset에서 가장 큰 항목의 URL과 그 너비(가능하면)를 반환"""
    if not srcset: return None, None
    best_url, best_w = None, -1
    for part in srcset.split(','):
        s = part.strip().split()
        if not s: continue
        url = s[0]
        w = None
        if len(s) > 1:
            desc = s[1]
            if desc.endswith('w'):
                try: w = int(desc[:-1])
                except: w = None
            elif desc.endswith('x'):
                # 배율 표기면 대략적인 비교용 가중치(실제 px 아님)로만 사용
                try: w = int(float(desc[:-1]) * 1000)
                except: w = None
        if (w or 0) > best_w:
            best_w, best_url = w or 0, url
    return best_url, (best_w if best_w > 0 else None)

def _collect_image_candidates(soup, base_url):
    cands = []
    def add(url, w=None, h=None, source=''):
        if not url: return
        cands.append({'url': urljoin(base_url, url), 'w': _to_int(w), 'h': _to_int(h), 'source': source})

    # 1) OpenGraph (여러 세트 지원 + width/height 매칭)
    og_blocks = []
    for meta in soup.find_all('meta'):
        prop = (meta.get('property') or meta.get('name') or '').strip().lower()
        content = meta.get('content')
        if not content: continue
        if prop in ('og:image', 'og:image:url', 'og:image:secure_url'):
            og_blocks.append({'url': content, 'w': None, 'h': None})
        elif prop == 'og:image:width' and og_blocks:
            og_blocks[-1]['w'] = content
        elif prop == 'og:image:height' and og_blocks:
            og_blocks[-1]['h'] = content
    for b in og_blocks:
        add(b['url'], b.get('w'), b.get('h'), 'og')

    # 2) Twitter / 기타 메타
    add(_get_meta(soup, 'twitter:image'), source='twitter')
    add(_get_meta(soup, 'image'), source='meta[name=image]')

    # 3) link rel="image_src"
    link = soup.find('link', rel=lambda v: v and 'image_src' in v)
    if link and link.get('href'):
        add(link['href'], source='link[image_src]')

    # 4) 모든 <img>
    for img in soup.find_all('img'):
        src = img.get('src')
        srcset = img.get('srcset')
        pick_url, pick_w = (src, None)
        if srcset:
            u, w = _parse_srcset(srcset)
            if u: pick_url, pick_w = u, w
        w = img.get('width') or img.get('data-width') or pick_w
        h = img.get('height') or img.get('data-height')
        add(pick_url, w, h, 'img')

    # 중복 제거(앞선 우선)
    seen, out = set(), []
    for c in cands:
        if c['url'] in seen: continue
        seen.add(c['url']); out.append(c)
    return out

def _pick_largest_by_declared(cands):
    best, area = None, -1
    for c in cands:
        w, h = c.get('w'), c.get('h')
        if w and h:
            a = w*h
            if a > area:
                area, best = a, c
    return best

def _probe_image_size(url, timeout=6, max_bytes=2_000_000, session=None):
    """실제 이미지를 최대 max_bytes만 받아 Pillow로 (w,h) 추출"""
    s = session or requests.Session()
    try:
        # HEAD로 과대 용량 건너뜀
        h = s.head(url, timeout=timeout, allow_redirects=True)
        cl = h.headers.get('Content-Length')
        if cl and int(cl) > max_bytes:
            return None, None
        r = s.get(url, timeout=timeout, stream=True)
        r.raise_for_status()
        buf, total = BytesIO(), 0
        for chunk in r.iter_content(8192):
            if not chunk: break
            buf.write(chunk)
            total += len(chunk)
            if total > max_bytes:
                return None, None
        buf.seek(0)
        with Image.open(buf) as im:
            return int(im.width), int(im.height)
    except Exception:
        return None, None

def pick_largest_image_url(soup, base_url, max_fetch=3, timeout=6, max_bytes=2_000_000):
    """
    수집된 후보들 중 가장 큰 이미지를 찾아 URL 반환.
    1) 명시된 w/h로 최대 면적 → 2) 상위 max_fetch개 실제 측정 → 3) 그래도 없으면 첫 후보
    """
    cands = _collect_image_candidates(soup, base_url)
    if not cands: return None

    best = _pick_largest_by_declared(cands)
    if best: return best['url']

    session = requests.Session()
    measured = []
    for c in cands[:max_fetch]:
        w, h = _probe_image_size(c['url'], timeout=timeout, max_bytes=max_bytes, session=session)
        if w and h:
            measured.append((w*h, c['url']))
    if measured:
        measured.sort(reverse=True)
        return measured[0][1]

    return cands[0]['url']


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
            tag = soup.find('meta', attrs={'property': property_name}) or soup.find('meta', attrs={'name': property_name})
            return tag['content'] if tag and 'content' in tag.attrs else None

        image_url = None
        # ❷ naver.me일 때 business_1 우선
        if url.startswith("https://naver.me/"):
            image_url = find_business1_src(driver)
        else:
            image_url = None

        if not image_url:
            # 가장 큰 이미지 우선
            largest = pick_largest_image_url(soup, driver.current_url, max_fetch=2)  # 네트워크 비용 줄이려면 0~2로
            image_url = largest  # 없으면 None
            print('largest', largest)

            # 안전한 이미지 추출
            # raw = get_meta('og:image') or get_meta('twitter:image') or get_meta('image')
            raw = largest
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
        print("fetch_url_preview_by_selenium error:", repr(e))
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

go_url = 'https://m.fmkorea.com/best/8405944051'
# go_url = 'https://link.coupang.com/a/cuXjoF'
# go_url = 'https://naver.me/xCB70lbu'

result = fetch_url_preview_by_selenium(go_url)
print(result)