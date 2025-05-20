

const chatContainer = document.getElementById("chat-container"),
    chatInput = document.getElementById("chat-input"),
    sendButton = document.getElementById('send-button'),
    textAreaOffsetHeight = 22,
    openDate = new Date(),
    fileInput = document.getElementById('file-input'),
    progressContainer = document.getElementById('progressContainer'),
    videoCallBtn = document.getElementById("videoCallBtn"),
    roomUserCount = document.getElementById('userCount');

let offset = 0, // 가장 최근 10개는 이미 로드됨
    socket,
    roomName = 'chat-room',
    isMine,
    isUnderline, // 알림에서 사용한다
    isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent),
    loading = false,
    chatState = { previousDate: null, latestDate: null },
    scrollHeight, // 전체 스크롤 높이
    scrollTop,    // 현재 스크롤 위치
    isMinimized = false,
    lastChatId = 0,
    lastReadChatId = 0,
    submitted = false,
    videoCallRoomName = null,
    typingTimeout,
    peerLastReadChatId = 0,
    isTyping = false,
    scrollButton = undefined,
    isVerifiedPassword = false;

openDate.setHours(openDate.getHours() + 9);  // UTC → KST 변환
const openTimestamp = openDate.toISOString().slice(2, 19).replace(/[-T:]/g, "");
const debouncedUpdate = debounce(updateChatSession, 1000 * 10);
const trottledUpdate = throttle(updateChatSession, 1000 * 10);
let controller = new AbortController();

////////////////////////////// Util Function ////////////////////////////

// debounce 적용 (일정 시간동안의 마지막 요청만)
function debounce(func, delay) {
    let debounceTimer;
    return function (...args) {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => func.apply(this, args), delay);
    };
}

// throttle 적용 (일정 시간마다 요청)
function throttle(func, delay) {
    let throttleTimer = null;
    return function (...args) {
        if (throttleTimer) return;
        throttleTimer = setTimeout(() => {
            func.apply(this, args);
            throttleTimer = null;
        }, delay);
    };
}

// 채팅 입력창 자동으로 높이 조절
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

function getCurrentTimeStr() {
    const now = new Date();

    const hour = now.getHours().toString().padStart(2, "0");
    const minute = now.getMinutes().toString().padStart(2, "0");

    return `${hour}:${minute}`;
}

function extractDomain(url) {
    try {
        const parsed = new URL(url);
        return parsed.hostname.replace(/^www\./, ''); // www. 제거
    } catch (e) {
        return null;
    }
}

function getFilenameFromUrl(url) {
    const urlObj = new URL(url);
    const params = new URLSearchParams(urlObj.search);
    return params.get('filename');
}

function showDebugToast(message, duration = 3000) {
    let container = document.getElementById('debug-toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'debug-toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = 'debug-toast';
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, duration);
}

/////////////////////////////// Web Socket /////////////////////////////

