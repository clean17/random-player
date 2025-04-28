// 새 워커가 등록되자마자 즉시 교체
self.addEventListener('install', event => {
    self.skipWaiting(); // 즉시 새로 등록된 워커로 교체
});

self.addEventListener('activate', event => {
    event.waitUntil(self.clients.claim()); // 모든 페이지에 바로 적용
});


self.addEventListener("notificationclick", function(event) {
    console.log("알림 클릭됨:", event.notification); // 디버깅용 로그

    event.notification.close();
    event.waitUntil(
        Promise.all([
            self.registration.getNotifications({ includeTriggered: true }).then(notifications => {
                // console.log("모든 알림 종료");
                notifications.forEach(n => n.close());
            }),

            clients.matchAll({ type: "window", includeUncontrolled: true }).then(clientList => {
                // console.log("열린 창 목록:", clientList);

                for (let client of clientList) {
                    if (client.url.includes("/func/chat") && "focus" in client) {
                        // console.log("채팅 창 포커스 시도:", client);
                        return client.focus();
                    }
                }
                console.log("새로운 창 열기: /chat");
                return clients.openWindow("/func/chat");
            })
        ])
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
