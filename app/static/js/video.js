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
        inactivityTimeout: 2000,
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
            let player = videojs.getPlayer(currentVideoPlayer.id);
            if (player) {
                try {
                    player.dispose(); // video.js 인스턴스 해제 > #videoPlayer도 자동으로 DOM에서 제거된다
                } catch (e) {
                    currentVideoPlayer.remove();
                }
            } else {
                currentVideoPlayer.remove();
            }
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
    currentVideo = videos[randomIndex]
    fetchVideoArr.splice(randomIndex, 1); // randomIndex에서 1개 제거
    // console.log('currentVideo', currentVideo)

    const previousVideo = previousVideos.slice(-1)[0]
    if (currentVideo === previousVideo) {
        currentVideo = videos[randomIndex === 0 ? 1 : 0]
    }

    const videoUrl = makeGetUrl(currentVideo);
    // console.log('videoUrl', videoUrl)
    playVideo(videoUrl)
}

function getVideo() {
    document.querySelectorAll('canvas').forEach(elem => elem.remove());
    resetLoop();
    if (fetchVideoArr.length === 0) {
        axios.get(`/video/videos?dir=${dir}`)
            .then(response => {
                let videos = response.data;
                if (videos.length > 0) {
                    fetchVideoArr = [...videos];
                    const randomIndex = Math.floor(Math.random() * fetchVideoArr.length);
                    selectVideoFromArr(fetchVideoArr, randomIndex);
                } else {
                    alert('No videos found');
                }
            });
    } else {
        const randomIndex = Math.floor(Math.random() * fetchVideoArr.length);
        selectVideoFromArr(fetchVideoArr, randomIndex);
    }
}

