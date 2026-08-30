const videoContainer = document.querySelector('#videoContainer');
let videoPlayer = document.querySelector('#videoPlayer');
let videoSource = document.querySelector('#videoSource');
let videoLeft ;
let videoRight ;
let player;
let currentVideo = '';
const previousVideos = []
const controls = document.querySelector('#controls');
const topDiv = document.querySelector('.top-bar');
const syncMessage = document.getElementById('sync-message');
const volumeMessage = document.getElementById('volume-message');
const filenameDisplay = document.getElementById('video-filename');
const videoCountEl = document.getElementById('videoCount');
let totalVideoCount = null; // 디렉터리 내 전체 영상 개수 (목록을 새로 받아올 때마다 갱신, 삭제 시 즉시 -1)
const prevButton = document.getElementById('prevButton');
const loopButton = document.getElementById('loopbutton');
const aBtn  = document.getElementById('aButton');
const bBtn  = document.getElementById('bButton');
const fullScreenBtn = document.getElementById('fullScreen');
const toggleGainBtn = document.getElementById('toggleGain');
let mimeType;
let audioContext;
let syncAudioElement; // 오디오만 따로 재생하는 숨김 <audio> 엘리먼트 (영상과 currentTime을 어긋나게 맞춰 동기화)
let syncVideoElement; // 위 오디오 엘리먼트가 currentTime을 맞춰 따라가는 기준이 되는 실제 <video> DOM 엘리먼트
let audioGainNode;
let audioOffset = 0;
let syncAudioActive = false; // 별도 <audio> 그래프가 실제로 켜져 있는지 (지연 초기화 — 안 만지면 부하 0)
let pendingIsVjs = false;
let hideControlsTimeout;
let isLooping = false;
let isSectionLooping = false;
let isClickAbtn = false;
let isClickBbtn = false;
let isClickGain = false;
let previousVolume = 1.0;
let startTime = 0;
let endTime = 0;
let fetchVideoArr = [];
let isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
const heartButton = document.getElementById('heartButton');
const likeFilterSelect = document.getElementById('likeFilterSelect');
let likedVideosSet = new Set(); // 현재 dir에서 하트한 영상 파일명 집합 (서버에서 한 번에 불러와 캐시)
let likeFilterMode = 'unliked'; // 'unliked' | 'liked' — Next가 어느 목록에서 뽑을지
let isFetchingVideoList = false; // 목록이 빈 상태에서 PageDown을 연타하면 axios.get이 중복으로 나가는 것을 막는 가드

/************************************************************************/
/******************************   Common   ******************************/
/************************************************************************/

function setVideoOptions(vodUrl, videoFileType) {
    let videoOptions = {
        sources: [
            {
                src: vodUrl,
                type: videoFileType
            }
        ],
        controls: true, // 동영상 제어를 위한 컨트롤 바 제공 여부
        playsinline: true, // 웹 브라우저 환경의 재생 형태
        muted: false, // 최초 재생시 무음인지
        preload: "auto", // 비디오 데이터를 즉시 다운로드 시작할 지 여부
        controlBar: {
            playToggle: true, // 재생, 일시정지 토글
            pictureInPictureToggle: true, // pip모드
            remainingTimeDisplay: true, // 남은 시간 표시
            progressControl: true // 재생 진행바
        },
        inactivityTimeout: 3000,
    };
    return videoOptions;
}

function makeGetUrl(filename) {
    const prefixUrl = dir === '0' ? `/video/stream/` : `/video/videos/`;
    return prefixUrl + `${encodeURIComponent(filename)}?dir=${dir}`;
}

function extractFilename(url) {
    const cleanUrl = url.split('?')[0];
    const parts = cleanUrl.split('/');
    return parts[parts.length - 1];
}

function initVideoElem() {
    if (videoLeft) {
        videoLeft.remove()
    }
    if (videoRight) {
        videoRight.remove()
    }

    const currentVideoPlayer = document.querySelector('#videoPlayer')
    if (currentVideoPlayer) {
        if (isVideoJs()) {
            const existingPlayer = videojs.getPlayer(currentVideoPlayer.id);
            if (existingPlayer) {
                try {
                    existingPlayer.dispose(); // video.js 인스턴스 해제 > #videoPlayer도 자동으로 DOM에서 제거된다
                } catch (e) {
                    currentVideoPlayer.remove();
                }
            } else {
                currentVideoPlayer.remove();
            }
            // 위 지역 변수가 전역 player를 가리는(shadowing) 이름과 같아서, dispose() 후에도
            // 전역 player는 여전히 죽은 인스턴스를 참조한 채로 남아있었다 — 이후 aButton/bButton
            // (및 '['/']' 키)에서 player.currentTime()을 호출하면 tech_가 null이라 그대로
            // "Cannot read properties of null (reading 'currentTime')"로 죽던 원인이었다.
            player = null;
        } else {
            currentVideoPlayer.remove();
        }
    }

    videoContainer.appendChild(getDefaultVideoElem())
    videoPlayer = videoContainer.querySelector('#videoPlayer')
    videoSource = videoPlayer.querySelector('#videoSource')
    addVideoEvent();
}

function initVideoSrc() {
    // syncAudioElement는 영상과 완전히 분리된 별도의 <audio>라서, 영상만 멈추고 지워도 얘는
    // 계속 재생된다 — 삭제 버튼을 누르면 화면은 까매졌는데 오디오만 계속 들리던 원인.
    if (syncAudioElement) {
        try { syncAudioElement.pause(); } catch (_) {}
    }

    const currentVideoPlayer = document.querySelector('#videoPlayer')
    if (currentVideoPlayer) {
        if (isVideoJs()) {
            /*player.pause();
            player.src({ src: '', type: 'video/mp4' });
            player.load();*/
            try { player.pause(); } catch {}
            try { player.reset(); } catch {}
            const cur = player.currentSrc && player.currentSrc();
            if (cur && cur.startsWith('blob:')) URL.revokeObjectURL(cur);
        } else if (currentVideoPlayer) {
            currentVideoPlayer.pause();
            currentVideoPlayer.onloadedmetadata = null;
            currentVideoPlayer.querySelector('#videoSource').src = '';
            currentVideoPlayer.load();
        }
    }

    if (videoLeft) {
        videoLeft.pause();
        videoLeft.onloadedmetadata = null;
        videoLeft.querySelector('source').src = ''
        videoLeft.load();
    }

    if (videoRight) {
        videoRight.pause();
        videoRight.onloadedmetadata = null;
        videoRight.querySelector('source').src = ''
        videoRight.load();
    }
}

function isVideoJs() {
    const videoPlayer = document.querySelector('#videoPlayer')
    return videojs.getPlayer(videoPlayer.id);
}

function getDefaultVideoElem() {
    /*<video id="videoPlayer" controls autoPlay preload="auto">
        <source src="" type="video/mp4" id="videoSource">
    </video>*/
    const video = document.createElement('video')
    const source = document.createElement('source')
    video.id = 'videoPlayer'
    video.controls = true
    video.autoplay = true
    video.preload = "auto"
    source.src = ""
    source.type ="video/mp4"
    source.id = 'videoSource'
    video.appendChild(source)
    return video;
}

function resetLoop() {
    // console.log('resetLoop')
    isClickAbtn = false;
    isClickBbtn = false;
    isClickGain = false;
    aBtn?.classList.remove('active');
    bBtn?.classList.remove('active');
    toggleGainBtn?.classList.remove('active');
    isSectionLooping = false;
    startTime = 0;
    endTime = 0;
    // loopButton.classList.remove('active');
}

/************************************************************************/
/*************************   Video Function   ***************************/
/************************************************************************/

function selectVideoFromArr(videos, randomIndex) {
    flushSyncOffsetPost(); // 다음 영상으로 넘어가기 전, 디바운스 중이던 이전 영상의 싱크 값을 즉시 저장
    scheduleLikeFlush();   // 방금 하트한 영상이 있으면, 스트림이 닫힌 뒤 like 폴더로 옮기게 한다
    currentVideo = videos[randomIndex]
    fetchVideoArr.splice(randomIndex, 1); // randomIndex에서 1개 제거
    // console.log('currentVideo', currentVideo)

    const previousVideo = previousVideos.slice(-1)[0]
    if (currentVideo === previousVideo && videos.length > 1) {
        // videos.length가 1이면 대체할 다른 인덱스가 없다 — videos[1]이 undefined가 되어
        // currentVideo가 undefined로 빠지고 이후 makeGetUrl(undefined)가 ".../videos/undefined"
        // 같은 깨진 URL을 만드는 원인이었다(PageDown을 빠르게 연타해 목록이 거의 소진됐을 때 재현).
        currentVideo = videos[randomIndex === 0 ? 1 : 0]
    }

    applySavedSyncOffset(); // 이 영상에 저장된 싱크 값이 있으면 불러오고, 없으면 기본값 0
    updateHeartButton();
    const videoUrl = makeGetUrl(currentVideo);
    // console.log('videoUrl', videoUrl)
    scheduleVideoPlayback(videoUrl)
}

function updateVideoCountDisplay() {
    if (videoCountEl) videoCountEl.textContent = totalVideoCount === null ? '' : `총 ${totalVideoCount}개`;
}

