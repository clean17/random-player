/**
 * 음성 분석 페이지 (templates/audio_analysis.html)
 *
 * 업로드 → 작업 목록 폴링 → 결과 표시. 결과는 워커가 만든 analysis.json(job.result)으로 그린다:
 *   - 화자별 발화 비율 막대, 타임라인(주제 구간 / 화자별 발화 / 선택한 키워드 위치 / 재생 위치)
 *   - 키워드 칩: 누르면 대화록(과 요약·회의록)에서 <mark> 로 강조, 이전/다음으로 이동
 *   - 탭: 요약(결론·핵심·주제 카드·결정·할 일·미결·참여자) / 회의록 / 대화록(화자 색, 주제 구분선) / 원문 MD
 *   - 시각을 누르면 원본 녹음을 그 지점부터 재생
 * analysis.json 이 없는 예전 결과는 markdown 만 렌더링한다.
 */
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    const STAGE_LABEL = { queued: '대기', running: '분석 중', done: '완료', error: '오류' };

    const drop = $('drop'), fileInput = $('file-input'), uploadBtn = $('upload-btn');
    const jobsEl = $('jobs'), resultCard = $('result-card');
    const audioEl = $('r-audio');
    let selectedFile = null, pollTimer = null;

    // 현재 열린 결과
    const view = {
        jobId: null, job: null, result: null, markdown: '', minutes: '',
        tab: 'summary', keyword: null, marks: [], markIdx: -1, utterStarts: [], playingIdx: -1, roles: {},
    };

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }
    function fmtTs(sec) {
        sec = Math.max(0, Math.floor(sec || 0));
        const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
        const mm = String(m).padStart(2, '0'), ss = String(s).padStart(2, '0');
        return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
    }
    function fmtDur(sec) {
        if (!sec) return '';
        sec = Math.round(sec);
        const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
        return h ? `${h}시간 ${m}분` : (m ? `${m}분 ${s}초` : `${s}초`);
    }
    function spkNo(label) {
        const m = /(\d+)\s*$/.exec(label || '');
        return m ? ((Number(m[1]) - 1) % 10) + 1 : 0;
    }
    function spkClass(label) { return 'spk-' + spkNo(label); }
    function chip(label, extra) {
        return `<span class="va-chip ${spkClass(label)}">${esc(label)}${extra || ''}</span>`;
    }
    function tsBtn(sec, text) {
        return `<button type="button" class="va-ts" data-seek="${sec}">${esc(text || fmtTs(sec))}</button>`;
    }
    function list(items, cls) {
        if (!items || !items.length) return '<p class="va-muted">없음</p>';
        return `<ul class="${cls || ''}">${items.map(x => `<li>${itemHtml(x)}</li>`).join('')}</ul>`;
    }
    // 결정·미결은 예전 결과에선 문자열, 2026-10-17 부터 {content, ts, quote} — 근거 시각 버튼을 붙인다
    function itemHtml(x, key) {
        if (typeof x === 'string') return esc(x);
        return esc(x[key || 'content'] || '') + quoteTs(x);
    }
    function quoteTs(x) {
        return x && typeof x.ts === 'number' ? ` <span title="${esc(x.quote || '')}">${tsBtn(x.ts)}</span>` : '';
    }
    const unset = v => !v || ['-', '미정', '불명', '없음'].includes(String(v).trim());
    // 한 발화를 문장마다 한 줄로 (클로바노트 음성 기록처럼) — 긴 발화가 한 덩어리 벽글이 되지 않게
    function splitSentences(text) {
        return String(text).trim().split(/(?<=[.?!])\s+/).filter(Boolean);
    }

    // ───────────────────────── 업로드 ─────────────────────────
    function setFile(f) {
        selectedFile = f || null;
        $('file-name').textContent = f ? `${f.name} (${(f.size / 1024 / 1024).toFixed(1)}MB)` : '';
        uploadBtn.disabled = !f;
        // 삼성 통화 녹음('통화 홍길동_261008_162732.m4a')은 2명 — 자동 감지는 상대 목소리를 둘로 쪼개곤 한다
        if (f && /^(통화|call)/i.test(f.name) && $('num-speakers').value === '0') {
            $('num-speakers').value = '2';
            showDebugToast('통화 녹음으로 보여 화자 수를 2명으로 맞췄습니다');
        }
    }
    fileInput.addEventListener('change', () => setFile(fileInput.files[0]));
    ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('is-over'); }));
    ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('is-over'); }));
    drop.addEventListener('drop', e => { if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); });

    uploadBtn.addEventListener('click', () => {
        if (!selectedFile) return;
        const fd = new FormData();
        fd.append('file', selectedFile);
        fd.append('num_speakers', $('num-speakers').value);
        fd.append('hotwords', $('job-hotwords').value);
        fd.append('previous_job', $('upload-previous').value);
        const bar = $('upload-bar'), fill = bar.firstElementChild;
        bar.style.display = 'block';
        fill.style.width = '0';
        uploadBtn.disabled = true;

        // 큰 녹음 파일 업로드 진행률을 보여주려고 fetch 대신 XHR
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/audio/upload');
        xhr.upload.onprogress = e => { if (e.lengthComputable) fill.style.width = (e.loaded / e.total * 100) + '%'; };
        xhr.onload = () => {
            bar.style.display = 'none';
            let data = {};
            try { data = JSON.parse(xhr.responseText); } catch (e) {}
            if (xhr.status !== 200) {
                alert(data.error || `업로드 실패 (${xhr.status})`);
                uploadBtn.disabled = false;
                return;
            }
            fileInput.value = '';
            $('job-hotwords').value = '';
            setFile(null);
            showDebugToast('업로드 완료 — 분석 대기열에 추가했습니다');
            loadJobs();
        };
        xhr.onerror = () => { bar.style.display = 'none'; uploadBtn.disabled = false; alert('업로드 중 네트워크 오류'); };
        xhr.send(fd);
    });

    // ───────────────────────── 작업 목록 ─────────────────────────
    function renderJobs(jobs) {
        if (!jobs.length) {
            jobsEl.innerHTML = '<div class="va-empty">아직 분석한 파일이 없습니다</div>';
            return;
        }
        jobsEl.innerHTML = jobs.map(j => {
            const meta = [j.created_at];
            if (j.duration) meta.push(fmtDur(j.duration));
            if (j.stage === 'done') meta.push(j.speakers ? `화자 ${j.speakers}명` : '화자 구분 없음');
            if (j.stage === 'done' && j.summarized === false) meta.push('요약 없음');
            const msg = (j.stage === 'running' || j.stage === 'error') ? `<div class="va-job-meta">${esc(j.message)}</div>` : '';
            const bar = j.stage === 'running' ? `<div class="va-progress"><div style="width:${j.progress}%"></div></div>` : '';
            const actions = [];
            if (j.stage === 'error') actions.push(`<button class="va-btn va-btn-sm" data-act="log">로그</button>`);
            if (j.stage === 'error' || j.stage === 'done') {
                // 화자 수만 바꿔 다시 돌릴 수 있게 — 받아쓰기는 재사용되므로 몇 분이면 끝난다
                const opts = ['<option value="0">화자 자동</option>']
                    .concat(Array.from({ length: 10 }, (_, k) => `<option value="${k + 1}">화자 ${k + 1}명</option>`))
                    .join('').replace(`value="${j.num_speakers || 0}"`, `value="${j.num_speakers || 0}" selected`);
                actions.push(`<select class="va-spk-select" data-role="spk">${opts}</select>`,
                    `<button class="va-btn va-btn-sm" data-act="retry">${j.stage === 'done' ? '재분석' : '재시도'}</button>`);
            }
            actions.push(`<button class="va-btn va-btn-sm" data-act="delete">삭제</button>`);
            return `<div class="va-job${j.id === view.jobId ? ' is-active' : ''}" data-id="${j.id}" data-stage="${j.stage}">
                <div class="va-job-top">
                    <span class="va-job-name">${esc(j.filename)}</span>
                    <span class="va-badge ${j.stage}">${STAGE_LABEL[j.stage] || j.stage}${j.stage === 'running' ? ' ' + Math.round(j.progress) + '%' : ''}</span>
                </div>
                <div class="va-job-meta">${esc(meta.join(' · '))}</div>
                ${msg}${bar}
                <div class="va-row" style="margin-top:6px">${actions.join('')}</div>
            </div>`;
        }).join('');
    }

    function fillUploadPrevious(jobs) {
        const sel = $('upload-previous'), keep = sel.value;
        sel.innerHTML = '<option value="">이전 회의 없음</option>' + jobs.filter(j => j.stage === 'done').map(j =>
            `<option value="${j.id}">${esc((j.title || j.filename) + ' · ' + j.created_at.slice(0, 10))}</option>`).join('');
        sel.value = keep;
    }

    async function loadJobs() {
        clearTimeout(pollTimer);
        try {
            const res = await fetch('/audio/jobs');
            const jobs = await res.json();
            view.jobs = jobs;
            renderJobs(jobs);
            fillUploadPrevious(jobs);
            if (jobs.some(j => j.stage === 'queued' || j.stage === 'running')) {
                pollTimer = setTimeout(loadJobs, 2000);
            }
            // 보고 있던 작업이 방금 끝났으면 결과를 바로 띄운다
            const active = jobs.find(j => j.id === view.jobId);
            if (active && active.stage === 'done' && (!view.job || view.job.stage !== 'done')) openJob(active.id);
        } catch (e) {
            pollTimer = setTimeout(loadJobs, 5000);
        }
    }

    jobsEl.addEventListener('click', async (e) => {
        const card = e.target.closest('.va-job');
        if (!card) return;
        const id = card.dataset.id;
        const act = e.target.dataset.act;
        if (act === 'delete') {
            if (!confirm('이 분석 결과와 업로드한 녹음 파일을 삭제할까요?')) return;
            if (id === view.jobId) { audioEl.pause(); audioEl.removeAttribute('src'); audioEl.load(); }
            const res = await fetch(`/audio/jobs/${id}/delete`, { method: 'POST' });
            if (!res.ok) alert((await res.json().catch(() => ({}))).error || '삭제 실패');
            if (id === view.jobId) { resultCard.hidden = true; view.jobId = null; }
            loadJobs();
        } else if (e.target.closest('select')) {
            return;  // 화자 수 선택은 카드 열기로 처리하지 않는다
        } else if (act === 'retry') {
            const spk = card.querySelector('[data-role="spk"]');
            const res = await fetch(`/audio/jobs/${id}/retry`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(spk ? { num_speakers: Number(spk.value) } : {}),
            });
            if (!res.ok) alert((await res.json()).error || '재시도 실패');
            loadJobs();
        } else if (act === 'log') {
            const data = await (await fetch(`/audio/jobs/${id}/log`)).json();
            showPlain(id, card.querySelector('.va-job-name').textContent + ' — 로그', data.log || '(로그 없음)');
        } else {
            openJob(id);
        }
    });

    // ───────────────────────── 결과 열기 ─────────────────────────
    async function openJob(id) {
        view.jobId = id;
        document.querySelectorAll('.va-job').forEach(el => el.classList.toggle('is-active', el.dataset.id === id));
        const job = await (await fetch(`/audio/jobs/${id}`)).json();
        view.job = job;
        if (job.stage !== 'done') {
            showPlain(id, job.filename, `${STAGE_LABEL[job.stage] || job.stage}: ${job.message || ''}`);
            return;
        }
        renderResult(job);
    }

    function showPlain(id, title, text) {
        view.result = null;
        resultCard.hidden = false;
        $('r-title').textContent = title;
        $('r-sub').textContent = '';
        $('r-warnings').innerHTML = '';
        $('r-visual').hidden = true;
        $('r-player').hidden = true;
        document.querySelector('.va-tabs').hidden = true;
        $('kw-nav').hidden = true;
        $('copy-btn').hidden = $('dl-full').hidden = $('dl-minutes').hidden = true;
        panels().forEach(p => p.hidden = p.dataset.panel !== 'raw');
        panel('raw').textContent = text;
        resultCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function panels() { return Array.from(document.querySelectorAll('.va-panel')); }
    function panel(name) { return document.querySelector(`.va-panel[data-panel="${name}"]`); }

    function renderResult(job) {
        const r = job.result || null;
        view.result = r;
        view.markdown = job.markdown || '';
        view.minutes = (r && r.minutes_md) || '';
        view.keyword = null;
        view.marks = [];
        view.playingIdx = -1;
        resultCard.hidden = false;
        document.querySelector('.va-tabs').hidden = false;
        $('copy-btn').hidden = $('dl-full').hidden = false;
        $('dl-full').href = `/audio/jobs/${job.id}/md`;
        $('dl-minutes').href = `/audio/jobs/${job.id}/md?kind=minutes`;
        $('dl-minutes').hidden = !view.minutes;
        panel('raw').textContent = view.markdown;

        const a = r && r.analysis;
        $('r-title').textContent = (a && a.title) || job.filename;
        const sub = [];
        if (r) {
            if (r.meta.recorded_at) sub.push('🗓 ' + r.meta.recorded_at);
            sub.push('⏱ ' + fmtDur(r.meta.duration));
            sub.push(r.diarized ? `👥 화자 ${r.speakers.length}명` : '화자 구분 없음');
            if (a && a.type) sub.push(a.type);
            sub.push(job.filename);
        }
        $('r-sub').textContent = sub.join(' · ');

        const warns = [];
        if (r && !r.diarized) warns.push(`화자분리를 하지 못했습니다 (${esc((r.diar_skip || '원인 불명').split('\n')[0])})`);
        if (r && !a) warns.push(`요약을 생성하지 못했습니다: ${esc(r.summary_skip || '')}`);
        if (!r) warns.push('예전 형식의 결과입니다 — 키워드·타임라인을 보려면 목록에서 "재분석"을 누르세요 (받아쓰기는 재사용).');
        const fixes = (r && r.vocab_changes) || [];
        $('r-warnings').innerHTML = warns.map(w => `<div class="va-warn">⚠️ ${w}</div>`).join('') + (fixes.length
            ? `<div class="va-info">📖 단어장 교정 ${fixes.reduce((n, c) => n + c.count, 0)}곳 — ${fixes.map(c =>
                `<span class="va-fix">${esc(c.from)} → <b>${esc(c.to)}</b>${c.count > 1 ? ` ×${c.count}` : ''}</span>`).join(' ')}</div>` : '');

        if (!r) {
            $('r-visual').hidden = true;
            $('r-player').hidden = true;
            panel('summary').innerHTML = `<div class="va-md">${DOMPurify.sanitize(marked.parse(view.markdown))}</div>`;
            panel('minutes').innerHTML = '<p class="va-muted">회의록이 없습니다 (재분석 필요)</p>';
            panel('transcript').innerHTML = '<p class="va-muted">요약 탭의 전체 대화록을 보세요 (재분석하면 화자별로 표시됩니다)</p>';
            switchTab('summary');
            return;
        }

        $('r-visual').hidden = false;
        view.roles = rolesOf(r);
        renderShare(r);
        renderTimeline(r);
        renderKeywords(a);
        renderSummary(r);
        panel('minutes').innerHTML = view.minutes
            ? DOMPurify.sanitize(marked.parse(view.minutes))
            : '<p class="va-muted">요약이 없어 회의록을 만들지 못했습니다</p>';
        // 회의록 표 — 담당·요청자·수신자·기한·날짜·구분·No 칸은 좁게(두 줄) 잡아 내용 칸을 넓힌다
        const NARROW = ['담당', '요청자', '수신자', '기한', '날짜', '구분', '시각'];
        // 근거 시각 `@12:34` → 대화록 이동 버튼
        panel('minutes').querySelectorAll('code').forEach(c => {
            const m = /^@(?:(\d+):)?(\d{1,2}):(\d{2})$/.exec(c.textContent.trim());
            if (!m) return;
            c.outerHTML = tsBtn(Number(m[1] || 0) * 3600 + Number(m[2]) * 60 + Number(m[3]));
        });
        panel('minutes').querySelectorAll('table').forEach(t => {
            const head = Array.from(t.querySelectorAll('th')).map(th => th.textContent.trim());
            if (!head.some(h => NARROW.includes(h))) return;
            t.classList.add('va-md-grid');
            head.forEach((h, i) => {
                const cls = h === 'No' ? 'va-col-no' : (NARROW.includes(h) ? 'va-col-narrow' : '');
                if (cls) t.querySelectorAll(`tr > :nth-child(${i + 1})`).forEach(c => c.classList.add(cls));
            });
        });
        if (r.diarized) { decorateSpeakers(panel('summary')); decorateSpeakers(panel('minutes')); }
        renderTranscript(r);

        // 녹음 재생
        resultCard.classList.toggle('has-player', !!job.has_audio);
        if (job.has_audio) {
            $('r-player').hidden = false;
            audioEl.src = `/audio/jobs/${job.id}/audio`;
            audioEl.playbackRate = 1;
            $('p-rate').textContent = '1x';
            $('r-now').textContent = '';
            updatePlayer();
        } else {
            $('r-player').hidden = true;
        }
        switchTab(view.tab || 'summary');
        clearKeyword();
        resultCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    // ───────────────────────── 시각화 ─────────────────────────
    // LLM 이 주는 역할 문구 정리 — '불명', '불명 (법무 관련 직원 추정)' → '' / '법무 관련 직원'
    function cleanRole(role) {
        role = String(role || '').trim();
        const m = /^불명\s*[(（](.*)[)）]$/.exec(role);
        if (m) role = m[1].replace(/\s*추정$/, '').trim();
        return (!role || role === '불명' || role === '-') ? '' : role;
    }
    function rolesOf(r) {
        const roles = {};
        ((r.analysis && r.analysis.participants) || []).forEach(p => {
            const role = cleanRole(p.role);
            if (role) roles[p.speaker] = role;
        });
        return roles;
    }
    // 화자 칩에 추정 역할을 작게 덧붙인다 (요약 주제 카드·할 일 담당 등)
    function spkChip(label) {
        const role = view.roles[label];
        return `<span class="va-chip ${spkClass(label)}">${esc(label)}${role ? `<span class="va-chip-role">${esc(role)}</span>` : ''}</span>`;
    }

    function renderShare(r) {
        const total = r.speakers.reduce((s, x) => s + x.seconds, 0) || 1;
        $('r-share').innerHTML = r.speakers.map(s =>
            `<div class="${spkClass(s.speaker)}" style="width:${(s.seconds / total * 100).toFixed(2)}%" title="${esc(s.speaker)} ${Math.round(s.seconds / total * 100)}%"></div>`).join('');
        // 화자 · 역할 · 비율을 칸으로 나눈 목록 — 한 칩에 다 붙이면 번호와 %가 섞여 한눈에 안 들어온다
        $('r-legend').innerHTML = r.speakers.map(s => `<div class="va-spk-row ${spkClass(s.speaker)}">
                <span class="va-spk-dot"></span><span class="va-spk-name">${esc(s.speaker)}</span>
                <span class="va-spk-role">${esc(view.roles[s.speaker] || '역할 미상')}</span>
                <span class="va-spk-pct">${Math.round(s.seconds / total * 100)}%</span>
            </div>`).join('');
    }

    // 요약·회의록 본문의 '화자 N' 에 화자 색과 추정 역할을 붙인다 (대화록 머리글과 같은 정보를 다른 탭에서도)
    function decorateSpeakers(root) {
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
            acceptNode: n => (/화자\s?\d+/.test(n.nodeValue) && !n.parentNode.closest('.va-chip, .va-spk-ref, button'))
                ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT,
        });
        const nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        nodes.forEach(node => {
            const frag = document.createDocumentFragment();
            const text = node.nodeValue, re = /화자\s?(\d+)/g;
            let pos = 0, m;
            while ((m = re.exec(text))) {
                if (m.index > pos) frag.appendChild(document.createTextNode(text.slice(pos, m.index)));
                const label = '화자 ' + m[1], role = view.roles[label];
                const span = document.createElement('span');
                span.className = 'va-spk-ref ' + spkClass(label);
                span.textContent = m[0];
                // 표 칸(회의록 참석자·향후 조치 담당)에는 역할이 이미 적혀 있어 다시 안 붙인다
                if (role && !node.parentNode.closest('td') && !text.slice(re.lastIndex).trimStart().startsWith('(')) {
                    const small = document.createElement('small');
                    small.textContent = role;
                    span.appendChild(small);
                }
                frag.appendChild(span);
                pos = re.lastIndex;
            }
            if (pos < text.length) frag.appendChild(document.createTextNode(text.slice(pos)));
            node.parentNode.replaceChild(frag, node);
        });
    }

    function renderTimeline(r) {
        const dur = r.meta.duration || 1;
        const pct = (t) => (Math.min(Math.max(t, 0), dur) / dur * 100).toFixed(3) + '%';
        const topics = (r.analysis && r.analysis.topics) || [];
        const rows = [];
        if (topics.length) {
            // 막대에는 번호만 — 안건이 많으면 제목이 '…'로 잘려 안 보였다. 제목은 아래 목록에서 다 보여 준다
            rows.push(`<div class="va-tl-row is-topic"><div class="va-tl-label">주제</div><div class="va-tl-track">${
                topics.map((t, i) => `<div class="va-tl-topic" data-seek="${t.start}" data-topic="${i}" style="left:${pct(t.start)};width:calc(${pct(t.end)} - ${pct(t.start)})" title="${i + 1}. ${esc(t.title)} (${fmtTs(t.start)}~${fmtTs(t.end)})">${i + 1}</div>`).join('')
            }</div></div>`);
        }
        if (r.diarized) {
            r.speakers.forEach(s => {
                const segs = r.utterances.filter(u => u.speaker === s.speaker)
                    .map(u => `<div class="va-tl-seg" style="left:${pct(u.start)};width:max(2px, calc(${pct(u.end)} - ${pct(u.start)}))"></div>`).join('');
                rows.push(`<div class="va-tl-row ${spkClass(s.speaker)}"><div class="va-tl-label" title="${esc(s.speaker)}">${esc(s.speaker)}</div><div class="va-tl-track">${segs}</div></div>`);
            });
        }
        rows.push(`<div class="va-tl-row" id="tl-kw-row" hidden><div class="va-tl-label">키워드</div><div class="va-tl-track" id="tl-kw-track"></div></div>`);
        // 눈금: 길이에 맞춰 1/5/10/15/30분 간격
        const step = [60, 300, 600, 900, 1800, 3600].find(s => dur / s <= 10) || 3600;
        const ticks = [];
        for (let t = 0; t <= dur; t += step) ticks.push(`<span style="left:${pct(t)}">${fmtTs(t)}</span>`);
        const legend = topics.length ? `<ol class="va-tl-topics">${topics.map((t, i) =>
            `<li data-seek="${t.start}" data-topic="${i}"><span class="va-tl-no">${i + 1}</span><span class="va-tl-title">${esc(t.title)}</span><span class="va-tl-time">${fmtTs(t.start)}–${fmtTs(t.end)}</span></li>`).join('')}</ol>` : '';
        $('r-timeline').innerHTML = `<div class="va-tl-scroll"><div class="va-tl-inner">${rows.join('')}<div class="va-tl-axis">${ticks.join('')}</div><div class="va-tl-cursor" id="tl-cursor"></div></div></div>${legend}`;
        // 주제가 많으면 막대 번호가 안 읽힐 만큼 좁아진다 — 주제당 48px 이상 확보하고 모자라면 가로 스크롤
        const inner = $('r-timeline').querySelector('.va-tl-inner');
        const scroller = $('r-timeline').querySelector('.va-tl-scroll');
        inner.style.minWidth = Math.max(560, topics.length * 48 + 64) + 'px';
        const markEnd = () => {
            scroller.classList.toggle('is-scrollable', scroller.scrollWidth > scroller.clientWidth + 2);
            scroller.classList.toggle('at-end', scroller.scrollLeft + scroller.clientWidth >= scroller.scrollWidth - 2);
        };
        scroller.addEventListener('scroll', markEnd, { passive: true });
        requestAnimationFrame(markEnd);
    }

    function timelineKeywordMarks(word) {
        const row = $('tl-kw-row');
        if (!row) return;
        if (!word || !view.result) { row.hidden = true; return; }
        const dur = view.result.meta.duration || 1, w = word.toLowerCase();
        const hits = view.result.utterances.filter(u => u.text.toLowerCase().includes(w));
        $('tl-kw-track').innerHTML = hits.map(u => `<div class="va-tl-kw" data-seek="${u.start}" style="left:${(u.start / dur * 100).toFixed(3)}%" title="${fmtTs(u.start)} ${esc(u.speaker)}"></div>`).join('');
        row.hidden = false;
    }

    // 막대에 올리면 목록의 같은 주제를, 목록에 올리면 막대를 함께 강조
    $('r-timeline').addEventListener('mouseover', (e) => {
        const t = e.target.closest('[data-topic]');
        document.querySelectorAll('#r-timeline [data-topic]').forEach(el =>
            el.classList.toggle('is-hover', !!t && el.dataset.topic === t.dataset.topic));
    });
    $('r-timeline').addEventListener('click', (e) => {
        const target = e.target.closest('[data-seek]');
        if (target) { seek(Number(target.dataset.seek)); return; }
        const track = e.target.closest('.va-tl-track');
        if (!track || !view.result) return;
        const rect = track.getBoundingClientRect();
        seek((e.clientX - rect.left) / rect.width * view.result.meta.duration);
    });

    function renderKeywords(a) {
        const kws = (a && a.keywords) || [];
        $('r-keywords').innerHTML = kws.length
            ? kws.map(k => `<button type="button" class="va-kw" data-kw="${esc(k.word)}">${esc(k.word)}<small>${k.count}</small></button>`).join('')
            : '<span class="va-muted">키워드 없음</span>';
    }

    // ───────────────────────── 요약 탭 ─────────────────────────
    // 할 일 표: 담당은 '화자 2 / 디자인 리더', 기한은 '차주 / 화요일' 두 줄로 — 모바일에서 내용 칸에 폭을 몰아준다
    function ownerHtml(owner) {
        const m = /^화자\s?(\d+)/.exec(owner || '');
        if (!m) return esc(owner);
        const label = '화자 ' + m[1], role = view.roles[label];
        const short = role ? role.split(/[,，/]/)[0].trim() : '';  // 좁은 칸이라 첫 마디만
        return `<span class="va-chip ${spkClass(label)}">${esc(label)}</span>${short ? `<span class="va-owner-role" title="${esc(role)}">${esc(short)}</span>` : ''}`;
    }
    function dueHtml(due) {
        const parts = String(due || '').trim().split(/\s+/);
        return parts.length > 1 ? `${esc(parts[0])}<br>${esc(parts.slice(1).join(' '))}` : esc(due);
    }
    // 요약 6개 항목: 회의 개요 · AI 핵심 요약 · 결정사항 · 조치사항 · 이슈 및 미결사항 · 이전 회의 대비 변경사항.
    // 논의 내용(주제별 세부)은 회의록 탭 '1. 논의사항'과 타임라인 주제 목록에서 본다 — 요약에 다 넣으니 너무 길었다
    function renderSummary(r) {
        const a = r.analysis;
        if (!a) {
            panel('summary').innerHTML = `<div class="va-md">${DOMPurify.sanitize(marked.parse(view.markdown))}</div>`;
            return;
        }
        const html = [];

        const ov = [];
        if (r.meta.recorded_at) ov.push(['일시', esc(r.meta.recorded_at)]);
        ov.push(['길이', esc(fmtDur(r.meta.duration))]);
        if (r.diarized && r.speakers.length) ov.push(['참석', r.speakers.map(s => spkChip(s.speaker)).join(' ')]);
        if (a.purpose) ov.push(['목적', esc(a.purpose)]);
        if (a.overview) ov.push(['안건', esc(a.overview)]);
        html.push(`<div class="va-sec"><h3>📌 회의 개요</h3><dl class="va-overview-list">${
            ov.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl></div>`);

        html.push(`<div class="va-sec va-conclusion"><h3>🧠 AI 핵심 요약</h3><p class="va-summary-text">${esc(a.summary_text || '-')}</p></div>`);

        html.push(`<div class="va-sec"><h3>✅ 결정사항</h3>${list(a.decisions, 'va-decisions')}</div>`);

        html.push(`<div class="va-sec"><h3>📋 조치사항</h3>${(a.action_items || []).length
            ? `<div class="va-table-wrap"><table class="va-table va-actions-table"><thead><tr><th class="va-owner-cell">담당</th><th>수행 작업</th><th class="va-due-cell">기한</th></tr></thead><tbody>${
                a.action_items.map(x => `<tr><td class="va-owner-cell">${ownerHtml(x.owner)}</td><td>${esc(x.task)}${quoteTs(x)}</td><td class="va-due-cell">${dueHtml(x.due)}${x.due_resolved ? `<br><small>${esc(x.due_resolved)}</small>` : ''}</td></tr>`).join('')
            }</tbody></table></div>` : '<p class="va-muted">없음</p>'}</div>`);

        const risks = (a.risks || []).map(x => `<li class="va-risk"><b>${esc(x.issue)}</b>${quoteTs(x)}${
            unset(x.risk) ? '' : `<span class="va-risk-line">영향: ${esc(x.risk)}</span>`}${
            unset(x.response) ? '' : `<span class="va-risk-line">대응: ${esc(x.response)}</span>`}</li>`);
        const open = (a.issues || []).map(x => `<li class="va-open">${itemHtml(x)}</li>`);
        html.push(`<div class="va-sec"><h3>⚠️ 이슈 및 미결사항</h3>${risks.length + open.length
            ? `<ul class="va-issue-list">${risks.join('')}${open.join('')}</ul>` : '<p class="va-muted">없음</p>'}</div>`);

        html.push(`<div class="va-sec" id="compare-sec"><h3>🔁 이전 회의 대비 변경사항</h3>${renderCompare(r)}</div>`);
        panel('summary').innerHTML = html.join('');
    }

    const FOLLOW_CLASS = { '완료': 'done', '진행 중': 'doing', '지연': 'late', '변경': 'changed', '언급 없음': 'none' };

    function renderCompare(r) {
        const c = r.compare;
        const picker = compareSelectHtml(c && c.previous && c.previous.job_id);
        if (!c) {
            return `<p class="va-muted">비교할 이전 회의를 고르면 지난번 조치사항의 진행 상태와 바뀐 결정·일정을 정리합니다 (요약만 다시 돌려 1~3분).</p>${picker}`;
        }
        const prev = c.previous || {};
        const parts = [`<p class="va-compare-target">비교 대상: <b>${esc(prev.title || '')}</b> <span class="va-muted">${esc(prev.recorded_at || prev.created_at || '')}</span></p>`];
        if ((c.followups || []).length) {
            parts.push(`<div class="va-table-wrap"><table class="va-table"><thead><tr><th>이전 조치·요청</th><th class="va-status-cell">상태</th></tr></thead><tbody>${
                c.followups.map(f => `<tr><td>${esc(f.item)}${f.note ? `<span class="va-risk-line">${esc(f.note)}</span>` : ''}</td><td class="va-status-cell"><span class="va-status ${FOLLOW_CLASS[f.status] || 'none'}">${esc(f.status)}</span></td></tr>`).join('')
            }</tbody></table></div>`);
        }
        if ((c.changes || []).length) {
            parts.push(`<ul class="va-change-list">${c.changes.map(x =>
                `<li><span class="va-change-cat">${esc(x.category)}</span> <s>${esc(x.before)}</s> → <b>${esc(x.after)}</b></li>`).join('')}</ul>`);
        }
        if (!(c.followups || []).length && !(c.changes || []).length) parts.push('<p class="va-muted">변경사항 없음</p>');
        parts.push(picker);
        return parts.join('');
    }

    // 이전 회의 고르기 — 본인의 다른 완료 작업. 바꾸면 요약만 다시 돌린다(받아쓰기·화자분리 재사용)
    function compareSelectHtml(current) {
        const cands = (view.jobs || []).filter(j => j.stage === 'done' && j.id !== view.jobId);
        if (!cands.length) return '<p class="va-muted">비교할 다른 분석 결과가 없습니다.</p>';
        return `<div class="va-row va-compare-pick"><select id="compare-select" class="va-input">
            <option value="">이전 회의 선택…</option>${cands.map(j =>
                `<option value="${j.id}"${j.id === current ? ' selected' : ''}>${esc((j.title || j.filename) + ' · ' + j.created_at.slice(0, 10))}</option>`).join('')}
            </select><button type="button" class="va-btn va-btn-sm" id="compare-btn">${current ? '다시 비교' : '비교하기'}</button></div>`;
    }

    panel('summary').addEventListener('click', async (e) => {
        if (e.target.id !== 'compare-btn') return;
        const prev = $('compare-select').value;
        if (!prev) { showDebugToast('이전 회의를 고르세요'); return; }
        const res = await fetch(`/audio/jobs/${view.jobId}/retry`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ previous_job: prev }),
        });
        if (!res.ok) { alert((await res.json().catch(() => ({}))).error || '비교 요청 실패'); return; }
        showDebugToast('이전 회의와 비교를 시작했습니다 — 끝나면 자동으로 다시 보여 줍니다');
        view.job = Object.assign({}, view.job, { stage: 'queued' });  // 끝나면 loadJobs 가 다시 연다
        loadJobs();
    });

    // ───────────────────────── 대화록 탭 ─────────────────────────
    function renderTranscript(r) {
        const roles = rolesOf(r);
        const topics = ((r.analysis && r.analysis.topics) || []).slice();
        let ti = 0, prev = null;
        const html = [];
        view.utterStarts = r.utterances.map(u => u.start);
        r.utterances.forEach((u, i) => {
            while (ti < topics.length && topics[ti].start <= u.start + 0.5) {
                html.push(`<div class="va-topic-divider"><span class="va-topic-no">${ti + 1}</span>${esc(topics[ti].title)} ${tsBtn(topics[ti].start)}</div>`);
                ti++;
                prev = null;  // 주제가 바뀌면 같은 화자여도 머리글을 다시 보인다
            }
            const cont = prev && prev.speaker === u.speaker;
            html.push(`<div class="va-utt ${spkClass(u.speaker)}${cont ? ' is-cont' : ''}" data-idx="${i}">
                <div class="va-utt-head">${cont ? '' : `<span class="va-utt-name">${esc(u.speaker)}</span>${roles[u.speaker] ? `<span class="va-utt-role">${esc(roles[u.speaker])}</span>` : ''}`}${tsBtn(u.start)}</div>
                <div class="va-utt-body">${splitSentences(u.text).map(p => `<p>${esc(p)}</p>`).join('')}</div>
            </div>`);
            prev = u;
        });
        panel('transcript').innerHTML = `<div class="va-utts">${html.join('')}</div>`;
    }

    // ───────────────────────── 탭 / 복사 ─────────────────────────
    function switchTab(name) {
        view.tab = name;
        document.querySelectorAll('.va-tab').forEach(b => b.classList.toggle('is-active', b.dataset.tab === name));
        panels().forEach(p => p.hidden = p.dataset.panel !== name);
        if (view.keyword) collectMarks(true);
    }
    document.querySelector('.va-tabs').addEventListener('click', (e) => {
        const b = e.target.closest('.va-tab');
        if (b) switchTab(b.dataset.tab);
    });

    $('copy-btn').addEventListener('click', async () => {
        const text = view.tab === 'minutes' && view.minutes ? view.minutes : view.markdown;
        try {
            await navigator.clipboard.writeText(text);
            showDebugToast(view.tab === 'minutes' ? '회의록을 복사했습니다' : '전체 마크다운을 복사했습니다');
        } catch (e) {
            alert('복사 실패: ' + e);
        }
    });

    // ───────────────────────── 키워드 하이라이트 ─────────────────────────
    const HL_PANELS = ['summary', 'minutes', 'transcript'];

    function clearMarks(root) {
        root.querySelectorAll('mark.va-hl').forEach(m => {
            const parent = m.parentNode;
            parent.replaceChild(document.createTextNode(m.textContent), m);
            parent.normalize();
        });
    }

    function markText(root, word) {
        const w = word.toLowerCase();
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
            acceptNode: n => (n.nodeValue.toLowerCase().includes(w) && !n.parentNode.closest('button')) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT,
        });
        const nodes = [];
        while (walker.nextNode()) nodes.push(walker.currentNode);
        nodes.forEach(node => {
            const text = node.nodeValue, lower = text.toLowerCase();
            const frag = document.createDocumentFragment();
            let pos = 0, idx;
            while ((idx = lower.indexOf(w, pos)) !== -1) {
                if (idx > pos) frag.appendChild(document.createTextNode(text.slice(pos, idx)));
                const m = document.createElement('mark');
                m.className = 'va-hl';
                m.textContent = text.slice(idx, idx + w.length);
                frag.appendChild(m);
                pos = idx + w.length;
            }
            if (pos < text.length) frag.appendChild(document.createTextNode(text.slice(pos)));
            node.parentNode.replaceChild(frag, node);
        });
    }

    function countIn(name) { return panel(name).querySelectorAll('mark.va-hl').length; }

    function collectMarks(jumpFirst) {
        view.marks = Array.from(panel(view.tab).querySelectorAll('mark.va-hl'));
        view.markIdx = -1;
        updateKwNav();
        if (jumpFirst && view.marks.length) gotoMark(0);
    }

    function updateKwNav() {
        const nav = $('kw-nav');
        if (!view.keyword) { nav.hidden = true; return; }
        nav.hidden = false;
        const tabName = { summary: '요약', minutes: '회의록', transcript: '대화록', raw: '원문' }[view.tab];
        const here = view.marks.length ? `${view.markIdx + 1}/${view.marks.length}` : '없음';
        $('kw-nav-label').textContent = `"${view.keyword}" — ${tabName} ${here} · 대화록 ${countIn('transcript')} · 요약 ${countIn('summary')} · 회의록 ${countIn('minutes')}`;
        $('kw-prev').disabled = $('kw-next').disabled = view.marks.length === 0;
    }

    function gotoMark(i) {
        if (!view.marks.length) return;
        view.markIdx = (i + view.marks.length) % view.marks.length;
        view.marks.forEach((m, k) => m.classList.toggle('is-current', k === view.markIdx));
        view.marks[view.markIdx].scrollIntoView({ behavior: 'smooth', block: 'center' });
        updateKwNav();
    }

    function setKeyword(word) {
        HL_PANELS.forEach(p => clearMarks(panel(p)));
        view.keyword = word;
        document.querySelectorAll('.va-kw').forEach(b => b.classList.toggle('is-active', b.dataset.kw === word));
        timelineKeywordMarks(word);
        if (!word) { view.marks = []; updateKwNav(); return; }
        HL_PANELS.forEach(p => markText(panel(p), word));
        // 키워드는 대화 원문에서 찾는 게 목적 — 원문 MD 탭에 있으면 대화록으로
        if (view.tab === 'raw') switchTab('transcript');
        if (!countIn(view.tab) && countIn('transcript')) switchTab('transcript');
        collectMarks(true);
    }
    function clearKeyword() { $('kw-search').value = ''; setKeyword(null); }

    $('r-keywords').addEventListener('click', (e) => {
        const b = e.target.closest('.va-kw');
        if (!b) return;
        if (view.keyword === b.dataset.kw) { clearKeyword(); return; }
        switchTab('transcript');
        setKeyword(b.dataset.kw);
    });
    // 키워드 목록에 없는 말도 찾을 수 있게 — 같은 강조·이동 기능을 쓴다
    $('kw-search').addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;
        const q = e.target.value.trim();
        if (!q) { clearKeyword(); return; }
        if (view.tab === 'summary' || view.tab === 'raw') switchTab('transcript');
        setKeyword(q);
        if (!view.marks.length && !countIn('transcript')) showDebugToast(`"${q}" — 찾지 못했습니다`);
    });
    $('kw-search').addEventListener('search', (e) => { if (!e.target.value) clearKeyword(); });
    $('kw-prev').addEventListener('click', () => gotoMark(view.markIdx - 1));
    $('kw-next').addEventListener('click', () => gotoMark(view.markIdx + 1));
    $('kw-clear').addEventListener('click', clearKeyword);

    // ───────────────────────── 재생 ─────────────────────────
    function seek(sec) {
        if (!view.result) return;
        sec = Math.max(0, sec);
        // 대화록에서 해당 발화로 이동
        const idx = utteranceAt(sec);
        if (view.tab !== 'transcript') switchTab('transcript');
        const el = panel('transcript').querySelector(`.va-utt[data-idx="${idx}"]`);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        if (!$('r-player').hidden) {
            try {
                audioEl.currentTime = sec;
                audioEl.play().catch(() => {});
            } catch (e) {}
        }
    }

    function utteranceAt(sec) {
        const starts = view.utterStarts;
        let lo = 0, hi = starts.length - 1, ans = 0;
        while (lo <= hi) {
            const mid = (lo + hi) >> 1;
            if (starts[mid] <= sec + 0.05) { ans = mid; lo = mid + 1; } else { hi = mid - 1; }
        }
        return ans;
    }

    resultCard.addEventListener('click', (e) => {
        const b = e.target.closest('.va-ts[data-seek]');
        if (b && !e.target.closest('#r-timeline')) seek(Number(b.dataset.seek));
    });

    // ── 재생 바 (직접 그림) — 전체 길이는 분석 결과에 있어 재생 전에도 '00:00 / 38:30' 으로 보인다
    const RATES = [1, 1.25, 1.5, 2];
    let seeking = false;
    function playerDuration() {
        return (isFinite(audioEl.duration) && audioEl.duration) || (view.result && view.result.meta.duration) || 0;
    }
    function updatePlayer() {
        const d = playerDuration(), t = audioEl.currentTime || 0;
        if (!seeking) {
            $('p-time').textContent = `${fmtTs(t)} / ${fmtTs(d)}`;
            $('p-seek').value = d ? Math.round(t / d * 1000) : 0;
        }
        $('p-play').textContent = audioEl.paused ? '▶' : '❚❚';
        $('p-play').setAttribute('aria-label', audioEl.paused ? '재생' : '일시정지');
    }
    $('p-play').addEventListener('click', () => { if (audioEl.paused) audioEl.play().catch(() => {}); else audioEl.pause(); });
    $('p-seek').addEventListener('input', (e) => {
        seeking = true;
        const d = playerDuration();
        $('p-time').textContent = `${fmtTs(d * e.target.value / 1000)} / ${fmtTs(d)}`;
    });
    $('p-seek').addEventListener('change', (e) => {
        try { audioEl.currentTime = playerDuration() * e.target.value / 1000; } catch (err) {}
        seeking = false;
        updatePlayer();
    });
    $('p-rate').addEventListener('click', () => {
        const next = RATES[(RATES.indexOf(audioEl.playbackRate) + 1) % RATES.length];
        audioEl.playbackRate = next;
        $('p-rate').textContent = next + 'x';
    });
    ['play', 'pause', 'ended', 'loadedmetadata', 'durationchange'].forEach(ev => audioEl.addEventListener(ev, updatePlayer));

    audioEl.addEventListener('timeupdate', () => {
        updatePlayer();
        if (!view.result) return;
        const t = audioEl.currentTime, dur = view.result.meta.duration || 1;
        const cursor = $('tl-cursor');
        if (cursor) {
            cursor.style.display = 'block';
            const track = document.querySelector('.va-tl-track');
            if (track) {
                const inner = track.closest('.va-tl-inner');
                const x = track.offsetLeft + track.offsetWidth * Math.min(t / dur, 1);
                cursor.style.left = x + 'px';
                cursor.style.height = (inner.offsetHeight - 16) + 'px';
            }
        }
        const idx = utteranceAt(t);
        if (idx !== view.playingIdx) {
            const old = panel('transcript').querySelector('.va-utt.is-playing');
            if (old) old.classList.remove('is-playing');
            const el = panel('transcript').querySelector(`.va-utt[data-idx="${idx}"]`);
            if (el) el.classList.add('is-playing');
            view.playingIdx = idx;
            const u = view.result.utterances[idx];
            if (u) $('r-now').textContent = `${fmtTs(u.start)} ${u.speaker}`;
        }
    });

    // ───────────────────────── 단어장 ─────────────────────────
    function renderDictSummary(d) {
        $('dict-summary').textContent = `— 힌트 ${d.hotwords.length}개 · 교정 규칙 ${d.corrections.length}개`;
    }
    async function loadDictionary() {
        try {
            const d = await (await fetch('/audio/dictionary')).json();
            $('dict-hotwords').value = d.hotwords.join('\n');
            $('dict-corrections').value = d.corrections.map(c => `${c.from} => ${c.to}`).join('\n');
            renderDictSummary(d);
        } catch (e) { /* 재시작 전 서버에는 이 경로가 없다 */ }
    }
    $('dict-save').addEventListener('click', async () => {
        const res = await fetch('/audio/dictionary', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ hotwords: $('dict-hotwords').value, corrections: $('dict-corrections').value }),
        });
        if (!res.ok) { alert('단어장 저장 실패 (' + res.status + ')'); return; }
        const d = await res.json();
        renderDictSummary(d);
        $('dict-corrections').value = d.corrections.map(c => `${c.from} => ${c.to}`).join('\n');
        showDebugToast('단어장을 저장했습니다 — 목록에서 재분석하면 반영됩니다');
    });

    document.addEventListener('visibilitychange', () => { if (!document.hidden) loadJobs(); });
    loadJobs();
    loadDictionary();
})();
