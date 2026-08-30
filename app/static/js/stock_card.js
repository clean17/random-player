const TRADING_TABLE_HTML = `
<table class="table" id="table-trading">
  <thead>
    <tr>
      <th>그래프</th>
<!--      <th>등록시간</th>-->
      <th>종목명</th>
      <th>카테고리</th>
      <th class="right">거래대금(5일 평균)</th>
      <th class="right">거래대금(실시간)</th>
      <th class="right">거래대금 증감</th>
      <th class="right">전일 종가</th>
      <th class="right">현재가</th>
      <th class="right">금일 등락</th>
    </tr>
  </thead>
  <tbody><!-- JS 렌더링 --></tbody>
</table>
`;

// 즐겨찾기는 실시간 탭과 같은 형태(get_favorite_stocks_latest)의 데이터를 쓰므로
// TRADING_TABLE_HTML과 동일한 컬럼 구성으로 별도 id만 다르게 둔다.
const FAVORITE_TABLE_HTML = `
<table class="table" id="table-favorite">
  <thead>
    <tr>
      <th>그래프</th>
      <th>종목명</th>
      <th>카테고리</th>
      <th class="right">거래대금(5일 평균)</th>
      <th class="right">거래대금(실시간)</th>
      <th class="right">거래대금 증감</th>
      <th class="right">전일 종가</th>
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
    v = String(v).replace(/,/g, "");
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
function fmt1(v) {
    const num = toFloat(v);
    if (num === null) return "";
    const s = num.toFixed(1);       // 소수점 첫째 자리까지 문자열로 변환
    return s.endsWith(".0")
        ? String(Math.round(num))                      // 끝이 .0이면 정수로
        : s;
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
        const curTv = toFloat(r.last_trading_value) ?? 0;
        const tvChg = toFloat(r.trading_value_change_pct) ?? 0;
        const yClose = toFloat(r.yesterday_close) ?? 0;
        // const cPrice = toFloat(r.current_price) ?? 0;
        const cPrice = toFloat(r.current_close) ?? 0;
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
            <div class="trade-sub">${r.stock_code ?? ""} · 시총 ${trValFmtWon(r.market_value) ?? ""} · ${r.category ?? ""}</div>
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
            <button
              class="reserve-btn"
              data-stock-code="${r.stock_code ?? ""}"
              data-reserved="false"
              aria-pressed="false"
              aria-label="자동매수 대상 추가"
            ></button>
          </div>
        </div>

        <div class="trade-grid">
          <div class="kv"><span class="k">5일평균 거래대금</span><span class="v">${trValFmtWon(avg5d)}</span></div>
          <div class="kv"><span class="k">금일 거래대금</span><span class="v">${trValFmtWon(curTv)}</span></div>
          <div class="kv"><span class="k">전일 종가</span><span class="v">${fmtKrClose(yClose)}</span></div>
          <div class="kv"><span class="k">현재가</span><span class="v">${fmtKrClose(cPrice)}</span></div>
          <div class="kv"><span class="k">거래대금 변동률</span><span class="v">${fmt1(tvChg)}%</span></div>
          <div class="kv"><span class="k">등락률</span><span class="v">${fmt1(pChg)}%</span></div>
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
        const nClose = toFloat(r.current_close) ?? 0;
        const pChg = toFloat(r.today_price_change_pct) ?? 0;
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
            <div class="trade-sub">${r.stock_code ?? ""} · 시총 ${trValFmtWon(r.market_value) ?? ""} · ${r.category ?? ""}</div>
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
            <button
              class="reserve-btn"
              data-stock-code="${r.stock_code ?? ""}"
              data-reserved="false"
              aria-pressed="false"
              aria-label="자동매수 대상 추가"
            ></button>
          </div>
        </div>

        <div class="trade-grid">
          <div class="kv"><span class="k">집계 횟수</span><span class="v">${r.count ?? ""}</span></div>
          <div class="kv"><span class="k">집계 기간</span><span class="v">${formatted_date1} ~ ${formatted_date2}</span></div>
          <!--<div class="kv"><span class="k">시총</span><span class="v">${trValFmtWon(r.market_value) ?? ""}</span></div>-->
          <div class="kv"><span class="k">평균 거래대금 (금일)</span><span class="v">${trValFmtWon(r.avg_trading_value) ?? ""} (${trValFmtWon(r.last_trading_value) ?? ""})</span></div>
          <div class="kv"><span class="k">종가 추이 (금일 등락률)</span><span class="v">${fmt2(r.min_close)} ➡️ ${fmtKrClose(nClose)} (${fmt1(pChg)}%)</span></div>
          <div class="kv"><span class="k">기간 총 상승</span><span class="v">${r.total_rate_of_increase ?? ""}</span></div>
          <div class="kv"><span class="k">일 평균 상승</span><span class="v">${r.increase_per_day ?? ""}</span></div>
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
        const nClose = toFloat(r.current_close) ?? 0;
        const pChg = toFloat(r.today_price_change_pct) ?? 0;
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
            <div class="trade-sub">${r.stock_code ?? ""} · 시총 ${trValFmtWon(r.market_value) ?? ""} · ${r.category ?? ""}</div>
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
            <button
              class="reserve-btn"
              data-stock-code="${r.stock_code ?? ""}"
              data-reserved="false"
              aria-pressed="false"
              aria-label="자동매수 대상 추가"
            ></button>
          </div>
        </div>

        <div class="trade-grid">
          <div class="kv"><span class="k">집계 횟수</span><span class="v">${r.count ?? ""}</span></div>
          <div class="kv"><span class="k">집계 기간</span><span class="v">${formatted_date1} ~ ${formatted_date2}</span></div>
          <!--<div class="kv"><span class="k">시총</span><span class="v">${trValFmtWon(r.market_value) ?? ""}</span></div>-->
          <div class="kv"><span class="k">평균 거래대금 (금일)</span><span class="v">${trValFmtWon(r.avg_trading_value) ?? ""} (${trValFmtWon(r.last_trading_value) ?? ""})</span></div>
          <div class="kv"><span class="k">종가 추이 (금일 등락률)</span><span class="v">${fmt2(r.min_close)} ➡️ ${fmtKrClose(nClose)} (${fmt1(pChg)}%)</span></div>
          <div class="kv"><span class="k">기간 총 상승</span><span class="v">${r.total_rate_of_increase ?? ""}</span></div>
          <div class="kv"><span class="k">일 평균 상승</span><span class="v">${r.increase_per_day ?? ""}</span></div>
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
        const avg5d  = toFloat(r.avg5d_trading_value) ?? 0;
        const curTv  = toFloat(r.last_trading_value) ?? 0;
        const pChg   = toFloat(r.today_price_change_pct) ?? 0;
        const yClose = toFloat(r.yesterday_close) ?? 0;
        const tClose = toFloat(r.current_price) ?? 0;
        const nClose = toFloat(r.current_close) ?? 0;
        const tvChg  = toFloat(r.trading_value_change_pct) ?? 0;

        // 이미지
        const hasImg = !!r.graph_file;
        const encoded_url = encodeURIComponent(String(r.graph_file ?? ""));
        const imgHtml = hasImg
            ? `<img class="preview" src="https://chickchick.kr/image/stock-graphs/kospil/${encoded_url}" alt="미리보기" />`
            : `<span class="hint">그래프 없음</span>`;

        // target: "low_v1" → 버전, find_rule: "shc" → 플래그
        const targetRuleHtml = (() => {
            const parts = String(r.target ?? "").split("_");
            const version = parts[1] ?? "";
            const flags = String(r.find_rule ?? "");
            const flagMap = { s: "안정", h: "고확률", c: "커버리지" };
            const tags = [...flags].filter(f => flagMap[f]).map(f =>
                `<span class="rule-tag rule-tag--${f}">${flagMap[f]}</span>`
            ).join("");
            const versionTag = version ? `<span class="rule-tag rule-tag--version">${version.toUpperCase()}</span>` : "";
            return `${versionTag}${tags}`;
        })();

        return `
      <article class="trade-card low-card" data-index="${idx}">
        <div class="trade-top">
          <img class="trade-logo" src="${r.logo_image_url}" alt="로고"/>
          <div class="trade-text">
            <div class="trade-name">${r.stock_name ?? ""}</div>
            <div class="trade-sub">${r.stock_code ?? ""} · 시총 ${trValFmtWon(r.market_value) ?? ""} · ${r.category ?? ""}</div>
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
            <button
              class="reserve-btn"
              data-stock-code="${r.stock_code ?? ""}"
              data-reserved="false"
              aria-pressed="false"
              aria-label="자동매수 대상 추가"
            ></button>
          </div>
        </div>

        <div class="trade-grid">
