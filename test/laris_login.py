from playwright.sync_api import sync_playwright
import json
import argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://192.168.60.101:8080/")
    ap.add_argument("--user", default="")
    ap.add_argument("--pw",   default="")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--cookies",  default="cookies.json")
    ap.add_argument("--timeout",  type=float, default=20000)  # ms
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=args.headless,
            # args=["--start-maximized"]
        )
        # start-maximized는 창 최대화에 가깝게 동작하므로 viewport를 None으로 두면 OS 창 크기를 사용
        ctx = browser.new_context(viewport={"width":1920, "height":1080})

        page = ctx.new_page()
        page.set_default_timeout(args.timeout)

        page.goto(args.url, wait_until="domcontentloaded")

        page.fill("#txtUsername", args.user)
        page.fill("#txtPassword", args.pw)
        page.click("#btnLogin")

        # 에러 팝업이 뜨면 닫기 (보이면 클릭)
        try:
            # 팝업이 나타날 시간을 아주 짧게 대기 (필요하면 3000~5000으로 늘리세요)
            page.wait_for_selector("div.error-pop.on", state="visible", timeout=2000)
            # 내부 확인 버튼 클릭
            page.click("div.error-pop.on button.b1.light-red1.hover-bg.ok")
            print("[INFO] Error popup detected and closed.")
        except Exception:
            # 팝업이 없으면 그냥 통과
            pass

        # .main-bbs mb20

        # 5) 메인 화면 로딩 대기:
        #   - URL 변화
        page.wait_for_load_state("domcontentloaded")
        #   - 로그인 폼 사라짐
        page.wait_for_selector("#txtUsername", state="detached", timeout=10000)
        #   - 메인 전용 요소가 생김
        # page.wait_for_selector(".main-bbs", timeout=10000)

        # 6) 제목 출력
        print("title", page.title())

        # 7) 쿠키 수집 및 저장 (HTTP-only 포함)
        cookies = ctx.cookies()  # [{name, value, domain, path, ...}]
        with open(args.cookies, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)

        # 요청 헤더로 바로 쓸 수 있는 Cookie 라인도 출력
        cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        print("Cookie header:", cookie_header)

        # CSRF가 meta/input에 있다면 추출
        csrf = None
        for sel, attr in [("meta[name=\"_csrf\"]", "content"), ("input[name=\"_csrf\"]", "value")]:
            try:
                el = page.query_selector(sel)
                if el:
                    csrf = el.get_attribute(attr)
                    break
            except Exception:
                pass
        if csrf:
            with open("csrf.json", "w", encoding="utf-8") as f:
                json.dump(csrf, f, ensure_ascii=False)
            print("_csrf", csrf)

        browser.close()

if __name__ == "__main__":
    main()