function connectSocket() {
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
        // 채팅방 입장 시 서버에 로그인된 유저 정보 전달, 이 코드가 없으면 username이 게스트 상태로 소켓에 남아 있는 경우가 있다
        socket.emit("user_info", { username: username, room: roomName });
    });

    socket.on("reconnect", () => {
        alert("🔄 소켓 재연결됨"); // 이거 호출 안된다..
        // socket.emit("user_info", { username: username, room: roomName });
    });

    socket.on("new_msg", function(data) {
        if (lastChatId < data.chatId) {
            addMessage(data);
        }
        if (data.username !== username) {
            sendNotification(data);
            sendReadDataLastChat();
            if (!isScrollAtTheBottom()) showDebugToast('새로운 메세지 도착');
        } else {
            updateUserReadChatId(true); // 본인 메세지는 바로 읽도록 한다
        }
    });

    socket.on("message_read_ack", function (data) {
        if (data.username !== username) {
            setCheckIconsGreenUpTo(data.chatId);
        }
    })

    socket.on("bye", function(data) {
        // console.log('현재 접속 중인 유저 목록:', userList);
        // addMessage(data);
        updateUserCount(Number(roomUserCount.textContent)-1);

        // 떠났는데 남아 있는 경우 처리
        if (data.username !== username) {
            document.getElementById('typingIndicator').style.display = 'none';
            isTyping = false;
        }
    });

    socket.on("enter_user", function(data) {
        roomName = data.room;
        // addMessage(data);
    });

    // enter_room >> room_user_list
    socket.on("room_user_list", (userList) => {
        console.log('현재 접속 중인 유저 목록:', userList);
        updateUserCount(userList.length);
        const tempUserList = [];
        userList.forEach(user => {
            if (user !== username) {
                tempUserList.push(user);
            }
        })
        socket.emit("check_video_call_by_user", { userList: tempUserList });
    });

    socket.on("find_video_call", (data) => {
        if (data.socketId && !data.userList.includes(username)) {
            videoCallBtn.style.backgroundColor = "green";
        }
    });

    socket.on("video_call_ready", (data) => {
        videoCallRoomName = data.videoCallRoomName;
        if (username !== data.username) {
            videoCallBtn.style.backgroundColor = "green";
        }
    });

    socket.on("video_call_ended", (data) => {
        videoCallRoomName = null;
        if (username !== data.username) {
            videoCallBtn.style.backgroundColor = "";
        }
    });

    socket.on("typing", (data) => {
        if ( data.username !== username ) {
            document.getElementById('typingIndicator').style.display = 'block';

            if (isScrollAtTheBottom() && !isTyping) {
                moveBottonScroll();
                isTyping = true;
            }
        }
    });

    socket.on("stop_typing", (data) => {
        if (data.username !== username) {
            document.getElementById('typingIndicator').style.display = 'none';
            isTyping = false;
        }
    });
}


////////////////////////// Focus on Browser  ///////////////////////////
document.addEventListener('visibilitychange', async () => {
    if (!document.hidden) { // 최초 실행 x, 다시 브라우저를 방문하면 한 번만 실행된다
        // 최후의 보루 아래 코드가 안되면 새로고침 할 수 밖에
        /*fetch("/func/chat", { method: "GET" })
            .then(res => {
                if (res.redirected) {
                    window.location.href = res.url;
                }
            })
            .catch(err => {
                console.error("요청 실패:", err);
            });*/

        chatInput.focus();

        await checkVerified();

        fetch("/func/chat/load-more-chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ offset: 0 })
        })
            .then(res => {
                if (res.redirected) {
                    window.location.href = res.url;
                } else {
                    return res.json();
                }
            })
            .then(data => {
                if (data.logs.length > 0) {
                    const tempArr = []

                    data.logs.map(log => {
                        tempArr.push(log)
                    });

                    tempArr.forEach(log => {
                        const [chatId, timestamp, username, msg] = log.toString().split("|");
                        chatObj = { chatId: chatId.trim(), timestamp: timestamp.trim(), username: username.trim(), msg: msg.replace('\n', '').trim() }
                        if (Number(lastChatId) < Number(chatObj.chatId)) {
                            addMessage(chatObj);
                        }
                    });
                }
            })
            .then(() => {
                if (typeof socket !== "undefined") {
                    if (!socket.connected) {
                        // alert("🔄 소켓 재연결 시도");
                        if (!socket.connected) {
                            // console.log('⚠️ 소켓 연결 끊김');
                            console.log('🔄 소켓 재연결 시도');
                            connectSocket();
                        }
                    }
                } else {
                    alert("⚠️ socket 객체가 정의되지 않음");
                    connectSocket();
                }
            })
            .finally(() => {
                socket.emit("enter_room", { username: username, room: roomName });
                sendReadDataLastChat(); // 스크롤이 최하단이면 상대에게 읽었다고 보낸다
            });

    } else {
        socket.emit("exit_room", { username: username, room: roomName });
        // 소켓을 끊어버리면 알림이 안온다..
        // if (typeof socket !== "undefined") socket.disconnect();

        document.getElementById('typingIndicator').style.display = 'none';
        isTyping = false;
    }
});


