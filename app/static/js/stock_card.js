const TRADING_TABLE_HTML = `
<table class="table" id="table-trading">
  <thead>
    <tr>
      <th>그래프</th>
      <th>등록시간</th>
      <th>종목명</th>
      <th>카테고리</th>
      <th class="right">거래대금(5일 평균)</th>
      <th class="right">거래대금(실시간)</th>
      <th class="right">거래대금 증감</th>
      <th class="right">전일종가</th>
      <th class="right">현재가</th>
      <th class="right">금일 등락</th>
    </tr>
  </thead>
  <tbody><!-- JS 렌더링 --></tbody>
</table>
`;

const SUMMARY_TABLE_HTML = `
<table class="table" id="table-summary">
    <thead>
    <tr>
        <th>그래프</th>
        <th>카운트</th>
        <th>종목명</th>
        <th>카테고리</th>
        <th>시작가</th>
        <th>최근 종가</th>
        <th>전체_상승률</th>
        <th>(전체/카운트)<br>
            ⭐(10%⬇️)</th> <!-- increase_per_day -->
        <th>최고_대비_변동</th>
        <th>시가총액<br>(1조⬇️)</th>
        <th>거래대금<br>(평균)</th> <!-- avg_trading_value -->
        <th class="right">마지막_상승일자</th>
    </tr>
    </thead>
    <tbody><!-- JS 렌더링 --></tbody>
</table>
`;

const LOW_TABLE_HTML = `
<table class="table" id="table-low">
    <thead>
    <tr>
        <th>그래프</th>
        <th>종목명</th>
        <th>카테고리</th>
        <th>시가총액</th>
        <th class="right">거래대금(금일)</th>
        <th>금일 등락률</th>
        <th>어제 종가</th>
        <th>금일 종가</th>
        <th class="right">현재가</th>
        <th class="right">현재 등락</th>
    </tr>
    </thead>
    <tbody><!-- JS 렌더링 --></tbody>
</table>
`;

let globalTradingRows = [];
let leftCarouselBtn;
let rightCarouselBtn;
let firstCarouselDot;
let lastCarouselDot;


// ---------- 안전 변환/포맷터 ----------
const toFloat = (v) => {
    if (v === null || v === undefined || v === "") return null;
    const num = parseFloat(v);         // parseFloat: 문자열을 숫자로 변환.. "42px" > 42
    return Number.isFinite(num) ? num : null;   // 유한한 숫자인지 확인.. NaN, Infinity, -Infinity는 걸러져서 null 반환
};

function hhmmFromRfc1123Gmt(s) {
    // "Mon, 29 Dec 2025 17:35:18 GMT"
    const m = s.match(/\b(\d{2}):(\d{2}):\d{2}\b/);
    return m ? `${m[1]}:${m[2]}` : "";
}

// 한국어(ko-KR) 로컬 기준의 시간 포맷터
const timeFmt = new Intl.DateTimeFormat("ko-KR", {
    hour: "2-digit",     // 시(hour)를 두 자리로 표시 (예: 09, 13)
    minute: "2-digit",   // 분(minute)을 두 자리로 표시 (예: 05, 45)
    hour12: false,       // 24시간제 사용 (true면 오전/오후 12시간제)
});

const now = new Date("2025-12-21T22:55:00");
// console.log(timeFmt.format(now));
// 출력: "22:55"

const d = new Date("2025-12-21");

const year = d.getFullYear();
const month = String(d.getMonth() + 1).padStart(2, "0");
const day = String(d.getDate()).padStart(2, "0");

// console.log(`${year}-${month}-${day}`); // 2025-12-21
// console.log(`${year}.${month}.${day}`); // 2025.12.21


// 소수점 둘째 자리까지 포맷팅
function fmt2(v) {
    const num = toFloat(v);
    if (num === null) return "";
    const s = num.toFixed(2);       // 소수점 둘째 자리까지 문자열로 변환
    return s.endsWith(".00")                            // 끝이 00이면 정수로
        ? String(Math.round(num))
        : s.replace(/0$/, "");   // 끝이 0이면 제거
}

