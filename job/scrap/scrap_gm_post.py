import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from config.config import settings
from job.scrap.scrap_gm_playwrigit import ensure_login

# ======== 설정 ========
# USER_DATA_DIR = str(Path("./data/ig_profile-2").resolve())  # fx015
USER_DATA_DIR = str(Path("./data/ig_profile-15").resolve())
HEADLESS = False

USERNAME = settings['SCRAP_USERNAME']
PASSWORD = settings['SCRAP_PASSWORD']

ACCOUNT = "lalababy.amy"

POST_URLS = [
    "https://www.instagram.com/p/DbSpNayxlSW/",   # 테스트할 포스트 URI
    # "",
]


async def main():
    from job.scrap.scrap_gm_playwrigit import (
        extract_media_from_post,
        download_media,
        ensure_dirs,
        BASE_SAVE_DIR,
    )

    dirs = ensure_dirs(BASE_SAVE_DIR, ACCOUNT)
    # print(f"[저장 위치] {dirs['images']}  /  {dirs['reels']}")

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

            ig_cookies = await page.context.cookies()
            saved, _ = await download_media(images, [], video_cdn, dirs, ACCOUNT, cookies=ig_cookies, page=page)
            print(f"  저장 완료 {len(saved)}개")
            # for p in saved:
            #     print(f"    {p}")

        await context.close()


if __name__ == "__main__":
    import traceback
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except Exception:
        traceback.print_exc()
    finally:
        loop.close()
        os._exit(0)  # anyio atexit 스레드 풀 경고 방지
