

const chatContainer = document.getElementById("chat-container"),
    chatInput = document.getElementById("chat-input"),
    sendButton = document.getElementById('send-button'),
    textAreaOffsetHeight = 22,
    openDate = new Date(),
    cameraButton = document.getElementById("camera-button"),
    videoCallBtn = document.getElementById("videoCallBtn");

let offset = 0, // 가장 최근 10개는 이미 로드됨
    socket,
    roomName,
    isMine,
    isUnderline,
    isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent),
    dateSet = new Set(),
    loading = false,
    lastMessageDate = null,
    dateStr,
    isScroll = false,
    scrollHeight, // 전체 스크롤 높이
    scrollTop,    // 현재 스크롤 위치
    videoCallWindow = null,
    isMinimized = false,
    isDragging = false,
    offsetX = 0,
    offsetY = 0,
    scrollButton = undefined;

openDate.setHours(openDate.getHours() + 9);  // UTC → KST 변환
const openTimestamp = openDate.toISOString().slice(2, 19).replace(/[-T:]/g, "");

function connectSocket() {
    // console.log('새로운 소켓 연결', username)
    // socket = io("https://192.168.60.205:3000", {
    socket = io("https://chickchick.shop:3000", {
        secure: true, // HTTPS 사용
        transports: ["websocket", "polling"],
        reconnection: true,              // 자동 재연결 활성화
        reconnectionAttempts: 20,        // 최대 재시도 횟수
        reconnectionDelay: 1000,         // 1초 간격
        timeout: 20000,                  // 서버로부터 응답 기다리는 시간 (기본값)
    });

    socket.on("connect", () => { // 소켓이 연결되면 자동으로 실행되는 콜백 함수
        console.log("✅ 소켓 연결됨, 유저 정보 전송");
        // 채팅방 입장 시 서버에 로그인된 유저 정보 전달
        socket.emit("user_info", { username: username, room: 'chat-room' });
    });

    socket.on("reconnect", () => {
        console.log("🔄 소켓 재연결됨");
        socket.emit("user_info", { username: username, room: 'chat-room' });
    });

    socket.on("new_msg", function(data) {
        addMessage(data);
        sendNotification(data);
    });

    socket.on("bye", function(data) {
        addMessage(data);
    });

    socket.on("enter_user", function(data) {
        roomName = data.room;
        if (data.username !== username) {
            addMessage(data);
        }
    });
}



document.addEventListener('visibilitychange', () => {
    console.log('visible')
    if (!document.hidden) {
        if (typeof socket !== "undefined") {
            if (!socket.connected) {
                // alert("🔄 소켓 재연결 시도");
                setTimeout(() => {
                    if (!socket.connected) {
                        console.log('⚠️ 소켓 연결 끊김')
                        connectSocket();
                    }
                }, 2000)
            }
        } else {
            alert("⚠️ socket 객체가 정의되지 않음");
            connectSocket();
        }
        chatInput.focus();
    }

    fetch("/func/chat", { method: "GET" })
        .then(res => {
            if (res.redirected) {
                window.location.href = res.url;
            }
        })
        .catch(err => {
            console.error("요청 실패:", err);
        });
});



// 위로 스크롤할 때 추가 데이터 불러오기 (무한 스크롤)
chatContainer.addEventListener("wheel", function () {
    if (Number(chatContainer.scrollTop) < 700 && !loading) {
        loadMoreChats("wheel");
    }
});
setTimeout(() => {
    chatContainer.addEventListener("scroll", function () {
        if (Number(chatContainer.scrollTop) < 700 && !loading) {
            loadMoreChats();
        }
    });
}, 200)


function loadMoreChats(event) {
    if (loading) return;  // 중복 호출 방지
    loading = true;

    // 현재 스크롤 위치 저장
    const prevScrollHeight = chatContainer.scrollHeight;
    const prevScrollTop = chatContainer.scrollTop;

    fetch("/func/chat/load-more-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ offset: offset })
    })
        .then(response => response.json())
        .then(data => {
            if (data.logs.length > 0) {
                const tempArr = []
                let isFisrtMsg = false;
                offset += Number(MAX_FETCH_MESSAGE_SIZE);

                if (data.logs.length !== MAX_FETCH_MESSAGE_SIZE) isFisrtMsg = true;

                data.logs.map(log => {
                    tempArr.push(log)
                });

                tempArr.reverse().forEach(log => {
                    const [timestamp, username, msg] = log.toString().split("|");
                    chatObj = { timestamp: timestamp.trim(), username: username.trim(), msg: msg.replace('\n', '').trim() }
                    addMessage(chatObj, true, isFisrtMsg)
                    if (event === "wheel") {
                        chatContainer.scrollTop = chatContainer.scrollHeight - prevScrollHeight + prevScrollTop;
                    }
                });

                if (isFisrtMsg) {
                    renderDateDivider(dateStr)
                }
            }
        })
        .finally(() => {
            loading = false;
        });

}