////////////////////////// Chat State ////////////////////////////

// 상대가 마지막으로 읽은 chatId 조회
function getPeerLastReadChatId() {
    peername = username === 'nh824' ? 'fkaus14' : 'nh824'
    fetch('/func/last-read-chat-id?username=' + peername, {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json'
        },
        credentials: 'include' // 세션 인증 유지용 (Flask-Login 등)
    })
        .then(response => response.json())
        .then(data => {
            peerLastReadChatId = data['last_read_chat_id']
        })
        .then(() => {
            loadMoreChats('init'); // 초기 채팅 데이터 조회
        });
}

// 본인이 읽은 마지막 chatId 변경 요청
function updateUserReadChatId(option = false) {
    if (option || isScrollAtTheBottom()) {
        fetch('/func/last-read-chat-id', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
                username: username,
                lastReadChatId: lastChatId
            })
        })
            .then(response => response.json())
            .then(data => {
                // console.log('POST /last-read-chat-id:', data);
            });
    }
}

// 오차 발생
// function isScrollAtTheBottom() {
//     const lastMessageRow = document.querySelector(`.messageRow[data-chat-id="${lastChatId}"]`);
//     const rect = lastMessageRow.getBoundingClientRect();
//     return inView = rect.top >= 0 && rect.bottom <= window.innerHeight;
// }

function isScrollAtTheBottom() {
    const threshold = 60; // 허용 오차 (픽셀)
    return chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight <= threshold;
}

const readDebounce = debounce(() => {
    socket.emit("message_read", { chatId: lastChatId, room: roomName, username: username });
    if (lastReadChatId !== lastChatId) {
        debounce(() => {
            updateUserReadChatId(); // 스크롤이 아래일 때 상대가 채팅을 치기만 해도 계속 요청을 보낸다
            lastReadChatId = lastChatId;
        }, 500)
    }
}, 100)

// 스크롤이 최하단일 경우 읽음 표시를 보내는 함수
function sendReadDataLastChat() {
    if (isScrollAtTheBottom()) {
        readDebounce();
    }
}

// 채팅 세션 갱신 (10분 한정)
function updateChatSession() {
    fetch("/auth/update-session-time").then(data => {})
}

// 클라이언트가 세션을 체크, 존재하는지만 판단.. 서버에서도 체크하므로 결과만 확인한다
async function checkVerified() {
    try {
        const response = await fetch("/auth/check-verified", {
            method: "GET",
            headers: { "Content-Type": "application/json" }
        });

        if (response.status === 200) {
            const result = await response.json();
            if (result && result.success) {
                isVerifiedPassword = true;
            } else {
                isVerifiedPassword = false;
            }
        }
    } catch (e) {
        // console.error("❌ 서버 오류", e);
        isVerifiedPassword = false;
    }
}


//////////////////////////////// Render Chat ////////////////////////////////

function loadMoreChats(event) {
    // 추가 전 맨 위 요소의 위치 저장
    const firstMsg = chatContainer.firstElementChild;
    const prevTop = firstMsg?.getBoundingClientRect().top || 0;

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
                    const [chatId, timestamp, username, msg] = log.toString().split("|");
                    chatObj = {chatId: chatId.trim(), timestamp: timestamp.trim(), username: username.trim(), msg: msg.replace('\n', '').trim() }
                    addMessage(chatObj, true)
                });

                requestAnimationFrame(() => {
                    const newTop = firstMsg?.getBoundingClientRect().top || 0;
                    const delta = newTop - prevTop;

                    // ✅ 기존 위치 유지하도록 scrollTop 보정
                    chatContainer.scrollTop += delta;
                });

                if (isFisrtMsg) {
                    // renderDateDivider(dateStr)
                }
            }
        })
        .then(() => {
            setTimeout(() => {
                updateUserReadChatId();
            }, 300);
            if (event === 'init') {
                // 채팅 데이터 로드 후 최하단으로 채팅창 스크롤링
                moveBottonScroll();
                socket.emit("message_read", {chatId: lastChatId, room: roomName, username: username });
            }
        })
        .finally(() => {
            loading = false;
        });
}

