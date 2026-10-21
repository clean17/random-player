// 채팅 검색 (메신저식): 헤더의 돋보기 → 상단 검색 바 → 결과 하이라이트 + ▲(더 오래된)/▼(더 최근) 이동
// 의존: chat.js 의 chatContainer, addMessage, offset, loading, chatState, scrollButton, loadMoreChats / common.js 의 showDebugToast
(() => {
    const bar = document.getElementById('chat-search-bar');
    const input = document.getElementById('chat-search-input');
    const clearBtn = document.getElementById('chat-search-clear');
    const countEl = document.getElementById('chat-search-count');
    const prevBtn = document.getElementById('chat-search-prev');
    const nextBtn = document.getElementById('chat-search-next');
    const closeBtn = document.getElementById('chat-search-close');
    const openBtn = document.getElementById('chat-search-open');
    if (!bar || !input) return;

    const state = {
        term: '',
        hits: [],       // 매칭된 chat id (오름차순)
        i: -1,          // 현재 hits 위치
        token: 0,       // 오래된 응답 무시용
        jumpSeq: 0,     // 화살표 연타 시 마지막 요청만 실제로 처리
    };
    let debounceTimer = null;

    function toast(msg) {
        if (typeof showDebugToast === 'function') showDebugToast(msg);
    }

    function findRow(id) {
        return chatContainer.querySelector(`.messageRow[data-chat-id="${id}"]`);
    }

    /* ---------- 하이라이트 ---------- */
    // 한 행의 텍스트 노드에서 검색어를 <mark> 로 감싼다
    function highlightRow(row, needle) {
        const div = row.querySelector('.messageDiv');
        if (!div) return;
        const walker = document.createTreeWalker(div, NodeFilter.SHOW_TEXT, {
            acceptNode(n) {
                const tag = n.parentNode && n.parentNode.nodeName;
                if (tag === 'MARK' || tag === 'SCRIPT' || tag === 'STYLE') return NodeFilter.FILTER_REJECT;
                return n.nodeValue.toLowerCase().includes(needle) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
            }
        });
        const nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        nodes.forEach(node => {
            const text = node.nodeValue;
            const lower = text.toLowerCase();
            const frag = document.createDocumentFragment();
            let pos = 0;
            let idx;
            while ((idx = lower.indexOf(needle, pos)) !== -1) {
                if (idx > pos) frag.appendChild(document.createTextNode(text.slice(pos, idx)));
                const mark = document.createElement('mark');
                mark.className = 'chat-hit';
                mark.textContent = text.slice(idx, idx + needle.length);
                frag.appendChild(mark);
                pos = idx + needle.length;
            }
            if (pos < text.length) frag.appendChild(document.createTextNode(text.slice(pos)));
            node.parentNode.replaceChild(frag, node);
        });
    }

    // 대화가 수천 개 렌더된 상태에서 매번 전체를 훑으면 화살표를 누를 때마다 버벅인다.
    // 결과 id 목록(state.hits)을 이미 알고 있으니, 현재 결과 주변 ±HIGHLIGHT_RANGE 개 행만 처리한다.
    const HIGHLIGHT_RANGE = 10;
    let highlightedRows = [];

    function clearHighlights() {
        highlightedRows.forEach(row => {
            row.querySelectorAll('mark.chat-hit').forEach(m => {
                const parent = m.parentNode;
                if (!parent) return;
                parent.replaceChild(document.createTextNode(m.textContent), m);
                parent.normalize();
            });
        });
        highlightedRows = [];
    }

    function highlightAround(i, term) {
        clearHighlights();
        if (!term) return;
        const needle = term.toLowerCase();
        const from = Math.max(0, i - HIGHLIGHT_RANGE);
        const to = Math.min(state.hits.length - 1, i + HIGHLIGHT_RANGE);
        for (let k = from; k <= to; k++) {
            const row = findRow(state.hits[k]);
            if (!row) continue;
            highlightRow(row, needle);
            highlightedRows.push(row);
        }
    }

    let currentRow = null;
    function markCurrent(row) {
        if (currentRow) {
            currentRow.classList.remove('chat-hit-row');
            currentRow.querySelectorAll('mark.chat-hit.is-current').forEach(m => m.classList.remove('is-current'));
        }
        currentRow = row || null;
        if (!row) return;
        row.classList.add('chat-hit-row');
        row.querySelectorAll('mark.chat-hit').forEach(m => m.classList.add('is-current'));
    }

    /* ---------- UI 상태 ---------- */
    function updateCounter() {
        const total = state.hits.length;
        if (!state.term) {
            countEl.textContent = '';
        } else if (total === 0) {
            countEl.textContent = '결과 없음';
        } else {
            // 시간순 번호: 가장 최근 결과가 total/total, ▲(더 오래된 쪽)로 갈수록 숫자가 줄어든다
            countEl.textContent = `${state.i + 1}/${total}`;
        }
        prevBtn.disabled = !(total > 0 && state.i > 0);
        nextBtn.disabled = !(total > 0 && state.i >= 0 && state.i < total - 1);
        clearBtn.hidden = !input.value;
    }

    /* ---------- 서버 통신 ---------- */
    async function apiSearch(q) {
        const res = await fetch('/func/chat/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ q })
        });
        if (res.redirected) { window.location.href = res.url; return { hits: [] }; }
        if (!res.ok) throw new Error('search failed');
        return res.json(); // { count, hits: number[] }
    }

    async function apiPost(url, body) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (res.redirected) { window.location.href = res.url; return { logs: [] }; }
        if (!res.ok) throw new Error(url + ' failed');
        return res.json();
    }

    /* ---------- 검색 모드 윈도잉 ----------
       멀리 있는 결과로 점프하면 사이 대화를 전부 붙이지 않고, 대상 주변 구간만 그린다.
       위/아래 끝에 가까워지면 그 방향으로 이어 불러오고, 멀어진 반대쪽은 DOM 에서 지운다.
       (일반 채팅 로직은 window.__chatWindowMode 동안만 비켜선다 — chat.js 참고) */
    const WIN = { AROUND: 40, LOAD: 50, MAX: 200, EDGE: 600 };
    const win = { on: false, hasOlder: false, hasNewer: false, busy: false };

    function parseLine(line) {
        const parts = line.toString().split('|');
        if (parts.length < 4) return null;
        // "id | ts | user | msg | room": 메시지 안에 '|' 가 있어도 잘리지 않게 가운데를 다시 합친다
        const msg = parts.length >= 5 ? parts.slice(3, parts.length - 1).join('|') : parts[3];
        return {
            chatId: parts[0].trim(),
            timestamp: parts[1].trim(),
            username: parts[2].trim(),
            msg: msg.replace('\n', '').trim(),
        };
    }

    function realRows() {
        return Array.from(chatContainer.querySelectorAll('.messageRow:not([data-chat-id="-1"])'));
    }

    function resetChatState() {
        chatState = { previousDate: null, latestDate: null };
    }

    // 화면에 보이는 첫 행을 기준으로, DOM 을 늘리거나 줄여도 보던 위치가 튀지 않게 한다
    function keepAnchor(fn) {
        const cTop = chatContainer.getBoundingClientRect().top;
        const anchor = realRows().find(r => r.getBoundingClientRect().bottom > cTop);
        const before = anchor ? anchor.getBoundingClientRect().top : 0;
        fn();
        if (anchor && anchor.isConnected) {
            const delta = anchor.getBoundingClientRect().top - before;
            if (delta) chatContainer.scrollTop += delta;
        }
    }

    function trimTop(count) {
        const rows = realRows();
        if (count <= 0 || count >= rows.length) return;
        const keepFrom = rows[count];
        while (chatContainer.firstElementChild && chatContainer.firstElementChild !== keepFrom) {
            chatContainer.firstElementChild.remove();
        }
        // 날짜 구분선은 "이전 날짜가 나타날 때" 붙는 방식이라, 맨 위 날짜 기준을 남은 첫 행으로 맞춘다
        if (keepFrom.dataset.date) chatState.previousDate = keepFrom.dataset.date;
        win.hasOlder = true;
    }

    function trimBottom(count) {
        const rows = realRows();
        if (count <= 0 || count >= rows.length) return;
        const removeFrom = rows[rows.length - count];
        const typing = chatContainer.querySelector('.messageRow[data-chat-id="-1"]');
        let el = removeFrom;
        while (el) {
            const next = el.nextElementSibling;
            if (el !== typing) el.remove();
            el = next;
        }
        const last = realRows().pop();
        if (last && last.dataset.date) chatState.latestDate = last.dataset.date;
        win.hasNewer = true;
    }

    function setWindowMode(on) {
        win.on = on;
        window.__chatWindowMode = on;
        document.body.classList.toggle('chat-window-mode', on);
        if (on && scrollButton) scrollButton.style.display = 'block';
    }

    // 대상 메시지 주변만 새로 그린다 (기존 대화창은 비운다)
    async function enterWindowAround(targetId) {
        const data = await apiPost('/func/chat/fetch-context',
            { center: targetId, before: WIN.AROUND, after: WIN.AROUND });
        const objs = (data.logs || []).map(parseLine).filter(Boolean);
        if (!objs.length) return false;

        clearHighlights();
        markCurrent(null);
        initialChatBottomLock = false;
        setWindowMode(true);
        window.__chatPendingNew = false;
        chatContainer.innerHTML = '';
        resetChatState();
        // 기존 loadMoreChats 와 같은 방식: 최신→과거 순으로 prepend
        objs.slice().reverse().forEach(o => addMessage(o, true));

        const before = objs.filter(o => Number(o.chatId) < targetId).length;
        const after = objs.filter(o => Number(o.chatId) > targetId).length;
        win.hasOlder = before >= WIN.AROUND;
        win.hasNewer = after >= WIN.AROUND;
        return true;
    }

    async function loadOlder() {
        const first = realRows()[0];
        if (!first) return;
        const data = await apiPost('/func/chat/load-range',
            { id: Number(first.dataset.chatId), direction: 'older', limit: WIN.LOAD });
        const objs = (data.logs || []).map(parseLine).filter(Boolean);
        win.hasOlder = objs.length >= WIN.LOAD;
        if (!objs.length) return;
        keepAnchor(() => {
            objs.slice().reverse().forEach(o => addMessage(o, true));
            trimBottom(realRows().length - WIN.MAX);
        });
    }

    async function loadNewer() {
        const rows = realRows();
        const last = rows[rows.length - 1];
        if (!last) return;
        const data = await apiPost('/func/chat/load-range',
            { id: Number(last.dataset.chatId), direction: 'newer', limit: WIN.LOAD });
        const objs = (data.logs || []).map(parseLine).filter(Boolean);
        win.hasNewer = objs.length >= WIN.LOAD;
        if (objs.length) {
            keepAnchor(() => {
                window.__chatWindowAppending = true; // 일반 새 메시지 도착 처리(자동 최하단 이동 등)를 피한다
                try {
                    objs.forEach(o => addMessage(o, false));
                } finally {
                    window.__chatWindowAppending = false;
                }
                trimTop(realRows().length - WIN.MAX);
            });
        }
        if (!win.hasNewer) await leaveWindowAtLatest();
    }

    // 아래로 내려오다 최신 메시지까지 도달하면 일반 모드로 자연스럽게 이어 붙는다
    async function leaveWindowAtLatest() {
        setWindowMode(false);
        offset = realRows().length; // 이후 위로 스크롤 로딩(loadMoreChats)이 이 개수 뒤부터 이어서 불러온다
        if (window.__chatPendingNew) { // 검색 모드 중 도착해서 건너뛴 메시지가 있으면 한 번 더 이어 받는다
            window.__chatPendingNew = false;
            const rows = realRows();
            const last = rows[rows.length - 1];
            if (last) {
                const data = await apiPost('/func/chat/load-range',
                    { id: Number(last.dataset.chatId), direction: 'newer', limit: 200 });
                (data.logs || []).map(parseLine).filter(Boolean).forEach(o => addMessage(o, false));
            }
        }
        if (state.term) highlightAround(Math.max(state.i, 0), state.term);
    }

    // 스크롤 버튼 등으로 최신 대화로 복귀: 대화창을 비우고 최신 구간을 다시 불러온다
    window.exitChatWindowMode = function () {
        clearHighlights();
        markCurrent(null);
        setWindowMode(false);
        window.__chatPendingNew = false;
        chatContainer.innerHTML = '';
        resetChatState();
        offset = 0;
        loading = true;
        loadMoreChats('init'); // 최신 구간을 불러오고 최하단으로 이동, loading 은 finally 에서 해제
    };

    async function maybeLoadMore() {
        if (!win.on || win.busy) return;
        const nearTop = chatContainer.scrollTop < WIN.EDGE;
        const nearBottom = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight < WIN.EDGE;
        if (!(nearTop && win.hasOlder) && !(nearBottom && win.hasNewer)) return;
        win.busy = true;
        try {
            if (nearTop && win.hasOlder) await loadOlder();
            else if (nearBottom && win.hasNewer) await loadNewer();
            if (win.on && state.term) highlightAround(Math.max(state.i, 0), state.term);
        } catch (err) {
            console.error(err);
        } finally {
            win.busy = false;
        }
        // 이어 불러온 뒤에도 끝에 가까우면 한 번 더 (스크롤 이벤트가 더 안 올 수 있다)
        if (win.on) requestAnimationFrame(maybeLoadMore);
    }

    let scrollTick = false;
    chatContainer.addEventListener('scroll', () => {
        if (!win.on || scrollTick) return;
        scrollTick = true;
        requestAnimationFrame(() => { scrollTick = false; maybeLoadMore(); });
    }, { passive: true });

    /* ---------- 이동 ---------- */
    function centerRow(row) {
        row.scrollIntoView({ block: 'center', behavior: 'auto' });
    }

    async function jumpTo(i) {
        if (i < 0 || i >= state.hits.length) return;
        const myToken = state.token;
        const mySeq = ++state.jumpSeq;
        state.i = i;
        updateCounter();

        const targetId = state.hits[i];
        // 위로 스크롤 로딩(loadMoreChats)이 진행 중이면 끝나길 기다린다 (대화창을 비우는 중에 끼어들면 꼬인다)
        const waitStart = Date.now();
        while (loading && Date.now() - waitStart < 3000) await new Promise(r => setTimeout(r, 50));
        if (mySeq !== state.jumpSeq) return; // 기다리는 사이 더 새로운 이동 요청이 들어옴 — 이건 건너뛴다
        loading = true;
        try {
            let row = findRow(targetId);
            if (!row) {
                await enterWindowAround(targetId);
                row = findRow(targetId);
            }
            if (myToken !== state.token || mySeq !== state.jumpSeq) return; // 검색어가 바뀌었거나 더 새로운 이동이 있음
            if (!row) {
                toast('메시지를 불러오지 못했어요');
                return;
            }
            highlightAround(i, state.term);
            markCurrent(row);
            centerRow(row);
            // 이미지가 늦게 로드되며 높이가 바뀌어도 대상이 가운데에 오게 한 번씩 더 맞춘다
            [150, 500].forEach(ms => setTimeout(() => {
                if (myToken === state.token && mySeq === state.jumpSeq) centerRow(row);
            }, ms));
        } catch (err) {
            console.error(err);
            toast('검색 결과 이동에 실패했어요');
        } finally {
            loading = false;
        }
    }

    function goOlder() { if (state.i > 0) jumpTo(state.i - 1); }
    function goNewer() { if (state.i >= 0 && state.i < state.hits.length - 1) jumpTo(state.i + 1); }

    async function runSearch() {
        const q = input.value.trim();
        const myToken = ++state.token;
        if (!q) {
            resetResults();
            return;
        }
        try {
            const data = await apiSearch(q);
            if (myToken !== state.token) return; // 더 최신 검색이 있음
            state.term = q;
            state.hits = data.hits || [];
            state.i = -1;
            updateCounter();
            if (state.hits.length) {
                jumpTo(state.hits.length - 1); // 가장 최근 결과부터
            } else {
                clearHighlights();
                markCurrent(null);
            }
        } catch (err) {
            console.error(err);
            if (myToken === state.token) countEl.textContent = '검색 실패';
        }
    }

    function resetResults() {
        state.term = '';
        state.hits = [];
        state.i = -1;
        clearHighlights();
        markCurrent(null);
        updateCounter();
    }

    /* ---------- 열기/닫기 ---------- */
    function openSearch() {
        bar.hidden = false;
        document.body.classList.add('chat-search-active');
        input.focus();
        input.select();
    }

    function closeSearch() {
        state.token++;
        clearTimeout(debounceTimer);
        bar.hidden = true;
        document.body.classList.remove('chat-search-active');
        input.value = '';
        input.blur();
        resetResults();
    }

    window.openChatSearch = openSearch;
    window.closeChatSearch = closeSearch;

    openBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        if (bar.hidden) openSearch(); else closeSearch();
    });
    closeBtn.addEventListener('click', closeSearch);
    clearBtn.addEventListener('click', () => {
        input.value = '';
        state.token++;
        resetResults();
        input.focus();
    });
    prevBtn.addEventListener('click', goOlder);
    nextBtn.addEventListener('click', goNewer);

    input.addEventListener('input', () => {
        clearBtn.hidden = !input.value;
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(runSearch, 300);
    });

    input.addEventListener('keydown', (e) => {
        if (e.isComposing) return; // 한글 조합 중 Enter 무시
        if (e.key === 'Enter') {
            e.preventDefault();
            if (input.value.trim() !== state.term) {
                clearTimeout(debounceTimer);
                runSearch();
            } else if (e.shiftKey) {
                goNewer();
            } else {
                goOlder();
            }
        }
    });

    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd+F → 브라우저 검색 대신 채팅 검색
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
            e.preventDefault();
            openSearch();
        } else if (e.key === 'Escape' && !bar.hidden) {
            closeSearch();
        }
    });
})();
