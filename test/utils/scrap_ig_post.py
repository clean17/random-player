import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

# ======== 설정 ========
USER_DATA_DIR = str(Path("./ig_profile").resolve())  # 세션 저장 (2회차부터 자동 로그인)
HEADLESS = False

USERNAME = "fkaus015"   # 인스타 로그인 계정
PASSWORD = ""   # 비밀번호

POST_URLS = [
    "https://www.instagram.com/fkaus014/p/DOuWTchj75b/",   # 테스트할 포스트 URI
]

async def ensure_login(page):
    await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
    # 로그인 폼 보이면 로그인
    login_user = page.locator("input[name='username']")
    login_pass = page.locator("input[name='password']")
    if await login_user.count() and await login_pass.count():
        await login_user.fill(USERNAME)
        await login_pass.fill(PASSWORD)
        await login_pass.press("Enter")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        # 팝업 닫기
        for txt in ["나중에 하기", "Not Now"]:
            btn = page.locator(f"button:has-text('{txt}')")
            if await btn.count():
                await btn.click()
                await asyncio.sleep(0.5)



# 컨테이너: section > main > div:first-child > div:first-child > div[role="presentation"] > ul > li > img
UL_SEL   = "section main > div:nth-of-type(1) > div:nth-of-type(1) div[role='presentation'] ul"
LI_SEL   = UL_SEL + " > li"
IMG_SEL  = UL_SEL + " > li img"
FALLBACK_IMG  = "section main > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) > div:nth-of-type(1) img"
NEXT_BTN_SEL  = (
    "section main > div:nth-of-type(1) > div:nth-of-type(1) "
    "button[aria-label*='다음'], :has(button:has-text('다음')), "
    "button[aria-label*='Next'], :has(button:has-text('Next'))"
)

async def extract_imgs_src_only(page, post_url: str):
    await page.goto(post_url, wait_until="domcontentloaded")

    # ===== 1) 기본 컨테이너 대기 (없으면 fallback로 진입) =====
    ul_found = False
    try:
        await page.wait_for_selector(UL_SEL, timeout=20000)
        ul_found = True
    except Exception:
        ul_found = False

    # ===== 공통: 이미지 한 번에 최대 해상도만 수집하는 헬퍼 =====
    async def collect_max_images(selector: str):
        # lazy-load 유도: 마지막 항목 스크롤 (가능할 때만)
        try:
            n = await page.locator(selector).count()
            if n > 0:
                await page.locator(selector).nth(n - 1).scroll_into_view_if_needed()
        except:
            pass

        urls = await page.evaluate(
            """
            (sel) => {
              // srcset에서 가장 큰 width를 가진 URL 선택
              const pickLargestFromSrcset = (img) => {
                const ss = img.getAttribute('srcset');
                if (!ss) return null;
                // "url 300w, url 600w ..." 파싱
                const items = ss.split(',')
                  .map(s => s.trim())
                  .map(entry => {
                    const [u, d] = entry.split(/\s+/);
                    let w = 0;
                    if (d && d.endsWith('w')) {
                      const n = parseInt(d.slice(0, -1), 10);
                      if (!isNaN(n)) w = n;
                    }
                    return { url: u, w };
                  })
                  .filter(it => it.url);

                if (!items.length) return null;
                // width 가장 큰 항목
                items.sort((a, b) => b.w - a.w);
                return items[0].url;
              };

              const preferAttrs = (img) => {
                // 몇몇 사이트의 원본 속성들
                const candAttrs = [
                  'data-src-large', 'data-src-2x', 'data-large', 'data-original',
                  'data-srcset', 'data-fullsrc', 'data-full', 'data-url'
                ];
                for (const a of candAttrs) {
                  const v = img.getAttribute(a);
                  if (v) return v;
                }
                return null;
              };

              const imgs = Array.from(document.querySelectorAll(sel));
              // 각 IMG마다 "가장 큰 것"만 1개 선택
              return imgs.map(img => {
                  return pickLargestFromSrcset(img)
                      || preferAttrs(img)
                      || img.currentSrc
                      || img.getAttribute('src');
              }).filter(Boolean);
            }
            """,
            selector
        )
        return urls

    seen = set()

    if ul_found:
        # ===== 2) 기본 캐러셀 처리: 클릭 전-수집 누적 방식 =====
        async def collect_from_main():
            # 캐러셀 내부 IMG에서만 수집 (최대해상도 선택)
            urls = await collect_max_images(IMG_SEL)
            for u in urls:
                seen.add(u)

        await collect_from_main()

        # "다음" 클릭 반복 (클릭 전 수집 → 클릭 → 잠깐 대기)
        for _ in range(20):
            next_btn = page.locator(NEXT_BTN_SEL).first
            if not await next_btn.count():
                break

            # 클릭 전 수집(현재 화면)
            await collect_from_main()

            # 클릭
            try:
                await next_btn.click(timeout=1000)
            except:
                try:
                    await next_btn.click(timeout=1000, force=True)
                except:
                    break

            await asyncio.sleep(0.35)

        # 마지막 한 번 더
        await collect_from_main()

    else:
        # ===== 3) Fallback: 전체 영역에서 IMG 수집 (최대해상도만) =====
        # section main 이 없을 수도 있으니 즉시 검사
        has_any_img = await page.locator(FALLBACK_IMG).count()
        if not has_any_img:
            # 정말로 이미지가 전혀 없다면 패스
            # print(f"[INFO] {post_url}: 이미지 없음 (UL도 IMG도 못 찾음)")
            return []

        urls = await collect_max_images(FALLBACK_IMG)
        seen.update(urls)

    # ===== 4) (선택) 추가 중복 축소: 사이즈 파라미터 무시 키로 병합 =====
    # 같은 사진인데 ?w=, ?h=, =s2048 등만 다른 경우를 더 줄이고 싶다면 사용
    import re
    def norm(u: str) -> str:
        # 아주 보수적으로 몇 가지 사이즈 토큰만 제거
        #  - Google 계열: "=s1234" 꼬리 토큰
        u2 = re.sub(r'(=s\d+)(?=$)', '', u)
        #  - 흔한 width/height 쿼리파라미터 제거 (다른 토큰 보존)
        u2 = re.sub(r'([?&])(w|width|h|height|size|s)=\d+(?=(&|$))', r'\1', u2, flags=re.I)
        u2 = re.sub(r'[?&]+$', '', u2)
        return u2

    best_by_key = {}
    for u in seen:
        key = norm(u)
        # 같은 키면 더 긴(대체로 고해상도) URL을 보존하는 간단 규칙
        if key not in best_by_key or len(u) > len(best_by_key[key]):
            best_by_key[key] = u

    final_urls = list(best_by_key.values())

    # 로그
    print(f"\n=== {post_url} ===")
    for i, u in enumerate(final_urls, 1):
        print(f"[IMG {i}] {u}")

    return final_urls

