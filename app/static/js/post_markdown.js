/**
 * PostMarkdown — 게시글 조회 화면에서 마크다운으로 작성된 글을 렌더링해 보여주는 토글
 *
 * 마크다운 텍스트를 편집기(Quill)에 붙여넣으면 한 줄이 <p> 하나로 저장된다(예: <p># 제목</p>, <p>```</p>).
 * 본문 DOM 에서 줄 단위 텍스트를 다시 뽑아 마크다운 원문을 복원한 뒤 marked 로 렌더링하고 DOMPurify 로 정리한다.
 *
 * 마크다운으로 판별된 글(looksLikeMarkdown)만 버튼이 보이고, 처음부터 MD 로 보여준다(버튼은 '원문 보기').
 * 판별에서 가장 조심할 것은 '# -*- coding: utf-8 -*-' / '# 주석' 이 가득한 파이썬 코드 글 — '# ' 줄만으로는
 * 마크다운이라고 보지 않고, 코드 블록(```) 밖에 코드처럼 보이는 줄이 많으면 마크다운이 아니라고 본다.
 * 사용자가 '원문 보기'를 고른 글은 그 선택을 브라우저(localStorage)에 기억한다.
 *
 * 사용법 (view_post.html):
 *   PostMarkdown.init({ content: <원본 본문 element>, button: <토글 버튼(처음엔 hidden)>, postId: '<public_id>' });
 *   PostMarkdown.isOn() / PostMarkdown.source()  — 내용 복사 버튼이 MD 모드일 때 마크다운 원문을 복사하는 데 쓴다
 */
