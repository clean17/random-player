import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from config.config import settings

# ======== 설정 ========
# USER_DATA_DIR = str(Path("./ig_profile-2").resolve())  # fx015
USER_DATA_DIR = str(Path("./ig_profile-14").resolve())
HEADLESS = False

USERNAME = settings['SCRAP_USERNAME']
PASSWORD = settings['SCRAP_PASSWORD']

ACCOUNT = "test"   # 저장 폴더명: IMAGE_DIR2/{ACCOUNT}/images|reels/

POST_URLS = [
    "https://www.instagram.com/fkaus014/p/DOuWTchj75b/",   # 테스트할 포스트 URI
]


async def ensure_login(page):
    await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
    login_user = page.locator("input[name='username'], input[name='email']")
    login_pass = page.locator("input[name='password'], input[name='pass']")
    if await login_user.count() and await login_pass.count():
        await login_user.fill(USERNAME)
        await login_pass.fill(PASSWORD)
        await login_pass.press("Enter")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(10)
        for txt in ["나중에 하기", "Not Now"]:
            btn = page.locator(f"button:has-text('{txt}')")
            if await btn.count():
                await btn.click()
                await asyncio.sleep(1)


async def main():
    from job.scrap.scrap_gm_playwrigit import (
        extract_media_from_post,
        download_media,
        ensure_dirs,
        BASE_SAVE_DIR,
    )

    dirs = ensure_dirs(BASE_SAVE_DIR, ACCOUNT)
    print(f"[저장 위치] {dirs['images']}  /  {dirs['reels']}")

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=HEADLESS,
            viewport={"width": 1280, "height": 720},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        page = await context.new_page()
        await ensure_login(page)

        for url in POST_URLS:
            print(f"\n[URL] {url}")
            result = await extract_media_from_post(page, url)

            images    = result.get("images", [])
            video_cdn = result.get("video_cdn", [])
            print(f"  이미지 {len(images)}개 / 비디오 {len(video_cdn)}개")

            saved = await download_media(images, [], video_cdn, dirs, ACCOUNT)
            print(f"  저장 완료 {len(saved)}개")
            for p in saved:
                print(f"    {p}")

        await context.close()


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
        os._exit(0)  # anyio atexit 스레드 풀 경고 방지
