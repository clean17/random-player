# save_page_offline.py
import base64
import time
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# ----- HTML 파싱/치환 -----
from bs4 import BeautifulSoup

# ----- MHTML 파싱 -----
from email import policy
from email.parser import BytesParser
from email.message import EmailMessage


# TARGET_URL = "https://www.rtings.com/headphones/reviews/samsung/galaxy-buds3-pro-truly-wireless"
# TARGET_URL = "https://www.rtings.com/headphones/reviews/nothing/ear-truly-wireless"
# TARGET_URL = "https://www.rtings.com/headphones/reviews/jabra/elite-8-active-gen-2-true-wireless"
# TARGET_URL = "https://www.rtings.com/headphones/reviews/technics/eah-az100"
# TARGET_URL = "https://www.rtings.com/headphones/reviews/anker/soundcore-space-a40-truly-wireless"
# TARGET_URL = "https://www.rtings.com/headphones/reviews/anker/soundcore-liberty-4-nc-truly-wireless"
TARGET_URL = "https://www.rtings.com/headphones/reviews/nothing/ear-a-truly-wireless"

# TARGET_NAME = "galaxy-buds3-pro-truly-wireless"
# TARGET_NAME = "ear-truly-wireless"
# TARGET_NAME = "elite-8-active-gen-2-true-wireless"
# TARGET_NAME = "eah-az100"
# TARGET_NAME = "soundcore-space-a40-truly-wireless"
# TARGET_NAME = "soundcore-liberty-4-nc-truly-wireless"
TARGET_NAME = "ear-a-truly-wireless"


def wait_for_document_ready(driver, timeout: float = 20.0):
    """document.readyState == 'complete' 대기"""
    end = time.time() + timeout
    while time.time() < end:
        try:
            state = driver.execute_script("return document.readyState")
            if state == "complete":
                return
        except Exception:
            pass
        time.sleep(0.2)
    # 타임아웃이어도 진행 (필요시 예외)
    return


def scroll_to_bottom(driver, step_px: int = 200, delay_s: float = 0.3, tail_wait_s: float = 2.0):
    """무한스크롤 페이지 대비 바닥까지 스크롤"""
    last_total = None
    while True:
        driver.execute_script("window.scrollBy(0, arguments[0]);", step_px)
        time.sleep(delay_s)
        new_pos = driver.execute_script("return window.scrollY + window.innerHeight")
        total_h = driver.execute_script("return document.body.scrollHeight")

        # 진행 표시나 무한 루프 방지 로직
        if last_total is not None and total_h == last_total and new_pos >= total_h:
            break
        if new_pos >= total_h:
            # 더 안 내려가면 종료
            break
        last_total = total_h
    time.sleep(tail_wait_s)


def save_mhtml(driver, out_path: Path) -> str:
    """CDP Page.captureSnapshot(format=mhtml) → 파일 저장, 그리고 문자열 반환"""
    driver.execute_cdp_cmd("Page.enable", {})
    snap = driver.execute_cdp_cmd("Page.captureSnapshot", {"format": "mhtml"})
    mhtml = snap.get("data") or ""
    out_path.write_text(mhtml, encoding="utf-8")
    return mhtml


def save_pdf(driver, out_path: Path, a4: bool = True, print_background: bool = True, landscape: bool = False):
    """CDP Page.printToPDF → 파일 저장"""
    driver.execute_cdp_cmd("Page.enable", {})
    params = {
        "printBackground": bool(print_background),
        "landscape": bool(landscape),
    }
    if a4:
        params.update({"paperWidth": 8.27, "paperHeight": 11.69})  # A4 inch

    pdf_result = driver.execute_cdp_cmd("Page.printToPDF", params)
    b64 = pdf_result.get("data", "")
    out_path.write_bytes(base64.b64decode(b64))


# ---------------- MHTML → 단일 self-contained HTML 변환기 ----------------