// 메시지 전송 후 아래쪽에 추가
function sendMsg() {
    // console.log(JSON.stringify(chatInput.value));
    const msg = chatInput.value.replace(/\n/g, "<br>").replace(/(<br>\s*)$/, "");  // 마지막 모든 <br> 제거
    if (msg !== "") {
        socket.emit("new_msg", { username, msg, room: roomName });
    }
    chatInput.value = "";
    chatInput.blur();  // IME 조합을 강제로 끊기 위해 포커스 제거
    setTimeout(() => chatInput.focus(), 0); // 다시 포커스를 살짝 늦게 줘서 안전하게 초기화
}

function callNotification() {
    if ("vibrate" in navigator) {
        navigator.vibrate([300, 200, 300]); // 400ms 진동 → 200ms 정지 → 400ms 진동
    }

    /*const audio = document.getElementById("alert-sound");
    if (audio) {
        audio.currentTime = 0;  // 처음부터 재생
        audio.play().catch(err => {
            console.warn("오디오 재생 실패:", err);
        });
    }*/
}

// 바깥 컨테이너: 메시지 한 줄을 구성
function renderMessageRow(isMine) {
    const messageRow = document.createElement("div");
    messageRow.style.display = "flex";
    messageRow.style.alignItems = "flex-end";
    messageRow.style.marginBottom = "6px";
    messageRow.style.maxWidth = "100%";
    messageRow.style.justifyContent = isMine ? "flex-end" : "flex-start";
    return messageRow;
}

// 메시지 박스
function renderMessageDiv() {
    const messageDiv = document.createElement("div");
    messageDiv.classList.add(
        "p-2",
        "rounded-lg",
        "max-w-[75%]",  // 최대 너비 75%
        "w-fit",
        "block",        // 내용에 맞게 크기 조정
        "break-words",  // 긴 단어가 자동으로 줄바꿈되도록 설정
    );
    return messageDiv;
}

// 시간 박스
function renderTimeDiv(timeStr) {
    const timeDiv = document.createElement("div");
    timeDiv.textContent = timeStr;
    timeDiv.style.fontSize = "0.75em";
    timeDiv.style.color = "#666";
    timeDiv.style.margin = isMine ? "0 8px 0 0" : "0 0 0 8px";  // 메시지와 간격
    return timeDiv;
}

// 메세지 추가
function addMessage(data, load = false) {
    isMine = data.username === username;
    isUnderline = data.underline;
    const now = new Date();

    if (data && !data.timestamp) {
        now.setHours(now.getHours() + 9);  // UTC → KST 변환
        const timestamp = now.toISOString().slice(2, 19).replace(/[-T:]/g, "");
        data.timestamp = timestamp;
    }

    const messageRow = renderMessageRow(isMine);
    const messageDiv = renderMessageDiv();

    if (isMine) {
        messageDiv.classList.add("bg-blue-200", "text-left");
    } else {
        if (data.isUnderline !== 1 && openTimestamp < data.timestamp) {
            callNotification();
        }
        messageDiv.classList.add("bg-gray-200", "text-left");
    }


    if (data.underline) { // 출입 알림
        if (!isMine) {
            const divider = createDateDivider('['+getCurrentTimeStr()+'] '+ data.msg);
            chatContainer.appendChild(divider);
            if (scrollHeight - scrollTop < 1300) {
                setTimeout(() => {
                    moveBottonScroll();
                }, 50)
            }
        }
    } else { // 메세지 생성
        const messageSpan = document.createElement("span");
        const safeText = data.msg.replace(/ /g, "&nbsp;");
        messageSpan.innerHTML = safeText;
        messageDiv.appendChild(messageSpan);

        // 시간 계산
        let timeStr = ""; // 14:33 형식
        dateStr = ""; // 25.04.12 형식

        // 채팅 불러와서 렌더링
        if (data.timestamp && data.timestamp.length >= 10) {
            const hour = data.timestamp.slice(6, 8);
            const minute = data.timestamp.slice(8, 10);
            timeStr = `${hour}:${minute}`;

            const yy = data.timestamp.slice(0, 2);
            const mm = data.timestamp.slice(2, 4);
            const dd = data.timestamp.slice(4, 6);
            dateStr = `20${yy}.${mm}.${dd}`;
        } else { // 신규 채팅
            const pad = (n) => String(n).padStart(2, '0');
            const hour = pad(now.getHours());
            const minute = pad(now.getMinutes());
            timeStr = `${hour}:${minute}`;

            dateStr = `20${pad(now.getFullYear() % 100)}.${pad(now.getMonth() + 1)}.${pad(now.getDate())}`;
            lastMessageDate = dateStr;
        }
        // console.log('lastMessageDate', lastMessageDate)
        // console.log('dateStr', dateStr)

        renderDateDivider(dateStr)

        if (load) {
            // 저장된 메세지 렌더링
            chatContainer.prepend(messageRow);
        } else {
            // 새로운 메세지 렌더링
            chatContainer.appendChild(messageRow);
            // console.log('check', scrollHeight - scrollTop )
            if (scrollHeight - scrollTop < 1300) {
                setTimeout(() => {
                    moveBottonScroll();
                }, 50)
            }
        }

        // 정렬 순서: 시간 → 메시지 또는 메시지 → 시간
        if (isMine) {
            messageRow.appendChild(renderTimeDiv(timeStr));
            messageRow.appendChild(messageDiv);
        } else {
            messageRow.appendChild(messageDiv);
            messageRow.appendChild(renderTimeDiv(timeStr));
        }
    }

}