function getVideo() {
    document.querySelectorAll('canvas').forEach(elem => elem.remove());
    resetLoop();
    if (fetchVideoArr.length === 0) {
        if (isFetchingVideoList) return; // 이전 목록 요청이 아직 안 끝났으면 PageDown 연타로 중복 요청을 쏘지 않는다
        isFetchingVideoList = true;
        const likedParam = likeFilterMode === 'liked' ? 'true' : 'false';
        axios.get(`/video/videos?dir=${dir}&liked=${likedParam}`)
            .then(response => {
                let videos = response.data;
                if (videos.length > 0) {
                    fetchVideoArr = [...videos];
                    totalVideoCount = videos.length;
                    updateVideoCountDisplay();
                    const randomIndex = Math.floor(Math.random() * fetchVideoArr.length);
                    selectVideoFromArr(fetchVideoArr, randomIndex);
                } else {
                    totalVideoCount = 0;
                    updateVideoCountDisplay();
                    alert(likeFilterMode === 'liked' ? '하트한 영상이 없습니다' : '안누른 영상이 없습니다');
                }
            })
            .finally(() => { isFetchingVideoList = false; });
    } else {
        const randomIndex = Math.floor(Math.random() * fetchVideoArr.length);
        selectVideoFromArr(fetchVideoArr, randomIndex);
    }
}

function updateHeartButton() {
    if (!heartButton) return;
    const liked = likedVideosSet.has(currentVideo);
    heartButton.classList.toggle('liked', liked);
}

// 세로 영상(3분할 대상)인지 실제 재생 없이 가볍게 먼저 확인한다. preload="metadata"만 받으므로
// (전체 영상을 새로 받는 video.js/네이티브 로드보다 훨씬 가볍다) PC에서 fast path(video.js)로
// 재생을 시작했다가 metadata 도착 후에야 세로인 걸 알고 처음부터 다시 네이티브로 받는 이중
// 다운로드를 피하려는 용도다 — 그 중복 다운로드가 초반 네트워크 버스트 구간을 낭비해서, 3초쯤
// 뒤 버퍼가 바닥나며 2초가량 끊기는 원인이었다. 실패해도(네트워크 에러 등) false로 처리해
// 기존 fast path의 loadedmetadata 안전장치가 그대로 잡아내도록 한다.
// PageDown을 빠르게 연타하면 이전 probe가 응답(loadedmetadata/error)을 받기 전에 다음 probe가
// 또 뜬다 — 브라우저 동시 연결 제한에 걸려 먼저 뜬 probe가 영영 응답을 못 받으면 finish()가
// 호출되지 않고, 그 press만 콜백 없이 방치돼 화면이 검게 남는 원인이었다(다음 PageDown이 새
// probe/새 currentVideo로 다시 시도하니 그제서야 나오는 것처럼 보임). 이전 probe를 새 probe가
// 시작할 때 즉시 취소해 연결을 바로 반납하고, 그래도 응답이 없으면 타임아웃으로 강제 종결한다.
let activeProbe = null;
const PROBE_TIMEOUT_MS = 2000;

function probeVideoIsVerticalSplit(videoUrl, callback) {
    if (activeProbe) activeProbe.abort();

    const probe = document.createElement('video');
    let done = false;
    const timeoutId = setTimeout(function() { finish(false); }, PROBE_TIMEOUT_MS);
    function finish(isVertical) {
        if (done) return;
        done = true;
        clearTimeout(timeoutId);
        if (activeProbe === selfHandle) activeProbe = null;
        probe.removeEventListener('loadedmetadata', onMeta);
        probe.removeEventListener('error', onError);
        probe.src = '';
        probe.load();
        probe.remove();
        callback(isVertical);
    }
    function onMeta() {
        const ratio = probe.videoWidth ? probe.videoHeight / probe.videoWidth : 0;
        finish(ratio > 1 && window.innerWidth > window.innerHeight);
    }
    function onError() {
        finish(false);
    }
    const selfHandle = { abort: function() { finish(false); } };
    activeProbe = selfHandle;

    probe.preload = 'metadata';
    probe.muted = true;
    probe.style.display = 'none';
    probe.addEventListener('loadedmetadata', onMeta);
    probe.addEventListener('error', onError);
    document.body.appendChild(probe);
    probe.src = videoUrl;
    probe.load();
}

// 기존 fast path 본문 — video.js가 이미 실행 중일 때 그 위에서 바로 재생한다. Android는 비동기
// 콜백(loadedmetadata → changeVideo)에서 play()를 차단하므로, 사용자 제스처 컨텍스트 안에서
// 기존 플레이어를 재활용해 동기적으로 play()를 호출해야 한다 — 그래서 모바일에서는 이 함수를
// probe 없이 즉시(동기) 호출한다.
// video.js가 같은 <video> 엘리먼트에 src만 계속 바꿔 끼우는 fast path에서는(특히 PageDown을
// 짧은 간격으로 연달아 눌러 src를 자주 바꿀 때) 크롬이 하드웨어 오버레이 합성 경로에서 새
// 프레임을 못 올리고 화면만 까맣게 굳는 경우가 간헐적으로 있다 — 소리와 재생 시간(timeupdate)은
// 정상이라 timeupdate로는 이 상태를 구분할 수 없다. requestVideoFrameCallback은 실제로 컴포지터에
// 프레임이 제출됐을 때만 불리므로 이걸로 "화면만 멈춘" 상태를 감지한다(미지원 브라우저는
// timeupdate로 대체 — 정확도는 떨어지지만 최소한의 안전장치는 된다). 복구는 같은 엘리먼트에
// src만 다시 끼우지 않는다 — 그게 원인과 같은 동작이라 못 미덥다. 대신 이 파일에서 이미 검증된
// playNative() 경로(비디오 엘리먼트를 완전히 새로 만듦)로 넘겨 확실하게 복구한다.
const PLAYBACK_STALL_TIMEOUT_MS = 2500;
let stallWatchdogTimer = null;
let stallWatchdogCancel = null;

function armPlaybackStallWatchdog(expectedVideo, videoUrl) {
    clearTimeout(stallWatchdogTimer);
    if (stallWatchdogCancel) stallWatchdogCancel();

    const videoEl = player.el().getElementsByTagName('video')[0];
    let frameSeen = false;
    const markFrame = function() { frameSeen = true; };

    if (videoEl && typeof videoEl.requestVideoFrameCallback === 'function') {
        const rvfcHandle = videoEl.requestVideoFrameCallback(markFrame);
        stallWatchdogCancel = function() {
            if (videoEl.cancelVideoFrameCallback) videoEl.cancelVideoFrameCallback(rvfcHandle);
        };
    } else {
        player.one('timeupdate', markFrame);
        stallWatchdogCancel = function() { player.off('timeupdate', markFrame); };
    }

    stallWatchdogTimer = setTimeout(function() {
        stallWatchdogCancel();
        stallWatchdogCancel = null;
        if (frameSeen) return; // 실제 프레임이 제출됐으면 정상 — 아무 것도 안 함
        if (currentVideo !== expectedVideo) return; // 그새 다른 영상으로 넘어갔으면 무시
        if (!player || player.isDisposed()) return;
        playNative(videoUrl, false); // 이미 startVjsFastPath에서 pushVideoArr 했으니 다시 push하지 않음
    }, PLAYBACK_STALL_TIMEOUT_MS);
}

function startVjsFastPath(videoUrl) {
    mimeType = currentVideo.split('.').pop() === 'ts' ? 'video/mp2t' : 'video/mp4';
    pushVideoArr(currentVideo);
    // player.currentSrc()는 절대 URL로 바뀌어 원본 문자열과 안 맞으므로, 식별자로는
    // currentVideo를 그대로 스냅샷해 이후 콜백들에서 그 사이 다른 영상으로 넘어갔는지 확인한다.
    const expectedVideo = currentVideo;
    player.off('loadeddata');
    player.one('loadeddata', function() {
        filenameDisplay.textContent = extractFilename(decodeURIComponent(videoUrl));
    });
    player.src({type: mimeType, src: videoUrl});
    player.load();
    player.volume(previousVolume);
    player.loop(isLooping);
    player.play().catch(() => {});
    showControls(); // 새 영상 시작 시 컨트롤을 즉시 노출 (삭제 후 등 재사용 경로 대비)

    // fast path는 delayAudio()를 다시 안 타므로, 이 영상에 저장된 싱크 오프셋이 있는데
    // 그래프가 아직 한 번도 켜진 적 없다면 여기서 직접 켜준다(안 그러면 값은 불러와졌어도
    // 실제로 들리지는 않는다). 이미 켜져 있다면 loadstart/timeupdate가 알아서 따라간다.
    bindSyncVideoElement(player.el().getElementsByTagName('video')[0], true);

    armPlaybackStallWatchdog(expectedVideo, videoUrl);

    // PC는 probeVideoIsVerticalSplit()이 미리 걸러주지만, 모바일은 안 거치고(또는 probe가
    // 틀렸을 때) 여전히 여기서 실제 metadata로 다시 한번 확인해 3분할 대상이면 네이티브로
    // 전환한다 — 기존 안전장치를 그대로 둔다.
    player.one('loadedmetadata', function() {
        if (currentVideo !== expectedVideo) return; // 그새 다른 영상으로 넘어갔으면 무시
        const vp = player.el().getElementsByTagName('video')[0];
        const ratio = vp && vp.videoWidth ? vp.videoHeight / vp.videoWidth : 0;
        if (ratio > 1 && window.innerWidth > window.innerHeight) {
            // loadedmetadata 콜백 안에서 바로 player.dispose()를 부르면, 같은 이벤트에
            // 걸린 video.js 자체 내부 리스너(반응형 스타일 갱신 등)가 뒤이어 실행되다가
            // 이미 지워진 tech를 참조해서 "Cannot read properties of null (reading
            // 'videoWidth')" 에러를 던진다. 디스패치가 끝난 다음 틱으로 미뤄서 피한다.
            setTimeout(function() {
                if (currentVideo !== expectedVideo) return;
                playNative(videoUrl, false); // 이미 위에서 pushVideoArr 했으니 다시 push하지 않음
            }, 0);
        }
    });
}

