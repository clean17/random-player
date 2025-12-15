from pathlib import Path
import asyncio
from typing import Optional, List
from playwright.async_api import async_playwright, Page, BrowserContext


ACCOUNTS = [

]

USER_DATA_DIR = str(Path("./ig_profile-1").resolve())


async def ensure_login(page):
    await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
    await asyncio.sleep(4)
    # 로그인 폼 보이면 로그인
    login_user = page.locator("input[name='username']")
    login_pass = page.locator("input[name='password']")
    if await login_user.count() and await login_pass.count():
        await login_user.fill('fkaus015')
        await login_pass.fill('gPdnjs0705.hyem')
        await login_pass.press("Enter")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(10)
        # 팝업 닫기
        for txt in ["나중에 하기", "Not Now"]:
            btn = page.locator(f"button:has-text('{txt}')")
            if await btn.count():
                await btn.click()
                await asyncio.sleep(3)

async def get_focus_page(context: BrowserContext, focus_page: Optional[Page]) -> Page:
    # 1) 전달된 focus_page가 살아있으면 그대로 사용
    if focus_page is not None and not focus_page.is_closed():
        return focus_page

    # 2) context.pages 중 살아있는 페이지 찾기
    for p in context.pages:
        if not p.is_closed():
            return p

    # 3) 하나도 없으면 새로 생성
    p = await context.new_page()
    await p.goto("about:blank")
    return p


async def open_tabs_keep_focus(context: BrowserContext, urls: List[str], focus_page: Optional[Page] = None) -> List[Page]:
    pages: List[Page] = []

    # 시작 시 포커스 탭 확보
    focus_page = await get_focus_page(context, focus_page)

    for u in urls:
        # 루프마다 포커스 탭이 닫혔는지 확인(사용자가 닫을 수 있으니)
        focus_page = await get_focus_page(context, focus_page)

        url = "https://www.instagram.com/" + u.lstrip("/")
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded")

        # 닫히는 타이밍 레이스 방지: 한 번 더 보정 후 포커스 복귀
        focus_page = await get_focus_page(context, focus_page)
        try:
            await focus_page.bring_to_front()
        except Exception:
            # 사용자가 닫는 순간 등에 걸리면 그냥 무시
            pass

        pages.append(page)
        await asyncio.sleep(1)

    return pages

async def open_tabs(context, urls):
    pages = []
    for url in urls:
        url = 'https://www.instagram.com//'+ url
        page = await context.new_page()   # 새 탭
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(1)
        pages.append(page)
    return pages

async def open_one(context, url):
    url = 'https://www.instagram.com//'+ url
    page = await context.new_page()
    await page.goto(url, wait_until="domcontentloaded")
    return page

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await pw.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=False,
            viewport={"width": 2560, "height": 1440},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )

        page = await context.new_page()
        await ensure_login(page)

        # pages = await open_tabs(context, ACCOUNTS) # 순차
        pages = await open_tabs_keep_focus(context, ACCOUNTS) # 첫번째 탭 유지 + 순차
        # pages = await asyncio.gather(*(open_one(context, url) for url in ACCOUNTS)) # 비동기

        # 탭들이 열린 상태로 유지 (원하면 시간 늘리기)
        await asyncio.sleep(6000000)

        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())

