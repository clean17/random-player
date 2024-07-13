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