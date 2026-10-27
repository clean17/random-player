/**
 * PostEditToc — 게시글 작성/수정 화면의 PC 왼쪽 목차 네비게이션
 *
 * 조회 화면(post_markdown.js)과 같은 .post-toc 스타일을 쓴다. 편집기(Quill)에는 렌더된 제목이 없으므로
 * 본문에서 직접 제목을 찾는다 — Quill 제목 서식(<h1>~<h6>)과, 마크다운을 붙여넣어 생긴 '# 제목' 문단(<p>).
 * 코드 블록(<pre>, 문단으로 이어진 ``` 구간) 안의 '# 주석'은 제목으로 보지 않는다.
 * 타이핑 중 매번 다시 만들지 않도록 debounce 하고, 목차를 클릭하면 해당 줄로 스크롤한다(커서는 건드리지 않는다).
 *
 * 사용법 (edit_post.html):  PostEditToc.init(quill)
 */
const PostEditToc = (function () {
    'use strict';

    const RE_FENCE = /^\s*(```|~~~)/;
    const RE_MD_HEAD = /^(#{1,6})\s+(\S.*)$/;
    const DEBOUNCE_MS = 250;

    let root = null, tocEl = null, items = [], links = [];
    let timer = null, ticking = false, signature = '';

    // Quill 은 연속 공백을 &nbsp; 로 저장한다
    const clean = s => s.replace(/ /g, ' ').replace(/\s+$/, '');

    function collect() {
        const found = [];
        let inFence = false;
        Array.from(root.children).forEach(el => {
            const tag = el.tagName;
            if (tag === 'PRE') return;
            if (/^H[1-6]$/.test(tag)) {
                const text = clean(el.textContent).trim();
                if (text) found.push({ el, level: Number(tag[1]), text });
                return;
            }
            if (tag !== 'P') return;
            const line = clean(el.textContent);
            if (RE_FENCE.test(line)) { inFence = !inFence; return; }
            if (inFence) return;
            const m = RE_MD_HEAD.exec(line);
            if (m) found.push({ el, level: m[1].length, text: m[2].trim() });
        });
        return found;
    }

    function rebuild() {
        timer = null;
        const found = collect();
        // 제목이 2개 미만이면 목차를 두지 않는다(조회 화면과 동일)
        if (found.length < 2) {
            if (tocEl) { tocEl.remove(); tocEl = null; }
            items = []; links = []; signature = '';
            return;
        }
        // 제목 목록이 그대로면(본문 문장만 고친 경우) DOM 을 다시 만들지 않는다
        const sig = found.map(f => f.level + ':' + f.text).join('\n');
        if (sig === signature && tocEl) {
            items = found;   // 줄 element 는 바뀌었을 수 있으니 참조만 갱신
            updateActive();
            return;
        }
        signature = sig;
        items = found;
        links = [];

        if (!tocEl) {
            tocEl = document.createElement('nav');
            tocEl.className = 'post-toc';
            tocEl.setAttribute('aria-label', '목차');
            document.body.appendChild(tocEl);
        }
        tocEl.textContent = '';
        const minLevel = Math.min.apply(null, found.map(f => f.level));
        found.forEach((f, i) => {
            const a = document.createElement('a');
            a.href = '#';
            a.textContent = f.text;
            a.title = f.text;
            a.style.paddingLeft = (8 + (f.level - minLevel) * 12) + 'px';
            a.addEventListener('click', e => {
                e.preventDefault();
                const el = items[i].el;
                el.style.scrollMarginTop = (headerOffset() + 16) + 'px';
                el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
            tocEl.appendChild(a);
            links.push(a);
        });
        updateActive();
    }

    function headerOffset() {
        const bar = document.querySelector('.top-bar');
        return bar ? bar.getBoundingClientRect().height : 56;
    }

    // 화면 위쪽(고정 헤더 아래)에 걸린 마지막 제목을 현재 위치로 표시한다
    function updateActive() {
        ticking = false;
        if (!tocEl || !items.length) return;
        const limit = headerOffset() + 20;
        let cur = 0;
        items.forEach((f, i) => {
            if (f.el.getBoundingClientRect().top <= limit) cur = i;
        });
        links.forEach((a, i) => {
            a.classList.toggle('is-active', i === cur);
            if (i === cur) {
                const top = a.offsetTop;
                if (top < tocEl.scrollTop || top + a.offsetHeight > tocEl.scrollTop + tocEl.clientHeight) {
                    tocEl.scrollTop = top - tocEl.clientHeight / 2;
                }
            }
        });
    }

    function schedule() {
        clearTimeout(timer);
        timer = setTimeout(rebuild, DEBOUNCE_MS);
    }

    function init(quill) {
        if (!quill || !quill.root) return;
        root = quill.root;
        quill.on('text-change', schedule);
        window.addEventListener('scroll', () => {
            if (ticking || !tocEl) return;
            ticking = true;
            requestAnimationFrame(updateActive);
        }, { passive: true });
        rebuild();   // 수정 모드 초기 본문
    }

    return { init };
})();
