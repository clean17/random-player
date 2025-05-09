

const chatContainer = document.getElementById("chat-container"),
    chatInput = document.getElementById("chat-input"),
    sendButton = document.getElementById('send-button'),
    textAreaOffsetHeight = 22,
    openDate = new Date(),
    fileInput = document.getElementById('file-input'),
    progressContainer = document.getElementById('progressContainer'),
    videoCallBtn = document.getElementById("videoCallBtn");

let offset = 0, // 가장 최근 10개는 이미 로드됨
    socket,
    roomName = 'chat-room',
    isMine,
    isUnderline,
    isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent),
    loading = false,
    chatState = { previousDate: null, latestDate: null },
    scrollHeight, // 전체 스크롤 높이
    scrollTop,    // 현재 스크롤 위치
    isMinimized = false,
    lastChatId = 0,
    submitted = false,
    videoCallRoomName = null,
    typingTimeout,
    peerLastReadChatId,
    scrollButton = undefined;

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
        // 채팅방 입장 시 서버에 로그인된 유저 정보 전달
        // socket.emit("user_info", { username: username, room: roomName });
    });

    socket.on("reconnect", () => {
        alert("🔄 소켓 재연결됨");
        // socket.emit("user_info", { username: username, room: roomName });
    });

    socket.on("new_msg", function(data) {
        addMessage(data);
        sendNotification(data);
        sendDataReadLastChat();
    });

    socket.on("message_read_ack", function (data) {
        setCheckIconsGreenUpTo(data.chatId)
    })

    socket.on("bye", function(data) {
        addMessage(data);
    });

    socket.on("enter_user", function(data) {
        roomName = data.room;
        addMessage(data);
    });

    socket.on('room_user_list', (userList) => {
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

    socket.on('find_video_call', (data) => {
        if (data.socketId && !data.userList.includes(username)) {
            videoCallBtn.style.backgroundColor = "green";
        }
    });

    socket.on('video_call_ready', (data) => {
        videoCallRoomName = data.videoCallRoomName;
        if (username !== data.username) {
            videoCallBtn.style.backgroundColor = "green";
        }
    });

    socket.on('video_call_ended', (data) => {
        videoCallRoomName = null;
        if (username !== data.username) {
            videoCallBtn.style.backgroundColor = "";
        }
    });

    socket.on("typing", () => {
        document.getElementById('typingIndicator').style.display = 'block';
        // const messageRow = renderMessageRow(false);
        // const messageDiv = renderMessageDiv();
        // messageRow.appendChild(messageDiv);
        // chatContainer.appendChild(messageRow);
        /*if (scrollHeight - scrollTop < 1300) {
            setTimeout(() => {
                moveBottonScroll();
            }, 500)
        }*/
    });

    socket.on("stop_typing", () => {
        document.getElementById('typingIndicator').style.display = 'none';
    });
}


////////////////////////// Focus on Browser  ///////////////////////////
document.addEventListener('visibilitychange', () => {
    if (!document.hidden) { // 최초 실행 x, 다시 브라우저를 방문하면 실행된다
        socket.emit("enter_room", { username: username, room: roomName });
        if (typeof socket !== "undefined") {
            if (!socket.connected) {
                // alert("🔄 소켓 재연결 시도");
                setTimeout(() => {
                    if (!socket.connected) {
                        console.log('⚠️ 소켓 연결 끊김')
                        connectSocket();
                    }
                }, 400)
            }
        } else {
            alert("⚠️ socket 객체가 정의되지 않음");
            connectSocket();
        }
        chatInput.focus();

        /*fetch("/func/chat", { method: "GET" })
            .then(res => {
                if (res.redirected) {
                    window.location.href = res.url;
                }
            })
            .catch(err => {
                console.error("요청 실패:", err);
            });*/

        // fetch("/func/chat/load-more-chat", {
        //     method: "POST",
        //     headers: { "Content-Type": "application/json" },
        //     body: JSON.stringify({ offset: 0 })
        // })
        //     .then(res => {
        //         if (res.redirected) {
        //             window.location.href = res.url;
        //         } else {
        //             return res.json();
        //         }
        //     })
        //     .then(data => {
        //         if (data.logs.length > 0) {
        //             const tempArr = []
        //             let isFisrtMsg = false;
        //
        //             if (data.logs.length !== MAX_FETCH_MESSAGE_SIZE) isFisrtMsg = true;
        //
        //             data.logs.map(log => {
        //                 tempArr.push(log)
        //             });
        //
        //             tempArr.forEach(log => {
        //                 const [chatId, timestamp, username, msg] = log.toString().split("|");
        //                 chatObj = {chatId: chatId.trim(), timestamp: timestamp.trim(), username: username.trim(), msg: msg.replace('\n', '').trim() }
        //                 if (Number(lastChatId) < Number(chatObj.chatId)) {
        //                     // addMessage(chatObj);
        //                 }
        //             });
        //
        //             if (isFisrtMsg) {
        //                 // renderDateDivider(dateStr)
        //             }
        //         }
        //     })
        //     .finally(() => {
        //         loading = false;
        //     });

        sendDataReadLastChat(); // 스크롤이 최하단이면 상대에게 읽었다고 보낸다
        updateUserReadChatId(); // 마지막으로 읽은 chatId 수정 요청
    } else {
        socket.emit("exit_room", { username: username, room: roomName });
        // if (typeof socket !== "undefined") socket.disconnect();
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
            console.log('peerLastReadChatId', peerLastReadChatId)
        });
}

// 본인이 읽은 마지막 chatId 변경 요청
function updateUserReadChatId() {
    console.log('updateUserReadChatId', username,  lastChatId)
    // chatContainer 스크롤이 최하단일 경우에만 실행
    if (chatContainer.scrollTop + chatContainer.clientHeight >= chatContainer.scrollHeight - 1) {
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

// 스크롤이 최하단일 경우 읽음 표시를 보내는 함수
function sendDataReadLastChat() {
    const lastMessageRow = document.querySelector(`.messageRow[data-chat-id="${lastChatId}"]`);
    const rect = lastMessageRow.getBoundingClientRect();
    const inView = rect.top >= 0 && rect.bottom <= window.innerHeight;

    if (inView) {
        socket.emit("message_read", { chatId: lastChatId, room: roomName });
    }
}

// 채팅 세션 갱신 (10분 한정)
function updateChatSession() {
    fetch("/auth/update-session-time").then(data => {
    })
}


//////////////////////////////// Render Chat ////////////////////////////////

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
                    const [chatId, timestamp, username, msg] = log.toString().split("|");
                    chatObj = {chatId: chatId.trim(), timestamp: timestamp.trim(), username: username.trim(), msg: msg.replace('\n', '').trim() }
                    addMessage(chatObj, true)
                    if (event === "wheel") {
                        chatContainer.scrollTop = chatContainer.scrollHeight - prevScrollHeight + prevScrollTop;
                    }
                });

                if (isFisrtMsg) {
                    // renderDateDivider(dateStr)
                }
            }
        }).then(() => {
            updateUserReadChatId();
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
        socket.emit("stop_typing", {room: roomName});
    }
    // chatInput.blur();  // IME 조합을 강제로 끊기 위해 포커스 제거
    chatInput.value = "";
    chatInput.style.height = textAreaOffsetHeight + "px";
    // requestAnimationFrame(() => {
    //     chatInput.focus();  // ⏱️ 다음 프레임에서 포커스, IME 안정
    // });
    chatInput.focus();
    chatInput.setSelectionRange(0, 0);  // 커서 위치 다시 지정
}