// PageDown/PageUp을 아주 빠르게(초당 여러 번) 연타하면 매 press마다 probe+실제 디코드 세션을
// 새로 여는데, 20~30회 정도 몰아치면 윈도우 하드웨어 비디오 디코더가 못 버티고 화면만 까맣게
// 굳는 경우가 있었다(소리는 정상 재생 — 다음/이전 영상으로 바꿔도 안 풀림, 즉 특정 영상이 아니라
// 디코더 세션 자체가 맛이 간 상태). 목록 위치(currentVideo/previousVideos 등)는 매 press마다
// 그대로 즉시 갱신하되, 실제 재생(디코드 세션 생성)만 최소 간격으로 묶어서 연타 중 나온 디코드
// 세션 생성 횟수 자체를 줄인다 — 한 번 눌렀을 때는 지연 없이 바로 재생되고, 연타 중에는 마지막
// 요청만 반영된다(중간 요청들은 어차피 화면에 보일 새도 없이 다음 요청으로 덮였을 것들이다).
const PLAY_VIDEO_MIN_GAP_MS = 200;
let playVideoLastRunAt = 0;
let playVideoPendingTimer = null;

function scheduleVideoPlayback(videoUrl) {
    // 모바일은 play()를 사용자 제스처 콜스택 안에서 동기 호출해야 하는 제약이 있다(위 startVjsFastPath
    // 주석 참고) — setTimeout으로 미루면 그 제스처 컨텍스트가 깨져 자동재생이 막힌다. PC의 검은
    // 화면 문제와 무관하므로 모바일은 이 throttle을 아예 타지 않고 항상 동기 호출한다.
    if (isMobile) {
        playVideo(videoUrl);
        return;
    }
    clearTimeout(playVideoPendingTimer);
    const elapsed = Date.now() - playVideoLastRunAt;
    if (elapsed >= PLAY_VIDEO_MIN_GAP_MS) {
        playVideoLastRunAt = Date.now();
        playVideo(videoUrl);
    } else {
        playVideoPendingTimer = setTimeout(function() {
            playVideoLastRunAt = Date.now();
            playVideo(videoUrl);
        }, PLAY_VIDEO_MIN_GAP_MS - elapsed);
    }
}

function playVideo(videoUrl) {
    if (player && !player.isDisposed() && isVideoJs()) {
        if (isMobile) {
            // 모바일: 위에서 설명한 Android 제스처 제약 때문에 probe 없이 기존처럼 동기 호출한다.
            startVjsFastPath(videoUrl);
            return;
        }

        // PC: 어느 경로로 재생할지 먼저 가볍게 확인한 뒤 한 번만 로드한다(중복 다운로드 방지).
        // 그 대가로 재생 시작이 probe만큼(대개 매우 짧게) 늦어질 수 있다.
        const expectedVideo = currentVideo;
        probeVideoIsVerticalSplit(videoUrl, function(isVerticalSplit) {
            if (currentVideo !== expectedVideo) return; // probe 도중 다른 영상으로 넘어갔으면 무시
            if (isVerticalSplit) {
                playNative(videoUrl, true); // video.js는 건드리지 않고 바로 네이티브+3분할로
            } else {
                startVjsFastPath(videoUrl);
            }
        });
        return;
    }

    playNative(videoUrl, true);
}

function playNative(videoUrl, shouldPush) {
    initVideoSrc();
    initVideoElem();
    if (videoSource) {
        videoSource.src = videoUrl;
    }
    if (shouldPush) {
        pushVideoArr(currentVideo);
    }
    if (videoPlayer) {
        videoPlayer.volume = previousVolume;
        videoPlayer.loop = isLooping;
        videoPlayer.load();
        const capturedElem = videoPlayer;
        videoPlayer.removeEventListener('loadedmetadata', getVideoEvent);
        videoPlayer.addEventListener('loadedmetadata', function onMetadata() {
            videoPlayer.removeEventListener('loadedmetadata', onMetadata);
            if (videoPlayer !== capturedElem) return;
            getVideoEvent();
        });
    }
}

function getVideoEvent() {
    let decodedUrl = decodeURIComponent(videoSource.src)
    let videoFilename = extractFilename(decodedUrl);
    filenameDisplay.textContent = videoFilename;

    videoPlayer.addEventListener('timeupdate', function() {
        if (isSectionLooping && endTime > startTime) {
            if (videoPlayer.currentTime >= endTime) {
                videoPlayer.currentTime = startTime;
                videoPlayer.play();
            }
        }
    });

    videoPlayer.addEventListener('ended', function() {
        if (isLooping && endTime === 0) {
            videoPlayer.currentTime = startTime;
            videoPlayer.play();
        }
    });

    if (!isMobile) {
        // if (!threeSplitLayout()) {
        //     changeVideo(); // change to videojs
        // }
    }
    setupThreeSplitCanvas();
    addKeyboardControls();
}

function setupThreeSplitCanvas() {
    // 이 호출 시점의 비디오 엘리먼트를 고정해서 클로저에 담는다 — videoPlayer(모듈 변수)는 다음
    // 영상으로 넘어가면 재할당되므로, 고정해두지 않으면 아래 draw()/positionAll()이 다음 영상이
    // 재생 중인 동안에도 멈추지 않고 계속 돌면서(정지 조건이 항상 "재생 중"이 되어버림) 이미
    // DOM에서 제거된 캔버스에 매 프레임 drawImage를 계속 호출해 영상을 여러 개 볼수록 CPU
    // 사용량이 누적되어 점점 심하게 끊기는 원인이었다.
    const myVideoPlayer = videoPlayer;
    let videoRatio = myVideoPlayer.videoHeight / myVideoPlayer.videoWidth;
    if (videoRatio > 1 && window.innerWidth > window.innerHeight) {
        const checkLeftCanvas = document.getElementById('leftCanvas');
        let leftCanvas;
        if (!checkLeftCanvas) {
            leftCanvas = document.createElement('canvas');
            leftCanvas.id = 'leftCanvas';
            leftCanvas.style.position = 'absolute';
            leftCanvas.style.top = '0';
        } else {
            leftCanvas = checkLeftCanvas;
        }

        const checkRightCanvas = document.getElementById('rightCanvas');
        let rightCanvas;
        if (!checkRightCanvas) {
            rightCanvas = document.createElement('canvas');
            rightCanvas.id = 'rightCanvas';
            rightCanvas.style.position = 'absolute';
            rightCanvas.style.top = '0';
        } else {
            rightCanvas = checkRightCanvas;
        }

        // 비디오와 같은 크기
        const videoW = myVideoPlayer.videoWidth;
        const videoH = myVideoPlayer.videoHeight;

        // 컨테이너(부모) 크기에 맞춰 리사이즈
        function positionAll() {
            // 다음 영상으로 넘어가 캔버스가 DOM에서 제거됐으면 이 리스너 자체를 정리한다
            // (안 그러면 영상을 볼수록 resize 리스너가 계속 쌓인다)
            if (!document.body.contains(leftCanvas)) {
                window.removeEventListener('resize', positionAll);
                return;
            }
            // 현재 비디오의 보이는 크기 계산
            const containerW = videoContainer.clientWidth;
            const containerH = videoContainer.clientHeight;
            // 전체화면에서 네이티브 <video controls> 바가 유휴 상태로 사라졌다 나타났다 할 때
            // 그 공간이 여닫히며 resize 이벤트가 튀는데, 그 순간 컨테이너 크기가 0으로
            // 읽히는 경우가 있다 — 이걸 그대로 반영하면 캔버스가 0 크기로 찌그러져 배경색만
            // 보이고, 그 상태가 다음 resize 전까지 그대로 남는다. 값이 이상하면 아예 반영하지
            // 않고 이전 레이아웃을 유지한다.
            if (!containerW || !containerH) {
                return;
            }
            let scale = Math.min(containerW / videoW, containerH / videoH);
            let shownW = videoW * scale;
            let shownH = videoH * scale;

            // myVideoPlayer 가운데 배치
            myVideoPlayer.style.position = 'absolute';
            myVideoPlayer.style.width = shownW + 'px';
            myVideoPlayer.style.height = shownH + 'px';
            myVideoPlayer.style.left = (containerW - shownW) / 2 + 'px';
            myVideoPlayer.style.top = (containerH - shownH) / 2 + 'px';
            // 전체화면+유휴 상태에서 브라우저가 이 <video>를 하드웨어 오버레이로 승격시켜 같은
            // 자리의 형제 캔버스를 완전히 덮어버리는 것으로 확인됐다(CSS/DOM은 안 변하고 그림만
            // 안 보임 — 콘솔 진단으로 확정). transform을 걸어 비디오를 일반 컴포지팅 레이어로
            // 강제해서 이 하드웨어 오버레이 경로를 타지 않게 한다.
            myVideoPlayer.style.transform = 'translateZ(0)';

            // leftCanvas: 비디오 왼쪽으로 가로길이만큼 떨어져 배치
            leftCanvas.width = shownW;
            leftCanvas.height = shownH;
            leftCanvas.style.left = (containerW - shownW) / 2 - shownW + 'px';
            leftCanvas.style.top = myVideoPlayer.style.top;

            // rightCanvas: 비디오 오른쪽으로 가로길이만큼 떨어져 배치
            rightCanvas.width = shownW;
            rightCanvas.height = shownH;
            rightCanvas.style.left = (containerW - shownW) / 2 + shownW + 'px';
            rightCanvas.style.top = myVideoPlayer.style.top;
        }

        // DOM에 먼저 추가해야 한다(중복 방지) — positionAll()의 "캔버스가 DOM에서 제거됐으면
        // 멈춘다" 가드가 아직 붙기도 전인 캔버스를 "이미 떨어져나감"으로 오판해서, 최초 배치
        // 자체가 실행되지 않고 resize 리스너도 곧바로 스스로 제거해버려 3분할이 통째로
        // 동작하지 않는 원인이었다.
        if (!document.getElementById('leftCanvas')) videoContainer.appendChild(leftCanvas);
        if (!document.getElementById('rightCanvas')) videoContainer.appendChild(rightCanvas);

        positionAll();
        window.addEventListener('resize', positionAll);

        // drawImage로 영상 복제 (컨텍스트는 한 번만 얻어서 재사용)
        const leftCtx = leftCanvas.getContext('2d');
        const rightCtx = rightCanvas.getContext('2d');
        function draw() {
            // 다음 영상으로 넘어가 이 캔버스가 DOM에서 제거됐으면 루프를 여기서 끝낸다
            if (!document.body.contains(leftCanvas)) return;
            leftCtx.clearRect(0, 0, leftCanvas.width, leftCanvas.height);
            leftCtx.drawImage(myVideoPlayer, 0, 0, leftCanvas.width, leftCanvas.height);
            rightCtx.clearRect(0, 0, rightCanvas.width, rightCanvas.height);
            rightCtx.drawImage(myVideoPlayer, 0, 0, rightCanvas.width, rightCanvas.height);
            if (!myVideoPlayer.paused && !myVideoPlayer.ended) {
                requestAnimationFrame(draw);
            }
        }
        myVideoPlayer.addEventListener('play', draw);
    } else {
        changeVideo(); // change to videojs
    }
}

