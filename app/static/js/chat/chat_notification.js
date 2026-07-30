let userInteracted = false;
let pushSubscriptionStarted = false;

// VAPID 공개키(base64url) → PushManager가 요구하는 Uint8Array로 변환
// (문자열을 그대로 넘기면 Safari 등 표준을 엄격히 따르는 브라우저에서 구독이 실패한다)
function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const rawData = atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; i++) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

async function subscribeForPush() {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
    if (Notification.permission !== "granted") return;

    try {
        // http + localhost, https(공인 ssl) 환경에서만 기동
        const registration = await navigator.serviceWorker.register('/service-worker.js?v={{ version }}');
        await navigator.serviceWorker.ready;

        const keyRes = await fetch("/vapid-public-key");
        const { publicKey } = await keyRes.json();
        const applicationServerKey = urlBase64ToUint8Array(publicKey);

        let subscription;
        try {
            // 현재 브라우저를 푸시 수신 대상으로 등록, 성공하면 subscription 객체를 반환
            subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,   // 푸시를 보내면 사용자에게 보이는 알림을 반드시 띄워야 한다
                applicationServerKey       // 서버 VAPID 공개키, 서버에는 대응되는 개인키가 있어야 함
            });
        } catch (err) {
            // 예전에 다른 키로 구독된 상태면 InvalidStateError 발생 → 해지 후 새 키로 재구독
            const existing = await registration.pushManager.getSubscription();
            if (!existing) throw err;
            await existing.unsubscribe();
            subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey
            });
        }

        console.log("Push Subscription:", JSON.stringify(subscription));

        await fetch("/subscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(subscription)
        });
    } catch (error) {
        console.error("푸시 구독 실패:", error);
    }
}

function trySubscribeForPushOnce() {
    if (pushSubscriptionStarted) return;
    pushSubscriptionStarted = true;
    subscribeForPush();
}

// 이미 알림 권한이 허용된 상태면(재방문) 페이지 로드 시 바로 구독 시도
if ("Notification" in window && Notification.permission === "granted") {
    trySubscribeForPushOnce();
}

function requestNotificationPermission() {
    if (!("Notification" in window)) {
        console.log("이 브라우저는 알림을 지원하지 않습니다.");
        return;
    }

    // 이미 결정된 상태(허용/거부)면 다시 묻지 않는다 (Safari는 default가 아니면 재요청 시 예외 발생)
    if (Notification.permission !== "default") {
        if (Notification.permission === "granted") trySubscribeForPushOnce();
        return;
    }

    Notification.requestPermission().then(permission => {
        if (permission === "granted") {
            // console.log("알림 권한이 허용되었습니다 ㅅㅅ.");
            trySubscribeForPushOnce();
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
            navigator.serviceWorker.getRegistration().then(registration => {
                console.log('서비스워커 등록 확인', registration);
            });

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