// 메세지 추가
function addMessage(data, load = false) {
    isMine = data.username === username;
    isUnderline = data.underline;
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
        if (data.msg.trim().startsWith('https://chickchick.shop/image/images/')) {
            const fileUrl = '';

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

            /*if (fileUrl.match(/\.(jpeg|jpg|png|gif|webp)$/i)) {
                // 이미지 파일
                const img = document.createElement('img');
                img.src = fileUrl;
                img.className = 'w-40 h-40 object-cover rounded'; // Tailwind 예시
                img.alt = 'Uploaded Image';
                messageDiv.appendChild(img);
            } else if (fileUrl.match(/\.(mp4|webm|ogg)$/i)) {
                // 비디오 파일
                const video = document.createElement('video');
                video.src = fileUrl;
                video.controls = true;
                video.className = 'w-60 h-40 rounded';
                messageDiv.appendChild(video);
            } else {
                // 기타 파일
                const link = document.createElement('a');
                link.href = fileUrl;
                link.innerText = '파일 보기';
                link.target = '_blank';
                messageDiv.appendChild(link);
            }*/
        } else {
            const messageSpan = document.createElement("span");
            const safeText = data.msg.replace(/ /g, "&nbsp;");
            messageSpan.innerHTML = safeText;
            messageDiv.appendChild(messageSpan);
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
            if (scrollHeight - scrollTop < 1300) {
                setTimeout(() => {
                    moveBottonScroll();
                }, 50)
            }
        }

        // 정렬 순서: 시간 → 메시지 또는 메시지 → 시간
        if (isMine) {
            messageRow.appendChild(renderTimeDiv(timeStr));
            const checkIcon = renderCheckIcon();
            if (peerLastReadChatId >= data.chatId) {
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
    if (scrollHeight - scrollTop < 1300) {
        setTimeout(() => {
            moveBottonScroll();
        }, 50)
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
    const countEl = document.getElementById('userCount');
    countEl.textContent = number;
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

                files.forEach(file => {
                    const url = "https://chickchick.shop/image/images/?filename="+file+"&dir=temp&selected_dir=chat";
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
                socket.emit("typing", {room: roomName}); // 입력 중임을 알림
            }
            if (chatInput.value.trim().length === 0) {
                socket.emit("stop_typing", {room: roomName});
            }
        }, 10)

        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            socket.emit("stop_typing", {room: roomName}); // 일정 시간 입력 없으면 중단 알림
        }, 2000); // 2초간 입력 없으면 stop_typing
    }
}