function changeVideo() {
    initVideoSrc()
    initVideoElem();
    videoPlayer.removeEventListener('loadedmetadata', getVideoEvent);
    // videoPlayer.addEventListener('loadedmetadata', getVideoEvent); # 여기서 넣으면 안된다
    videoPlayer.classList.add('video-js', ',vjs-default-skin')

    const videoUrl = makeGetUrl(currentVideo)
    const fileExtension = currentVideo.split('.').pop();
    mimeType = fileExtension === 'ts' ? 'video/mp2t' : 'video/mp4';
    // document.title = currentVideo.split('/')[1]

    const existingPlayer = videojs.players['videoPlayer'];
    if (existingPlayer && !existingPlayer.isDisposed()) {
        player = existingPlayer;
    } else {
        player = videojs('videoPlayer', setVideoOptions(videoUrl, mimeType));
    }

    player.off('loadeddata');
    player.one('loadeddata', function () {
        filenameDisplay.textContent = extractFilename(decodeURIComponent(videoUrl));
    });
    player.src({type: mimeType, src: videoUrl});
    player.load();
    player.volume(previousVolume);
    player.loop(isLooping);
    player.play().catch(() => {});
    showControls(); // 새 영상 시작 시 컨트롤을 즉시 노출 (모바일에서 play 이벤트 누락 대비)
    const readyPlayer = player;
    readyPlayer.ready(function() {
        if (readyPlayer.isDisposed()) return;
        let controlBar = readyPlayer.controlBar;

        controlBar.on('keydown', function(event) {
            // page up key: 33, page down key: 34
            if (event.keyCode === 33 || event.keyCode === 34) {
                event.preventDefault();
            }
        });

        const progressEl = controlBar.progressControl && controlBar.progressControl.el();
        if (progressEl) {
            progressEl.addEventListener('touchend', function() {
                setTimeout(function() { if (!readyPlayer.isDisposed()) readyPlayer.userActive(false); }, 2000);
            }, { passive: true });
        }
    });
    player.off('timeupdate', onPlayerTimeupdate);
    player.on('timeupdate', onPlayerTimeupdate);
    // 컨트롤 표시 트리거는 video.js 자체 이벤트 버스로 건다(player.on). timeupdate/ended와
    // 마찬가지로 내부적으로 재발급되는 tech에도 안전하게 유지된다 — 반면 addVideoEvent()의
    // videoPlayer.addEventListener(...)는 최초 영상 로드 시 한 번만 바인딩되므로, 이후
    // delVideo() → initVideoSrc() → player.reset()을 거치면(삭제 버튼 경로에서만 발생) 다시
    // 걸리지 않는다. PC는 document 전역 mousemove로 가려져 있어 못 느꼈지만, 모바일은 터치가
    // click/touchstart에만 의존해 삭제 후 컨트롤이 안 돌아오는 원인이었다.
    // ⚠️ off(type)를 리스너 지정 없이 부르면 video.js가 내부적으로 걸어둔 리스너까지 전부
    // 지워진다 — play/pause 아이콘(vjs-paused/vjs-playing 클래스)을 갱신하는 내부 리스너도
    // 여기 포함되어 있어서, 모바일에서 영상을 멈춰도 하단 재생바의 일시정지 아이콘이 안 바뀌던
    // 원인이었다. 항상 우리가 등록한 것과 같은 함수 레퍼런스로 off/on을 짝지어 우리 리스너만
    // 지우고 다시 걸도록 고친다.
    player.off('click', showControls); player.on('click', showControls);
    player.off('touchstart', showControls); player.on('touchstart', showControls);
    player.off('play', showControls); player.on('play', showControls);
    player.off('pause', showControls); player.on('pause', showControls);
    player.off('ended', onPlayerEnded);
    player.on('ended', onPlayerEnded);
}

function onPlayerTimeupdate() {
    if (isSectionLooping && endTime > startTime) {
        if (player.currentTime() >= endTime) {
            player.currentTime(startTime);
            player.play();
        }
    }
}

function onPlayerEnded() {
    if (isLooping && endTime === 0) {
        player.currentTime(startTime);
        player.play();
    }
}

function delVideo() {
    if (currentVideo) {
        const deletedVideo = currentVideo; // currentVideo는 아래에서 다음 영상으로 바뀌므로 미리 캡처
        if (confirm(`Delete \r\n ${deletedVideo} ?`)) {
            keepFullscreenOnDelete = isFullscreen();
            clearTimeout(keepFullscreenTimer);
            keepFullscreenTimer = setTimeout(function() { keepFullscreenOnDelete = false; }, 4000);
            cancelSyncOffsetPost(); // 삭제될 영상이라 디바운스 중이던 값은 보낼 필요 없음 (아래서 0으로 정리함)
            initVideoSrc() // 삭제하려는 파일이 사용중이면 접근이 안된다 (서버에서 스트림 중이므로 삭제가 안된다)

            // 삭제 응답을 기다리지 않고 바로 다음 영상을 불러온다 — 삭제 자체는 백그라운드에서 처리
            if (totalVideoCount !== null) {
                totalVideoCount = Math.max(0, totalVideoCount - 1);
                updateVideoCountDisplay();
            }
            currentVideo = '';
            updateHeartButton();
            getVideo();

            axios.post(`/video/delete/${encodeURIComponent(deletedVideo)}?dir=${dir}`)
                .then(response => {
                    if (response.status === 204) {
                        delete videoSyncOffsetsMap[deletedVideo]; // 삭제된 영상의 싱크 값도 같이 정리
                        axios.post('/video/sync-offset', {dir: dir, filename: deletedVideo, offset: 0}).catch(() => {});
                        likedVideosSet.delete(deletedVideo); // 서버에서도 delete 라우트가 같이 정리한다
                    } else {
                        alert('Failed to delete video');
                        if (totalVideoCount !== null) { // 실제로는 안 지워졌으니 낙관적으로 줄인 카운트를 되돌림
                            totalVideoCount += 1;
                            updateVideoCountDisplay();
                        }
                    }
                }).catch(err => {
                alert(deletedVideo)
                if (totalVideoCount !== null) {
                    totalVideoCount += 1;
                    updateVideoCountDisplay();
                }
            });
        }
    }
}

function pushVideoArr(url) {
    if (previousVideos.length > 1) {
        previousVideos.shift();
    }
    previousVideos.push(url)
}

/************************************************************************/
/***************************   Key Event   ******************************/
/************************************************************************/

const hideControls = () => {
    clearTimeout(hideControlsTimeout);
    hideControlsTimeout = setTimeout(() => {
        controls.style.display = 'none';
        topDiv.style.display = 'none';
        // filenameDisplay는 항상 보이도록 둔다 — 이걸 숨겼을 때 전체화면에서 3분할 좌우
        // 영상이 같이 사라지는 문제가 생겨서 되돌림.
        videoContainer.style.cursor = 'none';
        // 네이티브 <video controls> 바의 자동숨김을 브라우저에 맡기지 않고 직접 제어한다
        // (영상 교체 후 브라우저 자체 유휴 타이머가 멈춰 계속 떠있던 문제 — video.css 참고).
        if (videoPlayer) videoPlayer.classList.add('controls-idle');
    }, 3000);
};

