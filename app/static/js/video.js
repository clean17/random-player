let videoPlayer = document.querySelector('#videoPlayer');
let player;
let currentVideo = '';
let controls = document.querySelector('#controls');
let topDiv = document.querySelector('.top-bar');
let audioOffset = 0;
let syncMessage = document.getElementById('sync-message');
let volumeMessage = document.getElementById('volume-message');
let videoLeft;
let videoRight;
let filenameDisplay = document.getElementById('video-filename');
let previousVideos = []
let mimeType;

function getVideo() {
    axios.get(`/video/videos?directory=${directory}`)
        .then(response => {
            let videos = response.data;
            if (videos.length > 0) {
                let randomIndex = Math.floor(Math.random() * videos.length);
                currentVideo = videos[randomIndex];
                let url = directory === '0' ? `/video/stream/` : `/video/video/`;
                let videoUrl = url + `${encodeURIComponent(currentVideo)}?directory=${directory}`;
                let fileExtension = currentVideo.split('.').pop();
                mimeType = fileExtension === 'ts' ? 'video/mp2t' : 'video/mp4';
                videoPlayer.querySelector('source').src = videoUrl;
                document.title = currentVideo.replace(/.\\/g,'')
                player = videojs('videoPlayer', setVideoOptions(videoUrl, mimeType));
                player.src({ type: mimeType, src: videoUrl });
                player.load();
                player.off('loadeddata');
                player.on('loadeddata', function() {
                    player.play();
                    pushVideoArr(videoUrl)
                    addKeyboardControls();
                    let sourceElement = videoPlayer.getElementsByTagName('source')[0];
                    let videoFilename = sourceElement.getAttribute('src').split('/').pop().split('?')[0].slice(4)

                    filenameDisplay.textContent = decodeURIComponent(videoFilename);
                });
                player.off('loadedmetadata');
                player.on('loadedmetadata', function() {
                    //threeSplitLayout();
                });
            } else {
                alert('No videos found');
            }
        });
}

function delVideo() {
    if (currentVideo) {
        if (confirm("Are you sure?")) {
            videoPlayer.pause();
            videoPlayer.src = '';
            videoPlayer.load();

            axios.delete(`/video/delete/${encodeURIComponent(currentVideo)}?directory=${directory}`)
                .then(response => {
                    if (response.status === 204) {
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

document.getElementById('prevButton').addEventListener('click', function() {
    let prevVideoUrl = previousVideos.shift();
    if (prevVideoUrl) {
        player.src({ mimeType, src: prevVideoUrl });
        player.play();
        let url1 = prevVideoUrl.split('/')[3]
        let url2 = url1.slice(0, url1.lastIndexOf('?'))
        currentVideo = decodeURIComponent(url2)
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


let hideControlsTimeout;
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
    volumeMessage.textContent = 'Volume: ' + Math.round(player.volume() * 100) + '%';
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

function videoKeyEvent(event) {
    let currentTime = player.currentTime();
    let duration = player.duration();

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
        case ' ':  // 스페이스바를 눌러 재생/일시정지 토글
            event.preventDefault();  // 스페이스바의 기본 동작 방지
            if (player.paused()) {
                player.play();
            } else {
                player.pause();
            }
            break;
        case 'Escape':  // ESC 키를 눌러 전체화면 해제
            exitFullscreen();
            break;
        case 'Enter':
            toggleFullscreen();
            break;
    }
}

// TODO 이벤트만 붙이면 작동할것 같다
function threeSplitLayout() {
    let videoElement = player.el().querySelector('video');
    let videoRatio = videoElement.videoHeight / videoElement.videoWidth;
    if (videoRatio > 1) {
        let videoContainer = document.getElementById('videoContainer');
        let videoPlayer = document.getElementById('videoPlayer');
        // 왼쪽 비디오 추가
        videoLeft = document.createElement('video');
        videoLeft.id = 'videoLeft';
        videoLeft.className = 'video-mirror video-js vjs-default-skin';
        videoLeft.muted = 'true'
        videoLeft.autoplay = 'true'
        videoLeft.setAttribute('loop', '');
        videoContainer.insertBefore(videoLeft, videoPlayer);

        // 오른쪽 비디오 추가
        videoRight = document.createElement('video');
        videoRight.id = 'videoRight';
        videoRight.className = 'video-mirror video-js vjs-default-skin';
        videoRight.muted = 'true'
        videoRight.autoplay = 'true'
        videoRight.setAttribute('loop', '');
        videoContainer.appendChild(videoRight);

        let mainSrc = videoPlayer.querySelector('source').src;

        videoLeft.src = mainSrc;
        videoRight.src = mainSrc;
        videoLeft.load();
        videoRight.load();

        function playVideo() {
            videoLeft.play();
            videoRight.play();
        }

        function pauseVideo() {
            video.pause();
        }

        function skipForward() {
            if (video.duration - video.currentTime > 10) {
                video.currentTime += 10;
            } else {
                video.currentTime = video.duration; // Move to the end of the video if less than 10s remain
            }
        }

        function skipBackward() {
            if (video.currentTime > 10) {
                video.currentTime -= 10;
            } else {
                video.currentTime = 0; // Go back to the start if less than 10s into the video
            }
        }
    }
}

function initPage() {
    previousVideos.push(undefined)
    // player = videojs('videoPlayer');
    getVideo();
}

document.addEventListener("DOMContentLoaded", initPage)