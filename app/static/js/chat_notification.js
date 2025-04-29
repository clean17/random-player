// 도메인 구입 전까지 서비스 워커 기능 비활성화 > PWA 기능 or FCM 추가해야함
if ("serviceWorker" in navigator) {
    // http + localhost, https(공인 ssl) 환경에서만 기동
    navigator.serviceWorker.register('/service-worker.js?v=2').then(registration => {
        return registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: "BM3Xq3X-hbmCtGvoJv3Dl-WmW1nTYenl4tKQtE4pdcMTK0XDxjrECQSmtFgnPd1aqUoBINRCKrLqfqwIdemSXZs" // YOUR_PUBLIC_VAPID_KEY
        });
    }).then(subscription => {
        console.log("Push Subscription:", JSON.stringify(subscription));
    });
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

function sendNotification(data) {
    if (document.hidden && Notification.permission === "granted") {
        if (!isMine && !isUnderline) {
            navigator.serviceWorker.ready.then(registration => { // 서비스 워커 알림
                registration.showNotification("새 메시지 도착!", {
                    // body: `${data.username}: ${data.msg}`,
                    icon: "/static/favicon.ico",
                    badge: "/static/favicon.ico",
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

// 클라이언트에서 서버에 푸시 구독 정보 전송
/*if ("serviceWorker" in navigator && "PushManager" in window) {
    navigator.serviceWorker.register("/service-worker.js")
        .then(registration => {
            console.log("서비스 워커 등록 완료:", registration);

            return registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: "YOUR_PUBLIC_VAPID_KEY"
            });
        })
        .then(subscription => {
            console.log("푸시 구독 성공:", subscription);
            return fetch("/subscribe", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(subscription)
            });
        })
        .catch(error => console.error("푸시 구독 실패:", error));
}*/