<!--          <div class="kv"><span class="k">시가총액</span><span class="v">${r.market_value ?? ""}</span></div>-->
          <div class="kv"><span class="k">5일평균 거래대금</span><span class="v">${trValFmtWon(avg5d)}</span></div>
          <div class="kv"><span class="k">당일 거래대금</span><span class="v">${trValFmtWon(curTv)}</span></div>
          <div class="kv"><span class="k">종가(전일/당일)</span><span class="v">${fmtKrClose(yClose)} ➡️ ${fmtKrClose(tClose)}</span></div>
          <div class="kv"><span class="k">현재가 (수익률)</span><span class="v">${fmtKrClose(nClose)} (${calCloseReturn(nClose, tClose)})</span></div>
          <div class="kv"><span class="k">거래대금 변동률</span><span class="v">${fmt1(tvChg)}%</span></div>
          <div class="kv"><span class="k">당일 등락률</span><span class="v">${fmt1(pChg)}%</span></div>
          ${targetRuleHtml ? `<div class="kv"><span class="k">룰</span><span class="v rule-tags">${targetRuleHtml}</span></div>` : ""}
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


// 예측종목(LightGBM) — /stocks/interest/data/predict 응답을 기존 카드 셸(article.trade-card)
// 그대로 재사용해서 그린다. 거래대금/시총 같은 필드가 없어(DB 기반이 아니라 파일명 파싱이라)
// 다른 카드보다 정보가 단순하다 — 즐겨찾기/자동매수 버튼도 이 목록엔 의미가 없어 뺐다.
// 시장별로 통화가 다르다(KR=원, US=달러) — signal_price/target_price/latest_price는 원본
// 통화 그대로 내려온다(job/multi_kor_stocks_lgbm.py 등 참고).
function fmtPredictPrice(v, market) {
    const num = toFloat(v);
    if (num === null) return "-";
    return market === 'us' ? `$${num.toFixed(2)}` : `${Math.round(num).toLocaleString()}원`;
}

