class BufferedRecorder {
    constructor(stream, options = {}) {
        this.stream = stream;
        this.mimeType = 'video/webm';
        this.chunkDuration = options.chunkDuration || 10; // seconds
        this.bufferDuration = options.bufferDuration || 60; // seconds
        this.maxChunks = Math.ceil(this.bufferDuration / this.chunkDuration);

        this.recorder = null;
        this.initChunk = null; // EBML 헤더 + Tracks 포함 첫 번째 청크 (절대 버리지 않음)
        this.chunks = [];
    }

    start() {
        if (this.recorder) return;

        this.recorder = new MediaRecorder(this.stream, { mimeType: this.mimeType });
        this.recorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) {
                if (!this.initChunk) {
                    // 첫 번째 청크: EBML 헤더 + Tracks 포함 → 항상 보존
                    this.initChunk = e.data;
                } else {
                    this.chunks.push(e.data);
                    if (this.chunks.length > this.maxChunks) {
                        this.chunks.shift(); // 오래된 클러스터만 제거
                    }
                }
            }
        };
        this.recorder.start(this.chunkDuration * 1000); // 일정 시간마다 blob 생성
        console.log('[Recorder] started with', this.maxChunks, 'chunks max');
    }

    stop() {
        if (this.recorder && this.recorder.state !== 'inactive') {
            this.recorder.stop();
            this.recorder = null;
        }
    }

    getBufferedBlob() {
        // initChunk 없으면 녹화 시작 전에 버튼 누른 것
        if (!this.initChunk) return new Blob([], { type: this.mimeType });
        return new Blob([this.initChunk, ...this.chunks], { type: this.mimeType });
    }

    uploadBufferedBlob(uploadUrl, title = "video-call") {
        const blob = this.getBufferedBlob();
        const formData = new FormData();
        formData.append('files[]', blob, `video-call_${this.#getTimestamp()}_recording.webm`);
        formData.append('title', title);

        return fetch(uploadUrl, {
            method: 'POST',
            body: formData
        }).then(res => {
            if (res.ok) {
                this.#showDebugToast('✅ 업로드 성공');
            } else {
                res.json().then(data => {
                    console.error('[Upload] 실패:', res.status, data);
                    this.#showDebugToast(`❌ 업로드 실패 (${res.status}): ${data?.error || 'retry'}`);
                }).catch(() => {
                    console.error('[Upload] 실패:', res.status, res.url);
                    this.#showDebugToast(`❌ 업로드 실패 (${res.status})`);
                });
            }
        }).catch(error => {
            console.error('[Upload] 네트워크 오류:', error);
            this.#showDebugToast('❌ 업로드 실패');
        });
    }

    // 2025-05-09T10-05-16-041Z
    /*#getTimestamp() {
        const now = new Date();
        return now.toISOString().replace(/[:.]/g, '-');
    }*/

    // 2025-05-09_220933
    #getTimestamp() {
        const now = new Date();
        const yyyy = now.getFullYear();
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        const hh = String(now.getHours()).padStart(2, '0');
        const mi = String(now.getMinutes()).padStart(2, '0');
        const ss = String(now.getSeconds()).padStart(2, '0');

        return `${yyyy}-${mm}-${dd}_${hh}${mi}${ss}`;
    }

    #showDebugToast(message, duration = 3000) {
        let container = document.getElementById('debug-toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'debug-toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = 'debug-toast';
        toast.textContent = message;

        container.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, duration);
    }

}