// 메시지를 웹소켓에 전송 후 채팅 입력창 정리
function sendMessage() {
    const msg = chatInput.value.replace(/\n/g, "<br>").replace(/(<br>\s*)$/, "");  // 마지막 모든 <br> 제거
    if (msg !== "") {
        socket.emit("new_msg", { chatId: Number(lastChatId)+1, username, msg, room: roomName });
        socket.emit("stop_typing", {room: roomName, username: username });
    }
    // chatInput.blur();  // IME 조합을 강제로 끊기 위해 포커스 제거
    chatInput.value = "";
    chatInput.style.height = textAreaOffsetHeight + "px";
    chatInput.focus();
    // chatInput.setSelectionRange(0, 0);  // 커서 위치 맨 앞으로 다시 지정,  iOS Safari에서 포커스 후 스크롤 위치 이상 현상을 유발할 수도
}

// url 미리보기 카드 렌더링
function renderPreviewCard(data) {
    const copyLinkPreview = document.querySelector('.link-preview').cloneNode(true);
    copyLinkPreview.style.display = '';
    copyLinkPreview.querySelector('a').href = data.url;
    copyLinkPreview.querySelector('a').classList.add('bg-white');
    copyLinkPreview.querySelector('img').src = data.image;
    copyLinkPreview.querySelector('.message').textContent = data.url;
    copyLinkPreview.querySelector('.preview-title').textContent = data.title;
    copyLinkPreview.querySelector('.preview-description').textContent = data.description;
    copyLinkPreview.querySelector('.preview-url').textContent = extractDomain(data.url);
    return copyLinkPreview;
}