function renderPredictCardHtml(track, rows) {
    if (!track) return;

    track.innerHTML = rows.map((r, idx) => {
        const hasImg = !!r.graph_file;
        const marketDir = r.market === 'us' ? 'us' : 'kr';
        const encoded_url = encodeURIComponent(String(r.graph_file ?? ""));
        // 캐러셀이라 화면엔 카드 1장만 보이는데, loading="lazy" 없이는 카드 N장분 이미지가
        // 렌더링 즉시 전부 동시에 요청된다 — waitress 큐 깊이가 매번 튀는 원인이었다(2026-08-31).
        const imgHtml = hasImg
            ? `<img class="preview" loading="lazy" src="https://chickchick.kr/image/lgbm-stocks/${marketDir}/${encoded_url}" alt="미리보기" />`
            : `<span class="hint">그래프 없음</span>`;

        // 사이드카가 없는(예전에 만들어진) 파일은 signal_price/target_price가 null이라
        // fmtPredictPrice가 "-"로 표시한다 — 행 자체는 그대로 보여준다.
        const thresholdPct = r.threshold_pct ?? 10;

        return `
      <article class="trade-card predict-card" data-index="${idx}">
        <div class="trade-top">
          <div class="trade-text">
            <div class="trade-name">${r.stock_name ?? ""}</div>
            <div class="trade-sub">${r.stock_code ?? ""} · ${r.date ?? ""}</div>
          </div>
        </div>

        <div class="trade-grid">
          <div class="kv"><span class="k">예측일</span><span class="v">${r.date ?? ""}</span></div>
          <div class="kv"><span class="k">상승 확률</span><span class="v">${fmt1(r.proba)}%</span></div>
          <div class="kv"><span class="k">신호 당일</span><span class="v">${fmtPredictPrice(r.signal_price, r.market)}</span></div>
          <div class="kv"><span class="k">목표가 (+${thresholdPct}%)</span><span class="v">${fmtPredictPrice(r.target_price, r.market)}</span></div>
          <div class="kv"><span class="k">현재가</span><span class="v">${fmtPredictPrice(r.latest_price, r.market)}${(toFloat(r.latest_price) !== null && toFloat(r.signal_price)) ? ` (${calCloseReturn(toFloat(r.latest_price), toFloat(r.signal_price))})` : ''}</span></div>
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
    // 즐겨찾기는 기간 집계 대신 종목별 최신 스냅샷 1건을 보여주므로 실시간 탭과 동일한 카드 렌더러를 쓴다
    if (tableName === 'table-favorite') renderTradingCardHtml(track, rows);
    // reserved 탭은 favorite과 동일했던 쿼리(get_interest_stocks_info) 결과라 카드 렌더러를 재사용
    if (tableName === 'table-reserved') renderFavoriteCardHtml(track, rows);
    if (tableName === 'table-predict') renderPredictCardHtml(track, rows);
    initFavoriteButtons();
    initReserveButtons();
    applyStockFlagState();      // 우선 캐시 값으로 즉시 그리고
    syncStockFlagsFromServer(); // 서버 목록을 다시 받아 어긋난 표기를 정정한다(비동기)
    setupViewedDwellObserver(track); // 카드를 5초 이상 보고 있으면 '확인함' 처리

    track.addEventListener("click", (e) => {
        if (isDragging) return;
        const trigger = e.target.closest(".trade-logo, .trade-name");
        if (!trigger) return;
        const article = trigger.closest("article.trade-card");
        if (!article) return;
        const stockCode = article.querySelector(".fav-btn")?.dataset.stockCode;
        if (stockCode) {
            window.open(`https://m.stock.naver.com/domestic/stock/${stockCode}/total`, "_blank");
            markStockViewed(stockCode, article);
        }
    });

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
        if (tableName === 'table-favorite') tableHtml = FAVORITE_TABLE_HTML;
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


