class BufferedRecorder {
    constructor(stream, options = {}) {
        this.stream = stream;
        this.mimeType = 'video/webm';
        this.chunkDuration = options.chunkDuration || 10; // seconds
        this.bufferDuration = options.bufferDuration || 60; // seconds
        this.maxChunks = Math.ceil(this.bufferDuration / this.chunkDuration);

        this.recorder = null;
        this.chunks = [];
    }

    start() {
        if (this.recorder) return;

        this.recorder = new MediaRecorder(this.stream, { mimeType: this.mimeType });
        this.recorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) {
                this.chunks.push(e.data);
                if (this.chunks.length > this.maxChunks) {
                    this.chunks.shift(); // 오래된 것 제거
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
        return new Blob(this.chunks, { type: this.mimeType });
    }

    uploadBufferedBlob(uploadUrl, title = "video-call") {
        const blob = this.getBufferedBlob();
        const formData = new FormData();
        formData.append('files[]', blob, `video-call_${this._getTimestamp()}_recording.webm`);
        formData.append('title', title);

        return fetch(uploadUrl, {
            method: 'POST',
            body: formData
        }).then(res => {
            if (res.ok) {
                this._showDebugToast('✅ 업로드 성공');
            } else {
                this._showDebugToast('❌ 업로드 실패, retry');
            }
        }).catch(error => {
            this._showDebugToast('❌ 업로드 실패');
        });
    }

    // 2025-05-09T10-05-16-041Z
    /*_getTimestamp() {
        const now = new Date();
        return now.toISOString().replace(/[:.]/g, '-');
    }*/

    // 2025-05-09_220933
    _getTimestamp() {
        const now = new Date();
        const yyyy = now.getFullYear();
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        const hh = String(now.getHours()).padStart(2, '0');
        const mi = String(now.getMinutes()).padStart(2, '0');
        const ss = String(now.getSeconds()).padStart(2, '0');

        return `${yyyy}-${mm}-${dd}_${hh}${mi}${ss}`;
    }

    _showDebugToast(message, duration = 3000) {
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
