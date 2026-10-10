/**
 * PostMarkdown — 게시글 조회 화면에서 마크다운으로 작성된 글을 렌더링해 보여주는 토글
 *
 * 마크다운 텍스트를 편집기(Quill)에 붙여넣으면 한 줄이 <p> 하나로 저장된다(예: <p># 제목</p>, <p>```</p>).
 * 본문 DOM 에서 줄 단위 텍스트를 다시 뽑아 마크다운 원문을 복원한 뒤 marked 로 렌더링하고 DOMPurify 로 정리한다.
 * 어떤 글이 마크다운인지는 자동으로 판별하지 않는다 — '# -*- coding: utf-8 -*-' 로 시작하는 코드 글이 많아
 * 자동 판별하면 주석이 제목으로 바뀌어 망가진다. 글마다 버튼으로 켜고, 선택은 브라우저(localStorage)에 기억한다.
 *
 * 사용법 (view_post.html):
 *   PostMarkdown.init({ content: <원본 본문 element>, button: <토글 버튼>, postId: '<public_id>' });
 *   PostMarkdown.isOn() / PostMarkdown.source()  — 내용 복사 버튼이 MD 모드일 때 마크다운 원문을 복사하는 데 쓴다
 */
const PostMarkdown = (function () {
    'use strict';

    // 처음 켤 때만 불러온다 — 대부분의 글은 MD 모드를 안 쓰므로 조회 화면 로딩에 비용을 더하지 않는다
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

    function save(value) {
        try {
            if (value) localStorage.setItem(storageKey, '1');
            else localStorage.removeItem(storageKey);
        } catch (e) { /* 저장 불가(시크릿 창 등) — 이번 화면에서만 적용 */ }
    }

    function load() {
        try { return localStorage.getItem(storageKey) === '1'; } catch (e) { return false; }
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

        // 원본 본문과 같은 카드 모양을 쓰되 Quill 전용 목록 스타일 등은 post.css 의 .post-md 에서 되돌린다
        mdEl = document.createElement('div');
        mdEl.className = 'post-content ql-editor post-md';
        mdEl.hidden = true;
        contentEl.after(mdEl);

        buttonEl.addEventListener('click', () => set(!on, true));
        if (load()) set(true, false);
    }

    return {
        init,
        isOn: () => on,
        source: () => (mdSource === null && contentEl ? toMarkdown(contentEl) : mdSource),
    };
})();