// 현재 선택된 탭의 대상 셀렉터('#tab-xxx')를 반환.
// 탭 UI가 버튼에서 드롭다운(#tabSelect)으로 바뀌어서, 활성 탭을 읽는 곳은 모두 이 함수를 쓴다.
// (예전 .tab-btn.active 마크업이 남아 있는 경우를 대비해 폴백도 둔다)
function getActiveTabTarget() {
    const sel = document.getElementById('tabSelect');
    if (sel && sel.value) return sel.value;
    return document.querySelector('.tab-bar .tab-btn.active')?.dataset.target || '#tab-trading';
}

function renderTradingView(tradingRows) {
    globalTradingRows = tradingRows;

    // 요소 중 'display: none' 아닌 요소 찾기
    // const el = [...document.querySelectorAll('.view-toggle')]
    //     .find(x => x.offsetParent !== null);

    // const section = el.closest('section');

    const activeTable = getActiveTabTarget();
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
        // 즐겨찾기도 실시간 탭과 같은 데이터 형태라 renderTradingTable을 그대로 재사용
        if (tableName === 'table-favorite') renderTradingTable(tradingRows, tableName);
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

function openStockOnToss(stockName) {
    axios.post('/stocks/info', { stock_name: stockName }, {})
        .then(response => {
            if (response.status !== 200) { showDebugToast('요청 실패'); return; }
            const code = response.data.result[0].data.items[0].code;
            window.open("https://www.tossinvest.com/stocks/" + code, "_blank");
        })
        .catch(err => console.error(err));
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
                    // preventDefault 없으면 포커스가 #tabSelect(드롭다운) 등 폼 요소에 있을 때
                    // 캐러셀 이동과 동시에 브라우저 기본 동작(드롭다운 값 변경)도 같이 일어난다.
                    event.preventDefault();
                    leftCarouselBtn.click();
                    break;
                case 'ArrowRight':
                    event.preventDefault();
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
                case 'l':
                    event.preventDefault();
                    const currentArticle1 = getCurrentArticle();
                    currentArticle1.querySelector('.fav-btn').click();
                    break;
                case 'o':
                    event.preventDefault();
                    const currentArticle3 = getCurrentArticle();
                    currentArticle3?.querySelector('.reserve-btn')?.click();
                    break;
                case 'Enter':
                    event.preventDefault();
                    const currentArticle2 = getCurrentArticle();
                    openStockOnToss(currentArticle2.querySelector(".trade-name")?.textContent);
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

async function requestToggleFavorite({ stockCode }) {
    const res = await fetch("/stocks/favorite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ "stock_code": stockCode })
    });

    if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(text || "Server request failed");
    }
    return res.json().catch(() => ({}));
}

