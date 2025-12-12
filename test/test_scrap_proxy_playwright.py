import asyncio
import datetime
import configparser
from pathlib import Path
from urllib.parse import quote

from playwright.async_api import async_playwright


# ─────────────────────────────────────────────
# 1. 타겟 URL 및 동작 파라미터
# ─────────────────────────────────────────────
URL = "https://m.blog.naver.com/PostView.naver?blogId=mojjustice&logNo=224100395324"
URL = "https://mojjustice.tistory.com/8710890"

HEADLESS = False
SCROLL_PAUSE = 1.8
MAX_SCROLLS = 3000  # 너무 크면 시간 오래 걸리니 적당히 조절


async def auto_scroll_page(page):
    await page.evaluate("""
        () => {
            return new Promise((resolve) => {
                let totalHeight = 0;
                const distance = 20; // px 단위로 조금씩 내리기
                const timer = setInterval(() => {
                    const scrollHeight = document.body.scrollHeight;
                    window.scrollBy(0, distance);
                    totalHeight += distance;
                    if (totalHeight >= scrollHeight - window.innerHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 100);
            });
        }
    """)

    # 스크롤 끝난 뒤 자잘한 네트워크 작업 대기
    await page.wait_for_timeout(2000)


async def main():
    # ─────────────────────────────────────────
    # 2. Playwright 시작 + SOCKS5 프록시 설정
    # ─────────────────────────────────────────
    proxy = {
        "server": "http://127.0.0.1:8899"
    }


    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=HEADLESS,
            proxy=proxy,
        )

        context = await browser.new_context()
        page = await context.new_page()

        # ─────────────────────────────────────
        # 3. 페이지 이동 (timeout 여유 있게)
        # ─────────────────────────────────────
        print(f"[goto] {URL}")
        await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)

        # ─────────────────────────────────────
        # 4. 아래까지 스크롤해서 전체 컨텐츠 로드 유도
        # ─────────────────────────────────────
        await auto_scroll_page(page)

        # ─────────────────────────────────────
        # 5. 전체 HTML 가져와서 파일 저장
        # ─────────────────────────────────────
        html = await page.content()

        out_dir = Path(__file__).resolve().parent / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"naver_m_blog.html"

        out_path.write_text(html, encoding="utf-8")
        print(f"✅ 전체 HTML 저장 완료: {out_path}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
