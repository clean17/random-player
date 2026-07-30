const searchBtn = document.getElementById('searchBtn');
const searchWrap = document.getElementById('chat-search-wrap');
// ===== 설정(페이지에 맞게 조정) =====
const CHAT_LIST_SEL = '#chat-list'; // 채팅 아이템이 들어가는 컨테이너 선택자
const CONTEXT_BEFORE = 25;
const CONTEXT_AFTER  = 25;

// addMessage(chatObj, prepend) 는 사용자가 이미 가지고 있는 함수 사용
// chatObj = {chatId, timestamp, username, msg}

// ===== 상태 =====
const searchState = {
    term: '',
    hits: [],          // 매칭 인덱스 목록 (서버 기준 라인/오프셋)
    i: -1,             // 현재 매칭 인덱스의 포지션 (0-based)
    start: 0,          // 현재 렌더링된 구간 시작 인덱스(서버 기준)
    end: 0,            // 현재 렌더링된 구간 끝 인덱스(서버 기준)
};

// ===== 유틸 =====
function $(sel) { return document.querySelector(sel); }
function getChatContainer() { return document.querySelector(CHAT_LIST_SEL); }

function parseLineToChatObj(line) {
    const [chatId, timestamp, username, msgRaw] = line.toString().split("|");
    return {
        chatId: chatId?.trim(),
        timestamp: timestamp?.trim(),
        username: username?.trim(),
        msg: (msgRaw || '').replace('\n', '').trim(),
    };
}

function clearChat() {
    const box = getChatContainer();
    if (box) box.innerHTML = '';
}

function renderLogs(lines, highlightTerm = '') {
    // 서버가 준 logs 배열을 기존 방식대로 렌더
    // 기존 코드가 tempArr.reverse()를 쓰셨다면 그대로 반영:
    const tempArr = lines.slice();
    tempArr.reverse().forEach(line => {
        const obj = parseLineToChatObj(line);
        // 필요하다면 여기서 obj.msg에 <mark> 하이라이트 추가 가능(escape 주의)
        addMessage(obj, true);
    });
}

function updateCounter() {
    const span = $('#hit-counter');
    const total = searchState.hits.length;
    const pos = searchState.i >= 0 ? (searchState.i + 1) : 0;
    span.textContent = `${pos}/${total}`;
    $('#btn-prev-hit').disabled = !(total > 0 && searchState.i > 0);
    $('#btn-next-hit').disabled = !(total > 0 && searchState.i < total - 1);
}

// 현재 렌더링된 DOM에서 "매칭 중심" 라인으로 스크롤 이동(옵션)
// 채팅 DOM 구조에 따라 조정하세요. 여기선 마지막 메시지로 스크롤 예시:
function scrollToCenterMessage() {
    const box = getChatContainer();
    if (!box) return;
    box.lastElementChild?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// ===== 서버 통신 =====
async function apiSearch(q) {
    const res = await fetch('/chat/search', {
        method: 'POST',
        headers: { 'Content-Type':'application/json' },
        body: JSON.stringify({ q })
    });
    if (!res.ok) throw new Error('Search failed');
    return res.json(); // { count, hits: number[] }
}

async function apiFetchContext(center, before, after) {
    const res = await fetch('/chat/fetch-context', {
        method: 'POST',
        headers: { 'Content-Type':'application/json' },
        body: JSON.stringify({ center, before, after })
    });
    if (!res.ok) throw new Error('Fetch context failed');
    return res.json(); // { logs, start, end, center }
}

// ===== 메인 로직 =====
async function runSearch() {
    const q = $('#chat-search-input').value.trim();
    if (!q) return;
    try {
        const data = await apiSearch(q);
        searchState.term = q;
        searchState.hits = data.hits || [];
        searchState.i = searchState.hits.length ? 0 : -1;
        updateCounter();

        if (searchState.i >= 0) {
            await jumpToHit(searchState.i);
        } else {
            clearChat();
            // 검색 결과 없음 → 필요시 안내 메시지 렌더
        }
    } catch (err) {
        console.error(err);
    }
}

async function jumpToHit(i) {
    if (i < 0 || i >= searchState.hits.length) return;
    searchState.i = i;
    updateCounter();

    const centerIndex = searchState.hits[i];
    try {
        const ctx = await apiFetchContext(centerIndex, CONTEXT_BEFORE, CONTEXT_AFTER);
        // ctx.logs: 서버가 보낸 라인 배열("chatId|timestamp|username|msg")
        searchState.start  = ctx.start;
        searchState.end    = ctx.end;

        clearChat();
        renderLogs(ctx.logs, searchState.term);
        scrollToCenterMessage();
    } catch (err) {
        console.error(err);
    }
}

function gotoPrev() { if (searchState.i > 0) jumpToHit(searchState.i - 1); }
function gotoNext() { if (searchState.i < searchState.hits.length - 1) jumpToHit(searchState.i + 1); }

// ===== 스크롤 로딩(자리만) =====
// 위로 스크롤시 이전 구간, 아래로 스크롤시 다음 구간 가져오려면
// /chat/fetch-context 대신 "범위" API가 필요합니다(예: /chat/fetch-range { start, size }).
// 여기선 훅만 걸어둠:
function bindScrollForMore() {
    const box = getChatContainer();
    if (!box) return;
    box.addEventListener('scroll', async () => {
        const nearTop = box.scrollTop < 50;
        const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 50;

        // 여기에 이전/다음 범위를 더 붙이는 로직 구현
        // 예: await apiFetchRange(searchState.start - 100, 100) → prepend
        //     await apiFetchRange(searchState.end + 1, 100)     → append
    });
}

// ===== UI 바인딩 =====
function initChatSearchUI() {
    searchBtn.addEventListener('click', () => {
        searchWrap.display = 'block';
    })

    const panel = $('#chat-search-panel');

    $('#btn-open-search').addEventListener('click', () => {
        panel.hidden = !panel.hidden;
        if (!panel.hidden) $('#chat-search-input').focus();
    });

    $('#btn-close-search').addEventListener('click', () => {
        panel.hidden = true;
    });

    $('#btn-run-search').addEventListener('click', runSearch);
    $('#chat-search-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') runSearch();
    });

    $('#btn-prev-hit').addEventListener('click', gotoPrev);
    $('#btn-next-hit').addEventListener('click', gotoNext);

    bindScrollForMore();
}

// 실행
document.addEventListener('DOMContentLoaded', initChatSearchUI);