// ── 자동매수 대상(reserved) 토글 ──────────────────────────────────────────
// 즐겨찾기(별)와 구분되도록 장바구니 담기 느낌의 '+/체크 원형' 아이콘을 쓴다.
function getReserveIconSVG(reserved) {
    return reserved
        ? `<svg class="fav-icon" viewBox="0 0 24 24" aria-hidden="true">
         <path fill="currentColor" d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm4.7 7.3-5.4 5.4a1 1 0 0 1-1.4 0l-2.6-2.6a1 1 0 0 1 1.4-1.4l1.9 1.9 4.7-4.7a1 1 0 0 1 1.4 1.4z"/>
       </svg>`
        : `<svg class="fav-icon" viewBox="0 0 24 24" aria-hidden="true">
         <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/>
         <path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" d="M12 8v8M8 12h8"/>
       </svg>`;
}

function renderReserveButton(btn) {
    const reserved = btn.dataset.reserved === "true";
    btn.innerHTML = getReserveIconSVG(reserved);
    btn.setAttribute("aria-pressed", String(reserved));
    btn.setAttribute("aria-label", reserved ? "자동매수 대상 해제" : "자동매수 대상 추가");
    btn.classList.toggle("is-reserved", reserved);
}

async function requestToggleReserved({ stockCode }) {
    const res = await fetch("/stocks/reserved", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ "stock_code": stockCode })
    });
    if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(text || "Server request failed");
    }
    return res.json().catch(() => ({}));
}

// ── '확인함' 표시 — 종목명/로고를 눌러 상세를 열어본 카드에 배지를 남긴다 ──────────────
// 토글이 아니라 한 방향(계속 확인함 상태 유지)이라 즉시 낙관적으로 클래스부터 붙이고,
// 실패해도 롤백하지 않는다 — 다음 동기화(syncStockFlagsFromServer)가 알아서 맞춰준다.
function markStockViewed(stockCode, article) {
    if (!stockCode) return;
    article?.classList.add("is-viewed");
    updateFlagCache(typeof viewedStocks !== "undefined" ? viewedStocks : null, stockCode, true);
    fetch("/stocks/viewed", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ "stock_code": stockCode })
    }).catch((e) => console.error("확인함 기록 실패", e));
}