// 메세지 추가
function addMessage(data, load = false) {
    isMine = data.username === username;
    isUnderline = data.underline; // 알림에서 사용한다
    const now = new Date();

    if (data && !data.timestamp) { // 보낸 메세지는 timestemp가 없어서 만들어 준다. 채팅 로그를 node서버에 일임해야 할까 ?
        now.setHours(now.getHours() + 9);  // UTC → KST 변환
        const timestamp = now.toISOString().slice(2, 19).replace(/[-T:]/g, "");
        data.timestamp = timestamp;
    }

    if (Number(lastChatId) < Number(data.chatId)) { // 로드한 메세지가 아닌 추가된 메세지는 chatId가 없는데 ?
        lastChatId = data.chatId;
    }

    const messageRow = renderMessageRow(isMine, data.chatId);
    const messageDiv = renderMessageDiv();

    if (isMine) {
        messageDiv.classList.add("bg-blue-200", "text-left");
    } else {
        if (data.underline !== 1 && openTimestamp < data.timestamp) {
            callNotification();
        }
        messageDiv.classList.add("bg-gray-200", "text-left");
    }

    if (data.underline) { // 출입 알림
        if (!isMine) {
            renderEnterOrExit(data.msg);
        }
    } else { // 메세지 생성
        const urlRegex = /(https?:\/\/[^\s]+)/g;
        const matches = data.msg.match(urlRegex);

        if (data.msg.trim().startsWith('https://chickchick.shop/image/images')) {
            // const fileUrl = '';

            const img = document.createElement('img');
            img.src = data.msg;
            // img.className = 'w-40 h-40 object-cover rounded'; // Tailwind 예시
            img.alt = 'Uploaded Image';
            img.style.width = '100%';
            img.style.height = 'auto'; // 비율 유지 (이미지가 찌그러지지 않게)
            img.onerror = () => {
                img.onerror = null; img.src = '/static/no-image.png';
                img.style.width = '200px';
            };
            messageDiv.appendChild(img);
            messageDiv.classList.remove('p-2');
            messageDiv.classList.add('border');

            const urlRegex = /(https?:\/\/[^\s]+)/g;
            const matches = data.msg.match(urlRegex);
        } else if (data.msg.trim().startsWith('https://chickchick.shop/video/temp-video/')) {
            const video = document.createElement('video');
            video.classList.add('thumbnail');
            video.controls = true;
            video.style.height = '500px';
            const source = document.createElement('source');
            source.type = 'video/mp4';
            source.src = data.msg;
            video.appendChild(source);
            messageDiv.innerHTML = '';
            messageDiv.appendChild(video);
            messageDiv.classList.remove('p-2');
            messageDiv.classList.remove('bg-gray-200')
            messageDiv.classList.remove('bg-blue-200')
            messageDiv.classList.add('border');
        } else if (data.msg.trim().startsWith('https://chickchick.shop/file/files')) {
            const link = document.createElement('a');
            link.href = data.msg;
            link.innerText = getFilenameFromUrl(data.msg);
            link.target = '_blank';
            link.style.color = 'blue';
            messageDiv.innerHTML = '';
            messageDiv.appendChild(link);
        } else {
            const messageSpan = document.createElement("span");
            const safeText = data.msg.replace(/ /g, "&nbsp;");
            messageSpan.innerHTML = safeText;
            messageDiv.appendChild(messageSpan);

            if (matches) {
                fetch('/func/api/url-preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: matches[0] })
                })
                    .then(res => res.json())
                    .then(preview => {
                        if (preview) {
                            const previewEl = renderPreviewCard(preview, isMine);
                            messageDiv.innerHTML = '';
                            messageDiv.appendChild(previewEl);
                            messageDiv.classList.remove('p-2');
                            // messageDiv.classList.remove('bg-gray-200')
                            // messageDiv.classList.remove('bg-blue-200')
                        }
                    });
            }
        }


        // 시간 계산
        const hour = data.timestamp.slice(6, 8);
        const minute = data.timestamp.slice(8, 10);
        const timeStr = `${hour}:${minute}`; // 14:33 형식

        const yy = data.timestamp.slice(0, 2);
        const mm = data.timestamp.slice(2, 4);
        const dd = data.timestamp.slice(4, 6);
        const dateStr = `20${yy}.${mm}.${dd}`; // 25.04.12 형식

        renderDateDivider(chatState, dateStr)

        if (load) {
            // 저장된 메세지 렌더링
            chatContainer.prepend(messageRow);
        } else {
            // 새로운 메세지 렌더링
            chatContainer.appendChild(messageRow);
            // console.log('check', scrollHeight - scrollTop )
            if (isScrollAtTheBottom()) {
                moveBottonScroll();
            }
            /*if (scrollHeight - scrollTop < 1300) {
                setTimeout(() => {
                    moveBottonScroll();
                }, 50);
            }*/
        }

        // 정렬 순서: 시간 → 메시지 또는 메시지 → 시간
        if (isMine) {
            messageRow.appendChild(renderTimeDiv(timeStr));
            const checkIcon = renderCheckIcon();
            if (peerLastReadChatId && Number(peerLastReadChatId) >= Number(data.chatId)) {
                if (load) {
                    // checkIcon.style.color = "green";
                    checkIcon.style.setProperty("color", "green", "important");
                }
            }
            messageRow.appendChild(checkIcon);
            messageRow.appendChild(messageDiv);
        } else {
            messageRow.appendChild(messageDiv);
            messageRow.appendChild(renderTimeDiv(timeStr));
        }
    }
}