function getCurrentTimeStr() {
    const now = new Date();

    const hour = now.getHours().toString().padStart(2, "0");
    const minute = now.getMinutes().toString().padStart(2, "0");

    return `${hour}:${minute}`;
}

// 날짜 구분선 추가
function renderDateDivider(dateStr) {

    let shouldAddDivider = false;
    if (dateStr !== lastMessageDate) {
        shouldAddDivider = true;
    }

    if (shouldAddDivider) {
        if (lastMessageDate && !dateSet.has(dateStr)) {
            const divider = createDateDivider(lastMessageDate);
            // console.log('divider',divider)
            chatContainer.prepend(divider);
            dateSet.add(lastMessageDate)
        }
        lastMessageDate = dateStr;
    }
}

function createDateDivider(dateStr) {
    const divider = document.createElement("div");
    divider.style.display = "flex";
    divider.style.alignItems = "center";
    divider.style.textAlign = "center";
    divider.style.margin = "16px 0";
    divider.style.color = "#999";
    divider.style.fontSize = "0.9em";

    divider.innerHTML = `
        <hr style="flex:1; border:none; border-top:1px solid #ccc;" />
        <span style="margin: 0 10px;">${dateStr}</span>
        <hr style="flex:1; border:none; border-top:1px solid #ccc;" />
    `;

    return divider;
}

function enterEvent(event) {
    if (event.key === 'Enter') {
        if (event.shiftKey) {
            return; // 줄바꿈만 하고 종료
        }
        if (!isMobile) {
            event.preventDefault(); // 기본 Enter 줄바꿈 방지
            // sendMsg();
            sendButton.click();
            chatInput.style.height = textAreaOffsetHeight + "px";
        }
    }
}

function cameraEvent(event) {

}

function checkScroll() {
    scrollHeight = chatContainer.scrollHeight;  // 전체 스크롤 높이
    scrollTop = chatContainer.scrollTop;        // 현재 스크롤 위치

    if (scrollHeight - scrollTop > 1400) {
        if (!isScroll) {
            isScroll = true;
        }
        scrollButton.style.display = "block";
    } else {
        if (scrollButton) {
            scrollButton.style.display = "none";
        }
    }

}

function moveBottonScroll() {
    // const scrollHeight = chatContainer.scrollHeight;  // 전체 스크롤 높이
    // const scrollTop = chatContainer.scrollTop;        // 현재 스크롤 위치

    // scrollHeight = chatContainer.scrollHeight;  // 전체 스크롤 높이
    // scrollTop = chatContainer.scrollTop;        // 현재 스크롤 위치

    // console.log(scrollHeight, scrollTop)
    // console.log('moveBottonScroll', scrollHeight - scrollTop);
    chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: "auto" });
}

function renderBottomScrollButton() {
    scrollButton = document.createElement("button");
    scrollButton.id = "scroll-button";
    scrollButton.innerHTML = "↓";
    scrollButton.style.display = 'none';
    document.body.appendChild(scrollButton);
}

