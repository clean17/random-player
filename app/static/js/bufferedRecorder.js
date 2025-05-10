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
        formData.append('files[]', blob, `video-call_recording_${this._getTimestamp()}.webm`);
        formData.append('title', title);

        return fetch(uploadUrl, {
            method: 'POST',
            body: formData
        }).then(res => {
            if (res.ok) {
                console.log('✅ 업로드 성공');
            } else {
                console.error('❌ 업로드 실패');
            }
        });
    }

    _getTimestamp() {
        const now = new Date();
        return now.toISOString().replace(/[:.]/g, '-');
    }
}
