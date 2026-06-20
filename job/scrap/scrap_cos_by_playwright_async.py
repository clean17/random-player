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
filename = f"{month_dir}/scrap_cos_{today}.log"
log_file = open(filename, "w", encoding="utf-8")
sys.stdout = log_file
# stderr는 콘솔로 유지 (오류 확인용)

BASE_URL = ''
COS_URL = settings['COS_URL']
COS_DIR = settings['COS_DIR']


def download_image(img_url: str, save_dir: str, post_id: str, fallback_url: str = None) -> bool:
    try:
        basename = os.path.basename(img_url.split('?')[0])
        name, ext = os.path.splitext(basename)
        ts = datetime.now().strftime("%H%M%S%f")[:9]
        new_filename = f"{post_id}_{name}_{ts}{ext}"
        save_path = os.path.join(save_dir, new_filename)
        try:
            resp = requests.get(img_url, timeout=30, headers={'Referer': COS_URL})
            resp.raise_for_status()
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404 and fallback_url:
                print(f"  404 → fallback src: {fallback_url}")
                resp = requests.get(fallback_url, timeout=30, headers={'Referer': COS_URL})
                resp.raise_for_status()
            else:
                raise
        with open(save_path, 'wb') as f:
            f.write(resp.content)
        print(f"  Downloaded: {new_filename}")
        return True
    except Exception as e:
        print(f"  Failed {img_url}: {e}")
        return False


async def scroll_to_bottom(page):
    """실제 scrollY가 더 이상 변하지 않을 때까지 반복 스크롤 (lazy 렌더링 대응)"""
    no_change_count = 0
    while True:
        before_height = await page.evaluate("document.body.scrollHeight")
        before_y = await page.evaluate("window.scrollY")
        await page.evaluate("window.scrollBy(0, 300)")
        await page.wait_for_timeout(1000)
        after_y = await page.evaluate("window.scrollY")

        if after_y == before_y:
            no_change_count += 1
            if no_change_count >= 3:
                await page.wait_for_timeout(4000)
                after_height = await page.evaluate("document.body.scrollHeight")
                if after_height > before_height:
                    print(f"  [lazy] 새 콘텐츠 렌더링 감지 ({before_height} → {after_height}), 스크롤 재개")
                    log_file.flush()
                    no_change_count = 0
                else:
                    break
        else:
            no_change_count = 0


async def goto_with_retry(page, url: str, retries: int = 3, wait_sec: int = 10):
    for attempt in range(1, retries + 1):
        try:
            await page.goto(url, timeout=30000)
            return
        except Exception as e:
            print(f"  [goto] 시도 {attempt}/{retries} 실패: {e}")
            log_file.flush()
            if attempt < retries:
                await page.wait_for_timeout(wait_sec * 1000)
    raise Exception(f"goto 실패 ({retries}회 재시도 후): {url}")


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
      → 5초 내 #photo-container 자식 div(spinner 제외) 증가 시 재개
      → 5초 내 증가 없으면 다운로드 시작
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

            deadline = loop.time() + 8
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
                break
            continue

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
        # print(f"  [scroll] center={state}")
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


async def collect_and_download(page, post_id: str, save_dir: str) -> int:
    downloaded_count = 0
    loop = asyncio.get_event_loop()

    await auto_scroll_until_div_pt2(page)

    pairs = await page.eval_on_selector_all(
        "div.position-relative.d-inline-block > a[data-fancybox='gallery']",
        """els => els.map(a => [
            a.getAttribute('href'),
            a.querySelector('img') ? a.querySelector('img').getAttribute('src') : null
        ]).filter(p => p[0])"""
    )

    seen = {}
    for href, _ in pairs:
        seen[href] = seen.get(href, 0) + 1
    duplicates = {url: cnt for url, cnt in seen.items() if cnt > 1}
    print(f"  [collect] a태그={len(pairs)}개  unique={len(seen)}개  중복={len(duplicates)}건")
    for url, cnt in duplicates.items():
        print(f"  [dup] {cnt}회 등장: {url}")
    log_file.flush()

    for href, src in pairs:
        if await loop.run_in_executor(None, download_image, href, save_dir, post_id, src):
            downloaded_count += 1

    return downloaded_count