// 바깥 컨테이너: 메시지 한 줄을 구성
function renderMessageRow(isMine, chatId) {
    const messageRow = document.createElement("div");
    messageRow.style.display = "flex";
    messageRow.style.alignItems = "flex-end";
    messageRow.style.marginBottom = "6px";
    messageRow.style.maxWidth = "100%";
    messageRow.style.justifyContent = isMine ? "flex-end" : "flex-start";
    messageRow.classList.add('messageRow')
    messageRow.dataset.chatId = chatId;
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
        "messageDiv",
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

// 들어옴, 나감 표기 함수
function renderEnterOrExit(msg) {
    const divider = createDateDivider('[' + getCurrentTimeStr() + '] ' + msg);
    chatContainer.appendChild(divider);
    if (isScrollAtTheBottom()) {
        moveBottonScroll();
    }
}

// 날짜 구분선 추가
function renderDateDivider(chatState, dateStr) {
    // 메세지를 불러오다가 lastMessageDate > dateStr => prepend; lastMessageDate 직 후 lastMessageDate = dateStr;
    // 메세지를 불러오다가 lastMessageDate < dateStr => append; dateStr          직 후 lastMessageDate = dateStr;

    let lastest = null;
    let previos = null;
    let otherDate = null;

    if (chatState.latestDate) lastest = Number(chatState.latestDate.replace(/\./g, ''));
    if (chatState.previousDate) previos = Number(chatState.previousDate.replace(/\./g, ''));
    if (dateStr) otherDate = Number(dateStr.replace(/\./g, ''));

    // 스크롤 올려서 이전 날짜가 나오면 메세지 렌더링 전에 prepend
    if (lastest && otherDate && otherDate < previos) {
        const divider = createDateDivider(chatState.previousDate);
        chatContainer.prepend(divider);
        chatState.previousDate = dateStr;
    }
    // 채팅을 쳤는데 오늘 첫 메세지라면 메세지 렌더링 전에 append
    if (lastest && otherDate && otherDate > lastest) {
        const divider = createDateDivider(dateStr);
        chatContainer.append(divider);
        chatState.latestDate = dateStr;
    }
    if (!chatState.latestDate) {
        chatState.previousDate = dateStr;
        chatState.latestDate = dateStr;
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

// 참여중 인원 수 표기 변경
function updateUserCount(number) {
    roomUserCount.textContent = number;
    if (number === 1) {
        videoCallBtn.style.backgroundColor = "";
    }
}

// 최하단으로 가는 버튼 생성
function renderBottomScrollButton() {
    scrollButton = document.createElement("button");
    scrollButton.id = "scroll-button";
    scrollButton.innerHTML = "↓";
    scrollButton.style.display = 'none';
    document.body.appendChild(scrollButton);
}


////////////////////////// File Upload /////////////////////////////

function uploadFile(event) {
    const files = event.target.files;

    if (!files || files.length === 0) {
        console.log("❌ 파일이 선택되지 않았습니다.");
        return;
    }

    const file = files[0];
    if (file) {
        const form = event.target.closest('form');  // 🔧 이걸 먼저 정의해줘야 아래에서 사용 가능

        if (submitted) {
            return;  // 이미 제출한 경우
        }
        submitted = true;

        // 버튼 비활성화해서 UI도 중복 방지
        const button = document.querySelector('label[for="file-input"]');
        if (button) {
            button.disabled = true;
        }

        const formData = new FormData(form);
        const xhr = new XMLHttpRequest();

        xhr.open('POST', '/upload/', true);

        // 진행률 표시
        xhr.upload.onprogress = function (e) {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                progressContainer.style.display = 'block';
                document.getElementById('progressBar').value = percent;
            }
        };

        // 완료 후 리다이렉트
        xhr.onload = function () {
            // submitted = false; // 다시 전송 가능하게
            if (xhr.status === 200) {

                // submitted = false; // 다시 전송 가능하게
                // progressContainer.style.display = 'none';
                submitted = false;
                progressContainer.style.display = 'none';

                const response = JSON.parse(xhr.responseText); // 서버 응답
                const files = response.files;

                // files는 서버에서 json 형태로 만들어줘야 한다
                files.forEach(file => {
                    const filename = file.name;
                    const isImage = file.type.startsWith("image/");
                    const isVideo = file.type.startsWith("video/");

                    /*const ext = file.split('.').pop().toLowerCase();

                    const imageExts = ["jpg", "jpeg", "png", "gif", "bmp", "webp"];
                    const videoExts = ["mp4", "webm", "mov", "ogg", "mkv"];*/

                    let url = '';
                    if (isImage) { // imageExts.includes(ext)
                        url = "https://chickchick.shop/image/images?filename="+filename+"&dir=temp&selected_dir=chat";
                    } else if (isVideo) { // videoExts.includes(ext)
                        url = "https://chickchick.shop/video/temp-video/"+filename+"?dir=temp&selected_dir=chat";
                    } else { // 파일
                        url = "https://chickchick.shop/file/files?filename="+filename+"&dir=temp&selected_dir=chat";
                    }

                    const msg = url.replace(/\n/g, "<br>").replace(/(<br>\s*)$/, "");  // 마지막 모든 <br> 제거
                    if (msg !== "") {
                        socket.emit("new_msg", { chatId: Number(lastChatId)+1, username, msg, room: roomName });
                    }
                })
            } else {
                submitted = false; // 다시 전송 가능하게
                alert('업로드 실패: ' + xhr.statusText);
                if (button) {
                    button.disabled = false;
                }
            }
        };

        xhr.onerror = function () {
            submitted = false;
            alert('서버에 연결할 수 없습니다.');
            if (button) {
                button.disabled = false;
                button.innerText = 'Start Upload';
            }
        };

        xhr.send(formData);
    }
}


//////////////////////////////// Chat Check Icon  ////////////////////////////////

function renderCheckIcon() {
    const checkIcon = document.createElement("div");
    checkIcon.className = "checkIcon";
    // checkIcon.innerHTML = "✔"; // 나중에 SVG 아이콘으로 바꿔도 좋음
    checkIcon.innerHTML = '<i class="fas fa-check"></i>';
    // checkIcon.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
    //     <path d="M20.285 6.709l-11.025 11.025-5.046-5.046 1.414-1.414 3.632 3.632 9.611-9.611z"/>
    // </svg>`;

    // 스타일 설정
    checkIcon.style.width = "20px";
    checkIcon.style.height = "20px";
    checkIcon.style.display = "flex";
    checkIcon.style.alignItems = "center";
    checkIcon.style.justifyContent = "center";
    checkIcon.style.marginRight = "6px";
    checkIcon.style.flexShrink = "0";
    checkIcon.style.fontSize = "0.9em";
    checkIcon.style.color = "whitesmoke";
    checkIcon.style.background = "#ddd"; // 밝은 회색 배경
    checkIcon.style.borderRadius = "4px";
    checkIcon.style.fontWeight = "bold";

    return checkIcon;
}

function setCheckIconGreen(chatId) {
    const row = document.querySelector(`.messageRow[data-chat-id="${chatId}"]`);
    if (!row) return;

    const checkIcon = row.querySelector('.checkIcon');
    if (checkIcon) {
        checkIcon.style.color = "green";
    }
}

// 파라미터 보다 낮은 채팅 ID들 모두 읽음 표시 전환
function setCheckIconsGreenUpTo(chatId) {
    const rows = document.querySelectorAll('.messageRow[data-chat-id]');
    rows.forEach(row => {
        const rowChatId = parseInt(row.dataset.chatId, 10);
        if (!isNaN(rowChatId) && rowChatId <= chatId) {
            const checkIcon = row.querySelector('.checkIcon');
            if (checkIcon) {
                // checkIcon.style.color = "green";
                checkIcon.style.setProperty("color", "green", "important");
            }
        }
    });
}


///////////////////////////// Event Listener //////////////////////////////

// 채팅 입력 이벤트 함수
function enterEvent(event) {
    debouncedUpdate();

    if (event.key === 'Enter') {
        if (event.shiftKey) {
            return; // 줄바꿈만 하고 종료
        }
        if (!isMobile) {
            event.preventDefault(); // 기본 Enter 줄바꿈 방지
            // sendMessage();
            sendButton.click();
        }
    } else {
        setTimeout(() => {
            if (chatInput.value.trim().length > 0) {
                socket.emit("typing", { room: roomName, username: username }); // 입력 중임을 알림
            }
            if (chatInput.value.trim().length === 0) {
                socket.emit("stop_typing", { room: roomName, username: username });
            }
        }, 10)

        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            socket.emit("stop_typing", { room: roomName, username: username }); // 일정 시간 입력 없으면 중단 알림
        }, 2000); // 2초간 입력 없으면 stop_typing
    }
}

