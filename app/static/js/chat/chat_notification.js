let userInteracted = false;

// 도메인 구입 전까지 서비스 워커 기능 비활성화 > PWA 기능 or FCM 추가해야함
if ("serviceWorker" in navigator) {
    // http + localhost, https(공인 ssl) 환경에서만 기동
    /*navigator.serviceWorker.register('/service-worker.js?v=2').then(registration => {
        return registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: "BM3Xq3X-hbmCtGvoJv3Dl-WmW1nTYenl4tKQtE4pdcMTK0XDxjrECQSmtFgnPd1aqUoBINRCKrLqfqwIdemSXZs" // YOUR_PUBLIC_VAPID_KEY
        });
    }).then(subscription => {
        console.log("Push Subscription:", JSON.stringify(subscription));

        return fetch("/subscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(subscription)
        });
    }).catch(error => console.error("푸시 구독 실패:", error));
    ;*/
}

function requestNotificationPermission() {
    if (!("Notification" in window)) {
        console.log("이 브라우저는 알림을 지원하지 않습니다.");
        return;
    }

    Notification.requestPermission().then(permission => {
        if (permission === "granted") {
            // console.log("알림 권한이 허용되었습니다 ㅅㅅ.");
        } else {
            // console.log("알림 권한이 거부되었습니다 ㅠㅠ.");
        }
    });
}

function vibrate() {
    if (userInteracted && "vibrate" in navigator) {
        navigator.vibrate([400, 200, 400]); // 400ms 진동 → 200ms 정지 → 400ms 진동
    }

    /*const audio = document.getElementById("alert-sound");
    if (audio) {
        audio.currentTime = 0;  // 처음부터 재생
        audio.play().catch(err => {
            console.warn("오디오 재생 실패:", err);
        });
    }*/
}

function sendNotification(data) {
    if (document.hidden && Notification.permission === "granted") {
        if (!isMine && !isUnderline) {
            navigator.serviceWorker.ready.then(registration => { // 서비스 워커 알림
                registration.showNotification("새 알림", {
                    // body: `${data.username}: ${data.msg}`,
                    // icon: "/static/favicon.ico", // 메인 블록 우측 큰 이미지
                    badge: "/static/favicon.ico", // 상단 헤더 뱃지
                    vibrate: [200, 100, 200],  // 진동 패턴 (안드로이드)
                });
            });
        }

        // http 환경에서는 아래 코드로 가능
        /*const notification = new Notification('새 메시지 도착!', { // 일반 알림
            body: `${data.username}: ${data.msg}`,
            icon: "/static/favicon.ico",
            badge: "/static/favicon.ico",
            vibrate: [200, 100, 200],  // 진동 패턴 (안드로이드)
        });
        notification.onclick = function () {
            window.focus(); // 또는 특정 페이지로 이동
        };*/
    }
}

function handleUserInteraction() {
    if (!userInteracted) {
        userInteracted = true;

        // 이벤트 리스너 제거 (불필요한 호출 방지)
        window.removeEventListener("click", handleUserInteraction);
        window.removeEventListener("touchstart", handleUserInteraction);
        window.removeEventListener("scroll", handleUserInteraction);
        window.removeEventListener("keydown", handleUserInteraction);
    }
}

// 상호작용 시 상태플래그만 저장
window.addEventListener("click", handleUserInteraction);
window.addEventListener("touchstart", handleUserInteraction);
window.addEventListener("scroll", handleUserInteraction);
window.addEventListener("keydown", handleUserInteraction);

// 상호작용 시 알림 권한 허용
document.body.removeEventListener('touchstart', requestNotificationPermission);
document.body.addEventListener('touchstart', requestNotificationPermission);
document.body.removeEventListener('ended', requestNotificationPermission);
document.body.addEventListener('ended', requestNotificationPermission);
document.body.removeEventListener('touchmove', requestNotificationPermission);
document.body.addEventListener('touchmove', requestNotificationPermission);
document.body.removeEventListener('click', requestNotificationPermission);
document.body.addEventListener('click', requestNotificationPermission);