function fmt_won(v) {
    const num = toFloat(v);
    if (num === null) return "";
    return `${Math.round(num).toLocaleString("ko-KR")}원`;
}

function fastScrollTo(el, left, duration = 60) {
    const start = el.scrollLeft;
    const change = left - start;
    const startTime = performance.now();

    // easeOutCubic
    const ease = (t) => 1 - Math.pow(1 - t, 3);

    function step(now) {
        const t = Math.min(1, (now - startTime) / duration);
        el.scrollLeft = start + change * ease(t);
        if (t < 1) requestAnimationFrame(step);
    }

    requestAnimationFrame(step);
}


// ---------- 메인 ----------
function renderTradingCardHtml(track, rows) {
    if (!track) return;

    track.innerHTML = rows.map((r, idx) => {
        /*const ts = Date.parse(r.created_at);
        const date = Number.isFinite(ts) ? new Date(ts) : new Date();
        const formatted_time = timeFmt.format(date);*/
        const formatted_time = hhmmFromRfc1123Gmt(r.created_at);

        const avg5d = toFloat(r.avg5d_trading_value) ?? 0;
        const curTv = toFloat(r.current_trading_value) ?? 0;
        const tvChg = toFloat(r.trading_value_change_pct) ?? 0;
        const yClose = toFloat(r.yesterday_close) ?? 0;
        // const cPrice = toFloat(r.current_price) ?? 0;
        const cPrice = toFloat(r.close) ?? 0;
        const pChg = toFloat(r.today_price_change_pct) ?? 0;

        const hasImg = !!r.graph_file;
        const encoded_url = encodeURIComponent(String(r.graph_file ?? ""));
        const imgHtml = hasImg
            ? `<img class="preview" src="https://chickchick.kr/image/stock-graphs/interest/${encoded_url}" alt="미리보기" />`
            : `<span class="hint">그래프 없음</span>`;

        return `
      <article class="trade-card" data-index="${idx}">

        <div class="trade-top">
          <img class="trade-logo" src="${r.logo_image_url}" alt="로고"/>
          <div class="trade-text">
            <div class="trade-name">${r.stock_name ?? ""}</div>
            <div class="trade-sub">${r.stock_code ?? ""} · 시총 ${r.market_value_fmt ?? ""} · ${r.category ?? ""}</div>
          </div>
          <div class="fav-toggle">
            <button
              class="fav-btn"
              data-stock-code="${r.stock_code ?? ""}"
              data-favorited="false"
              data-shape="star"
              aria-pressed="false"
              aria-label="즐겨찾기 추가"
            ></button>
          </div>
        </div>

        <div class="trade-grid">
          <div class="kv"><span class="k">5일평균 거래대금</span><span class="v">${fmt_won(avg5d)}</span></div>
          <div class="kv"><span class="k">현재거래대금</span><span class="v">${fmt_won(curTv)}</span></div>
          <div class="kv"><span class="k">전일종가</span><span class="v">${Math.round(yClose).toLocaleString("ko-KR")}원</span></div>
          <div class="kv"><span class="k">현재가</span><span class="v">${Math.round(cPrice).toLocaleString("ko-KR")}원</span></div>
          <div class="kv"><span class="k">거래대금 변동율</span><span class="v">${fmt2(tvChg)}%</span></div>
          <div class="kv"><span class="k">등락률</span><span class="v">${fmt2(pChg)}%</span></div>
        </div>

        <div class="trade-detail" style="margin-top:10px;">
          ${imgHtml}
        </div>
      </article>
    `;
    }).join("");

    const countEl = document.getElementById("count");
    if (countEl) countEl.textContent = `${rows.length}건`;
}