def mhtml_to_single_html(mhtml_text: str) -> str:
    """
    Java의 MhtmlToSingleHtmlConverter와 동등한 역할.
    - 첫 파트: HTML
    - 나머지 파트: Content-Location / Content-ID 매핑 → data:URI
    - HTML의 img/src, script/src, link rel=stylesheet, style 속성, <style> 내 url(...) 모두 치환
    """
    # 1) MHTML 파싱
    raw_bytes = mhtml_text.encode("utf-8", errors="ignore")
    msg: EmailMessage = BytesParser(policy=policy.default).parsebytes(raw_bytes)

    if not msg.is_multipart():
        # 일부 환경에서 단일 파트일 수도 있으나 보통 multipart/related
        # 이 경우 그냥 원문 반환
        return mhtml_text

    parts = [p for p in msg.iter_parts()]
    if not parts:
        return ""

    # 2) 첫 파트(HTML)
    html_part = parts[0]
    html_charset = html_part.get_content_charset() or "utf-8"
    base_url = html_part.get("Content-Location", "") or ""

    html_bytes = html_part.get_payload(decode=True) or b""
    html_str = html_bytes.decode(html_charset, errors="replace")

    soup = BeautifulSoup(html_str, "html.parser")

    # 3) 리소스 매핑 테이블 구성
    res_map = {}
    for part in parts[1:]:
        ctype = part.get_content_type() or "application/octet-stream"  # e.g., image/png, text/css
        loc = part.get("Content-Location")
        cid = part.get("Content-ID")
        payload = part.get_payload(decode=True) or b""

        data_uri = f"data:{ctype};base64,{base64.b64encode(payload).decode('ascii')}"

        if loc:
            abs_u = urljoin(base_url, loc)
            # 절대경로/상대경로 둘 다 키로 보관
            res_map[abs_u] = data_uri
            res_map[loc] = data_uri

        if cid:
            cid_clean = cid.strip("<>").strip()
            res_map[f"cid:{cid_clean}"] = data_uri
            res_map[f"CID:{cid_clean}"] = data_uri

    def map_resource(url: str) -> str:
        if not url:
            return url
        # cid:
        if url.lower().startswith("cid:"):
            return res_map.get(url, url)
        # 절대/상대 모두 탐색
        abs_u = urljoin(base_url, url)
        return res_map.get(abs_u, res_map.get(url, url))

    # 4) HTML 내 리소스 치환
    # 4-1) <img src>, srcset
    for img in soup.select("img[src]"):
        img["src"] = map_resource(img.get("src", ""))
        if img.has_attr("srcset"):
            img["srcset"] = _rewrite_srcset(img["srcset"], map_resource)

    # 4-2) <script src>
    for s in soup.select("script[src]"):
        s["src"] = map_resource(s.get("src", ""))

    # 4-3) <link rel=stylesheet href>
    for l in soup.select("link[rel=stylesheet][href]"):
        href = l.get("href", "")
        mapped = map_resource(href)
        if mapped.startswith("data:text/css"):
            # 그대로 dataURI 유지
            l["href"] = mapped
        elif mapped.startswith("data:"):
            # 혹시 text/css가 아닌 data로 왔다면 <style>에 인라인 삽입
            css_text = _decode_data_text(mapped)
            css_text = _rewrite_css_urls(css_text, map_resource)
            style = soup.new_tag("style", type="text/css")
            style.string = css_text
            l.insert_after(style)
            l.decompose()
        else:
            l["href"] = mapped

    # 4-4) <source src>, <video poster>, <audio src>
    for e in soup.select("source[src]"):
        e["src"] = map_resource(e.get("src", ""))
    for e in soup.select("video[poster]"):
        e["poster"] = map_resource(e.get("poster", ""))
    for e in soup.select("audio[src]"):
        e["src"] = map_resource(e.get("src", ""))

    # 4-5) style 속성
    for e in soup.select("[style]"):
        e["style"] = _rewrite_css_urls(e.get("style", ""), map_resource)

    # 4-6) <style> 태그 내 CSS
    for st in soup.select("style"):
        css = st.string or st.text or ""
        css = _rewrite_css_urls(css, map_resource)
        st.clear()
        st.append(css)

    # 4-7) <base href> 제거(상대경로 오작동 방지)
    for b in soup.select("base[href]"):
        b.decompose()

    return str(soup)


