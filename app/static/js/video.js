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
let mimeType;
let audioContext;
let delayNode;
let source;
let audioOffset = 0;
let hideControlsTimeout;
let isLooping = false;
let previousVolume = 1.0;

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
    const prefixUrl = directory === '0' ? `/video/stream/` : `/video/video/`;
    return prefixUrl + `${encodeURIComponent(filename)}?directory=${directory}`;
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

/************************************************************************/
/*************************   Video Function   ***************************/
/************************************************************************/

function getVideo() {
    axios.get(`/video/videos?directory=${directory}`)
        .then(response => {
            let videos = response.data;
            if (videos.length > 0) {
                let randomIndex = Math.floor(Math.random() * videos.length);
                currentVideo = videos[randomIndex]

                const previousVideo = previousVideos.slice(-1)[0]
                if (currentVideo === previousVideo) {
                    currentVideo = videos[randomIndex === 0 ? 1 : 0]
                }

                const videoUrl = makeGetUrl(currentVideo);
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

    if (!threeSplitLayout()) {
        changeVideo()
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
}

function delVideo() {
    if (currentVideo) {
        if (confirm(`Delete \r\n ${currentVideo} ?`)) {
            initVideoSrc() // 삭제하려는 파일이 사용중이면 접근이 안된다
            axios.delete(`/video/delete/${encodeURIComponent(currentVideo)}?directory=${directory}`)
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
    }, 500)
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

function addKeyboardControls() {
    document.removeEventListener('keydown', videoKeyEvent)
    document.addEventListener('keydown', videoKeyEvent)
    document.removeEventListener('wheel', wheelEvent)
    document.addEventListener('wheel', wheelEvent)
    delayAudio();
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
    }
}

function delayAudio() {
    let video = document.querySelector('#videoPlayer')
    if (video) {
        if (isVideoJs()) {
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