import time
from playwright.sync_api import Playwright, sync_playwright
from playwright.async_api import Playwright, async_playwright
from config import settings

USER_ID = settings['LOTTO_USER_ID']
USER_PW = settings['LOTTO_PASSWORD']

COUNT = 1 # 구매 수량

def buy_lotto(playwright: Playwright) -> None:

    # chrome 브라우저를 실행
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()

    # Open new page
    page = context.new_page()

    # Go to https://dhlottery.co.kr/user.do?method=login
    page.goto("https://dhlottery.co.kr/user.do?method=login")

    # Click [placeholder="아이디"]
    page.click("[placeholder=\"아이디\"]")

    # Fill [placeholder="아이디"]
    page.fill("[placeholder=\"아이디\"]", USER_ID)

    # Press Tab
    page.press("[placeholder=\"아이디\"]", "Tab")

    # Fill [placeholder="비밀번호"]
    page.fill("[placeholder=\"비밀번호\"]", USER_PW)

    # Press Tab
    page.press("[placeholder=\"비밀번호\"]", "Tab")

    # Press Enter
    # with page.expect_navigation(url="https://ol.dhlottery.co.kr/olotto/game/game645.do"):
    with page.expect_navigation():
        page.press("form[name=\"jform\"] >> text=로그인", "Enter")

    time.sleep(5)

    page.goto(url="https://ol.dhlottery.co.kr/olotto/game/game645.do")
    # "비정상적인 방법으로 접속하였습니다. 정상적인 PC 환경에서 접속하여 주시기 바랍니다." 우회하기
    # page.locator("#popupLayerAlert").get_by_role("button", name="확인").click()
    # print(page.content())

    # Click text=자동번호발급
    page.click("text=자동번호발급")
    #page.click('#num2 >> text=자동번호발급')

    # 구매할 개수를 선택
    # Select 1
    page.select_option("select", str(COUNT))

    # Click text=확인
    page.click("text=확인")

    # Click input:has-text("구매하기")
    page.click("input:has-text(\"구매하기\")")

    time.sleep(2)
    # Click text=확인 취소 >> input[type="button"]
    page.click("text=확인 취소 >> input[type=\"button\"]")

    # Click input[name="closeLayer"]
    page.click("input[name=\"closeLayer\"]")
    # assert page.url == "https://el.dhlottery.co.kr/game/TotalGame.jsp?LottoId=LO40"

    print(f'### 로또 자동 {COUNT}장 구매 완료 !!')
    # ---------------------
    context.close()
    browser.close()

# with sync_playwright() as playwright:
#     buy_lotto(playwright) # ✅ 모듈이 import될 때 자동 실행됨!
if __name__ == "__main__":
    with sync_playwright() as playwright:
        buy_lotto(playwright)  # ✅ import해도 실행되지 않음


# task_manager.py 에서 호출
async def run(playwright):
    """비동기 Playwright 로또 구매 실행"""
    print('### 로또 구매 시작')
    browser = await playwright.chromium.launch(headless=True)  # await 추가
    context = await browser.new_context()
    page = await context.new_page()

    # 로그인 페이지 이동
    await page.goto("https://dhlottery.co.kr/user.do?method=login")

    # 아이디 & 비밀번호 입력
    await page.fill("[placeholder=\"아이디\"]", USER_ID)
    await page.press("[placeholder=\"아이디\"]", "Tab")
    await page.fill("[placeholder=\"비밀번호\"]", USER_PW)
    await page.press("[placeholder=\"비밀번호\"]", "Tab")

    # 로그인 버튼 클릭
    async with page.expect_navigation():
        await page.press("form[name=\"jform\"] >> text=로그인", "Enter")

    # 로또 구매 페이지 이동
    await page.goto("https://ol.dhlottery.co.kr/olotto/game/game645.do")
    await page.wait_for_load_state("networkidle")

    # 자동번호 발급 클릭
    await page.wait_for_selector("text=자동번호발급")
    await page.click("text=자동번호발급")

    # 구매 개수 선택
    await page.wait_for_selector("select")
    await page.select_option("select", str(COUNT))

    # 확인 버튼 클릭
    await page.wait_for_selector("text=확인")
    await page.click("text=확인")

    # 구매하기 버튼 클릭
    await page.wait_for_selector("input:has-text(\"구매하기\")")
    await page.click("input:has-text(\"구매하기\")")

    # 최종 확인 버튼 클릭
    await page.wait_for_selector("text=확인 취소 >> input[type=\"button\"]")
    await page.click("text=확인 취소 >> input[type=\"button\"]")

    # 닫기
    await page.wait_for_selector("input[name=\"closeLayer\"]")
    await page.click("input[name=\"closeLayer\"]")

    print(f'### async_buy_lotto 자동 {COUNT}장 구매 완료 ###')

    await context.close()
    await browser.close()

async def async_buy_lotto():
    async with async_playwright() as playwright:
        await run(playwright)  # ✅ 올바른 await 사용