function renderVideoCallWindow() {
    if (!videoCallWindow) {
        openVideoCallWindow();
    } else {
        if (isMinimized) {
            videoCallWindow.style.visibility = "";
            videoCallWindow.style.opacity = "1";
            isMinimized = false;
        } else {
            videoCallWindow.style.visibility = "hidden";
            videoCallWindow.style.opacity = "0";
            isMinimized = true;
        }
    }

    updateButtonColor();
}

function updateButtonColor() {
    // videoCallBtn.style.backgroundColor = videoCallWindow && !isMinimized ? "red" : "green";
}

function openVideoCallWindow() {
    videoCallWindow = document.createElement("div");
    videoCallWindow.style.position = "fixed";
    videoCallWindow.style.bottom = "140px";
    videoCallWindow.style.right = "30px";
    videoCallWindow.style.width = "350px";
    videoCallWindow.style.height = "500px";
    videoCallWindow.style.background = "#000";
    videoCallWindow.style.border = "2px solid #ccc";
    videoCallWindow.style.zIndex = "9998";
    videoCallWindow.style.display = "flex";
    videoCallWindow.style.flexDirection = "column";
    videoCallWindow.style.boxShadow = "0 0 10px rgba(0,0,0,0.5)";

    const topBar = document.createElement("div");
    topBar.style.display = "flex";
    topBar.style.justifyContent = "space-between";
    topBar.style.background = "#222";
    topBar.style.color = "#fff";
    topBar.style.padding = "4px 8px";

    const hideBtn = document.createElement("span");
    hideBtn.innerHTML = '<i class="fas fa-chevron-down"></i>';  // 🔽 숨기기
    hideBtn.style.cursor = "pointer";
    hideBtn.onclick = () => {
        videoCallWindow.style.visibility = "hidden";
        videoCallWindow.style.opacity = "0";
        isMinimized = true;
        updateButtonColor();
    };

    const closeBtn = document.createElement("span");
    closeBtn.innerHTML = '<i class="fas fa-times"></i>'; // ❌ 닫기
    closeBtn.style.cursor = "pointer";
    closeBtn.onclick = () => {
        document.body.removeChild(videoCallWindow);
        videoCallWindow = null;
        updateButtonColor();
        videoCallBtn.style.backgroundColor = "";
    };

    topBar.appendChild(hideBtn);
    topBar.appendChild(closeBtn);

    const iframe = document.createElement("iframe");
    iframe.src = "/func/video-call/window";
    iframe.style.flex = "1";
    iframe.style.border = "none";

    const dragOverlay = document.createElement("div");
    dragOverlay.style.position = "absolute";
    dragOverlay.style.bottom = "0";
    dragOverlay.style.left = "0";
    dragOverlay.style.width = "85%";
    dragOverlay.style.height = "90%";
    dragOverlay.style.zIndex = "9999";
    dragOverlay.style.background = "transparent"; // 완전 투명

    // iframe 추가 전에 삽입
    videoCallWindow.appendChild(dragOverlay);
    // 드래그 이벤트 연결
    dragOverlay.addEventListener("mousedown", startDrag);
    dragOverlay.addEventListener("touchstart", startDrag, { passive: false });

    videoCallWindow.appendChild(topBar);
    videoCallWindow.appendChild(iframe);

    // ✅ 마우스 이벤트
    videoCallWindow.addEventListener("mousedown", startDrag);
    document.addEventListener("mousemove", onDrag);
    document.addEventListener("mouseup", endDrag);

    // ✅ 터치 이벤트
    videoCallWindow.addEventListener("touchstart", startDrag, { passive: false });
    document.addEventListener("touchmove", onDrag, { passive: false });
    document.addEventListener("touchend", endDrag);

    document.body.appendChild(videoCallWindow);

    updateButtonColor();

    // videoCallBtn.style.backgroundColor = "green";
    // videoCallBtn.style.backgroundColor = "";
    // closeBtn.click();
    // 소켓으로 컨트롤 해야할지도

}
function initPage() {
    // keydown 에서만 event.preventDefault() 가 적용된다 !!
    chatInput.removeEventListener('keydown', enterEvent);
    chatInput.addEventListener('keydown', enterEvent)
    chatInput.addEventListener('blur', () => {
        setTimeout(() => {
            window.scrollTo(0, 0);  // 키보드 내려간 후에도 복구
        }, 100);
    });
    cameraButton.removeEventListener('click', cameraEvent);
    cameraButton.addEventListener('click', cameraEvent);
    sendButton.removeEventListener('click', sendMsg);
    sendButton.addEventListener('click', sendMsg);
    videoCallBtn?.removeEventListener('click', renderVideoCallWindow)
    videoCallBtn?.addEventListener('click', renderVideoCallWindow)
    document.body.removeEventListener('touchstart', requestNotificationPermission);
    document.body.addEventListener('touchstart', requestNotificationPermission);
    document.body.removeEventListener('ended', requestNotificationPermission);
    document.body.addEventListener('ended', requestNotificationPermission);
    document.body.removeEventListener('touchmove', requestNotificationPermission);
    document.body.addEventListener('touchmove', requestNotificationPermission);
    document.body.addEventListener('click', requestNotificationPermission);
    document.body.addEventListener('click', requestNotificationPermission);
    loadMoreChats();
    renderBottomScrollButton();

    // requestNotificationPermission(); // 상호작용 시 권한 허용

    chatContainer.removeEventListener("scroll", checkScroll);
    chatContainer.addEventListener("scroll", checkScroll);
    setTimeout(() => {
        moveBottonScroll();
    }, 200)

    scrollButton?.removeEventListener("click", () => {moveBottonScroll()});
    scrollButton?.addEventListener("click", () => {moveBottonScroll()});

    if (typeof socket !== "undefined") {
        if (!socket.connected) {
            connectSocket();
        }
    } else {
        connectSocket();
    }
    chatInput.focus();
}