// ── '확인함' — 카드를 5초 이상 계속 보고 있으면 자동으로 확인 처리 ──────────────────
// 캐러셀은 한 화면에 카드 1장(grid-auto-columns:100%)이라, IntersectionObserver로 지금
// 화면에 꽉 찬(ratio>=0.9) 카드를 찾아 4초 타이머를 걸고, 스크롤로 빠져나가면 취소한다.
const VIEWED_DWELL_MS = 4000;
let activeDwellTimers = null;   // 가장 최근에 렌더된 캐러셀의 Map(article -> timeoutId)만 추적

function armViewedDwell(article) {
    if (!activeDwellTimers || activeDwellTimers.has(article)) return;
    const code = article.querySelector(".fav-btn")?.dataset.stockCode;
    if (!code) return;
    const t = setTimeout(() => {
        activeDwellTimers?.delete(article);
        markStockViewed(code, article);
    }, VIEWED_DWELL_MS);
    activeDwellTimers.set(article, t);
}
function disarmViewedDwell(article) {
    const t = activeDwellTimers?.get(article);
    if (t) { clearTimeout(t); activeDwellTimers.delete(article); }
}

// 카드 전환(스와이프/스크롤)마다 서버 상태를 다시 물어본다 — 안 그러면 다른 기기에서
// 방금 확인한 카드로 넘어와도 다음 60초 폴링 전까지 체크 표시가 안 보인다. 빠르게 여러 장
// 넘길 때 매 카드마다 요청이 나가지 않도록 최소 간격을 둔다.
let _lastCardSyncTs = 0;
const CARD_SYNC_MIN_GAP_MS = 3000;

function syncOnCardChange() {
    const now = Date.now();
    if (now - _lastCardSyncTs < CARD_SYNC_MIN_GAP_MS) return;
    _lastCardSyncTs = now;
    if (typeof window.syncStockFlagsFromServer === 'function') window.syncStockFlagsFromServer();
}

function setupViewedDwellObserver(track) {
    const timers = new Map();
    activeDwellTimers = timers;   // 이전 렌더의 트랙은 DOM에서 이미 제거됐으니 이걸로 교체

    const observer = new IntersectionObserver((entries) => {
        if (document.hidden) return;   // 탭이 안 보이는 동안은 '보고 있다'로 치지 않는다
        entries.forEach((entry) => {
            if (entry.isIntersecting && entry.intersectionRatio >= 0.9) {
                armViewedDwell(entry.target);
                syncOnCardChange();
            } else {
                disarmViewedDwell(entry.target);
            }
        });
    }, { root: track, threshold: [0, 0.9, 1] });

    track.querySelectorAll("article.trade-card").forEach((el) => observer.observe(el));
}

// 백그라운드로 가면 진행 중이던 타이머를 전부 취소한다 — 안 보는 동안 몰래 5초가
// 채워지는 걸 막는다. 복귀 시엔 지금 화면 중앙 카드부터 다시 5초를 잰다.
document.addEventListener("visibilitychange", () => {
    if (!activeDwellTimers) return;
    if (document.hidden) {
        activeDwellTimers.forEach((t) => clearTimeout(t));
        activeDwellTimers.clear();
    } else {
        const current = getCurrentArticle();
        if (current) armViewedDwell(current);
    }
});

// ── 즐겨찾기(별) / 자동매수 대상(체크) 상태를 서버와 일치시키는 공통 로직 ────────────
// 어긋나던 원인:
//  1) 서버 upsert가 조건 없는 토글(flag = NOT flag)인데 클라이언트는 자기가 알던 상태의
//     반대값을 그렸다 — 알던 값이 낡아 있으면 서버는 반대로 뒤집혀 영구히 어긋난다.
//     → 이제 응답의 flag(반영된 실제 값)를 그대로 그린다.
//  2) favoriteStocks/reservedStocks가 페이지 최초 로드 시점 스냅샷에 고정돼 있었다.
//     → 카드를 그릴 때마다, 그리고 탭에 다시 돌아올 때마다 서버 목록을 다시 받아 맞춘다.
//  3) init*Buttons가 목록에 있으면 'true'로 켜기만 하고 꺼주지는 않아서, 이미 그려져 있던
//     다른 탭 패널의 버튼이 해제 후에도 켜진 채로 남았다.
//     → applyStockFlagState()가 문서 전체 버튼에 on/off를 모두 반영한다.
function flagCacheHas(list, code) {
    return typeof list !== "undefined" && !!list && list.indexOf(code) !== -1;
}

