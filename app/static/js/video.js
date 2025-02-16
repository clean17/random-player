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
let delayNode;
let source;
let audioOffset = 0;
let hideControlsTimeout;
let isLooping = false;
let isSectionLooping = false;
let isClickAbtn = false;
let isClickBbtn = false;
let isClickGain = false;
let previousVolume = 1.0;
let startTime = 0;
let endTime = 0;
let gainNode;

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
                player.dispose(); // video.js 인스턴스 해제
            }
        }
        currentVideoPlayer.remove();
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
            player.pause();
            player.src({ src: '', type: 'video/mp4' });
            player.load();
            player.reset();
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
    console.log('resetLoop')
    isClickAbtn = false;
    isClickBbtn = false;
    isClickGain = false;
    aBtn.classList.remove('active');
    bBtn.classList.remove('active');
    toggleGainBtn.classList.remove('active');
    isSectionLooping = false;
    // loopButton.classList.remove('active');
}

/************************************************************************/
/*************************   Video Function   ***************************/
/************************************************************************/

function getVideo() {
    resetLoop();
    axios.get(`/video/videos?dir=${dir}`)
        .then(response => {
            let videos = response.data;
            if (videos.length > 0) {
                let randomIndex = Math.floor(Math.random() * videos.length);
                currentVideo = videos[randomIndex]
                console.log('currentVideo', currentVideo)

                const previousVideo = previousVideos.slice(-1)[0]
                if (currentVideo === previousVideo) {
                    currentVideo = videos[randomIndex === 0 ? 1 : 0]
                }

                const videoUrl = makeGetUrl(currentVideo);
                console.log('videoUrl', videoUrl)
                playVideo(videoUrl)
            } else {
                alert('No videos found');
            }
        });
}

function playVideo(videoUrl) {
    initVideoSrc()
    initVideoElem();
    if (videoSource) {
        videoSource.src = videoUrl;
    }
    pushVideoArr(currentVideo)
    /*console.log('-----------------------')
    previousVideos.forEach(item => {
        console.log(extractFilename(decodeURIComponent(item)))
    })
    console.log('-----------------------')*/
    if (videoPlayer) {
        videoPlayer.volume = previousVolume;
        videoPlayer.loop = isLooping;
        videoPlayer.load();
        videoPlayer.removeEventListener('loadedmetadata', getVideoEvent);
        videoPlayer.addEventListener('loadedmetadata', getVideoEvent);
    }
}