let controller = new AbortController();

document.querySelectorAll('textarea[data-textarea-auto-resize]').forEach(textarea => {
    const maxLines = Number(textarea.dataset.textareaAutoResize) || 5;
    const maxHeight = maxLines * textAreaOffsetHeight;

    const resize = () => {
        textarea.style.height = '22px';  // ✅ 초기화
        // const lineCount = textarea.value.split('\n').length;
        // const newHeight = Math.min(lineCount * textAreaOffsetHeight, maxHeight);

        const scrollHeight = textarea.scrollHeight - 10; // ✅ 실제 내용 높이
        const newHeight = Math.min(scrollHeight, maxHeight);

        textarea.style.height = `${newHeight}px`;
    };

    textarea.addEventListener('input', resize, { signal: controller.signal });

    // 초기 설정
    resize();
});

// 📱 공통 좌표 추출 함수 (마우스 or 터치 구분)
function getClientPosition(e) {
    if (e.touches && e.touches.length > 0) {
        return {
            x: e.touches[0].clientX,
            y: e.touches[0].clientY
        };
    } else {
        return {
            x: e.clientX,
            y: e.clientY
        };
    }
}

function startDrag(e) {
    isDragging = true;
    const pos = getClientPosition(e);
    offsetX = pos.x - videoCallWindow.offsetLeft;
    offsetY = pos.y - videoCallWindow.offsetTop;
    // e.preventDefault(); // 터치 스크롤 방지
}

function onDrag(e) {
    if (!isDragging) return;
    const pos = getClientPosition(e);

    const x = pos.x - offsetX;
    const y = pos.y - offsetY;

    const windowWidth = window.innerWidth;
    const windowHeight = window.innerHeight;

    const elemWidth = videoCallWindow.offsetWidth;
    const elemHeight = videoCallWindow.offsetHeight;

    // ✅ 화면(뷰포트)을 벗어나지 않도록 제한
    const clampedX = Math.max(0, Math.min(x, windowWidth - elemWidth));
    const clampedY = Math.max(0, Math.min(y, windowHeight - elemHeight));

    videoCallWindow.style.left = `${clampedX}px`;
    videoCallWindow.style.top = `${clampedY}px`;
    videoCallWindow.style.right = "auto";
    videoCallWindow.style.bottom = "auto";
}

function endDrag() {
    isDragging = false;
}

// touchmove 강제 차단
document.addEventListener('touchmove', function (e) {
    const isChatContainer = e.target.closest('#chat-container');
    if (!isChatContainer) {
        e.preventDefault();  // ❌ chat-container 아닌 경우만 터치 이동 막기
    }
}, { passive: false }); // 브라우저에게 "이 리스너는 preventDefault()를 호출할 수 있다"고 알려주는 옵션
// passive: true     preventDefault() 안한다      (브라우저 최적화 OK)
// passive: false    preventDefault() 쓸 수도 있음 (브라우저가 스크롤 최적화 안 함)

document.addEventListener("DOMContentLoaded", initPage);