const showControls = () => {
    controls.style.display = 'block';
    topDiv.style.display = 'block';
    videoContainer.style.cursor = 'default';
    if (videoPlayer) videoPlayer.classList.remove('controls-idle');
    hideControls();
};

document.getElementById('nextButton')?.removeEventListener('click', getVideo);
document.getElementById('nextButton')?.addEventListener('click', getVideo);
document.getElementById('deleteButton')?.removeEventListener('click', delVideo);
document.getElementById('deleteButton')?.addEventListener('click', delVideo);
heartButton?.addEventListener('click', function() {
    if (!currentVideo) return;
    const newLiked = !likedVideosSet.has(currentVideo);
    if (newLiked) {
        likedVideosSet.add(currentVideo);
    } else {
        likedVideosSet.delete(currentVideo);
    }
    updateHeartButton();
    // 하트 상태가 바뀌면 현재 영상이 지금 보고 있는 필터 목록에서 빠지거나(-1) 다시 들어온다(+1) —
    // 목록을 새로 받아올 때까지 기다리지 않고 카운트에 즉시 반영한다(삭제 경로와 동일한 낙관적 갱신).
    const stillInFilter = (likeFilterMode === 'liked') === newLiked;
    if (totalVideoCount !== null) {
        totalVideoCount = Math.max(0, totalVideoCount + (stillInFilter ? 1 : -1));
        updateVideoCountDisplay();
    }
    const likedVideo = currentVideo; // 응답이 오기 전에 다음 영상으로 넘어갈 수 있으므로 미리 캡처
    hasPendingLikeMove = true;       // 이 영상에서 넘어갈 때 서버에 실제 파일 이동을 시킨다
    axios.post('/video/like', {dir: dir, filename: likedVideo, liked: newLiked})
        .catch(() => { // 저장 실패 — 낙관적으로 바꾼 캐시/카운트를 되돌린다
            if (newLiked) likedVideosSet.delete(likedVideo);
            else likedVideosSet.add(likedVideo);
            if (currentVideo === likedVideo) updateHeartButton();
            if (totalVideoCount !== null) {
                totalVideoCount = Math.max(0, totalVideoCount + (stillInFilter ? -1 : 1));
                updateVideoCountDisplay();
            }
        });
});
// 하트를 누르면 서버는 그 파일을 <디렉터리>/like/ 폴더로 실제 이동시킨다. 다만 재생 중인
// 파일은 Windows에서 잠겨 있어 못 옮기고, 옮겨봤자 브라우저가 이어서 요청할 range가 404가 돼
// 재생이 끊긴다 — 그래서 서버는 예약만 해두고, 그 영상에서 넘어간 뒤 여기서 실제 이동을 시킨다.
let hasPendingLikeMove = false;
let likeFlushTimer = null;
const LIKE_FLUSH_DELAY_MS = 1500; // 이전 영상의 스트림이 확실히 닫힌 뒤에 요청 (서버도 재시도한다)

function scheduleLikeFlush() {
    if (!hasPendingLikeMove) return;
    clearTimeout(likeFlushTimer);
    likeFlushTimer = setTimeout(function() { flushLikeMoves(); }, LIKE_FLUSH_DELAY_MS);
}

// 서버가 파일을 옮기면 상대경로가 바뀐다(./a.mp4 → like/a.mp4). 클라이언트가 들고 있는 경로도
// 같이 갱신해야 Prev로 되돌아갔을 때 404가 나지 않고, 하트/싱크 값도 계속 맞는다.
function applyLikeMoves(moves) {
    if (!moves) return;
    Object.keys(moves).forEach(function(oldRel) {
        const newRel = moves[oldRel];
        if (!newRel || newRel === oldRel) return;
        for (let i = 0; i < previousVideos.length; i++) {
            if (previousVideos[i] === oldRel) previousVideos[i] = newRel;
        }
        const idx = fetchVideoArr.indexOf(oldRel);
        if (idx !== -1) fetchVideoArr[idx] = newRel;
        if (currentVideo === oldRel) currentVideo = newRel;
        if (likedVideosSet.delete(oldRel)) likedVideosSet.add(newRel);
        if (videoSyncOffsetsMap[oldRel] !== undefined) {
            videoSyncOffsetsMap[newRel] = videoSyncOffsetsMap[oldRel];
            delete videoSyncOffsetsMap[oldRel];
        }
    });
}

function flushLikeMoves(useBeacon) {
    if (!hasPendingLikeMove) return;
    clearTimeout(likeFlushTimer);
    likeFlushTimer = null;
    hasPendingLikeMove = false;
    const payload = {dir: dir};
    if (useBeacon && navigator.sendBeacon) {
        // 페이지를 벗어나는 시점엔 axios 요청이 완료 전에 취소될 수 있다 (싱크 오프셋과 동일한 사정)
        const blob = new Blob([JSON.stringify(payload)], {type: 'application/json'});
        navigator.sendBeacon('/video/like/flush', blob);
        return;
    }
    axios.post('/video/like/flush', payload)
        .then(function(res) {
            applyLikeMoves(res.data && res.data.moves);
            // 잠겨 있어서 못 옮긴 게 남았으면 다음 기회에 다시 시도한다
            if (res.data && res.data.deferred > 0) hasPendingLikeMove = true;
        })
        .catch(function() { hasPendingLikeMove = true; }); // 실패하면 예약을 살려둔다
}

likeFilterSelect?.addEventListener('change', function() {
    likeFilterMode = likeFilterSelect.value;
    fetchVideoArr = []; // 필터가 바뀌었으니 이전 목록 캐시는 버리고 새로 받아온다
    currentVideo = '';
    getVideo();
});
document.getElementById('fullScreen')?.removeEventListener('click', toggleFullscreen);
document.getElementById('fullScreen')?.addEventListener('click', toggleFullscreen);
document.addEventListener('mousemove', showControls);

function addVideoEvent() {
    if (videoPlayer) {
        videoPlayer.removeEventListener('play', showControls);
        videoPlayer.addEventListener('play', showControls);
        videoPlayer.removeEventListener('pause', showControls);
        videoPlayer.addEventListener('pause', showControls);
        videoPlayer.removeEventListener('click', showControls);
        videoPlayer.addEventListener('click', showControls);
        videoPlayer.removeEventListener('touchstart', showControls);
        videoPlayer.addEventListener('touchstart', showControls);
        videoPlayer.removeEventListener('ended', getVideo);
        videoPlayer.addEventListener('ended', getVideo);
        videoPlayer.removeEventListener('touchmove', showControls);
        videoPlayer.addEventListener('touchmove', showControls);
        videoPlayer.removeEventListener('touchend', hideControls);
        videoPlayer.addEventListener('touchend', hideControls);
        videoPlayer.removeEventListener('focus', function(event) {
            event.target.blur();
        });
        videoPlayer.addEventListener('focus', function(event) {
            event.target.blur();
        });
        videoPlayer.removeEventListener('mousedown', function(event) {
            event.preventDefault();
            setTimeout(() => videoPlayer.blur(), 0);
        });
        videoPlayer.addEventListener('mousedown', function(event) {
            event.preventDefault();
            setTimeout(() => videoPlayer.blur(), 0);
        });
    }
}

prevButton?.addEventListener('click', function () {
    let prevVideo = previousVideos.shift();

    if (prevVideo) {
        flushSyncOffsetPost(); // 다음 영상으로 넘어가기 전, 디바운스 중이던 이전 영상의 싱크 값을 즉시 저장
        scheduleLikeFlush();
        const videoFilename = extractFilename(decodeURIComponent(prevVideo));
        console.log('prevButton', videoFilename);
        pushVideoArr(currentVideo)
        currentVideo = prevVideo;
        applySavedSyncOffset(); // selectVideoFromArr()와 동일하게 이 영상의 저장된 싱크 값을 불러온다
        updateHeartButton();

        const videoUrl = makeGetUrl(prevVideo)
        scheduleVideoPlayback(videoUrl)
    }
});

loopButton?.removeEventListener('click', toggleLoop);
loopButton?.addEventListener('click', toggleLoop);
function toggleLoop() {
    isLooping = !isLooping;
    if (videoPlayer) videoPlayer.loop = isLooping;
    else if (player) player.loop(isLooping);
    if (syncAudioElement) syncAudioElement.loop = isLooping;
    loopButton.classList.toggle('active', isLooping);
}

aBtn?.addEventListener('click', function() {
    isClickAbtn = !isClickAbtn;
    if (player && !player.isDisposed()) startTime = player.currentTime();
    if (videoPlayer) startTime = videoPlayer.currentTime;
    isSectionLooping = isClickAbtn && isClickBbtn
    aBtn.classList.toggle('active', isClickAbtn);
    if (isSectionLooping && videoPlayer) {
        videoPlayer.removeAttribute('controls');
    } else if (videoPlayer) {
        videoPlayer.setAttribute('controls', 'controls');
    }
});

bBtn?.addEventListener('click', function() {
    isClickBbtn = !isClickBbtn;
    if (player && !player.isDisposed()) endTime = player.currentTime();
    if (videoPlayer) endTime = videoPlayer.currentTime;
    isSectionLooping = isClickAbtn && isClickBbtn
    bBtn.classList.toggle('active', isClickBbtn);
    if (isSectionLooping && videoPlayer) {
        videoPlayer.removeAttribute('controls');
    } else if (videoPlayer) {
        videoPlayer.setAttribute('controls', 'controls');
    }
});