function updateFlagCache(list, code, on) {
    if (typeof list === "undefined" || !list) return;
    const i = list.indexOf(code);
    if (on && i === -1) list.push(code);
    if (!on && i !== -1) list.splice(i, 1);
}

// 캐시(= 서버에서 받은 목록)를 문서 안의 모든 버튼에 반영한다. 요청이 진행 중인 버튼
// (disabled)은 응답이 곧 정답을 덮어쓰므로 건드리지 않는다.
function applyStockFlagState() {
    // 상태가 그대로면 다시 그리지 않는다 — 주기 동기화가 카드 전부의 innerHTML을 매번
    // 새로 쓰지 않도록. 단, 갓 만들어진 버튼은 아직 아이콘이 없으므로(innerHTML 비어있음)
    // 상태가 같아도 한 번은 그려줘야 한다.
    document.querySelectorAll(".fav-btn").forEach((btn) => {
        if (btn.disabled) return;
        const next = String(flagCacheHas(typeof favoriteStocks !== "undefined" ? favoriteStocks : null, btn.dataset.stockCode));
        if (btn.dataset.favorited === next && btn.innerHTML !== "") return;
        btn.dataset.favorited = next;
        renderButton(btn);
    });
    document.querySelectorAll(".reserve-btn").forEach((btn) => {
        if (btn.disabled) return;
        const next = String(flagCacheHas(typeof reservedStocks !== "undefined" ? reservedStocks : null, btn.dataset.stockCode));
        if (btn.dataset.reserved === next && btn.innerHTML !== "") return;
        btn.dataset.reserved = next;
        renderReserveButton(btn);
    });
    // '확인함' 배지 — 버튼이 아니라 카드(article) 자체에 클래스로 표시한다.
    // fav-btn의 data-stock-code를 그대로 재사용해 카드마다 코드를 다시 마크업에 넣지 않는다.
    document.querySelectorAll("article.trade-card").forEach((card) => {
        const code = card.querySelector(".fav-btn")?.dataset.stockCode;
        if (!code) return;
        card.classList.toggle("is-viewed", flagCacheHas(typeof viewedStocks !== "undefined" ? viewedStocks : null, code));
    });
}

// 서버에서 즐겨찾기/자동매수 목록을 다시 받아 화면에 반영한다. 목록을 받아오는 함수는
// 템플릿(interesting_stocks.html)에 있으므로 window 훅으로 주입받는다 — 없으면 캐시만 반영.
let stockFlagSyncInFlight = null;
function syncStockFlagsFromServer() {
    if (typeof window.refreshStockFlagCaches !== "function") {
        applyStockFlagState();
        return Promise.resolve();
    }
    // 탭 전환/뷰 토글로 짧은 시간에 여러 번 불려도 요청은 한 번만 나가게 묶는다.
    if (stockFlagSyncInFlight) return stockFlagSyncInFlight;
    stockFlagSyncInFlight = Promise.resolve(window.refreshStockFlagCaches())
        .then(() => { applyStockFlagState(); })
        .catch((e) => { console.error("즐겨찾기/자동매수 목록 동기화 실패", e); })
        .finally(() => { stockFlagSyncInFlight = null; });
    return stockFlagSyncInFlight;
}
window.syncStockFlagsFromServer = syncStockFlagsFromServer;

