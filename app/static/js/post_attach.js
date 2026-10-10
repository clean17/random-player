/**
 * PostAttach — 게시글 에디터(Quill 1.3.7) 첨부 컴포넌트
 *
 * 붙여넣기(Ctrl+V)한 파일을 종류별로 처리한다.
 *   - 이미지  → 호출하는 쪽이 넘긴 uploadImage()(기존 /upload, 갤러리 temp)로 올리고 <img> 삽입
 *   - 영상    → /posts/files 로 올리고 <video class="post-video" controls> 삽입
 *   - 그 외   → /posts/files 로 올리고 첨부파일 카드(<div class="post-file">) 삽입 — 우측에 다운로드 버튼
 *
 * 저장은 quill.root.innerHTML 그대로라 보기 화면(view_post.html)에서도 같은 마크업이 그대로 보인다.
 * 서버: app/post.py upload_post_files / get_post_file, 스타일: static/css/post.css 맨 아래.
 *
 * 사용법 (edit_post.html):
 *   PostAttach.register();                       // new Quill(...) 전에 — 기존 글의 영상/첨부를 인식하려면 먼저 등록돼 있어야 한다
 *   const quill = new Quill('#editor', ...);
 *   PostAttach.bindPaste(quill, { uploadImage, insertEmbed });
 */