function playVideo(videoUrl) {
    // Fast path: Video.js가 이미 실행 중이면 사용자 제스처 컨텍스트 내에서 즉시 play()
    // Android는 비동기 콜백(loadedmetadata → changeVideo)에서 play()를 차단하므로
    // 기존 플레이어를 재활용해 동기적으로 호출한다
    if (player && !player.isDisposed() && isVideoJs()) {
        mimeType = currentVideo.split('.').pop() === 'ts' ? 'video/mp2t' : 'video/mp4';
        pushVideoArr(currentVideo);
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

        // 한 번 video.js 모드로 넘어가면 이후 영상은 전부 이 fast path만 타서, 세로영상이 다시
        // 나와도 3분할로 전환될 기회가 없었다(PC에서 3분할이 계속 안 되던 원인). 메타데이터가
        // 도착하면 이번 영상의 실제 비율을 확인해서, 3분할 대상이면 video.js를 버리고 네이티브
        // 경로로 다시 전환한다. play()는 이미 위에서 동기 호출했으니 안드로이드 제스처 제약과는
        // 무관하고, 판단만 메타데이터 도착 시점으로 늦춰질 뿐이다.
        const expectedVideo = currentVideo; // player.currentSrc()는 절대 URL로 바뀌어 원본 문자열과
                                             // 안 맞으므로, 식별자로는 currentVideo를 그대로 스냅샷
        player.one('loadedmetadata', function() {
            if (currentVideo !== expectedVideo) return; // 그새 다른 영상으로 넘어갔으면 무시
            const vp = player.el().getElementsByTagName('video')[0];
            const ratio = vp && vp.videoWidth ? vp.videoHeight / vp.videoWidth : 0;
            if (ratio > 1 && window.innerWidth > window.innerHeight) {
                playNative(videoUrl, false); // 이미 위에서 pushVideoArr 했으니 다시 push하지 않음
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
            let scale = Math.min(containerW / videoW, containerH / videoH);
            let shownW = videoW * scale;
            let shownH = videoH * scale;

            // myVideoPlayer 가운데 배치
            myVideoPlayer.style.position = 'absolute';
            myVideoPlayer.style.width = shownW + 'px';
            myVideoPlayer.style.height = shownH + 'px';
            myVideoPlayer.style.left = (containerW - shownW) / 2 + 'px';
            myVideoPlayer.style.top = (containerH - shownH) / 2 + 'px';

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
        if (confirm(`Delete \r\n ${currentVideo} ?`)) {
            initVideoSrc() // 삭제하려는 파일이 사용중이면 접근이 안된다 (서버에서 스트림 중이므로 삭제가 안된다)
            axios.post(`/video/delete/${encodeURIComponent(currentVideo)}?dir=${dir}`)
                .then(response => {
                    if (response.status === 204) {
                        // alert(`${currentVideo}`+` is deleted`)
                        currentVideo = '';
                        getVideo();
                    } else {
                        alert('Failed to delete video');
                    }
                }).catch(err => {
                alert(currentVideo)
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
        // filenameDisplay.style.display = 'none';
        // filenameDisplay.style.opacity = "0";
        videoContainer.style.cursor = 'none';
    }, 2000);
};

const showControls = () => {
    controls.style.display = 'block';
    topDiv.style.display = 'block';
    // filenameDisplay.style.display = 'block';
    // filenameDisplay.style.opacity = "1";
    videoContainer.style.cursor = 'default';
    hideControls();
};

document.getElementById('nextButton')?.removeEventListener('click', getVideo);
document.getElementById('nextButton')?.addEventListener('click', getVideo);
document.getElementById('deleteButton')?.removeEventListener('click', delVideo);
document.getElementById('deleteButton')?.addEventListener('click', delVideo);
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
        const videoFilename = extractFilename(decodeURIComponent(prevVideo));
        console.log('prevButton', videoFilename);
        pushVideoArr(currentVideo)
        currentVideo = prevVideo;

        const videoUrl = makeGetUrl(prevVideo)
        playVideo(videoUrl)
    }
});

loopButton?.removeEventListener('click', toggleLoop);
loopButton?.addEventListener('click', toggleLoop);
function toggleLoop() {
    isLooping = !isLooping;
    if (videoPlayer) videoPlayer.loop = isLooping;
    else if (player) player.loop(isLooping);
    loopButton.classList.toggle('active', isLooping);
}

aBtn?.addEventListener('click', function() {
    isClickAbtn = !isClickAbtn;
    if (player) startTime = player.currentTime();
    if (videoPlayer) startTime = videoPlayer.currentTime;
    isSectionLooping = isClickAbtn && isClickBbtn
    aBtn.classList.toggle('active', isClickAbtn);
    if (isSectionLooping && videoPlayer) {
        videoPlayer.removeAttribute('controls');
    } else {
        videoPlayer.setAttribute('controls', 'controls');
    }
});

bBtn?.addEventListener('click', function() {
    isClickBbtn = !isClickBbtn;
    if (player) endTime = player.currentTime();
    if (videoPlayer) endTime = videoPlayer.currentTime;
    isSectionLooping = isClickAbtn && isClickBbtn
    bBtn.classList.toggle('active', isClickBbtn);
    if (isSectionLooping && videoPlayer) {
        videoPlayer.removeAttribute('controls');
    } else {
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
    audioOffset += offset;
    resyncAudioElement(true);
    showSyncMessage();
}

function resetAudioSync() {
    ensureSyncAudioGraph();
    audioOffset = 0;
    resyncAudioElement(true);
    showSyncMessage();
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
    if (!document.fullscreenElement && !document.webkitFullscreenElement && !document.mozFullScreenElement && !document.msFullscreenElement) {  // 현재 전체화면이 아닌 경우
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
            adjustAudioSync(0.01); // Sync+와 동일 (오디오를 늦춰 영상이 빠르게 느껴짐)
            break;
        case 'd':
            adjustAudioSync(-0.01); // Sync-와 동일 (오디오를 앞당겨 영상이 느리게 느껴짐)
            break;
        case 's':
            resetAudioSync();
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

    function bindVideoElement(videoElement, isVjs) {
        syncVideoElement = videoElement;
        pendingIsVjs = isVjs;
        if (syncAudioActive) {
            // 이전 영상에서 이미 켠 상태라면 새 영상에도 그대로 이어서 켠다
            activateSyncAudio(videoElement, isVjs);
        }
    }

    if (isVideoJs()) {
        const audioPlayer = player;
        audioPlayer.ready(function() {
            if (audioPlayer.isDisposed()) return;
            const videoElement = audioPlayer.el().getElementsByTagName('video')[0];
            bindVideoElement(videoElement, true);
        });
    } else if (video instanceof HTMLMediaElement) {
        bindVideoElement(video, false);
    } else {
        console.error('Selected element is not an HTMLMediaElement');
    }
}

function ensureSyncAudioGraph() {
    if (syncAudioActive || !syncVideoElement) return;
    activateSyncAudio(syncVideoElement, pendingIsVjs);
}

// 비디오 자체의 소리는 끄고(muted), 같은 파일을 재생하는 별도의 <audio> 엘리먼트를 하나 더
// 만들어 그 currentTime을 "비디오의 currentTime + audioOffset"으로 계속 맞춰준다. 두 트랙의
// 재생 위치가 독립적이라 DelayNode 방식과 달리 음수(오디오를 앞당기는) 방향에 상한이 없다.
function activateSyncAudio(videoElement, isVjs) {
    syncAudioActive = true;

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

    const audioEl = document.createElement('audio');
    audioEl.preload = 'auto';
    audioEl.style.display = 'none';
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
        resyncAudioElement(true);
        audioEl.play().catch(() => {});
        audioContext && audioContext.resume();
    }

    videoElement.addEventListener('play', syncPlayState);
    videoElement.addEventListener('pause', () => {
        audioEl.pause();
        audioContext && audioContext.suspend();
    });
    videoElement.addEventListener('ended', () => {
        audioEl.pause();
        audioContext && audioContext.suspend();
    });
    videoElement.addEventListener('seeked', () => resyncAudioElement(true));
    videoElement.addEventListener('ratechange', () => { audioEl.playbackRate = videoElement.playbackRate; });
    videoElement.addEventListener('timeupdate', () => resyncAudioElement(false));

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
    getVideo();
}

document.addEventListener("DOMContentLoaded", initPage)