// 위로 스크롤할 때 추가 데이터 불러오기 (무한 스크롤)
function loadPreviosChats () {
    debounce(() => {
        if (Number(chatContainer.scrollTop) < 700 && !loading) {
            loadMoreChats("wheel");
        }
    }, 100);
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

// touchmove 강제 차단
function blockTouchMoveEvent (e) {
    /*const isChatContainer = e.target.closest('#chat-container');
    if (!isChatContainer) {
        e.preventDefault();  // ❌ chat-container 아닌 경우만 터치 이동 막기
    }*/
    const isTextArea = e.target.closest('textarea');
    const isScrollableContainer = e.target.closest('#chat-container');

    if (isTextArea || isScrollableContainer) {
        return; // ✅ 내부 스크롤 가능한 요소는 막지 않음
    }

    e.preventDefault(); // ❌ 외부 영역에서만 터치 이동 막기
}

// 스크롤 이동 버튼 클릭 > 최하단
function moveBottonScroll() {
    // const scrollHeight = chatContainer.scrollHeight;  // 전체 스크롤 높이
    // const scrollTop = chatContainer.scrollTop;        // 현재 스크롤 위치

    // scrollHeight = chatContainer.scrollHeight;  // 전체 스크롤 높이
    // scrollTop = chatContainer.scrollTop;        // 현재 스크롤 위치

    // console.log(scrollHeight, scrollTop)
    // console.log('moveBottonScroll', scrollHeight - scrollTop);
    chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: "auto" });
}

// 현재 스크롤 높이에 따른 스크롤 버튼 보여주기 유무
function checkHideOrShowScrollButton() {
    scrollHeight = chatContainer.scrollHeight;  // 전체 스크롤 높이
    scrollTop = chatContainer.scrollTop;        // 현재 스크롤 위치

    if (scrollHeight - scrollTop > 1400) {
        scrollButton.style.display = "block";
    } else {
        if (scrollButton) {
            scrollButton.style.display = "none";
        }
    }

    sendDataReadLastChat();
}




function initPage() {
    // 웹 소켓 최초 연결
    if (typeof socket !== "undefined") {
        if (!socket.connected) {
            connectSocket();
        }
    } else {
        connectSocket();
    }

    // 웹 소켓 연결 > 유저 입장
    socket.emit("enter_room", { username: username, room: roomName });

    // 상호작용 시 알림 권한 허용
    document.body.removeEventListener('touchstart', requestNotificationPermission);
    document.body.addEventListener('touchstart', requestNotificationPermission);
    document.body.removeEventListener('ended', requestNotificationPermission);
    document.body.addEventListener('ended', requestNotificationPermission);
    document.body.removeEventListener('touchmove', requestNotificationPermission);
    document.body.addEventListener('touchmove', requestNotificationPermission);
    document.body.removeEventListener('click', requestNotificationPermission);
    document.body.addEventListener('click', requestNotificationPermission);

    renderBottomScrollButton(); // 스크롤 버튼 렌더링
    getPeerLastReadChatId(); // 상대가 마지막으로 읽은 채팅 ID 조회
    loadMoreChats(); // 초기 채팅 데이터 조회

    // keydown 에서만 event.preventDefault() 가 적용된다 !!
    chatInput.removeEventListener('keydown', enterEvent);
    chatInput.addEventListener('keydown', enterEvent)
    // 모바일에서 키보드가 사라질 때의 이벤트
    chatInput.addEventListener('blur', () => {
        setTimeout(() => {
            window.scrollTo(0, 0);  // 키보드 내려간 후에도 복구
        }, 100);
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
    chatContainer.removeEventListener("wheel", loadPreviosChats);
    chatContainer.addEventListener("wheel", loadPreviosChats);
    chatContainer.removeEventListener("scroll", checkHideOrShowScrollButton);
    chatContainer.addEventListener("scroll", checkHideOrShowScrollButton);

    // 최하단 스크롤 버튼
    scrollButton?.removeEventListener("click", moveBottonScroll);
    scrollButton?.addEventListener("click", moveBottonScroll);

    // 브라우저에게 "이 리스너는 preventDefault()를 호출할 수 있다"고 알려주는 옵션
    // passive: true     preventDefault() 안한다      (브라우저 최적화 OK)
    // passive: false    preventDefault() 쓸 수도 있음 (브라우저가 스크롤 최적화 안 함)
    document.addEventListener('touchmove', blockTouchMoveEvent, { passive: false });

    setTimeout(() => {
        // 채팅 데이터 로드 후 최하단으로 채팅창 스크롤링
        moveBottonScroll();

        // 채팅 데이터가 렌더링 된 이후 리스너 추가
        chatContainer.addEventListener("scroll", function () {
            if (Number(chatContainer.scrollTop) < 700 && !loading) {
                loadMoreChats();
            }
        });

        socket.emit("message_read", { chatId: lastChatId, room: roomName });
    }, 200)
}

document.addEventListener("DOMContentLoaded", initPage);