function renderSummaryCardHtml(track, rows) {
    if (!track) return;

    const pad2 = (n) => String(n).padStart(2, "0");
    const fmtDate = (d) => {
        if (!(d instanceof Date) || Number.isNaN(d.getTime())) return "";
        // return `${d.getFullYear()}.${pad2(d.getMonth() + 1)}.${pad2(d.getDate())}`;
        return `${pad2(d.getMonth() + 1)}.${pad2(d.getDate())}`;
    };

    track.innerHTML = rows.map((r, idx) => {
        // 날짜
        const d1 = new Date(String(r.first_date ?? ""));
        const d2 = new Date(String(r.last_date ?? ""));
        const formatted_date1 = fmtDate(d1);
        const formatted_date2 = fmtDate(d2);

        const hasImg = !!r.graph_file;
        const encoded_url = encodeURIComponent(String(r.graph_file ?? ""));
        const imgHtml = hasImg
            ? `<img class="preview" src="https://chickchick.kr/image/stock-graphs/interest/${encoded_url}" alt="미리보기" />`
            : `<span class="hint">그래프 없음</span>`;

        return `
      <article class="trade-card summary-card" data-index="${idx}">
        <div class="trade-top">
          <img class="trade-logo" src="${r.logo_image_url}" alt="로고"/>
          <div class="trade-text">
            <div class="trade-name">${r.stock_name ?? ""}</div>
            <div class="trade-sub">${r.stock_code ?? ""} · 시총 ${r.market_value ?? ""} · ${r.category ?? ""}</div>
          </div>
          <div class="fav-toggle">
            <button
              class="fav-btn"
              data-stock-code="${r.stock_code ?? ""}"
              data-favorited="false"
              data-shape="star"
              aria-pressed="false"
              aria-label="즐겨찾기 추가"
            ></button>
          </div>
        </div>

        <div class="trade-grid">
          <div class="kv"><span class="k">출현횟수</span><span class="v">${r.count ?? ""}</span></div>
          <div class="kv"><span class="k">구간</span><span class="v">${formatted_date1} ~ ${formatted_date2}</span></div>
          <!--<div class="kv"><span class="k">시총</span><span class="v">${r.market_value ?? ""}</span></div>-->
          <div class="kv"><span class="k">거래(평균)</span><span class="v">${r.current_trading_value ?? ""}/${r.avg_trading_value ?? ""}</span></div>
          <div class="kv"><span class="k">종가</span><span class="v">${fmt2(r.min)} ➡️ ${fmt2(r.last)}</span></div>
          <div class="kv"><span class="k">총상승</span><span class="v">${r.total_rate_of_increase ?? ""}</span></div>
          <div class="kv"><span class="k">일상승(총/출현횟수)</span><span class="v">${r.increase_per_day ?? ""}</span></div>
        </div>

        <div class="trade-detail" style="margin-top:10px;">
          ${imgHtml}
        </div>
      </article>
    `;
    }).join("");

    const countEl = document.getElementById("count");
    if (countEl) countEl.textContent = `${rows.length}건`;
}

