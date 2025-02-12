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