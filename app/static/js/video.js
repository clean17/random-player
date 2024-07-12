const videoContainer = document.querySelector('#videoContainer');
const videoPlayer = document.querySelector('#videoPlayer');
const videoSource = document.querySelector('#videoSource');
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
let mimeType;
let audioOffset = 0;
let hideControlsTimeout;

function extractFilename(url) {
    const cleanUrl = url.split('?')[0];
    const parts = cleanUrl.split('/');
    return parts[parts.length - 1];
}

function videoReset() {
    if (videoLeft) {
        videoLeft.remove()
    }
    if (videoRight) {
        videoRight.remove()
    }
}

function initVideo() {
    if (videoPlayer) {
        videoPlayer.pause();
        videoPlayer.onloadedmetadata = null;
        videoSource.src = ''
        videoPlayer.load();
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

function getVideo() {
    initVideo()
    videoReset();
    axios.get(`/video/videos?directory=${directory}`)
        .then(response => {
            let videos = response.data;
            if (videos.length > 0) {
                let randomIndex = Math.floor(Math.random() * videos.length);
                currentVideo = videos[randomIndex]

                let videoUrl = `/video/video/${encodeURIComponent(currentVideo)}?directory=${directory}`
                videoSource.src = videoUrl;
                pushVideoArr(videoUrl)
                videoPlayer.load();
                videoPlayer.removeEventListener('loadedmetadata', getVideoEvent);
                videoPlayer.addEventListener('loadedmetadata', getVideoEvent);

            } else {
                alert('No videos found');
            }
        });
}

function getVideoEvent() {
    if (!threeSplitLayout()) {
        changeVideo(directory, currentVideo)
    }
    addKeyboardControls();
    let videoFilename = extractFilename(decodeURIComponent(videoSource.src));
    currentVideo = videoFilename;
    console.log('getvideo', extractFilename(decodeURIComponent(videoFilename)))

    filenameDisplay.textContent = videoFilename;
    document.title = videoFilename;
}

function changeVideo(directory, currentVideo) {
    videoPlayer.removeEventListener('loadedmetadata', getVideoEvent);
    initVideo()
    videoPlayer.classList.add('video-js', ',vjs-default-skin')

    let url = directory === '0' ? `/video/stream/` : `/video/video/`;
    let videoUrl = url + `${encodeURIComponent(currentVideo)}?directory=${directory}`;
    let fileExtension = currentVideo.split('.').pop();
    mimeType = fileExtension === 'ts' ? 'video/mp2t' : 'video/mp4';
    videoSource.src = videoUrl;
    document.title = currentVideo.split('/')[1]

    if (videojs.players['videoPlayer']) { // 재사용
        player = videojs.players['videoPlayer'];
    } else {
        player = videojs('videoPlayer', setVideoOptions(videoUrl, mimeType));
    }

    player.src({type: mimeType, src: videoUrl});
    player.load();
    player.off('loadeddata');
    player.on('loadeddata', function () {
        player.play();
        pushVideoArr(videoUrl)
        console.log('dddddddd')
        // console.log('pushVideoArr', extractFilename(decodeURIComponent(prevVideoUrl)))
        // addKeyboardControls();

        let sourceElement = videoPlayer.getElementsByTagName('source')[0];
        let videoFilename = (sourceElement.getAttribute('src'))

        console.log('getvideo', extractFilename(decodeURIComponent(videoFilename)))
        filenameDisplay.textContent = extractFilename(decodeURIComponent(videoFilename))
    });
}

function delVideo() {
    if (currentVideo) {
        if (confirm(`Delete \r\n ${currentVideo} ?`)) {
            initVideo()
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

/*prevButton.addEventListener('click', function() {
    let prevVideoUrl = previousVideos.shift();
    if (prevVideoUrl) {
        player.src({ mimeType, src: prevVideoUrl });
        player.load();
        player.off('loadeddata');
        player.on('loadeddata', function() {
            player.play();
            addKeyboardControls();
            let videoFilename = extractFilename(decodeURIComponent(extractFilename(prevVideoUrl)))
            currentVideo = videoFilename

            console.log('prevButton', videoFilename)
            filenameDisplay.textContent = videoFilename;
            document.title = videoFilename
        });
    }
});*/

function isVideoJs(player) {
    if (player) {
        return typeof player.src === 'function';
    } return false;
}

prevButton.addEventListener('click', function() {
    let prevVideoUrl = previousVideos.shift();
    if (prevVideoUrl) {
        if (isVideoJs(player)) {
            player.src({ type: mimeType, src: prevVideoUrl });
            player.load();
            player.off('loadeddata');
            player.on('loadeddata', function() {
                player.play();
                addKeyboardControls();
                let videoFilename = extractFilename(decodeURIComponent(prevVideoUrl));
                pushVideoArr(prevVideoUrl)
                currentVideo = videoFilename;

                console.log('prevButton', videoFilename);
                filenameDisplay.textContent = videoFilename;
                document.title = videoFilename;
            });
        } else {
            initVideo()
            videoReset();
            videoSource.src = prevVideoUrl;
            let videoFilename = extractFilename(decodeURIComponent(prevVideoUrl));
            pushVideoArr(prevVideoUrl)

            console.log('prevButton', videoFilename);
            videoPlayer.load();
            videoPlayer.removeEventListener('loadedmetadata', getVideoEvent);
            videoPlayer.addEventListener('loadedmetadata', getVideoEvent);
        }
    }
});


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



const hideControls = () => {
    clearTimeout(hideControlsTimeout);
    hideControlsTimeout = setTimeout(() => {
        controls.style.display = 'none';
        topDiv.style.display = 'none';
        filenameDisplay.style.display = 'none';
    }, 2000);
};

const showControls = () => {
    controls.style.display = 'block';
    topDiv.style.display = 'block';
    filenameDisplay.style.display = 'block';
    hideControls();
};

document.getElementById('nextButton').removeEventListener('click', getVideo);
document.getElementById('nextButton').addEventListener('click', getVideo);
document.getElementById('deleteButton').removeEventListener('click', delVideo);
document.getElementById('deleteButton').addEventListener('click', delVideo);

videoPlayer.addEventListener('play', showControls);
videoPlayer.addEventListener('pause', showControls);
videoPlayer.addEventListener('click', showControls);
videoPlayer.addEventListener('touchstart', showControls);
videoPlayer.addEventListener('ended', getVideo);

videoPlayer.addEventListener('mousemove', showControls);
videoPlayer.addEventListener('touchmove', showControls);


/************************************************************************/
/************************************************************************/
/************************************************************************/


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
    let videoElement = player.el().querySelector('video');
    let currentTime = videoElement.currentTime;
    videoElement.currentTime = currentTime + offset;
    showSyncMessage();
}

function resetAudioSync() {
    audioOffset = 0;
    showSyncMessage();
}

function showVolumeMessage() {
    if (player) {
        volumeMessage.textContent = 'Volume: ' + Math.round(player.volume() * 100) + '%';
    } else {
        volumeMessage.textContent = 'Volume: ' + Math.round(videoPlayer.volume * 100) + '%';
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

function addKeyboardControls() {
    document.removeEventListener('keydown', videoKeyEvent)
    document.addEventListener('keydown', videoKeyEvent)
}

/*function videoKeyEvent(event) {
    let currentTime, duration;
    let videojs = false;
    if (player) {
        videojs = true;
        currentTime = player.currentTime();
        duration = player.duration();
    } else {
        currentTime = videoPlayer.currentTime
        duration = videoPlayer.duration
    }

    switch(event.key) {
        case 'ArrowRight':
            if (event.shiftKey) {
                player.currentTime(Math.min(currentTime + 30, duration));
            } else {
                player.currentTime(Math.min(currentTime + 5, duration));
            }
            break;
        case 'ArrowLeft':
            if (event.shiftKey) {
                player.currentTime(Math.max(currentTime - 30, 0));
            } else {
                player.currentTime(Math.max(currentTime - 5, 0));
            }
            break;
        case 'ArrowUp':
            player.volume(Math.min(player.volume() + 0.1, 1));
            showVolumeMessage();
            break;
        case 'ArrowDown':
            player.volume(Math.max(player.volume() - 0.1, 0));
            showVolumeMessage();
            break;
        case 'a':  // 'a' 키를 눌러 오디오 싱크를 -0.02초 조정
            adjustAudioSync(-0.02);
            break;
        case 'd':  // 'd' 키를 눌러 오디오 싱크를 +0.02초 조정
            adjustAudioSync(0.02);
            break;
        case 's':  // 's' 키를 눌러 오디오 싱크를 0으로 초기화
            resetAudioSync();
            break;
        case 'Delete':  // 'Delete' 키를 눌러 비디오 삭제 함수 호출
            delVideo();
            break;
        case 'PageDown':  // 'PageDown' 키를 눌러 비디오 가져오기 함수 호출
            getVideo();
            break;
        case 'PageUp':
            prevButton.click(); // 'PageUp' 키를 눌러 이전 비디오 재생
            break;
        case ' ':  // 스페이스바를 눌러 재생/일시정지 토글
            event.preventDefault();  // 스페이스바의 기본 동작 방지
            if (videojs) {
                if (player.paused()) {
                    player.play();
                } else {
                    player.pause();
                }
            } else {
                if (player.paused) {
                    player.play();
                } else {
                    player.pause();
                }
            }
            break;
        case 'Escape':  // ESC 키를 눌러 전체화면 해제
            exitFullscreen();
            break;
        case 'Enter':
            toggleFullscreen();
            break;
    }
}*/

function videoKeyEvent(event) {
    let currentTime, duration;
    let isVideoJS = false;
    const videoPlayer = document.getElementById('videoPlayer');

    if (typeof player !== 'undefined' && player) {
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
            if (isVideoJS) {
                player.volume(Math.min(player.volume() + 0.1, 1));
            } else {
                videoPlayer.volume = Math.min(videoPlayer.volume + 0.1, 1);
            }
            showVolumeMessage();
            break;
        case 'ArrowDown':
            if (isVideoJS) {
                player.volume(Math.max(player.volume() - 0.1, 0));
            } else {
                videoPlayer.volume = Math.max(videoPlayer.volume - 0.1, 0);
            }
            showVolumeMessage();
            break;
        case 'a':
            adjustAudioSync(-0.02);
            break;
        case 'd':
            adjustAudioSync(0.02);
            break;
        case 's':
            resetAudioSync();
            break;
        case 'Delete':
            delVideo();
            break;
        case 'PageDown':
            getVideo();
            break;
        case 'PageUp':
            prevButton.click();
            break;
        case ' ':
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
            toggleFullscreen();
            break;
    }
}

function threeSplitLayout() {
    let videoRatio = videoPlayer.videoHeight / videoPlayer.videoWidth;
    if (videoRatio > 1 && window.innerWidth > window.innerHeight) {
        let videoPlayer = document.getElementById('videoPlayer');
        let videoWidth = window.screen.width * 0.3333;
        videoPlayer.style.minWidth = `${videoWidth}px`;

        // 왼쪽 비디오 추가
        videoLeft = document.createElement('video');
        videoLeft.id = 'videoLeft';
        videoLeft.className = 'video-mirror';
        videoLeft.muted = true;
        let videoLeftSource = document.createElement('source')
        videoLeftSource.type = 'video/mp4'
        videoLeft.appendChild(videoLeftSource)
        videoContainer.insertBefore(videoLeft, videoPlayer);

        // 오른쪽 비디오 추가
        videoRight = document.createElement('video');
        videoRight.id = 'videoRight';
        videoRight.className = 'video-mirror';
        videoRight.muted = true;
        let videoRightSource = document.createElement('source')
        videoRightSource.type = 'video/mp4'
        videoRight.appendChild(videoRightSource)
        videoContainer.appendChild(videoRight);

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
                playVideo();
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

        // setTimeout(() => {
        //     videoPlayer.click()
        // }, 1000)

        // videoPlayer.play().then(_ => {
        //     playVideo();
        // }).catch(error => {});

        function playVideo() {
            videoPlayer.play().catch(error => {});
            videoLeft.play().catch(error => {});
            videoRight.play().catch(error => {});
        }

        videoPlayer.addEventListener('play', function() {
            videoLeft.play().catch(error => {});
            videoRight.play().catch(error => {});
        });

        videoPlayer.addEventListener('pause', function() {
            videoLeft.pause();
            videoRight.pause();
        });

        videoPlayer.addEventListener('seeked', function() {
            videoPlayer.pause();
            videoLeft.pause();
            videoRight.pause();
            let currentTime = videoPlayer.currentTime;
            videoLeft.currentTime = currentTime;
            videoRight.currentTime = currentTime;
            setTimeout(() => {
                playVideo()
            }, 400)
        });

        return true;
    } else {
        return false;
    }
}

function initPage() {
    previousVideos.push(undefined)
    // player = videojs('videoPlayer');
    getVideo();
}

document.addEventListener("DOMContentLoaded", initPage)