async function onReserveButtonClick(e) {
    const btn = e.currentTarget;
    if (btn.disabled) return;
    const code = btn.dataset.stockCode;
    const current = btn.dataset.reserved === "true";
    const next = !current;

    // 4초 dwell과 별개로, 매수예약 버튼을 눌렀다는 것 자체가 이미 카드를 확인했다는 뜻이다.
    markStockViewed(code, btn.closest("article.trade-card"));

    // optimistic UI
    btn.dataset.reserved = String(next);
    renderReserveButton(btn);
    btn.disabled = true;

    try {
        const res = await requestToggleReserved({ stockCode: code });
        // 서버가 실제로 반영한 값을 진실로 삼는다 (응답에 flag가 없는 구버전 서버면 추측값 유지)
        const serverFlag = typeof res.flag === "boolean" ? res.flag : next;
        btn.dataset.reserved = String(serverFlag);
        renderReserveButton(btn);
        updateFlagCache(typeof reservedStocks !== "undefined" ? reservedStocks : null, code, serverFlag);
        showDebugToast(serverFlag ? "자동매수 대상 추가" : "자동매수 대상 해제");
    } catch (err) {
        btn.dataset.reserved = String(current);   // 실패 시 rollback
        renderReserveButton(btn);
        console.error(err);
        alert("자동매수 대상 변경에 실패했어요. 다시 시도해주세요.");
    } finally {
        btn.disabled = false;
        applyStockFlagState(); // 다른 탭에 그려진 같은 종목 버튼까지 같은 상태로 맞춘다
    }
}

async function onFavoriteButtonClick(e) {
    const btn = e.currentTarget;
    if (btn.disabled) return;
    const code = btn.dataset.stockCode;
    const current = btn.dataset.favorited === "true";
    const next = !current;

    // 4초 dwell과 별개로, 즐겨찾기 버튼을 눌렀다는 것 자체가 이미 카드를 확인했다는 뜻이다.
    markStockViewed(code, btn.closest("article.trade-card"));

    // optimistic UI
    btn.dataset.favorited = String(next);
    renderButton(btn);
    btn.disabled = true;

    try {
        const res = await requestToggleFavorite({ stockCode: code });
        const serverFlag = typeof res.flag === "boolean" ? res.flag : next;
        btn.dataset.favorited = String(serverFlag);
        renderButton(btn);
        updateFlagCache(typeof favoriteStocks !== "undefined" ? favoriteStocks : null, code, serverFlag);
        showDebugToast(serverFlag ? "즐겨찾기 등록 완료" : "즐겨찾기 취소 완료");
    } catch (err) {
        btn.dataset.favorited = String(current);  // 실패 시 rollback
        renderButton(btn);
        console.error(err);
        alert("즐겨찾기 변경에 실패했어요. 다시 시도해주세요.");
    } finally {
        btn.disabled = false;
        applyStockFlagState();
    }
}

// 카드는 매 렌더마다 innerHTML로 새로 그려지지만, 다른 탭 패널에 남아있는 예전 버튼은 그대로다 —
// data-bound로 이미 바인딩된 버튼은 건너뛰어 클릭 리스너가 중복 누적되지 않게 한다.
function initReserveButtons() {
    document.querySelectorAll(".reserve-btn").forEach((btn) => {
        if (btn.dataset.bound === "true") return;
        btn.dataset.bound = "true";
        btn.addEventListener("click", onReserveButtonClick);
    });
}

function initFavoriteButtons() {
    document.querySelectorAll(".fav-btn").forEach((btn) => {
        if (btn.dataset.bound === "true") return;
        btn.dataset.bound = "true";
        btn.addEventListener("click", onFavoriteButtonClick);
    });
}


function getCurrentArticle() {
    const articles = document.querySelectorAll("article.trade-card");
    const viewportCenter = window.innerWidth / 2;

    let current = null;
    let minDistance = Infinity;

    articles.forEach(article => {
        const rect = article.getBoundingClientRect();
        const articleCenter = rect.left + rect.width / 2;
        const distance = Math.abs(viewportCenter - articleCenter);

        if (distance < minDistance) {
            minDistance = distance;
            current = article;
        }
    });

    return current;
}