toggleGainBtn?.addEventListener('click', function() {
    isClickGain = !isClickGain;
    toggleGainBtn.classList.toggle('active', isClickGain);
    ensureSyncAudioGraph();
    if (audioGainNode) audioGainNode.gain.value = isClickGain ? 2.0 : 1.0;
});

function showSyncMessage() {
    syncMessage.textContent = 'Audio Sync Offset: ' + audioOffset.toFixed(2) + 's';
    syncMessage.style.display = 'block';
    clearTimeout(syncMessage.hideTimeout);
    syncMessage.hideTimeout = setTimeout(function() {
        syncMessage.style.display = 'none';
    }, 2000); // 2초 후 메시지 숨기기
}

// DelayNode는 "이미 디코딩된 오디오를 늦게 내보내는" 것만 가능해서, 오디오를 원본(네이티브
// 싱크)보다 더 앞당기는 건 버퍼를 얼마나 크게 잡든 근본적으로 불가능했다(최소 지연이 항상 0으로
// 귀결됨). 그래서 오디오를 영상과 완전히 분리된 별도의 <audio> 엘리먼트로 재생하고, 그
// currentTime을 영상의 currentTime + audioOffset으로 계속 맞춰주는 방식으로 바꾼다. 두 트랙이
// 독립된 재생 위치를 가지므로 음수/양수 상관없이(파일 길이 내에서) 자유롭게 어긋나게 할 수 있다.
function resyncAudioElement(force) {
    if (!syncAudioElement || !syncVideoElement) return;
    const duration = isFinite(syncVideoElement.duration) ? syncVideoElement.duration : Infinity;
    // audioOffset의 부호가 "오디오가 얼마나 빠른가"를 직접 나타내도록 뺄셈으로 둔다: 음수면
    // (video.currentTime - audioOffset)이 현재보다 더 뒤쪽(미래) 지점이 되어 그 오디오를
    // 지금 미리 들려주므로 오디오가 빨라지고, 양수면 반대로 오디오가 늦어진다.
    const target = Math.max(0, Math.min(syncVideoElement.currentTime - audioOffset, duration));
    // 매 timeupdate마다 currentTime을 강제로 맞추면 오디오가 계속 끊겨 들린다 — 어긋난 정도가
    // 작으면(재생 속도 미세 차이로 인한 드리프트) 그냥 흘러가게 두고, 크게 벌어졌을 때만 보정한다.
    if (force || Math.abs(syncAudioElement.currentTime - target) > 0.15) {
        syncAudioElement.currentTime = target;
    }
    syncAudioElement.volume = syncVideoElement.volume;
}

function adjustAudioSync(offset) {
    ensureSyncAudioGraph();
    // 0.01을 계속 더하면 JS 부동소수점 오차가 쌓여 -0.3000000000000001 같은 값이 된다 —
    // 소수점 2자리로 반올림해서 정리한다.
    audioOffset = Math.round((audioOffset + offset) * 100) / 100;
    resyncAudioElement(true);
    showSyncMessage();
    saveSyncOffsetForCurrentVideo();
}

function resetAudioSync() {
    ensureSyncAudioGraph();
    audioOffset = 0;
    resyncAudioElement(true);
    showSyncMessage();
    saveSyncOffsetForCurrentVideo();
}

// 영상별 오디오 싱크 오프셋을 서버(JSON 파일)에 저장해뒀다가, 같은 영상이 다시 나오면 그 값을,
// 처음 보는(또는 저장된 값이 없는) 영상이면 기본값 0을 불러온다 — localStorage는 기기/브라우저
// 마다 따로 쌓여서 다른 PC에서는 못 불러오므로 서버에 둔다. dir별로 통째로 한 번만 받아와
// 캐시해두고, 영상이 바뀔 때마다 그 캐시에서 즉시 조회한다(매번 네트워크 요청을 안 하기 위해).
let videoSyncOffsetsMap = {};
let videoSyncOffsetsLoaded = false;

function loadVideoSyncOffsetsFromServer() {
    return axios.get('/video/sync-offsets', {params: {dir}})
        .then(function(response) {
            videoSyncOffsetsMap = response.data || {};
        })
        .catch(function() {
            videoSyncOffsetsMap = {};
        })
        .finally(function() {
            videoSyncOffsetsLoaded = true;
        });
}

// 현재 dir에서 하트한 영상 목록을 한 번에 받아 캐시해둔다 (videoSyncOffsetsMap과 동일한 방식) —
// 영상이 바뀔 때마다 이 캐시에서 즉시 조회해 하트 버튼 상태를 표시한다.
function loadLikedVideosFromServer() {
    return axios.get('/video/liked-videos', {params: {dir}})
        .then(function(response) {
            likedVideosSet = new Set(response.data || []);
        })
        .catch(function() {
            likedVideosSet = new Set();
        });
}

function saveSyncOffsetForCurrentVideo() {
    if (!currentVideo) return;
    if (audioOffset === 0) {
        delete videoSyncOffsetsMap[currentVideo]; // 기본값이면 굳이 저장해두지 않는다
    } else {
        videoSyncOffsetsMap[currentVideo] = audioOffset;
    }
    scheduleSyncOffsetPost({dir: dir, filename: currentVideo, offset: audioOffset});
}

// a/d 키를 연타할 때 saveSyncOffsetForCurrentVideo()가 그때마다 불리는데, 중간값(-0.01,
// -0.02, ...)은 의미가 없고 마지막으로 정착한 값만 중요하다 — 그래서 디바운스로 처리한다:
// 조정할 때마다 타이머를 리셋하고, 3초간 추가 조정이 없어야 그제서야 실제로 보낸다.
// 3초가 되기 전에 다음 영상으로 넘어가거나 페이지를 벗어나면 flushSyncOffsetPost()로 그
// 시점에 즉시 보낸다(안 그러면 그 마지막 조정값이 서버에 영영 저장되지 않는다).
let syncOffsetDebounceTimer = null;
let syncOffsetPendingPayload = null;

function sendSyncOffsetPost(payload, useBeacon) {
    if (useBeacon && navigator.sendBeacon) {
        // 페이지를 벗어나는 시점(beforeunload)엔 일반 axios 요청이 완료 전에 취소될 수 있어
        // sendBeacon으로 보낸다 — 브라우저가 페이지 종료와 무관하게 전송을 보장해준다.
        const blob = new Blob([JSON.stringify(payload)], {type: 'application/json'});
        navigator.sendBeacon('/video/sync-offset', blob);
    } else {
        axios.post('/video/sync-offset', payload).catch(function() {});
    }
}

function scheduleSyncOffsetPost(payload) {
    syncOffsetPendingPayload = payload;
    clearTimeout(syncOffsetDebounceTimer);
    syncOffsetDebounceTimer = setTimeout(function() {
        syncOffsetDebounceTimer = null;
        const pending = syncOffsetPendingPayload;
        syncOffsetPendingPayload = null;
        if (pending) sendSyncOffsetPost(pending);
    }, 3000);
}

function flushSyncOffsetPost(useBeacon) {
    if (!syncOffsetDebounceTimer) return;
    clearTimeout(syncOffsetDebounceTimer);
    syncOffsetDebounceTimer = null;
    const pending = syncOffsetPendingPayload;
    syncOffsetPendingPayload = null;
    if (pending) sendSyncOffsetPost(pending, useBeacon);
}

function cancelSyncOffsetPost() {
    clearTimeout(syncOffsetDebounceTimer);
    syncOffsetDebounceTimer = null;
    syncOffsetPendingPayload = null;
}

window.addEventListener('beforeunload', function() { flushSyncOffsetPost(true); flushLikeMoves(true); });
window.addEventListener('pagehide', function() { flushSyncOffsetPost(true); flushLikeMoves(true); });

function applySavedSyncOffset() {
    const saved = videoSyncOffsetsMap[currentVideo];
    audioOffset = typeof saved === 'number' ? saved : 0;
}

function showVolumeMessage(isVideoJS) {
    if (isVideoJS) {
        volumeMessage.textContent = 'Volume: ' + Math.round(player.volume() * 100) + '%';
        previousVolume = player.volume()
    } else {
        volumeMessage.textContent = 'Volume: ' + Math.round(videoPlayer.volume * 100) + '%';
        previousVolume = videoPlayer.volume
    }

    volumeMessage.style.display = 'block';
    clearTimeout(volumeMessage.hideTimeout);
    volumeMessage.hideTimeout = setTimeout(function() {
        volumeMessage.style.display = 'none';
    }, 2000); // 2초 후 메시지 숨기기
}

function isFullscreen() {
    return !!(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement);
}

function requestDocFullscreen() {
    let docEl = document.documentElement;
    if (docEl.requestFullscreen) {
        docEl.requestFullscreen();
    } else if (docEl.webkitRequestFullscreen) {
        docEl.webkitRequestFullscreen();
    } else if (docEl.mozRequestFullScreen) {
        docEl.mozRequestFullScreen();
    } else if (docEl.msRequestFullscreen) {
        docEl.msRequestFullscreen();
    }
}