def _rewrite_srcset(srcset: str, mapper) -> str:
    # "url1 1x, url2 2x" 형태
    out = []
    for seg in [s.strip() for s in srcset.split(",") if s.strip()]:
        sp = seg.find(" ")
        if sp > 0:
            url = seg[:sp]
            desc = seg[sp + 1 :]
            out.append(f"{mapper(url)} {desc}")
        else:
            out.append(mapper(seg))
    return ", ".join(out)


_URL_FUNC = re.compile(r"url\(([^)]+)\)", re.IGNORECASE)


def _rewrite_css_urls(css: str, mapper) -> str:
    if not css:
        return css

    def repl(m):
        raw = m.group(1).strip().strip("\"'")  # 괄호 안 경로
        mapped = mapper(raw)
        # 작은따옴표 이스케이프
        mapped = mapped.replace("'", "%27")
        return f"url('{mapped}')"

    return _URL_FUNC.sub(repl, css)


def _decode_data_text(data_uri: str) -> str:
    """
    data:text/...;base64,XXXXX → 텍스트 디코딩
    """
    try:
        if not data_uri.startswith("data:"):
            return data_uri
        comma = data_uri.find(",")
        meta = data_uri[5:comma]  # e.g., 'text/css;base64'
        payload = data_uri[comma + 1 :]
        if "base64" in meta.lower():
            return base64.b64decode(payload).decode("utf-8", errors="replace")
        return payload
    except Exception:
        return ""


# ---------------- 메인 실행 ----------------

def main():
    url = TARGET_URL  # 저장하려는 대상 URL
    out_dir = Path("../html")
    out_dir.mkdir(parents=True, exist_ok=True)

    opts = Options()
    opts.add_argument("--headless=new")  # 필요시
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)

    try:
        driver.get(url)
        wait_for_document_ready(driver)
        scroll_to_bottom(driver)
        time.sleep(3)  # 네트워크 잔여요청 대기

        # # A) MHTML 저장
        mhtml_path = out_dir / "saved_page.mhtml"
        mhtml_text = save_mhtml(driver, mhtml_path)
        # print(f"[OK] MHTML: {mhtml_path.resolve()}")
        #
        # A-2) MHTML → 단일 HTML
        single_html = mhtml_to_single_html(mhtml_text)
        single_path = out_dir / f"{TARGET_NAME}.html"
        single_path.write_text(single_html, encoding="utf-8")
        print(f"[OK] Single HTML: {single_path.resolve()}")
        #
        # # B) PDF 저장
        # pdf_path = out_dir / "saved_page.pdf"
        # save_pdf(driver, pdf_path, a4=True, print_background=True, landscape=False)
        # print(f"[OK] PDF: {pdf_path.resolve()}")
        #
        # # B2) 옵션 축약본(배경만 켜고 기본 규격)
        # pdf2 = out_dir / "saved_page2.pdf"
        # driver.execute_cdp_cmd("Page.enable", {})
        # pdf_res = driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})
        # pdf2.write_bytes(base64.b64decode(pdf_res["data"]))
        # print(f"[OK] PDF2: {pdf2.resolve()}")

        # C) 원시 HTML 저장 (외부 리소스는 별도이므로 완전 재현 어려움)
        # raw_html = driver.page_source
        # raw_path = out_dir / "saved_page_raw.html"
        # raw_path.write_text(raw_html, encoding="utf-8")
        # print(f"[OK] RAW HTML: {raw_path.resolve()}")

    finally:
        driver.quit()


if __name__ == "__main__":
    # Windows에서 콘솔 인코딩 문제 시:
    # import io, sys; sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding="utf-8")
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