function renderFavoriteCardHtml(track, rows) {
    if (!track) return;

    const pad2 = (n) => String(n).padStart(2, "0");
    const fmtDate = (d) => {
        if (!(d instanceof Date) || Number.isNaN(d.getTime())) return "";
        // return `${d.getFullYear()}.${pad2(d.getMonth() + 1)}.${pad2(d.getDate())}`;
        return `${pad2(d.getMonth() + 1)}.${pad2(d.getDate())}`;
    };

    track.innerHTML = rows.map((r, idx) => {
        // 날짜
        const d1 = new Date(String(r.first_date ?? ""));
        const d2 = new Date(String(r.last_date ?? ""));
        const formatted_date1 = fmtDate(d1);
        const formatted_date2 = fmtDate(d2);

        const hasImg = !!r.graph_file;
        const encoded_url = encodeURIComponent(String(r.graph_file ?? ""));
        const imgHtml = hasImg
            ? `<img class="preview" src="https://chickchick.kr/image/stock-graphs/interest/${encoded_url}" alt="미리보기" />`
            : `<span class="hint">그래프 없음</span>`;

        return `
      <article class="trade-card summary-card" data-index="${idx}">
        <div class="trade-top">
          <img class="trade-logo" src="${r.logo_image_url}" alt="로고"/>
          <div class="trade-text">
            <div class="trade-name">${r.stock_name ?? ""}</div>
            <div class="trade-sub">${r.stock_code ?? ""} · 시총 ${r.market_value ?? ""} · ${r.category ?? ""}</div>
          </div>
          <div class="fav-toggle">
            <button
              class="fav-btn"
              data-stock-code="${r.stock_code ?? ""}"
              data-favorited="false"
              data-shape="star"
              aria-pressed="false"
              aria-label="즐겨찾기 추가"
            ></button>
          </div>
        </div>

        <div class="trade-grid">
          <div class="kv"><span class="k">출현횟수</span><span class="v">${r.count ?? ""}</span></div>
          <div class="kv"><span class="k">구간</span><span class="v">${formatted_date1} ~ ${formatted_date2}</span></div>
          <!--<div class="kv"><span class="k">시총</span><span class="v">${r.market_value ?? ""}</span></div>-->
          <div class="kv"><span class="k">거래(평균)</span><span class="v">${r.current_trading_value ?? ""}/${r.avg_trading_value ?? ""}</span></div>
          <div class="kv"><span class="k">종가</span><span class="v">${fmt2(r.min)} ➡️ ${fmt2(r.last)}</span></div>
          <div class="kv"><span class="k">총상승</span><span class="v">${r.total_rate_of_increase ?? ""}</span></div>
          <div class="kv"><span class="k">일상승(총/출현횟수)</span><span class="v">${r.increase_per_day ?? ""}</span></div>
        </div>

        <div class="trade-detail" style="margin-top:10px;">
          ${imgHtml}
        </div>
      </article>
    `;
    }).join("");

    const countEl = document.getElementById("count");
    if (countEl) countEl.textContent = `${rows.length}건`;
}


function renderLowCardHtml(track, rows) {
    if (!track) return;

    track.innerHTML = rows.map((r, idx) => {
        // 시간
        /*const ts = Date.parse(r.created_at);
        const date = Number.isFinite(ts) ? new Date(ts) : new Date();
        const formatted_time = timeFmt.format(date); // "HH:mm"*/
        const formatted_time = hhmmFromRfc1123Gmt(r.created_at);

        // 숫자 문자열 안전 변환(있으면 사용)
        const curTv  = toFloat(r.current_trading_value) ?? 0;
        const pChg   = toFloat(r.today_price_change_pct) ?? 0;
        const yClose = toFloat(r.yesterday_close) ?? 0;
        // const cPrice = toFloat(r.current_price) ?? 0;
        const cPrice = toFloat(r.close) ?? 0;

        // 이미지
        const hasImg = !!r.graph_file;
        const encoded_url = encodeURIComponent(String(r.graph_file ?? ""));
        const imgHtml = hasImg
            ? `<img class="preview" src="https://chickchick.kr/image/stock-graphs/kospil/${encoded_url}" alt="미리보기" />`
            : `<span class="hint">그래프 없음</span>`;

        return `
      <article class="trade-card low-card" data-index="${idx}">
        <div class="trade-top">
          <img class="trade-logo" src="${r.logo_image_url}" alt="로고"/>
          <div class="trade-text">
            <div class="trade-name">${r.stock_name ?? ""}</div>
            <div class="trade-sub">${r.stock_code ?? ""} · 시총 ${r.market_value ?? ""} · ${r.category ?? ""}</div>
          </div>
          <div class="fav-toggle">
            <button
              class="fav-btn"
              data-stock-code="${r.stock_code ?? ""}"
              data-favorited="false"
              data-shape="star"
              aria-pressed="false"
              aria-label="즐겨찾기 추가"
            ></button>
          </div>
        </div>

        <div class="trade-grid">
<!--          <div class="kv"><span class="k">시가총액</span><span class="v">${r.market_value ?? ""}</span></div>-->          
          <div class="kv"><span class="k">전일종가</span><span class="v">${Math.round(yClose).toLocaleString("ko-KR")}원</span></div>
          <div class="kv"><span class="k">현재가</span><span class="v">${Math.round(cPrice).toLocaleString("ko-KR")}원</span></div>
          <div class="kv"><span class="k">금일 거래대금</span><span class="v">${fmt_won(curTv)}</span></div>
          <div class="kv"><span class="k">등락률</span><span class="v">${fmt2(pChg)}%</span></div>
          <!--<div class="kv"><span class="k">비고</span><span class="v"></span></div>-->
        </div>

        <div class="trade-detail" style="margin-top:10px;">
          ${imgHtml}
        </div>
      </article>
    `;
    }).join("");

    const countEl = document.getElementById("count");
    if (countEl) countEl.textContent = `${rows.length}건`;
}