# async def extract_imgs_src_only(page, post_url: str):
#     await page.goto(post_url, wait_until="domcontentloaded")
#
#     # ul 등장 대기
#     await page.wait_for_selector(UL_SEL, timeout=20000)
#
#     for _ in range(10):
#         next_btn = page.locator(NEXT_BTN_SEL)
#         if not await next_btn.count():
#             break
#         try:
#             await next_btn.click()
#             await asyncio.sleep(0.6)
#         except:
#             break
#
#     # li 개수(참고용)
#     try:
#         li_count = await page.locator(LI_SEL).count()
#         print('li_count', li_count)
#     except:
#         li_count = 0
#
#     # 몇 번만 재시도하면서 img src 수집 (lazy-load/지연 렌더 대비)
#     urls = []
#     for _ in range(8):
#         # li 마지막을 한 번 보이게 해서 lazy-load 유도
#         if li_count > 0:
#             await page.locator(LI_SEL).nth(li_count - 1).scroll_into_view_if_needed()
#
#         urls = await page.evaluate("""
#         (sel) => {
#           const pickBestFromSrcset = (img) => {
#             const ss = img.getAttribute('srcset');
#             if (!ss) return null;
#             const parts = ss.split(',').map(s => s.trim().split(' ')[0]).filter(Boolean);
#             return parts.length ? parts[parts.length - 1] : null;
#           };
#           const imgs = Array.from(document.querySelectorAll(sel));
#           return imgs.map(img => img.currentSrc || img.getAttribute('src') || pickBestFromSrcset(img))
#                      .filter(Boolean);
#         }
#         """, IMG_SEL)
#
#         # li 수만큼 모였으면 종료 (아니어도 일단 다음 루프)
#         if li_count and len(urls) >= li_count:
#             break
#
#         await asyncio.sleep(0.3)
#
#     # 콘솔 출력
#     print(f"\n=== {post_url} ===")
#     for i, u in enumerate(urls, 1):
#         print(f"[IMG {i}] {u}")
#
#     return urls

async def main():
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=HEADLESS,
            viewport={"width": 900, "height": 480},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        page = await context.new_page()

        # 로그인 보장
        await ensure_login(page)

        # 지정한 포스트들 처리
        for url in POST_URLS:
            await extract_imgs_src_only(page, url)

        await context.close()

if __name__ == "__main__":
    asyncio.run(main())