function getVideoEvent() {
    let decodedUrl = decodeURIComponent(videoSource.src)
    let videoFilename = extractFilename(decodedUrl);
    filenameDisplay.textContent = videoFilename;
    document.title = videoFilename;
    // console.log('getvideo', videoFilename)

    videoPlayer.addEventListener('timeupdate', function() {
        if (isLooping && endTime > startTime) {
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

    if (!threeSplitLayout()) {
        changeVideo() // change to videojs
    }
    addKeyboardControls();
}

function changeVideo() {
    initVideoSrc()
    initVideoElem();
    videoPlayer.removeEventListener('loadedmetadata', getVideoEvent);
    videoPlayer.classList.add('video-js', ',vjs-default-skin')

    const videoUrl = makeGetUrl(currentVideo)
    const fileExtension = currentVideo.split('.').pop();
    mimeType = fileExtension === 'ts' ? 'video/mp2t' : 'video/mp4';
    document.title = currentVideo.split('/')[1]

    if (videojs.players['videoPlayer']) { // 재사용
        player = videojs.players['videoPlayer'];
    } else {
        player = videojs('videoPlayer', setVideoOptions(videoUrl, mimeType));
    }

    player.src({type: mimeType, src: videoUrl});
    player.load();
    player.volume(previousVolume)
    player.loop(isLooping)
    player.off('loadeddata');
    player.on('loadeddata', function () {
        player.play();
        filenameDisplay.textContent = extractFilename(decodeURIComponent(videoUrl))
    });
    // player.off('ended');
    // player.on('ended', function() {
    //     if (isLooping) {
    //         player.play();
    //     }
    // });
    player.ready(function() {
        let controlBar = player.controlBar;

        controlBar.on('keydown', function(event) {
            // page up key: 33, page down key: 34
            if (event.keyCode === 33 || event.keyCode === 34) {
                event.preventDefault();
            }
        });
    });
    player.off('timeupdate');
    player.on('timeupdate', function() {
        if (isSectionLooping && endTime > startTime) {
            if (player.currentTime() >= endTime) {
                player.currentTime(startTime);
                player.play();
            }
        }
    });
    player.off('ended');
    player.on('ended', function() {
        if (isLooping && endTime === 0) {
            player.currentTime(startTime);
            player.play();
        }
    });
}

function delVideo() {
    if (currentVideo) {
        if (confirm(`Delete \r\n ${currentVideo} ?`)) {
            initVideoSrc() // 삭제하려는 파일이 사용중이면 접근이 안된다
            axios.delete(`/video/delete/${encodeURIComponent(currentVideo)}?dir=${dir}`)
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

function threeSplitLayout() {
    let videoRatio = videoPlayer.videoHeight / videoPlayer.videoWidth;
    if (videoRatio > 1 && window.innerWidth > window.innerHeight) {
        // let videoWidth = window.screen.width * 0.3333;
        // videoPlayer.style.minWidth = `${videoWidth}px`;

        // 왼쪽 비디오 추가
        videoLeft = document.createElement('video');
        videoLeft.id = 'videoLeft';
        videoLeft.className = 'video-mirror';
        videoLeft.muted = true;
        let videoLeftSource = document.createElement('source')
        videoLeftSource.type = 'video/mp4'
        videoLeft.appendChild(videoLeftSource)
        if (videoContainer && videoPlayer && videoContainer.contains(videoPlayer)) {
            videoContainer.insertBefore(videoLeft, videoPlayer);
        }
        // videoContainer?.insertBefore(videoLeft, videoPlayer);

        // 오른쪽 비디오 추가
        videoRight = document.createElement('video');
        videoRight.id = 'videoRight';
        videoRight.className = 'video-mirror';
        videoRight.muted = true;
        let videoRightSource = document.createElement('source')
        videoRightSource.type = 'video/mp4'
        videoRight.appendChild(videoRightSource)
        videoContainer?.appendChild(videoRight);

        let mainSrc = videoSource.src;

        videoLeftSource.src = mainSrc;
        videoRightSource.src = mainSrc;
        videoLeft.load();
        videoRight.load();

        let videoLeftLoaded = false;
        let videoRightLoaded = false;
        let videoPlayerLoaded = false;

        function checkBothVideosLoaded() {
            if (videoLeftLoaded && videoRightLoaded && videoPlayerLoaded) {
                playTripleVideo();
            }
        }

        videoLeft.onloadedmetadata = () => {
            videoPlayerLoaded = true;
            checkBothVideosLoaded();
        };

        videoLeft.onloadedmetadata = () => {
            videoLeftLoaded = true;
            checkBothVideosLoaded();
        };

        videoRight.onloadedmetadata = () => {
            videoRightLoaded = true;
            checkBothVideosLoaded();
        };

        videoPlayer.play().then(_ => {
            playTripleVideo();
        }).catch(error => {});

        videoPlayer.addEventListener('play', function() {
            videoLeft.play().catch(error => {});
            videoRight.play().catch(error => {});
        });

        videoPlayer.addEventListener('pause', function() {
            videoLeft.pause();
            videoRight.pause();
        });

        videoPlayer.addEventListener('seeked', function() {
            initTriple()
        });
        initTriple()

        if (document.fullscreenElement) {
            setLeftPositionForFullscreen();
        } else {
            setLeftPositionForNormal();
        }

        return true;
    } else {
        return false;
    }
}

function playTripleVideo() {
    videoPlayer.play().catch(error => {});
    videoLeft.play().catch(error => {});
    videoRight.play().catch(error => {});
}

function initTriple() {
    videoPlayer.pause();
    videoLeft.pause();
    videoRight.pause();
    let currentTime = videoPlayer.currentTime;
    videoLeft.currentTime = currentTime;
    videoRight.currentTime = currentTime;

    setTimeout(() => {
        playTripleVideo()
        // checkDuration()
    }, 630)
}

function checkDuration() {
    if (videoLeft && videoRight) {
        const currentTime = videoPlayer.currentTime;
        videoLeft.currentTime = currentTime
        videoRight.currentTime = currentTime
    }
}

/************************************************************************/
/***************************   Key Event   ******************************/
/************************************************************************/

const hideControls = () => {
    clearTimeout(hideControlsTimeout);
    hideControlsTimeout = setTimeout(() => {
        controls.style.display = 'none';
        topDiv.style.display = 'none';
        filenameDisplay.style.display = 'none';
        videoContainer.style.cursor = 'none';
    }, 2000);
};

const showControls = () => {
    controls.style.display = 'block';
    topDiv.style.display = 'block';
    filenameDisplay.style.display = 'block';
    videoContainer.style.cursor = 'default';
    hideControls();
};

document.getElementById('nextButton').removeEventListener('click', getVideo);
document.getElementById('nextButton').addEventListener('click', getVideo);
document.getElementById('deleteButton').removeEventListener('click', delVideo);
document.getElementById('deleteButton').addEventListener('click', delVideo);
document.getElementById('fullScreen').removeEventListener('click', toggleFullscreen);
document.getElementById('fullScreen').addEventListener('click', toggleFullscreen);
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

prevButton.addEventListener('click', function () {
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

loopButton.addEventListener('click', function() {
    isLooping = !isLooping;
    if (player) player.loop(isLooping);
    if (videoPlayer) videoPlayer.loop = isLooping;
    loopButton.classList.toggle('active', isLooping);
});

aBtn.addEventListener('click', function() {
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

bBtn.addEventListener('click', function() {
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

toggleGainBtn.addEventListener('click', function() {
    isClickGain = !isClickGain;
    toggleGainBtn.classList.toggle('active', isClickGain);
});

function showSyncMessage() {
    syncMessage.textContent = 'Audio Sync Offset: ' + audioOffset.toFixed(2) + 's';
    syncMessage.style.display = 'block';
    clearTimeout(syncMessage.hideTimeout);
    syncMessage.hideTimeout = setTimeout(function() {
        syncMessage.style.display = 'none';
    }, 2000); // 2초 후 메시지 숨기기
}

function adjustAudioSync(offset) {
    audioOffset += offset;
    if (audioOffset < 0) {
        const currentTime = audioContext.currentTime;
        source.disconnect();
        setTimeout(() => {
            source.connect(delayNode).connect(audioContext.destination);
            delayNode.delayTime.value = Math.abs(audioOffset);
        }, Math.abs(audioOffset * 1000));
    } else if (delayNode) {
        delayNode.delayTime.value = audioOffset;
    }
    showSyncMessage();
}

function resetAudioSync() {
    audioOffset = 0;
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

    document.getElementById('minusTenSec').removeEventListener('click', minusTenSec);
    document.getElementById('minusTenSec').addEventListener('click', minusTenSec);
    document.getElementById('plusTenSec').removeEventListener('click', plusTenSec);
    document.getElementById('plusTenSec').addEventListener('click', plusTenSec);
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
            adjustAudioSync(-0.01);
            break;
        case 'd':
            adjustAudioSync(0.01);
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
        case 'Enter':
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


function delayAudio() {
    console.log('delayAudio')
    let video = document.querySelector('#videoPlayer')
    if (video) {
        if (isVideoJs()) {
            // 비디오 요소가 로드된 후 Web Audio API 연결
            player.ready(function() {
                // Video.js의 HTML5 비디오 요소 참조
                var videoElement = player.el().getElementsByTagName('video')[0];

                // Web Audio API 초기화
                var audioContext = new (window.AudioContext || window.webkitAudioContext)();
                var source = audioContext.createMediaElementSource(videoElement);
                var gainNode = audioContext.createGain();

                // 증폭률 설정 (1.0은 100%, 2.0은 200%)
                gainNode.gain.value = 1.0;

                // 오디오 노드를 연결
                source.connect(gainNode);
                gainNode.connect(audioContext.destination);

                toggleGainBtn.addEventListener('click', function() {
                    if (isClickGain) {
                        gainNode.gain.value = 2.0;
                    } else {
                        gainNode.gain.value = 1.0;
                    }
                });
            });

            /*video = videojs.getPlayer(video.id);

            player.ready(() => {
                const videoElement = player.el().querySelector('video');

                if (videoElement instanceof HTMLMediaElement) {
                    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                    console.log('audioContext',audioContext)
                    const source = audioContext.createMediaElementSource(videoElement);
                    const delayNode = audioContext.createDelay();

                    delayNode.delayTime.value = 0.1; // 0.1초 지연

                    source.connect(delayNode);
                    delayNode.connect(audioContext.destination);

                    videoElement.addEventListener('play', () => {
                        audioContext.resume();
                    });
                } else {
                    console.error('Selected element is not an HTMLMediaElement');
                }
            });*/
        } else {
            if (video instanceof HTMLMediaElement) {
                audioContext = new (window.AudioContext || window.webkitAudioContext)();
                console.log('audioContext',audioContext)
                source = audioContext.createMediaElementSource(video);
                delayNode = audioContext.createDelay();

                delayNode.delayTime.value = audioOffset;

                source.connect(delayNode).connect(audioContext.destination);

                // 비디오 재생이 시작될 때 오디오 컨텍스트를 재개
                video.addEventListener('play', () => {
                    audioContext.resume();
                });

                // 비디오 재생이 일시 중지되면 오디오도 일시 중지
                video.addEventListener('pause', () => {
                    audioContext.suspend();
                });

                // 비디오 재생이 중지되면 오디오도 중지
                video.addEventListener('ended', () => {
                    audioContext.suspend();
                });
            } else {
                console.error('Selected element is not an HTMLMediaElement');
            }
        }
    }
}

/************************************************************************/
/***************************   CSS   ************************************/
/************************************************************************/

// window.onload = setLeftPosition;
window.onresize = () => {
    if (videoLeft && videoRight) {
        if (document.fullscreenElement) {
            setLeftPositionForFullscreen();
        } else {
            setLeftPositionForNormal();
        }
    }
};
// document.removeEventListener('fullscreenchange', setLeftPosition);
// document.addEventListener('fullscreenchange', setLeftPosition);


function setLeftPositionForNormal() {
    event.preventDefault()
    let windowWidth = window.innerWidth;
    let videoWidth = videoPlayer.videoWidth;
    let videoHeight = videoPlayer.videoHeight;
    let videoAspectRatio = videoWidth / videoHeight; // 원본 비율
    let displayedHeight = videoPlayer.offsetHeight;
    let displayedWidth = displayedHeight * videoAspectRatio; // 내부 영상 가로길이
    let position = (windowWidth - displayedWidth * 3) / 2

    videoLeft.style.left = position + 'px';
    videoRight.style.right = position + 'px';
    removeWidthFromVideoMirror()
}

function setLeftPositionForFullscreen() {
    event.preventDefault()
    let windowHeight = window.innerHeight;
    let windowWidth = window.innerWidth;
    let aspectRatio = windowWidth / windowHeight;
    let position;

    if (aspectRatio === 16 / 9) {
        position = windowHeight * 0.0453;
    } else if (aspectRatio === 16 / 10) {
        addWidthToVideoMirror();
        position = windowHeight * 0.0;
    } else {
        position = windowHeight * 0.03;
    }

    videoLeft.style.left = position + 'px';
    videoRight.style.right = position + 'px';
}

function addWidthToVideoMirror() {
    const elements = document.querySelectorAll('.video-mirror');
    elements.forEach(element => {
        element.style.width = '33.33%';
    });
}

function removeWidthFromVideoMirror() {
    const elements = document.querySelectorAll('.video-mirror');
    elements.forEach(element => {
        element.style.width = '';
    });
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