// 삭제 버튼을 누르면 initVideoElem()이 기존 video.js 플레이어를 dispose()하는데, video.js는
// dispose 시점에 자신이 전체화면 중이라고 판단되면 내부적으로 exitFullscreen()을 호출해버린다
// (우리가 document.documentElement로 직접 진입한 전체화면이라도 video.js는 fullscreenchange를
// 전역으로 구독해 자기 상태로 착각한다) — 그래서 삭제 후 다음 영상이 전체화면 밖으로 튕겨나오던
// 원인이었다. 삭제 시작 시점에 전체화면이었는지 기록해두고, 그 직후 벌어지는 fullscreenchange로
// 전체화면이 풀리면 즉시 재진입시킨다.
let keepFullscreenOnDelete = false;
let keepFullscreenTimer = null;

function handleFullscreenChangeDuringDelete() {
    if (keepFullscreenOnDelete && !isFullscreen()) {
        keepFullscreenOnDelete = false;
        clearTimeout(keepFullscreenTimer);
        requestDocFullscreen();
    }
}
document.addEventListener('fullscreenchange', handleFullscreenChangeDuringDelete);
document.addEventListener('webkitfullscreenchange', handleFullscreenChangeDuringDelete);
document.addEventListener('mozfullscreenchange', handleFullscreenChangeDuringDelete);
document.addEventListener('MSFullscreenChange', handleFullscreenChangeDuringDelete);

function exitFullscreen() {
    if (document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement || document.msFullscreenElement) {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
        } else if (document.mozCancelFullScreen) {
            document.mozCancelFullScreen();
        } else if (document.msExitFullscreen) {
            document.msExitFullscreen();
        }
    }
}

function toggleFullscreen() {
    if (!isFullscreen()) {  // 현재 전체화면이 아닌 경우
        requestDocFullscreen();
    } else {  // 현재 전체화면인 경우
        if (document.exitFullscreen) {
            document.exitFullscreen();
        } else if (document.webkitExitFullscreen) {
            document.webkitExitFullscreen();
        } else if (document.mozCancelFullScreen) {
            document.mozCancelFullScreen();
        } else if (document.msExitFullscreen) {
            document.msExitFullscreen();
        }
    }
}

function adjustVolume(change) {
    if (isVideoJs()) {
        player.volume(Math.min(Math.max(player.volume() + change, 0), 1));
    } else {
        videoPlayer.volume = Math.min(Math.max(videoPlayer.volume + change, 0), 1);
    }
    showVolumeMessage();
}

function minusTenSec() {
    var event = new KeyboardEvent('keydown', {
        key: 'ArrowLeft',
        code: 'ArrowLeft',
        keyCode: 37, // ArrowLeft keyCode
        which: 37,
        bubbles: true,
        shiftKey: true // Shift key가 눌린 상태로 이벤트 발생
    });
    document.dispatchEvent(event); // 키보드 이벤트를 전역에 전달
}

function plusTenSec() {
    var event = new KeyboardEvent('keydown', {
        key: 'ArrowRight',
        code: 'ArrowRight',
        keyCode: 39, // ArrowRight keyCode
        which: 39,
        bubbles: true,
        shiftKey: true // Shift key가 눌린 상태로 이벤트 발생
    });
    document.dispatchEvent(event); // 키보드 이벤트를 전역에 전달
}

function addKeyboardControls() {
    document.removeEventListener('keydown', videoKeyEvent)
    document.addEventListener('keydown', videoKeyEvent)
    document.removeEventListener('wheel', wheelEvent)
    document.addEventListener('wheel', wheelEvent)
    delayAudio();

    document.getElementById('minusTenSec')?.removeEventListener('click', minusTenSec);
    document.getElementById('minusTenSec')?.addEventListener('click', minusTenSec);
    document.getElementById('plusTenSec')?.removeEventListener('click', plusTenSec);
    document.getElementById('plusTenSec')?.addEventListener('click', plusTenSec);
    document.getElementById('syncMinusBtn')?.removeEventListener('click', syncMinusClick);
    document.getElementById('syncMinusBtn')?.addEventListener('click', syncMinusClick);
    document.getElementById('syncPlusBtn')?.removeEventListener('click', syncPlusClick);
    document.getElementById('syncPlusBtn')?.addEventListener('click', syncPlusClick);
    document.getElementById('syncMinusBigBtn')?.removeEventListener('click', syncMinusBigClick);
    document.getElementById('syncMinusBigBtn')?.addEventListener('click', syncMinusBigClick);
    document.getElementById('syncPlusBigBtn')?.removeEventListener('click', syncPlusBigClick);
    document.getElementById('syncPlusBigBtn')?.addEventListener('click', syncPlusBigClick);
    document.getElementById('syncResetBtn')?.removeEventListener('click', resetAudioSync);
    document.getElementById('syncResetBtn')?.addEventListener('click', resetAudioSync);
}

function syncMinusClick() {
    // Sync-: 오디오를 앞당겨(먼저 재생) 영상이 상대적으로 느리게 느껴지도록 한다. 키보드 'd'와 동일.
    adjustAudioSync(-0.01);
}

function syncPlusClick() {
    // Sync+: 오디오를 늦춰 영상이 상대적으로 빠르게 느껴지도록 한다. 키보드 'a'와 동일.
    adjustAudioSync(0.01);
}

function syncMinusBigClick() {
    adjustAudioSync(-0.1);
}

function syncPlusBigClick() {
    adjustAudioSync(0.1);
}

function wheelEvent(evnet) {
    if (event.deltaY < 0) {
        adjustVolume(0.1);
    } else {
        adjustVolume(-0.1);
    }
}

function videoKeyEvent(event) {
    let currentTime, duration;
    let isVideoJS = false;
    const videoPlayer = document.getElementById('videoPlayer');

    if (isVideoJs()) {
        isVideoJS = true;
        currentTime = player.currentTime();
        duration = player.duration();
    } else if (videoPlayer) {
        currentTime = videoPlayer.currentTime;
        duration = videoPlayer.duration;
    }

    switch(event.key) {
        case 'ArrowRight':
            if (event.shiftKey) {
                if (isVideoJS) {
                    player.currentTime(Math.min(currentTime + 30, duration));
                } else {
                    videoPlayer.currentTime = Math.min(currentTime + 30, duration);
                }
            } else {
                if (isVideoJS) {
                    player.currentTime(Math.min(currentTime + 5, duration));
                } else {
                    videoPlayer.currentTime = Math.min(currentTime + 5, duration);
                }
            }
            break;
        case 'ArrowLeft':
            if (event.shiftKey) {
                if (isVideoJS) {
                    player.currentTime(Math.max(currentTime - 30, 0));
                } else {
                    videoPlayer.currentTime = Math.max(currentTime - 30, 0);
                }
            } else {
                if (isVideoJS) {
                    player.currentTime(Math.max(currentTime - 5, 0));
                } else {
                    videoPlayer.currentTime = Math.max(currentTime - 5, 0);
                }
            }
            break;
        case 'ArrowUp':
            adjustVolume(0.1)
            showVolumeMessage();
            break;
        case 'ArrowDown':
            adjustVolume(-0.1)
            showVolumeMessage(isVideoJS);
            break;
        case 'a':
        case 'A': // Shift+a는 event.key가 대문자 'A'로 들어온다
            adjustAudioSync(event.shiftKey ? 0.1 : 0.01); // Sync+와 동일 (오디오를 늦춰 영상이 빠르게 느껴짐), Shift면 0.1 단위
            break;
        case 'd':
        case 'D': // Shift+d
            adjustAudioSync(event.shiftKey ? -0.1 : -0.01); // Sync-와 동일 (오디오를 앞당겨 영상이 느리게 느껴짐), Shift면 0.1 단위
            break;
        case 's':
            resetAudioSync();
            break;
        case 'l':
        case 'L':
            heartButton?.click();
            break;
        case 'Delete':
            delVideo();
            break;
        case 'PageDown':
            event.preventDefault();
            getVideo();
            break;
        case 'PageUp':
            event.preventDefault();
            prevButton.click();
            break;
        case ' ': // Space
            event.preventDefault();
            if (isVideoJS) {
                if (player.paused()) {
                    player.play();
                } else {
                    player.pause();
                }
            } else {
                if (videoPlayer.paused) {
                    videoPlayer.play();
                } else {
                    videoPlayer.pause();
                }
            }
            break;
        case 'Escape':
            exitFullscreen();
            break;
        case 'Enter': case 'f' :
            event.preventDefault()
            toggleFullscreen();
            break;
        case 'F11':
            event.preventDefault();
            break;
        case '[':
            event.preventDefault();
            aBtn.click();
            break;
        case ']':
            event.preventDefault();
            bBtn.click();
            break;
        case '\\':
            event.preventDefault();
            resetLoop();
            break;
        default: break;
    }
}


// 별도 <audio> 그래프(아래 activateSyncAudio)는 항상 켜두면 모든 영상에서 같은 파일을 오디오용으로
// 한 번 더 디코딩하게 되어 부하가 커진다 — 특히 세로영상 3분할처럼 캔버스에 매 프레임 그리는
// 무거운 경로에서 끊김으로 드러난다. 그래서 영상이 바뀔 때는 어느 엘리먼트인지만 기록해두고,
// 실제 그래프는 사용자가 'a'/'d'/'s'나 더블볼륨 토글을 처음 쓰는 순간에만 지연 초기화한다.
function delayAudio() {
    let video = document.querySelector('#videoPlayer')
    if (!video) return;

    if (isVideoJs()) {
        const audioPlayer = player;
        audioPlayer.ready(function() {
            if (audioPlayer.isDisposed()) return;
            const videoElement = audioPlayer.el().getElementsByTagName('video')[0];
            bindSyncVideoElement(videoElement, true);
        });
    } else if (video instanceof HTMLMediaElement) {
        bindSyncVideoElement(video, false);
    } else {
        console.error('Selected element is not an HTMLMediaElement');
    }
}