const PostAttach = (function () {
    'use strict';

    const UPLOAD_URL = '/posts/files';
    let registered = false;

    function formatSize(bytes) {
        const n = Number(bytes) || 0;
        if (n < 1024) return n + ' B';
        const units = ['KB', 'MB', 'GB', 'TB'];
        let v = n / 1024, i = 0;
        while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
        return (v >= 100 ? v.toFixed(0) : v.toFixed(1)) + ' ' + units[i];
    }

    function downloadUrl(url) {
        return url + (url.indexOf('?') === -1 ? '?' : '&') + 'download=1';
    }

    // 첨부파일 카드 내용 — 블롯 생성과 (필요하면) 다른 화면에서도 같은 마크업을 쓰도록 분리
    function fillFileCard(node, file) {
        node.textContent = '';

        const icon = document.createElement('span');
        icon.className = 'post-file__icon';
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = '📎';

        const meta = document.createElement('span');
        meta.className = 'post-file__meta';
        const name = document.createElement('span');
        name.className = 'post-file__name';
        name.textContent = file.name;
        name.title = file.name;
        const size = document.createElement('span');
        size.className = 'post-file__size';
        size.textContent = formatSize(file.size);
        meta.append(name, size);

        // download 속성 + 서버의 Content-Disposition: attachment — 편집 중에 눌러도 페이지를 벗어나지 않는다
        const btn = document.createElement('a');
        btn.className = 'post-file__download';
        btn.href = downloadUrl(file.url);
        btn.setAttribute('download', file.name);
        btn.textContent = '다운로드';

        node.append(icon, meta, btn);
        return node;
    }

    function register() {
        if (registered) return;
        registered = true;

        const BlockEmbed = Quill.import('blots/block/embed');

        class PostVideoBlot extends BlockEmbed {
            static create(value) {
                const node = super.create();
                node.setAttribute('src', typeof value === 'string' ? value : value.url);
                node.setAttribute('controls', '');
                node.setAttribute('playsinline', '');
                node.setAttribute('preload', 'metadata');
                return node;
            }
            static value(node) {
                return node.getAttribute('src');
            }
        }
        PostVideoBlot.blotName = 'postVideo';
        PostVideoBlot.tagName = 'video';
        PostVideoBlot.className = 'post-video';   // Quill 기본 video(iframe.ql-video)와 구분

        class PostFileBlot extends BlockEmbed {
            static create(file) {
                const node = super.create();
                node.setAttribute('contenteditable', 'false');
                node.dataset.url = file.url;
                node.dataset.name = file.name;
                node.dataset.size = String(file.size || 0);
                return fillFileCard(node, file);
            }
            static value(node) {
                return { url: node.dataset.url, name: node.dataset.name, size: Number(node.dataset.size) || 0 };
            }
        }
        PostFileBlot.blotName = 'postFile';
        PostFileBlot.tagName = 'div';
        PostFileBlot.className = 'post-file';

        Quill.register(PostVideoBlot);
        Quill.register(PostFileBlot);
    }

    // 클립보드에서 파일 목록을 순서대로 꺼낸다
    // files 가 있으면 그걸(탐색기에서 파일 복사), 없으면 items 에서(캡처·그림판 등) — 둘 다 보면 같은 파일이 두 번 잡힌다
    function filesFromClipboard(clipboardData) {
        const out = [];
        if (clipboardData.files && clipboardData.files.length > 0) {
            for (let i = 0; i < clipboardData.files.length; i++) out.push(clipboardData.files[i]);
        } else if (clipboardData.items) {
            for (let i = 0; i < clipboardData.items.length; i++) {
                const item = clipboardData.items[i];
                if (item.kind === 'file') {
                    const f = item.getAsFile();
                    if (f) out.push(f);
                }
            }
        }
        return out;
    }

    function isImage(file) {
        // svg 는 이미지로 넣지 않는다(스크립트를 품을 수 있음) — 일반 첨부로 처리
        return !!file.type && file.type.startsWith('image/') && file.type !== 'image/svg+xml';
    }

    async function upload(file) {
        const formData = new FormData();
        formData.append('files[]', file);
        if (typeof renderLoadingOverlay === 'function') renderLoadingOverlay();
        try {
            const res = await fetch(UPLOAD_URL, { method: 'POST', body: formData });
            if (!res.ok) throw new Error('HTTP ' + res.status);
            const data = await res.json();
            return (data.files && data.files[0]) || null;
        } catch (err) {
            console.error('[PostAttach] upload failed', file.name, err);
            if (typeof showDebugToast === 'function') showDebugToast('파일 업로드 실패: ' + file.name);
            return null;
        } finally {
            if (typeof removeLoadingOverlay === 'function') removeLoadingOverlay();
        }
    }

    // 영상·첨부 카드는 블록 요소라 문단 중간(예: 이미지 바로 뒤)에 넣으면 Quill 이 문단을 쪼개며 그 줄 "뒤"에
    // 넣는다 — 그러면 range.index + 1 이 방금 넣은 블록 앞을 가리켜 다음 파일이 그 앞에 끼어 순서가 뒤집혔다.
    // 줄 중간이면 줄바꿈을 먼저 넣어 빈 줄의 맨 앞에서 삽입하게 한다(블록은 그 빈 줄 앞에 차례로 쌓인다).
    function moveToLineStart(quill, range) {
        const [line, offset] = quill.getLine(range.index);
        if (line && offset > 0) {
            quill.insertText(range.index, '\n', 'api');
            range.index += 1;
        }
    }

    /**
     * @param quill
     * @param opts.uploadImage  (file) => Promise<url|null>  이미지 업로드(기존 경로)
     * @param opts.insertEmbed  (blotName, value, range) => void  삽입 + 스크롤 보정(호출하는 쪽 구현).
     *                          삽입 뒤 range.index 를 다음 위치로 옮겨야 여러 파일이 순서대로 들어간다.
     */
    function bindPaste(quill, opts) {
        register();
        const insertEmbed = opts.insertEmbed;

        // capture: Quill clipboard 모듈도 같은 root 에 paste 리스너가 있어, 먼저 가로채야 기본 붙여넣기와 겹치지 않는다
        quill.root.addEventListener('paste', async (e) => {
            const clipboardData = e.clipboardData || window.clipboardData;
            if (!clipboardData) return;

            const files = filesFromClipboard(clipboardData);
            if (files.length === 0) return;   // 파일이 없으면 Quill 기본 붙여넣기(텍스트·HTML)

            e.preventDefault();
            e.stopImmediatePropagation();

            const range = quill.getSelection(true) || { index: quill.getLength(), length: 0 };

            // 순차 처리 — 병렬로 올리면 삽입 순서가 클립보드 순서와 달라진다
            for (const file of files) {
                if (isImage(file) && opts.uploadImage) {
                    const url = await opts.uploadImage(file);
                    if (url) insertEmbed('image', url, range);
                    continue;
                }
                const saved = await upload(file);
                if (!saved) continue;
                moveToLineStart(quill, range);
                if (saved.kind === 'video') {
                    insertEmbed('postVideo', saved.url, range);
                } else {
                    insertEmbed('postFile', { url: saved.url, name: saved.name, size: saved.size }, range);
                }
            }
        }, { capture: true });
    }

    return { register, bindPaste, upload, formatSize, fillFileCard };
})();