// 영상통화 창 열기
function renderVideoCallWindow() {
    if (!videoCallWindow) {
        openVideoCallWindow();
        trottledUpdate();
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
}

// 스크롤 이동 버튼 클릭 > 최하단
function moveBottonScroll() {
    requestAnimationFrame(() => {
        chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: "auto" });
    });
}

// 현재 스크롤 높이에 따른 스크롤 버튼 보여주기 유무
function handleChatScroll() {
    scrollHeight = chatContainer.scrollHeight;  // 전체 스크롤 높이
    scrollTop = chatContainer.scrollTop;        // 현재 스크롤 위치

    if (scrollHeight - scrollTop > 1400) {
        scrollButton.style.display = "block";
    } else {
        if (scrollButton) {
            scrollButton.style.display = "none";
        }
    }

    sendReadDataLastChat();
}



function initPage() {
    checkVerified();
    renderBottomScrollButton(); // 스크롤 버튼 렌더링
    getPeerLastReadChatId(); // 상대가 마지막으로 읽은 채팅 ID 조회

    // 웹 소켓 최초 연결
    if (typeof socket !== "undefined") {
        if (!socket.connected) {
            connectSocket();
        }
    } else {
        connectSocket();
    }

    // keydown 에서만 event.preventDefault() 가 적용된다 !!
    chatInput.removeEventListener('keydown', enterEvent);
    chatInput.addEventListener('keydown', enterEvent)
    // 모바일에서 키보드가 사라질 때의 이벤트
    chatInput.addEventListener('blur', () => {
        let attempt = 0;
        const maxAttempts = 20;

        const intervalId = setInterval(() => {
            moveBottonScroll();

            attempt++;
            if (attempt >= maxAttempts) {
                clearInterval(intervalId);
            }
        }, 50);
    });
    chatInput.focus();

    // 채팅 전송
    sendButton.removeEventListener('click', sendMessage);
    sendButton.addEventListener('click', sendMessage);

    // 영상통화 버튼
    videoCallBtn?.removeEventListener('click', renderVideoCallWindow)
    videoCallBtn?.addEventListener('click', renderVideoCallWindow)

    // 파일 업로드 기능
    fileInput.removeEventListener('change', uploadFile);
    fileInput.addEventListener('change', uploadFile);

    // 채팅창 스크롤 이벤트
    chatContainer.removeEventListener("scroll", handleChatScroll);
    chatContainer.addEventListener("scroll", handleChatScroll);

    // 최하단 스크롤 버튼
    scrollButton?.removeEventListener("click", moveBottonScroll);
    scrollButton?.addEventListener("click", moveBottonScroll);

    // 브라우저에게 "이 리스너는 preventDefault()를 호출할 수 있다"고 알려주는 옵션
    // passive: true     preventDefault() 안한다      (브라우저 최적화 OK)
    // passive: false    preventDefault() 쓸 수도 있음 (브라우저가 스크롤 최적화 안 함)
    // document.addEventListener('touchmove', blockTouchMoveEvent, {passive: false});

    // 웹 소켓 연결 > 유저 입장
    socket.emit("enter_room", { username: username, room: roomName });

    setTimeout(() => {
        // 채팅 데이터가 렌더링 된 이후 리스너 추가
        chatContainer.addEventListener("scroll", function () {
            if (Number(chatContainer.scrollTop) < 700 && !loading && chatContainer.scrollHeight > chatContainer.clientHeight) {
                loading = true;
                loadMoreChats();
            }
        });

        // 하단으로 스크롤링
        let attempt = 0;
        const maxAttempts = 10;

        const intervalId = setInterval(() => {
            moveBottonScroll();

            attempt++;
            if (attempt >= maxAttempts) {
                clearInterval(intervalId);
            }
        }, 20);
    }, 300)
}

document.addEventListener("DOMContentLoaded", initPage);