function renderTradingCards(rows, section, tableName) {
    const root = section.querySelector(".table-scroller");
    if (!root) {
        console.warn('[renderTradingCards] .table-scroller 요소가 없습니다.');
        return;
    }

    const countEl = document.getElementById('count');

    if (!rows || !rows.length) {
        root.innerHTML = `<div class="trade-card">데이터가 없습니다.</div>`;
        if (countEl) countEl.textContent = "0건";
        return;
    }

    root.innerHTML = `
    <div class="trade-carousel" style="position:relative;">
      <button type="button" class="carousel-btn left" aria-label="prev"><span class="chev">‹</span></button>
      <div class="trade-track"></div>
      <button type="button" class="carousel-btn right" aria-label="next"><span class="chev">›</span></button>
    </div>
    <div class="dots"></div>
  `;

    const track = root.querySelector(".trade-track");
    const dots  = root.querySelector(".dots");
    const btnL  = root.querySelector(".carousel-btn.left");
    const btnR  = root.querySelector(".carousel-btn.right");

    if (tableName === 'table-trading') renderTradingCardHtml(track, rows);
    if (tableName === 'table-summary') renderSummaryCardHtml(track, rows);
    if (tableName === 'table-low') renderLowCardHtml(track, rows);
    if (tableName === 'table-favorite') renderFavoriteCardHtml(track, rows);
    initFavoriteButtons();

    // dots (많으면 12개로 축약)
    const maxDots = 12;
    const dotCount = Math.min(rows.length, maxDots);
    dots.innerHTML = Array.from({ length: dotCount }, (_, i) => `<span class="dot" data-dot="${i}"></span>`).join("");

    if (countEl) countEl.textContent = `${rows.length}건`;

    // ✅ 한 장씩 넘기기(= track.clientWidth 기준)
    const go = (dir) => {
        const page = track.clientWidth;            // 현재 보이는 폭
        track.scrollBy({ left: dir * page, behavior: "smooth" });   // 부드럽게

        // const left = track.scrollLeft + dir * page;
        // fastScrollTo(track, left, 120);
    };

    btnL.addEventListener("click", () => go(-1));
    btnR.addEventListener("click", () => go(1));

    // 드래그/스와이프
/*    let isDown = false, startX = 0, startScroll = 0;
    track.addEventListener("pointerdown", (e) => {
        isDown = true;
        startX = e.clientX;
        startScroll = track.scrollLeft;
        track.setPointerCapture(e.pointerId);
    });
    track.addEventListener("pointermove", (e) => {
        if (!isDown) return;
        track.scrollLeft = startScroll - (e.clientX - startX);
    });
    track.addEventListener("pointerup", () => { isDown = false; });
    track.addEventListener("pointercancel", () => { isDown = false; });*/

    // 드래그/스와이프 (클릭과 충돌 방지)
    let isDown = false;
    let isDragging = false;
    let startX = 0;
    let startScroll = 0;
    let pointerId = null;
    const DRAG_THRESHOLD = 6; // px: 이 이상 움직이면 드래그로 판단

    // 드래그 제외 대상(버튼/링크/인풋 등)
    function isInteractiveTarget(e) {
        return !!e.target.closest("button, a, input, select, textarea, .fav-btn, .carousel-btn");
    }

    track.addEventListener("pointerdown", (e) => {
        // ✅ 즐겨찾기 버튼 등 인터랙티브 요소에서 시작하면 캐러셀 드래그 안 함
        if (isInteractiveTarget(e)) return;

        isDown = true;
        isDragging = false;
        startX = e.clientX;
        startScroll = track.scrollLeft;
        pointerId = e.pointerId;

        // ✅ 여기서 캡처하지 마세요. (드래그 판정 후에 캡처)
    }, { passive: true });

    track.addEventListener("pointermove", (e) => {
        if (!isDown || e.pointerId !== pointerId) return;

        const dx = e.clientX - startX;

        // ✅ 일정 거리 이상 움직일 때만 드래그 시작 + 포인터 캡처
        if (!isDragging && Math.abs(dx) > DRAG_THRESHOLD) {
            isDragging = true;
            track.setPointerCapture(pointerId);
        }

        if (!isDragging) return;

        // 드래그 중 스크롤
        track.scrollLeft = startScroll - dx;
    }, { passive: true });

    track.addEventListener("pointerup", () => {
        isDown = false;
        isDragging = false;
        pointerId = null;
    });

    track.addEventListener("pointercancel", () => {
        isDown = false;
        isDragging = false;
        pointerId = null;
    });

    // 현재 인덱스/버튼/dot 업데이트
    function updateUI() {
        const page = Math.max(1, track.clientWidth);
        const idx = Math.round(track.scrollLeft / page);
        const activeDot = Math.floor((idx * dotCount) / rows.length);

        dots.querySelectorAll(".dot").forEach((d, i) => d.classList.toggle("active", i === activeDot));
        btnL.disabled = idx <= 0;
        btnR.disabled = idx >= rows.length - 1;

        leftCarouselBtn = btnL;
        rightCarouselBtn = btnR;

        const visibleSection = [...document.querySelectorAll('section')]
            .find(sec => getComputedStyle(sec).display === 'block');

        firstCarouselDot = visibleSection?.querySelector('.dots > :first-child');
        lastCarouselDot = visibleSection?.querySelector('.dots > :last-child');
    }

    track.addEventListener("scroll", () => {
        if (updateUI._raf) return;
        updateUI._raf = requestAnimationFrame(() => {
            updateUI._raf = null;
            updateUI();
        });
    });

    dots.addEventListener("click", (e) => {
        const dot = e.target.closest(".dot");
        if (!dot) return;
        const i = Number(dot.dataset.dot);
        const targetIndex = Math.round((i * (rows.length - 1)) / Math.max(1, dotCount - 1));
        track.scrollTo({ left: targetIndex * track.clientWidth, behavior: "smooth" });

        // const left = targetIndex * track.clientWidth;
        // fastScrollTo(track, left, 120);
    });

    // 리사이즈 시 정렬 깨짐 방지(현재 페이지에 스냅)
    window.addEventListener("resize", () => {
        const page = Math.max(1, track.clientWidth);
        const idx = Math.round(track.scrollLeft / page);
        // track.scrollTo({ left: idx * page, behavior: "auto" });
        track.scrollLeft = idx * page; // ✅ 더 빠름(즉시)
        updateUI();
    });

    updateUI();
}






