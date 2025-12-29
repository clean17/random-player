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
      <th class="right">어제종가</th>
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
    track.innerHTML = rows.map((r, idx) => {
        const ts = Date.parse(r.created_at);
        const date = Number.isFinite(ts) ? new Date(ts) : new Date();
        const formatted_time = timeFmt.format(date);

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
            ? `<img class="preview" src="https://chickchick.shop/image/stock-graphs/interest/${encoded_url}" alt="미리보기" />`
            : `<span class="hint">그래프 없음</span>`;

        return `
      <article class="trade-card" data-index="${idx}">

        <div class="trade-top">
          <img class="trade-logo" src="${r.logo_image_url}" alt="로고"/>
          <div class="trade-text">
            <div class="trade-name">${r.stock_name ?? ""}</div>
            <div class="trade-sub">(${r.stock_code ?? ""}) · ${formatted_time} · ${r.category ?? ""}</div>
          </div>
        </div>

        <div class="trade-grid">
          <div class="kv"><span class="k">5일평균 거래대금</span><span class="v">${fmt_won(avg5d)}</span></div>
          <div class="kv"><span class="k">현재거래대금</span><span class="v">${fmt_won(curTv)}</span></div>
          <div class="kv"><span class="k">어제종가</span><span class="v">${Math.round(yClose).toLocaleString("ko-KR")}원</span></div>
          <div class="kv"><span class="k">현재가</span><span class="v">${Math.round(cPrice).toLocaleString("ko-KR")}원</span></div>
          <div class="kv"><span class="k">거래대금 변화율</span><span class="v">${fmt2(tvChg)}%</span></div>
          <div class="kv"><span class="k">등락률</span><span class="v">${fmt2(pChg)}%</span></div>
        </div>

        <div class="trade-detail" style="margin-top:10px;">
          ${imgHtml}
        </div>
      </article>
    `;
    }).join("");
}

function renderSummaryCardHtml(track, rows) {
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
            ? `<img class="preview" src="https://chickchick.shop/image/stock-graphs/interest/${encoded_url}" alt="미리보기" />`
            : `<span class="hint">그래프 없음</span>`;

        return `
      <article class="trade-card summary-card" data-index="${idx}">
        <div class="trade-top">
          <img class="trade-logo" src="${r.logo_image_url}" alt="로고"/>
          <div class="trade-text">
            <div class="trade-name">${r.stock_name ?? ""}</div>
            <div class="trade-sub">(${r.stock_code ?? ""}) · <!--${formatted_date1} ~ ${formatted_date2} · 카운트: ${r.count ?? ""} ·--> ${r.category ?? ""}</div>
          </div>
        </div>

        <div class="trade-grid">
          <div class="kv"><span class="k">출현횟수</span><span class="v">${r.count ?? ""}</span></div>
          <div class="kv"><span class="k">구간</span><span class="v">${formatted_date1} ~ ${formatted_date2}</span></div>
          <div class="kv"><span class="k">시총</span><span class="v">${r.market_value ?? ""}</span></div>
          <div class="kv"><span class="k">평균거래대금</span><span class="v">${r.avg_trading_value ?? ""}</span></div>
          <div class="kv"><span class="k">최저가</span><span class="v">${fmt2(r.min)}</span></div>
          <div class="kv"><span class="k">현재가</span><span class="v">${fmt2(r.last)}</span></div>
          <div class="kv"><span class="k">총상승</span><span class="v">${r.total_rate_of_increase ?? ""}</span></div>
          <div class="kv"><span class="k">일상승(총/출현횟수)</span><span class="v">${r.increase_per_day ?? ""}</span></div>
        </div>

        <div class="trade-detail" style="margin-top:10px;">
          ${imgHtml}
        </div>
      </article>
    `;
    }).join("");
}

function renderLowCardHtml(track, rows) {
    if (!track) return;

    if (!rows || !rows.length) {
        track.innerHTML = `<div class="trade-card">데이터가 없습니다.</div>`;
        const countEl = document.getElementById("count-low");
        if (countEl) countEl.textContent = "0건";
        return;
    }

    track.innerHTML = rows.map((r, idx) => {
        // 시간
        const ts = Date.parse(r.created_at);
        const date = Number.isFinite(ts) ? new Date(ts) : new Date();
        const formatted_time = timeFmt.format(date); // "HH:mm"

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
            ? `<img class="preview" src="https://chickchick.shop/image/stock-graphs/kospil/${encoded_url}" alt="미리보기" />`
            : `<span class="hint">그래프 없음</span>`;

        return `
      <article class="trade-card low-card" data-index="${idx}">
        <div class="trade-top">
          <img class="trade-logo" src="${r.logo_image_url}" alt="로고"/>
          <div class="trade-text">
            <div class="trade-name">${r.stock_name ?? ""}</div>
            <div class="trade-sub">(${r.stock_code ?? ""}) · ${formatted_time} · ${r.category ?? ""}</div>
          </div>
        </div>

        <div class="trade-grid">
          <div class="kv"><span class="k">시가총액</span><span class="v">${r.market_value ?? ""}</span></div>
          <div class="kv"><span class="k">금일 거래대금</span><span class="v">${fmt_won(curTv)}</span></div>
          <div class="kv"><span class="k">어제종가</span><span class="v">${Math.round(yClose).toLocaleString("ko-KR")}원</span></div>
          <div class="kv"><span class="k">현재가</span><span class="v">${Math.round(cPrice).toLocaleString("ko-KR")}원</span></div>
          <div class="kv"><span class="k">등락률</span><span class="v">${fmt2(pChg)}%</span></div>
          <div class="kv"><span class="k">비고</span><span class="v"></span></div>
        </div>

        <div class="trade-detail" style="margin-top:10px;">
          ${imgHtml}
        </div>
      </article>
    `;
    }).join("");

    const countEl = document.getElementById("count-low");
    if (countEl) countEl.textContent = `${rows.length}건`;
}


function renderTradingCards(rows, section, tableName) {
    const root = section.querySelector(".table-scroller");
    if (!root) {
        console.warn('[renderTradingCards] .table-scroller 요소가 없습니다.');
        return;
    }

    const countEl = section.querySelector('[id^="count-"]');   // count로 시작하는 id 찾기

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
    let isDown = false, startX = 0, startScroll = 0;
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
    track.addEventListener("pointercancel", () => { isDown = false; });

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
    const el = [...document.querySelectorAll('select.view-select')]
        .find(x => x.offsetParent !== null);
    // console.log(el); // 보이는 요소(없으면 undefined)
    const section = el.closest('section');
    const mode = section.querySelector('.view-select').value;
    const tableName = 'table-'+section.id.split('-')[1];

    if (mode === "table") {
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


// 드롭다운 변경 시 즉시 반영
setTimeout(()=>{
        /*document.getElementById('view-trading').addEventListener("change", (e) => {
            e.target.blur();
            renderTradingView(globalTradingRows || []);
        });*/

        document.querySelectorAll('.view-select').forEach((el)=>{
            el.addEventListener("change", (e) => {
                e.target.blur();
                renderTradingView(globalTradingRows || []);
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