// 새 영상으로 넘어갈 때마다 호출된다. 네이티브 경로는 매번 새 <video> 엘리먼트가 생기므로
// 그래프를 다시 만들어야 하지만, video.js의 fast path(player.src()로 같은 tech를 재사용)는
// 엘리먼트가 그대로라 다시 만들 필요가 없다 — 이미 켜져 있으면 loadstart/timeupdate가 새
// src와 새 audioOffset을 알아서 따라간다. 저장된 오프셋이 있는 영상은(그래프가 아직 없어도)
// 바로 들리게 해야 하므로 이번엔 즉시 활성화한다.
function bindSyncVideoElement(videoElement, isVjs) {
    const sameElement = videoElement === syncVideoElement;
    syncVideoElement = videoElement;
    pendingIsVjs = isVjs;

    // 저장된 오프셋이 0인 영상(싱크가 필요 없는 영상)인데 이전 영상에서 그래프가 켜진 채로
    // 넘어오면, 원본 비디오는 계속 muted 상태로 남고 별도 오디오 파이프라인에만 의존하게 된다 —
    // 그 파이프라인이 한 번이라도 어긋나면(오토플레이 정책, 로드 타이밍 등) 다음 영상 소리가
    // 아예 안 들리는 원인이었다. 오프셋이 0이면 그래프를 끄고 원본 소리로 그냥 재생한다.
    if (audioOffset === 0) {
        if (syncAudioActive) {
            deactivateSyncAudio(videoElement);
        }
        return;
    }

    if (sameElement && syncAudioActive) {
        return;
    }
    activateSyncAudio(videoElement, isVjs);
}

function ensureSyncAudioGraph() {
    if (syncAudioActive || !syncVideoElement) return;
    activateSyncAudio(syncVideoElement, pendingIsVjs);
}

// activateSyncAudio()가 videoElement에 걸어둔 play/pause/ended/seeked/ratechange/timeupdate
// 리스너를 떼어낸다. 안 떼면 video.js의 fast path(같은 tech 엘리먼트 재사용)에서 그래프를 껐다
// 켰다 할 때마다 예전 리스너가 계속 쌓여, 이미 지워진 오디오 엘리먼트를 참조하는 낡은 클로저가
// 뒤섞여 재생/음소거 상태가 들쭉날쭉해지는 원인이 됐다.
let syncListenersTarget = null;
let syncListeners = null;

function detachSyncListeners() {
    if (syncListenersTarget && syncListeners) {
        syncListenersTarget.removeEventListener('play', syncListeners.play);
        syncListenersTarget.removeEventListener('pause', syncListeners.pause);
        syncListenersTarget.removeEventListener('ended', syncListeners.ended);
        syncListenersTarget.removeEventListener('seeked', syncListeners.seeked);
        syncListenersTarget.removeEventListener('ratechange', syncListeners.ratechange);
        syncListenersTarget.removeEventListener('timeupdate', syncListeners.timeupdate);
    }
    syncListenersTarget = null;
    syncListeners = null;
}

// 그래프를 끄고 원본 비디오 소리로 되돌린다 (오프셋이 0인 영상으로 넘어갈 때 사용)
function deactivateSyncAudio(videoElement) {
    syncAudioActive = false;
    detachSyncListeners();
    videoElement.muted = false;
    videoElement.removeAttribute('muted');
    if (syncAudioElement) {
        try { syncAudioElement.pause(); } catch (_) {}
    }
    if (audioContext) {
        try { audioContext.suspend(); } catch (_) {}
    }
}

// 비디오 자체의 소리는 끄고(muted), 같은 파일을 재생하는 별도의 <audio> 엘리먼트를 하나 더
// 만들어 그 currentTime을 "비디오의 currentTime + audioOffset"으로 계속 맞춰준다. 두 트랙의
// 재생 위치가 독립적이라 DelayNode 방식과 달리 음수(오디오를 앞당기는) 방향에 상한이 없다.
function activateSyncAudio(videoElement, isVjs) {
    syncAudioActive = true;
    detachSyncListeners(); // 이 엘리먼트에 이전 호출로 걸려있던 리스너가 있으면 먼저 제거

    // 재호출(다음 영상, 네이티브↔video.js 전환 등) 대비 이전 그래프/엘리먼트 정리
    if (audioContext) {
        try { audioContext.close(); } catch (_) {}
        audioContext = null;
    }
    if (syncAudioElement) {
        try { syncAudioElement.pause(); } catch (_) {}
        syncAudioElement.remove();
    }

    videoElement.muted = true; // 실제 소리는 아래 syncAudioElement 하나로만 낸다 (이중재생 방지)
    videoElement.setAttribute('muted', ''); // iOS Safari는 JS 프로퍼티만으론 재생/일시정지 때 muted가
    // 풀리는 경우가 있어(모바일에서 오디오가 겹쳐 들리던 원인) attribute로도 같이 걸어둔다

    const audioEl = document.createElement('audio');
    audioEl.preload = 'auto';
    audioEl.style.display = 'none';
    audioEl.loop = isLooping; // 네이티브 loop 재생 시 audioEl이 자기 길이만큼만 돌고 멈추는 것에
    // 대한 안전망 (아래 onSeeked에서도 직접 재생을 재보장하지만, 이벤트 타이밍이 어긋나는
    // 경우를 대비해 이중으로 막아둔다)
    document.body.appendChild(audioEl);
    syncAudioElement = audioEl;

    function loadAudioSrc() {
        const src = videoElement.currentSrc || videoElement.src;
        if (!src || audioEl.src === src) return;
        audioEl.src = src;
        audioEl.load();
    }
    loadAudioSrc();

    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const gain = audioCtx.createGain();
        const src = audioCtx.createMediaElementSource(audioEl);
        gain.gain.value = isClickGain ? 2.0 : 1.0; // 기존 더블 볼륨 토글 상태를 새 그래프에도 반영
        src.connect(gain);
        gain.connect(audioCtx.destination);
        audioContext = audioCtx;
        audioGainNode = gain;
    } catch (e) {
        // Web Audio 연결에 실패해도 audioEl 자체 재생/음량 조절은 계속 동작한다
    }

    function syncPlayState() {
        videoElement.muted = true; // 모바일에서 재생을 누를 때마다 muted가 풀려 원본 오디오가 같이
        // 들리는 경우가 있어(합성 오디오와 겹쳐 트랙이 여러 개로 들림) 매 play 시점에 재확인한다
        resyncAudioElement(true);
        audioEl.play().catch(() => {});
        audioContext && audioContext.resume();
    }

    function onSeeked() {
        resyncAudioElement(true);
        // 네이티브 loop 재생은 'ended'/'play' 없이 끝에서 처음으로 조용히 seek만 하고 이어지므로,
        // audioEl은 루프를 안 따라가고(자기 길이만큼 재생하다 자연스럽게 멈춘 뒤) 무음으로 남아
        // 있었다 — 영상은 계속 재생되는데 소리만 사라지는(멈춘 것처럼 보이는) 원인이었다. 비디오가
        // 재생 중이면 매 seek마다 audioEl 재생을 다시 보장한다.
        if (!videoElement.paused && !videoElement.ended) {
            audioEl.play().catch(() => {});
        }
    }

    const listeners = {
        play: syncPlayState,
        pause: function() {
            audioEl.pause();
            audioContext && audioContext.suspend();
        },
        ended: function() {
            audioEl.pause();
            audioContext && audioContext.suspend();
        },
        seeked: onSeeked,
        ratechange: function() { audioEl.playbackRate = videoElement.playbackRate; },
        timeupdate: function() { resyncAudioElement(false); }
    };
    videoElement.addEventListener('play', listeners.play);
    videoElement.addEventListener('pause', listeners.pause);
    videoElement.addEventListener('ended', listeners.ended);
    videoElement.addEventListener('seeked', listeners.seeked);
    videoElement.addEventListener('ratechange', listeners.ratechange);
    videoElement.addEventListener('timeupdate', listeners.timeupdate);
    syncListenersTarget = videoElement;
    syncListeners = listeners;

    if (isVjs) {
        // video.js는 다음 영상을 player.src()로 같은 tech 엘리먼트에 갈아끼우는 방식(빠른
        // 경로)을 쓰는데, 이 경로에서는 delayAudio()가 다시 호출되지 않는다 — 그래서 매
        // 영상 교체 시점(loadstart)마다 오디오 엘리먼트의 src도 같이 갈아준다. click/
        // touchstart를 player.on()으로 옮겼던 것과 같은 이유로, videoElement의 DOM 리스너
        // 대신 player.reset() 이후에도 살아남는 player 자체 이벤트 버스를 쓴다.
        player.off('loadstart');
        player.on('loadstart', loadAudioSrc);
    }

    if (!videoElement.paused) {
        syncPlayState();
    }
}

/************************************************************************/
/***************************   init  ************************************/
/************************************************************************/


function initPage() {
    previousVideos.push(undefined)
    // player = videojs('videoPlayer');
    if (likeFilterSelect) likeFilterMode = likeFilterSelect.value;
    Promise.all([loadVideoSyncOffsetsFromServer(), loadLikedVideosFromServer()]).then(function() {
        getVideo();
    });
}


document.addEventListener("DOMContentLoaded", initPage)