function ensureTradingTableExists(section, tableName) {
    let table = document.getElementById(tableName);
    if (table) return table;

    const scroller = section.querySelector(".table-scroller");
    if (!table) {
        let tableHtml = undefined;
        if (tableName === 'table-trading') tableHtml = TRADING_TABLE_HTML;
        if (tableName === 'table-summary') tableHtml = SUMMARY_TABLE_HTML;
        if (tableName === 'table-low') tableHtml = LOW_TABLE_HTML;
        scroller.insertAdjacentHTML("beforeend", tableHtml);
    }
    return document.getElementById(tableName);
}

function removeTradingTable(tableName) {
    const table = document.getElementById(tableName);
    if (table) table.remove();
}

function removeTradingCards(section) {
    const scroller = section.querySelector(".table-scroller");
    scroller.innerHTML = '';
}


function renderTradingView(tradingRows) {
    globalTradingRows = tradingRows;

    // 요소 중 'display: none' 아닌 요소 찾기
    // const el = [...document.querySelectorAll('.view-toggle')]
    //     .find(x => x.offsetParent !== null);

    // const section = el.closest('section');

    const activeTable = document.querySelector('.tab-bar .tab-btn.active').dataset.target;
    const section = document.querySelector(activeTable);
    const tableName = 'table-'+section.id.split('-')[1];
    const viewToggleBtn = document.querySelector('.view-toggle .is-active');

    // if (el.dataset.view === "table") {
    if (viewToggleBtn.dataset.view === "table") {
        removeTradingCards(section);
        ensureTradingTableExists(section, tableName);
        if (tableName === 'table-trading') renderTradingTable(tradingRows, tableName);
        if (tableName === 'table-summary') renderSummaryTable(tradingRows, tableName);
        if (tableName === 'table-low') renderLowTable(tradingRows, tableName);
    } else {
        removeTradingTable(tableName);
        renderTradingCards(tradingRows, section, tableName);
    }
}



