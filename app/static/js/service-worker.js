self.addEventListener("notificationclick", function(event) {
    console.log("알림 클릭됨:", event.notification); // 디버깅용 로그

    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true }).then(clientList => {
            console.log("열린 창 목록:", clientList);

            for (let client of clientList) {
                if (client.url.includes("/func/chat") && "focus" in client) {
                    console.log("채팅 창 포커스 시도:", client);
                    return client.focus();
                }
            }
            console.log("새로운 창 열기: /chat");
            return clients.openWindow("/func/chat"); // 클릭하면 채팅방 열기
        })
    );
});

// https://geundung.dev/114#google_vignette 참조 웹푸시 구현 필요
self.addEventListener("push", function (event) {
    const data = event.data.json();
    self.registration.showNotification(data.title, {
        body: data.body,
        icon: "/static/favicon.ico",
        badge: "/static/favicon.ico",
    });
});

const notification = new Notification("📢 클릭 가능한 알림", {
    body: "클릭하면 어떤 동작을 수행합니다.",
});

notification.onclick = function () {
    window.focus(); // 또는 특정 페이지로 이동
    console.log("알림이 클릭되었습니다!");
};