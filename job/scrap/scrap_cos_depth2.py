import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from config.config import settings
from playwright.async_api import async_playwright
import requests
import asyncio
from datetime import datetime

today = datetime.now().strftime("%Y%m%d")
month = datetime.now().strftime("%y%m")
month_dir = f"logs/a/{month}"
os.makedirs(month_dir, exist_ok=True)
filename = f"{month_dir}/scrap_cos_depth2_{today}.log"
log_file = open(filename, "w", encoding="utf-8")
sys.stdout = log_file
# stderr는 콘솔로 유지 (오류 확인용)

IMAGE_DIR = settings['IMAGE_DIR']
COS_URL = settings['COS_URL']
SAVE_DIR = os.path.join(IMAGE_DIR, 'cos')
os.makedirs(SAVE_DIR, exist_ok=True)




def download_image(img_url: str, save_dir: str, post_id: str) -> bool:
    try:
        basename = os.path.basename(img_url.split('?')[0])
        name, ext = os.path.splitext(basename)
        ts = datetime.now().strftime("%H%M%S%f")[:9]
        new_filename = f"{name}_{post_id}_{ts}{ext}"
        save_path = os.path.join(save_dir, new_filename)
        resp = requests.get(img_url, timeout=30, headers={'Referer': COS_URL})
        resp.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(resp.content)
        print(f"  Downloaded: {new_filename}")
        return True
    except Exception as e:
        print(f"  Failed {img_url}: {e}")
        return False


async def get_photo_item_count(page) -> int:
    return await page.evaluate("""() => {
        const container = document.querySelector('#photo-container');
        if (!container) return 0;
        return [...container.children].filter(
            el => el.tagName === 'DIV' && el.id !== 'loading-spinner'
        ).length;
    }""")


async def is_spinner_visible(page) -> bool:
    return await page.evaluate("""() => {
        const el = document.getElementById('loading-spinner');
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        return rect.top < window.innerHeight && rect.bottom > 0 && rect.width > 0 && rect.height > 0;
    }""")


async def auto_scroll_until_div_pt2(page):
    """
    - id="loading-spinner" 보이면 스크롤 일시 중지
      → 5초 내 #photo-container 자식 div(spinner 제외) 증가 시 재개, 아니면 그냥 재개
    - div.pt-2 > center 가 뷰포트에 보이면서 5초 유지되면 종료
    """
    loop = asyncio.get_event_loop()
    in_view_since = None

    while True:
        # 스피너 감지 시 일시 중지
        if await is_spinner_visible(page):
            in_view_since = None
            before_count = await get_photo_item_count(page)
            print(f"  [scroll] 스피너 감지 · 중지 · items={before_count} · 최대 5초 대기")
            log_file.flush()

            deadline = loop.time() + 5
            new_items = False
            while loop.time() < deadline:
                await page.wait_for_timeout(500)
                after_count = await get_photo_item_count(page)
                if after_count > before_count:
                    print(f"  [scroll] 아이템 추가 ({before_count}→{after_count}) · 스크롤 재개")
                    log_file.flush()
                    new_items = True
                    break

            if not new_items:
                print(f"  [scroll] 5초 대기 완료 · 아이템 증가 없음 · 다운로드 시작")
                log_file.flush()
                break  # 스크롤 루프 종료 → 다운로드로 진행
            continue  # 새 아이템 추가됨 → 상태 재확인 후 스크롤 계속

        state = await page.evaluate("""() => {
            const el = document.querySelector('div.pt-2 > center');
            if (!el) return 'none';
            const rect = el.getBoundingClientRect();
            if (rect.bottom < 0) return 'above';
            if (rect.top < window.innerHeight && rect.bottom > 0) return 'in_view';
            return 'below';
        }""")

        if state == 'in_view':
            if in_view_since is None:
                in_view_since = loop.time()
            elapsed = loop.time() - in_view_since
            print(f"  [scroll] center=in_view · {elapsed:.0f}s/5s")
            log_file.flush()
            if elapsed >= 5:
                print(f"  [scroll] 5초 유지 · 종료")
                log_file.flush()
                break
            await page.wait_for_timeout(500)
            continue

        in_view_since = None
        print(f"  [scroll] center={state}")
        log_file.flush()

        if state == 'above':
            break

        at_bottom = await page.evaluate(
            "(window.scrollY + window.innerHeight) >= document.body.scrollHeight"
        )
        if at_bottom:
            print(f"  [scroll] 페이지 바닥 도달 · 종료")
            log_file.flush()
            break

        await page.evaluate("window.scrollBy(0, 250)")
        await page.wait_for_timeout(500)


async def collect_and_download(page, post_id: str) -> int:
    downloaded_count = 0
    loop = asyncio.get_event_loop()

    await auto_scroll_until_div_pt2(page)

    links = await page.eval_on_selector_all(
        "div.position-relative.d-inline-block > a[data-fancybox='gallery']",
        "els => els.map(a => a.getAttribute('href')).filter(Boolean)"
    )

    # 중복 URL 감지
    seen = {}
    for link in links:
        seen[link] = seen.get(link, 0) + 1
    duplicates = {url: cnt for url, cnt in seen.items() if cnt > 1}
    unique_count = len(seen)
    print(f"  [collect] a태그={len(links)}개  unique={unique_count}개  중복={len(duplicates)}건")
    for url, cnt in duplicates.items():
        print(f"  [dup] {cnt}회 등장: {url}")
    log_file.flush()

    for link in links:
        if await loop.run_in_executor(None, download_image, link, SAVE_DIR, post_id):
            downloaded_count += 1

    return downloaded_count


async def async_crawl_depth2():
    post_urls = ['']
    if not post_urls:
        print("URL 목록이 비어 있습니다.")
        log_file.close()
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--window-size=1280,900"],
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        total_downloaded = 0

        try:
            for i, post_url in enumerate(post_urls, start=1):
                try:
                    post_id = post_url.rstrip('/').split('/')[-1]
                    print(f"\n{'='*60}")
                    print(f"[{i}/{len(post_urls)}] {post_url}  (post_id={post_id})")
                    log_file.flush()

                    await page.goto(post_url, timeout=30000)
                    await page.wait_for_timeout(2000)

                    count = await collect_and_download(page, post_id)
                    print(f"  ✅ 이번 게시글 다운로드: {count}개")
                    total_downloaded += count
                    log_file.flush()

                except Exception as e:
                    print(f"  ❌ 오류: {e}")
                    log_file.flush()
        finally:
            print(f"\n{'='*60}")
            print(f"▶ 전체 완료")
            print(f"▶ 처리 게시글 수 : {len(post_urls)}개")
            print(f"▶ 총 다운로드 수  : {total_downloaded}개")
            print(f"▶ 저장 경로       : {SAVE_DIR}")
            log_file.flush()

            await page.close()
            await context.close()
            await browser.close()

    log_file.close()


asyncio.run(async_crawl_depth2())