const PostMarkdown = (function () {
    'use strict';

    // 마크다운으로 판별된 글에서만 불러온다 — 대부분의 글은 조회 화면 로딩에 비용을 더하지 않는다
    const LIBS = [
        'https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js',
        'https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js',
    ];
    const STORAGE_PREFIX = 'post-md-view:';

    let contentEl = null, buttonEl = null, mdEl = null, storageKey = null;
    let mdSource = null, on = false, libsPromise = null;

    function loadScript(src) {
        return new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = src;
            s.onload = resolve;
            s.onerror = () => reject(new Error('load failed: ' + src));
            document.head.appendChild(s);
        });
    }

    function loadLibs() {
        if (!libsPromise) libsPromise = Promise.all(LIBS.map(loadScript));
        return libsPromise;
    }

    const nbsp = s => s.replace(/ /g, ' ');   // Quill 은 연속 공백을 &nbsp; 로 저장한다 — 들여쓰기·마크다운 문법이 깨지지 않게

    // 문단 안의 인라인 내용 → 텍스트. 이미지는 ![](src), 텍스트와 주소가 다른 링크는 [text](href) 로 되살린다
    function inlineText(node) {
        let s = '';
        node.childNodes.forEach(n => {
            if (n.nodeType === Node.TEXT_NODE) {
                s += n.nodeValue;
            } else if (n.nodeType === Node.ELEMENT_NODE) {
                const tag = n.tagName;
                if (tag === 'BR') return;   // <p><br></p> = 빈 줄
                if (tag === 'IMG') {
                    s += '![](' + n.getAttribute('src') + ')';
                } else if (tag === 'A' && n.getAttribute('href') && n.textContent !== n.getAttribute('href')) {
                    s += '[' + n.textContent + '](' + n.getAttribute('href') + ')';
                } else {
                    s += inlineText(n);
                }
            }
        });
        return s;
    }

    // 저장된 본문 DOM → 마크다운 원문
    function toMarkdown(root) {
        const lines = [];
        root.childNodes.forEach(node => {
            if (node.nodeType === Node.TEXT_NODE) {   // Quill 도입 전 평문 글(\n 으로 줄 구분)
                if (node.nodeValue.trim()) lines.push(nbsp(node.nodeValue));
                return;
            }
            if (node.nodeType !== Node.ELEMENT_NODE) return;
            const tag = node.tagName;

            if (tag === 'PRE') {   // Quill 코드 블록
                lines.push('```', nbsp(node.textContent).replace(/\n$/, ''), '```');
            } else if (tag === 'OL' || tag === 'UL') {   // Quill 목록 서식
                let i = 1;
                Array.from(node.children).forEach(li => {
                    lines.push((tag === 'OL' ? (i++) + '. ' : '- ') + nbsp(inlineText(li)));
                });
            } else if (/^H[1-6]$/.test(tag)) {   // Quill 제목 서식
                lines.push('#'.repeat(Number(tag[1])) + ' ' + nbsp(inlineText(node)));
            } else if (node.matches('div.post-file, video.post-video')) {
                // 첨부 카드·영상은 HTML 그대로 — 마크다운에서 HTML 블록은 앞뒤 빈 줄이 있어야 한다
                lines.push('', node.outerHTML, '');
            } else {
                lines.push(nbsp(inlineText(node)));
            }
        });
        return lines.join('\n');
    }

    function render() {
        if (mdSource === null) mdSource = toMarkdown(contentEl);
        const html = window.marked.parse(mdSource, { gfm: true, breaks: false });
        // 본문은 작성자가 쓴 그대로라 스크립트·이벤트 속성이 섞일 수 있다 — 렌더 결과를 반드시 정리한다
        mdEl.innerHTML = window.DOMPurify.sanitize(html, { ADD_ATTR: ['download', 'target', 'playsinline'] });
        mdEl.querySelectorAll('a[href^="http"]').forEach(a => {
            a.target = '_blank';
            a.rel = 'noopener noreferrer';
        });
    }

    // ── 마크다운 판별 ────────────────────────────────────────────────────────────
    // 코드 블록(```) 밖의 줄만 본다. 마크다운 신호에 점수를 주고, 코드처럼 보이는 줄의 비율이 높으면 탈락시킨다.
    // '# ' 한 단계 제목은 파이썬 주석과 구분이 안 돼 약한 신호(1점)로만 친다.
    const RE_FENCE = /^\s*(```|~~~)/;
    const RE_H1 = /^#\s+\S/;
    const RE_H2PLUS = /^#{2,6}\s+\S/;
    const RE_LIST = /^\s*([-*+]|\d+[.)])\s+\S/;
    const RE_TABLE_SEP = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/;
    const RE_BOLD = /\*\*[^*\n]+\*\*/;
    const RE_LINK = /\[[^\]\n]+\]\([^)\s]+\)/;
    const RE_QUOTE = /^>\s?\S/;
    const RE_INLINE_CODE = /`[^`\n]+`/;
    const RE_CODE_LINE = new RegExp([
        /^#\s*-\*-/,                                             // # -*- coding: utf-8 -*-
        /^#!/,                                                   // #!/usr/bin/env
        /^\s*(def|class|async def)\s+\w+.*:\s*$/,                // def foo():
        /^\s*(import\s+[\w.]+|from\s+[\w.]+\s+import\b)/,        // import x / from x import y
        /^\s*(return|raise|yield|pass|break|continue)\b/,
        /^\s*(if|elif|for|while|with|try|except|finally|else)\b.*:\s*$/,
        /^\s*@\w+/,                                              // 데코레이터
        /\bself\.\w+/,
        /^\s*"""|"""\s*$/,
        /^\s*(const|let|var|function)\s+\w+/,                   // JS
        /[;{]\s*$|^\s*}\s*$/,                                    // ; { } 로 끝나는 줄
        /^\s*[\w.\[\]'"]+\s*=\s*\S/,                             // x = ...  (마크다운 문장에는 드묾)
    ].map(r => r.source).join('|'));

    function looksLikeMarkdown(src) {
        let inFence = false, fenceLines = 0, total = 0, codeLike = 0;
        let h1 = 0, h2 = 0, list = 0, tableSep = 0, bold = 0, link = 0, quote = 0, inline = 0;
        src.split('\n').forEach(line => {
            if (RE_FENCE.test(line)) { inFence = !inFence; fenceLines++; return; }
            if (inFence || !line.trim()) return;
            total++;
            if (RE_CODE_LINE.test(line)) codeLike++;
            if (RE_H2PLUS.test(line)) h2++;
            else if (RE_H1.test(line)) h1++;
            if (RE_LIST.test(line)) list++;
            if (RE_TABLE_SEP.test(line)) tableSep++;
            if (RE_BOLD.test(line)) bold++;
            if (RE_LINK.test(line)) link++;
            if (RE_QUOTE.test(line)) quote++;
            if (RE_INLINE_CODE.test(line)) inline++;
        });
        if (total === 0) return false;
        // 코드 블록 밖에서 코드 같은 줄이 15% 이상이면 코드 글로 본다
        if (codeLike / total >= 0.15) return false;
        const score =
            (h2 > 0 ? 2 : 0) +
            (tableSep > 0 ? 3 : 0) +
            (fenceLines >= 2 ? 2 : 0) +
            (h1 > 0 ? 1 : 0) +
            (bold > 0 ? 1 : 0) +
            (link > 0 ? 1 : 0) +
            (list >= 2 ? 1 : 0) +
            (quote > 0 ? 1 : 0) +
            (inline > 0 ? 1 : 0);
        return score >= 4;
    }

    // 기본은 MD — 사용자가 '원문 보기'를 고른 글만 'raw' 로 기억한다
    function save(value) {
        try {
            if (value) localStorage.removeItem(storageKey);
            else localStorage.setItem(storageKey, 'raw');
        } catch (e) { /* 저장 불가(시크릿 창 등) — 이번 화면에서만 적용 */ }
    }

    function prefersRaw() {
        try { return localStorage.getItem(storageKey) === 'raw'; } catch (e) { return false; }
    }

    async function set(value, persist) {
        if (value) {
            buttonEl.disabled = true;
            try {
                await loadLibs();
                render();
            } catch (err) {
                console.error('[PostMarkdown]', err);
                if (typeof showDebugToast === 'function') showDebugToast('마크다운 변환 실패');
                buttonEl.disabled = false;
                contentEl.hidden = false;   // 처음 열 때 미리 숨겨둔 원문을 되살린다
                mdEl.hidden = true;
                buttonEl.textContent = 'MD 보기';
                return;
            }
            buttonEl.disabled = false;
        }
        on = value;
        contentEl.hidden = value;
        mdEl.hidden = !value;
        buttonEl.textContent = value ? '원문 보기' : 'MD 보기';
        buttonEl.setAttribute('aria-pressed', value ? 'true' : 'false');
        if (persist) save(value);
    }

    function init(opts) {
        contentEl = opts.content;
        buttonEl = opts.button;
        if (!contentEl || !buttonEl) return;
        storageKey = STORAGE_PREFIX + opts.postId;

        mdSource = toMarkdown(contentEl);
        if (!looksLikeMarkdown(mdSource)) return;   // 마크다운이 아니면 버튼도 안 보인다
        buttonEl.hidden = false;

        // 원본 본문과 같은 카드 모양을 쓰되 Quill 전용 목록 스타일 등은 post.css 의 .post-md 에서 되돌린다
        mdEl = document.createElement('div');
        mdEl.className = 'post-content ql-editor post-md';
        mdEl.hidden = true;
        contentEl.after(mdEl);

        buttonEl.addEventListener('click', () => set(!on, true));
        if (!prefersRaw()) {
            contentEl.hidden = true;   // 라이브러리를 받는 동안 원문(# ** 등)이 잠깐 보였다 바뀌는 깜빡임 방지
            buttonEl.textContent = '원문 보기';
            set(true, false);
        }
    }

    return {
        init,
        looksLikeMarkdown,
        toMarkdown,
        isOn: () => on,
        source: () => (mdSource === null && contentEl ? toMarkdown(contentEl) : mdSource),
    };
})();