function setView(toggle, view, focus = false) {
    toggle.dataset.view = view;

    const btns = Array.from(toggle.querySelectorAll(".view-btn"));
    btns.forEach(b => {
        const active = b.dataset.view === view;
        b.classList.toggle("is-active", active);
        b.setAttribute("aria-selected", String(active));
        b.tabIndex = active ? 0 : -1;
        if (active && focus) b.focus();
    });

    renderTradingView(globalTradingRows);
}

// 드롭다운 변경 시 즉시 반영
setTimeout(()=>{
        document.querySelectorAll('.view-toggle').forEach((el)=>{
            el.addEventListener("click", (e) => {
                const btn = e.target.closest(".view-btn");
                if (!btn) return;
                setView(el, btn.dataset.view, true);
            });
        });

        document.addEventListener('keydown', function(event) {
            switch (event.key) {
                case 'ArrowLeft':
                    leftCarouselBtn.click();
                    break;
                case 'ArrowRight':
                    rightCarouselBtn.click();
                    break;
                case 'Home':
                    event.preventDefault();
                    firstCarouselDot.click();
                    break;
                case 'End':
                    event.preventDefault();
                    lastCarouselDot.click();
                    break;
                default:
                    break;
            }
        });
    }
    ,100)



// --- SVG 아이콘 템플릿 ---
function getIconSVG(shape, filled) {
    if (shape === "heart") {
        return filled
            ? `<svg class="fav-icon" viewBox="0 0 24 24" aria-hidden="true">
           <path fill="currentColor"
             d="M12 21s-7.2-4.6-9.6-8.6C.6 9.3 2.2 6.2 5.4 5.3c2.1-.6 4.2.3 6.6 2.8 2.4-2.5 4.5-3.4 6.6-2.8 3.2.9 4.8 4 3 7.1C19.2 16.4 12 21 12 21z"/>
         </svg>`
            : `<svg class="fav-icon" viewBox="0 0 24 24" aria-hidden="true">
           <path fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"
             d="M12 21s-7.2-4.6-9.6-8.6C.6 9.3 2.2 6.2 5.4 5.3c2.1-.6 4.2.3 6.6 2.8 2.4-2.5 4.5-3.4 6.6-2.8 3.2.9 4.8 4 3 7.1C19.2 16.4 12 21 12 21z"/>
         </svg>`;
    }

    // Star (default)
    // OFF=테두리 / ON=채움
    return filled
        ? `<svg class="fav-icon" viewBox="0 0 24 24" aria-hidden="true">
         <path fill="currentColor"
           d="M12 2.6c.4 0 .8.2 1 .6l2.4 4.9c.2.4.6.6 1 .7l5.4.8c.9.1 1.3 1.2.7 1.8l-3.9 3.8c-.3.3-.4.7-.3 1.1l.9 5.4c.2.9-.8 1.6-1.6 1.2l-4.8-2.5c-.4-.2-.8-.2-1.2 0L6.9 22c-.8.4-1.8-.3-1.6-1.2l.9-5.4c.1-.4-.1-.8-.3-1.1L2 11.5c-.6-.6-.2-1.7.7-1.8l5.4-.8c.4-.1.8-.3 1-.7l2.4-4.9c.2-.4.6-.6 1-.6z"/>
       </svg>`
        : `<svg class="fav-icon" viewBox="0 0 24 24" aria-hidden="true">
         <path fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"
           d="M12 2.6c.4 0 .8.2 1 .6l2.4 4.9c.2.4.6.6 1 .7l5.4.8c.9.1 1.3 1.2.7 1.8l-3.9 3.8c-.3.3-.4.7-.3 1.1l.9 5.4c.2.9-.8 1.6-1.6 1.2l-4.8-2.5c-.4-.2-.8-.2-1.2 0L6.9 22c-.8.4-1.8-.3-1.6-1.2l.9-5.4c.1-.4-.1-.8-.3-1.1L2 11.5c-.6-.6-.2-1.7.7-1.8l5.4-.8c.4-.1.8-.3 1-.7l2.4-4.9c.2-.4.6-.6 1-.6z"/>
       </svg>`;
}