async def async_crawl_cos():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--window-size=1280,900"],
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        # ── 1. 목록 페이지: 바닥까지 스크롤 ──────────────────────────────
        print(f"목록 페이지 이동: {BASE_URL}")
        await page.goto(BASE_URL, timeout=30000)
        await page.wait_for_timeout(3000)

        print("바닥까지 스크롤 중...")
        await scroll_to_bottom(page)
        print("스크롤 완료 · 30초 대기...")
        await page.wait_for_timeout(30000)

        # ── 2. grid-item 링크 수집 후 출력 ───────────────────────────────
        cos_base = COS_URL.rstrip('/')
        post_urls = await page.eval_on_selector_all(
            "div.grid-item.p-0.m-0[onclick]",
            f"""els => els.map(el => {{
                const m = el.getAttribute('onclick').match(/location\\.href='([^']+)'/);
                return m ? '{cos_base}' + m[1] : null;
            }}).filter(Boolean)"""
        )
        print(f"\n▶ 수집된 게시글 수: {len(post_urls)}")
        for idx, u in enumerate(post_urls, 1):
            print(f"  [{idx:>3}] {u}")
        log_file.flush()

        # ── 3. 각 게시글 순회 ─────────────────────────────────────────────
        total_downloaded = 0

        account = BASE_URL.rstrip('/').split('/')[-1]  # Rumi
        account_dir = os.path.join(COS_DIR, account)
        os.makedirs(account_dir, exist_ok=True)
        # print(f"저장 경로: {account_dir}")
        log_file.flush()

        for i, post_url in enumerate(post_urls, start=1):
            try:
                full_url = post_url.split('?')[0]
                post_id = full_url.split('/')[-1]
                check_path = '/' + '/'.join(full_url.split('/')[3:])  # /kr/post/101114
                print(f"\n{'='*60}")
                print(f"[{i}/{len(post_urls)}] {full_url}  (post_id={post_id})")
                log_file.flush()

                # 수집한 적이 있는지 확인
                try:
                    res = requests.get(
                        "https://chickchick.kr/func/scrap-posts?urls=" + check_path,
                        timeout=(3, 10)
                    )
                    if res.json().get("result"):
                        print(f"  Skip: 이미 수집된 URL")
                        log_file.flush()
                        continue
                except Exception as e:
                    print(f"  중복 체크 실패 (계속 진행): {e}")
                    log_file.flush()

                await goto_with_retry(page, full_url)
                await page.wait_for_timeout(5000)

                count = await collect_and_download(page, post_id, account_dir)
                print(f"  ✅ 이번 게시글 다운로드: {count}개")
                total_downloaded += count
                log_file.flush()

                # 수집 후 URL 등록
                try:
                    requests.post(
                        'https://chickchick.kr/func/scrap-posts',
                        json={
                            "account": account,
                            "post_urls": full_url,
                            "type": 'cos',
                        },
                        timeout=(3, 20)
                    )
                except Exception as e:
                    print(f"  URL 등록 실패: {e}")
                    log_file.flush()

            except Exception as e:
                print(f"  ❌ 오류: {e}")
                log_file.flush()

        # ── 4. 최종 집계 ─────────────────────────────────────────────────
        print(f"\n{'='*60}")
        print(f"▶ 전체 완료")
        print(f"▶ 처리 게시글 수 : {len(post_urls)}개")
        print(f"▶ 총 다운로드 수  : {total_downloaded}개")
        # print(f"▶ 저장 경로       : {account_dir}")
        log_file.flush()

        await browser.close()

    log_file.close()


loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
try:
    loop.run_until_complete(async_crawl_cos())
finally:
    loop.close()
    os._exit(0)  # anyio atexit 스레드 풀 경고 방지
