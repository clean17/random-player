// 도메인 구입 전까지 서비스 워커 기능 비활성화 > PWA 기능 or FCM 추가해야함
/*if ("serviceWorker" in navigator) {
    // http + localhost, https(공인 ssl) 환경에서만 기동
    // navigator.serviceWorker.register("/service-worker.js", { scope: "/" })
    // navigator.serviceWorker.register("/static/js/service-worker.js", { scope: "/static/js/" })
    navigator.serviceWorker.register("/service-worker.js")
        .then(reg => console.log("서비스 워커 등록 완료:", reg))
        .catch(err => console.log("서비스 워커 등록 실패:", err));
}*/

function requestNotificationPermission() {
    if (!("Notification" in window)) {
        console.log("이 브라우저는 알림을 지원하지 않습니다.");
        return;
    }

    Notification.requestPermission().then(permission => {
        if (permission === "granted") {
            console.log("알림 권한이 허용되었습니다.");
        } else {
            console.log("알림 권한이 거부되었습니다.");
        }
    });
}

function sendNotification(data) {
    // if (document.hidden && Notification.permission === "granted") {
    if (Notification.permission === "granted") {
        /*navigator.serviceWorker.ready.then(registration => { // 서비스 워커 알림
            registration.showNotification("새 메시지 도착!", {
                body: `${data.username}: ${data.msg}`,
                icon: "/static/favicon.ico",
                badge: "/static/favicon.ico",
                vibrate: [200, 100, 200],  // 진동 패턴 (안드로이드)
            });
        });*/
        new Notification('새 메시지 도착!', { // 일반 알림
            body: `${data.username}: ${data.msg}`,
            icon: "/static/favicon.ico",
            badge: "/static/favicon.ico",
            vibrate: [200, 100, 200],  // 진동 패턴 (안드로이드)
        });
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