function renderButton(btn) {
    const shape = btn.dataset.shape || "star";
    const favorited = btn.dataset.favorited === "true";

    btn.innerHTML = getIconSVG(shape, favorited);
    btn.setAttribute("aria-pressed", String(favorited));
    btn.setAttribute("aria-label", favorited ? "즐겨찾기 해제" : "즐겨찾기 추가");
}

async function requestToggleFavorite({ stockCode, next }) {
    const res = await fetch("/stocks/favorite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ "stock_code": stockCode })
    });

    if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(text || "Server request failed");
    }
    showDebugToast("즐겨찾기 변경완료")
    return res.json().catch(() => ({}));


}

function initFavoriteButtons() {
    document.querySelectorAll(".fav-btn").forEach((btn) => {
        renderButton(btn);

        const stockCode = btn.dataset.stockCode;
        const favorited = favoriteStocks.includes(stockCode);
        if (favorited) {
            btn.dataset.favorited = String(true);
            renderButton(btn);
        }

        btn.addEventListener("click", async () => {
            if (btn.disabled) return;

            const stockCode = btn.dataset.stockCode;
            const current = btn.dataset.favorited === "true";
            const next = !current;

            // optimistic UI
            btn.dataset.favorited = String(next);
            renderButton(btn);
            btn.disabled = true;

            try {
                await requestToggleFavorite({ stockCode, next });
                // 성공: 그대로 유지
            } catch (e) {
                // 실패: rollback
                btn.dataset.favorited = String(current);
                renderButton(btn);
                console.error(e);
                alert("즐겨찾기 변경에 실패했어요. 다시 시도해주세요.");
            } finally {
                btn.disabled = false;
            }
        });
    });
}

