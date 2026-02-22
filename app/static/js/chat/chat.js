

const chatContainer = document.getElementById("chat-container"),
    chatInput = document.getElementById("chat-input"),
    sendButton = document.getElementById('send-button'),
    textAreaOffsetHeight = 22,
    openDate = new Date(),
    fileInput = document.getElementById('file-input'),
    progressContainer = document.getElementById('progressContainer'),
    videoCallBtn = document.getElementById("videoCallBtn"),
    toggleNotificationBtn = document.getElementById("toggleNotification"),
    roomUserCount = document.getElementById('userCount'),
    typingIndicator = document.getElementById('typingIndicator');

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
    intervalId,
    dateDividerPreviousDate,
    isNotificationOn = true,
    isVerifiedPassword = false;

openDate.setHours(openDate.getHours() + 9);  // UTC → KST 변환
const openTimestamp = openDate.toISOString().slice(2, 19).replace(/[-T:]/g, "");
const debouncedUpdate = debounce(updateChatSession, 1000 * 10);
// const trottledUpdate = throttle(updateChatSession, 1000 * 10);
let controller = new AbortController();

////////////////////////////// Util Function ////////////////////////////

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

// 태그 내부 text만 replace
function replaceSpacesOutsideTags(html) {
    // 임시 컨테이너에 html 파싱
    const div = document.createElement('div');
    div.innerHTML = html;

    // 재귀적으로 text node만 &nbsp; 처리
    function traverse(node) {
        node.childNodes.forEach(child => {
            if (child.nodeType === Node.TEXT_NODE) {
                child.nodeValue = child.nodeValue.replace(/ /g, "\u00A0");
            } else if (child.nodeType === Node.ELEMENT_NODE) {
                traverse(child);
            }
        });
    }

    traverse(div);
    return div.innerHTML;
}

function isWithin1Min(openTimestamp, dataTimestamp) {
    const openDt = parseTimestamp(openTimestamp);
    const dataDt = parseTimestamp(dataTimestamp);
    const diff = (dataDt - openDt) / 1000; // ms → 초
    return isMobile && diff > 0 && diff <= 60;
}


/////////////////////////////// Web Socket /////////////////////////////

function connectSocket() {
    // socket = io("https://192.168.60.205:3000", {
    socket = io("https://chickchick.kr:3000", {
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

    socket.on("enter_user", function(data) {
        roomName = data.room;
        // addMessage(data);
    });

    socket.on("bye", function(data) {
        // console.log('현재 접속 중인 유저 목록:', userList);
        // addMessage(data); // '나갔습니다.' 문구
        const userCount = (Number(roomUserCount.textContent)-1 === 0) ? 1 : Number(roomUserCount.textContent)-1
        updateUserCount(userCount);

        // 떠났는데 남아 있는 경우 처리
        if (data.username !== username) {
            removeTypingBox();
        }
    });

    socket.on("new_msg", async function (data) {
        if (lastChatId < Number(data.chatId)) {
            await addMessage(data);
        }

        // 채팅 읽음 요청은 스크롤 이벤트에 일임한다 >> sendReadDataLastChat
        if (data.username !== username && isNotificationOn) {
            if (!isMobile) {
                sendNotification(data);
            } else {
                if (isWithin1Min(openTimestamp, data.timestamp)) {
                    sendNotification(data);
                }
            }

            // sendReadDataLastChat(); // 상대 메세지를 읽어야 하는데
            if (!isScrollAtTheBottom()) showDebugToast('새로운 메세지 도착');
        } else {
            // updateUserReadChatId(true); // 본인 메세지는 바로 읽도록 한다
        }
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

    socket.on("message_read_ack", async function (data) {
        // 임시 하드코딩
        /*if ((username === 'nh824' && data.username === 'fkaus14') || (username === 'fkaus14' && data.username === 'nh824')) {
            setCheckIconsGreenUpTo();
        }*/
        await getPeerLastReadChatId(); // 상대가 마지막으로 읽은 채팅 ID 조회
        setCheckIconsGreenUpTo();
    })

    socket.on("typing", (data) => {
        if ( data.username !== username ) {
            setTimeout(()=>{
                addTypingBox(typingIndicator);
                if (isScrollAtTheBottom() && !isTyping) {
                    moveBottonScroll();
                    isTyping = true;
                }
            }, 200);
        }
    });

    socket.on("stop_typing", (data) => {
        if (data.username !== username) {
            removeTypingBox();
        }
    });



    // 채팅방에 들어오고 나서 진행중인 영상통화 소켓 데이터 받음
    socket.on("find_video_call", (data) => {
        if (data.socketId && !data.userList.includes(username)) {
            videoCallBtn.style.backgroundColor = "green";
        }
    });

    // 채팅방에 들어와있는데 상대가 영상통화를 시작하면 채팅방으로 알림을 보낸다
    socket.on("video_call_ready", (data) => {
        videoCallRoomName = data.videoCallRoomName;
        if (username !== data.username) {
            videoCallBtn.style.backgroundColor = "green";
        }
    });

    socket.on("video_call_ended", (data) => {
        videoCallRoomName = null;
        // if (username !== data.username) {
        //     videoCallBtn.style.backgroundColor = "";
        // }
        videoCallBtn.style.backgroundColor = "";
    });
}


////////////////////////// Focus on Browser  ///////////////////////////

let m_intervalId = null;
let m_intervalId2 = null;
let m_intervalId3 = null;

function startPolling() {
    if (!m_intervalId) {
        m_intervalId = setInterval(() => {
            const now = new Date();
            now.setHours(now.getHours() + 9);
            const timestamp = now.toISOString().slice(2, 19).replace(/[-T:]/g, "");
            socket.emit("polling_chat_user", { username: username, room: roomName, timestamp: timestamp }) // 채팅방 참여자 요청
        }, 500);
    }
    if (!m_intervalId2) {
        setTimeout(()=>{
            m_intervalId2 = setInterval(() => {
                moveMinusOneToEnd(); // 채팅중을 가장 아래로 이동
            }, 50);
        }, 1000)
    }
    if (!m_intervalId3) {
        m_intervalId3 = setInterval(() => {
            getPeerLastReadChatId(); // 상대가 읽었는지 확인
            setCheckIconsGreenUpTo(); // 있었으면 읽음 표시
        }, 500);
    }
}
function stopPolling() {
    if (m_intervalId) {
        clearInterval(m_intervalId);
        m_intervalId = null;
    }
    if (m_intervalId2) {
        clearInterval(m_intervalId2);
        m_intervalId2 = null;
    }
    if (m_intervalId3) {
        clearInterval(m_intervalId3);
        m_intervalId3 = null;
    }
}


// 3. 관찰 시작
document.addEventListener('visibilitychange', async () => {
    removeTypingBox();
    await forceBlurInput();


    /**
     * document.visibilityState는 세밀한 제어가 가능하다
     * [document.visibilityState === "visible"] == [!document.hidden]
     */
    if (!document.hidden) { // 최초 실행 x, 다시 브라우저를 방문하면 한 번만 실행된다
        startPolling();
        chatInput.focus();

        const isValidSession = await checkVerified();
        if (!isValidSession) {
            console.log('return false');
            return false; // 세션 유효 시간이 끝났으면 요청 종료
        }
        await getPeerLastReadChatId(); // 상대가 마지막으로 읽은 채팅 ID 조회

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
                    /*const tempArr = []

                    data.logs.map(log => {
                        tempArr.push(log)
                    });*/

                    const tempArr = data.logs.map(log => log);

                    tempArr.forEach(log => {
                        const [chatId, timestamp, username, msg, chatRoomId] = log.toString().split("|");
                        chatObj = {
                            chatId: chatId.trim(),
                            timestamp: timestamp.trim(),
                            username: username.trim(),
                            msg: msg.replace('\n', '').trim(),
                            chatRoomId: chatRoomId.trim(),
                        }
                        if (lastChatId < Number(chatObj.chatId)) {
                            addMessage(chatObj);
                            setCheckIconsGreenUpTo();
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
        stopPolling();
        socket.emit("exit_room", { username: username, room: roomName });
        // 소켓을 끊어버리면 알림이 안온다..
        // if (typeof socket !== "undefined") socket.disconnect();
    }
});

function forceBlurInput() {
    const active = document.activeElement;
    if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')) {
        active.blur();
    }
}

////////////////////////// Chat State ////////////////////////////

// 상대가 마지막으로 읽은 chatId 조회
function getPeerLastReadChatId(option = null) {
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
            peerLastReadChatId = Number(data['last_read_chat_id']);
        })
        .then(() => {
            if (option === 'init') {
                loadMoreChats('init'); // 초기 채팅 데이터 조회
            }
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
            .then(response => {
                if (response.redirected) {
                    console.warn('리다이렉트')
                    window.location.href = response.url; // 302 응답 처리 - 미들웨어가 보내버린다면
                    return;
                }
                return response.json();
            })
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
    const threshold = 100; // 허용 오차 (픽셀)
    return chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight <= threshold;
}

function isScrollAtTheBottom2() {
    const threshold = 300; // 허용 오차 (픽셀)
    return chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight <= threshold;
}

const readDebounce = debounce(() => {
    socket.emit("message_read", { chatId: lastChatId, room: roomName, username: username });
    if (lastReadChatId !== lastChatId) {
        updateUserReadChatId(); // 스크롤이 아래일 때 상대가 채팅을 치기만 해도 계속 요청을 보낸다
        lastReadChatId = lastChatId;
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
    return axios.get("/auth/update-session-time")
        .then(resp => {
            if (resp.status === 200) {
                return resp.data["update_session_time"];
            }
        })
}

// 클라이언트가 세션을 체크, 존재하는지만 판단.. 서버에서도 체크하므로 결과만 확인한다
async function checkVerified() {
    let funcResult = false;
    try {
        const response = await fetch("/auth/check-verified", {
            method: "GET",
            headers: { "Content-Type": "application/json" }
        });

        if (response.status === 200) {
            const result = await response.json();
            if (result && result['success']) {
                isVerifiedPassword = true;
                funcResult = true;
            } else {
                isVerifiedPassword = false;
            }
        }
    } catch (e) {
        // console.error("❌ 서버 오류", e);
        isVerifiedPassword = false;
    } finally {
        return funcResult;
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
            /*setTimeout(() => {
                updateUserReadChatId();
            }, 300);*/
            if (event === 'init') {
                // 채팅 데이터 로드 후 최하단으로 채팅창 스크롤링
                moveBottonScroll();
                socket.emit("message_read", {chatId: lastChatId, room: roomName, username: username });
            }
        })
        .finally(() => {
            loading = false;

            // 감시 대상 등록, MutationObserver로 dom추가를 감시하지 않을 경우 매번 element를 감시 대상에 추가하면 된다.
            /*document.querySelectorAll('img[data-src]').forEach(img => {
                console.log('img', img)
                observer.observe(img);
            });*/
        });
}

// 메시지를 웹소켓에 전송 후 채팅 입력창 정리
function sendMessage() {
    const msg = chatInput.value.replace(/\n/g, "<br>").replace(/(<br>\s*)$/, "");  // 마지막 모든 <br> 제거
    if (msg !== "") {
        socket.emit("new_msg", { username, msg, room: roomName });
        socket.emit("stop_typing", {room: roomName, username: username });
    }
    // chatInput.blur();  // IME 조합을 강제로 끊기 위해 포커스 제거
    chatInput.value = "";
    chatInput.style.height = textAreaOffsetHeight + "px";
    chatInput.focus();
    // chatInput.setSelectionRange(0, 0);  // 커서 위치 맨 앞으로 다시 지정,  iOS Safari에서 포커스 후 스크롤 위치 이상 현상을 유발할 수도
    localStorage.setItem("#tempChat-250706", '');
    updateChatSession();  // 채팅 세션 갱신
}

// url 미리보기 카드 렌더링
function renderPreviewCard(data) {
    const copyLinkPreview = document.querySelector('.link-preview').cloneNode(true);
    copyLinkPreview.style.display = '';
    copyLinkPreview.querySelector('a').href = data.origin_url;
    copyLinkPreview.querySelector('a').classList.add('bg-white');
    copyLinkPreview.querySelector('img').src = data.thumbnail_url;
    // copyLinkPreview.querySelector('.message').textContent = data.origin_url;
    copyLinkPreview.querySelector('.message').innerHTML  = data.msg;
    copyLinkPreview.querySelector('.preview-title').textContent = data.title;
    // copyLinkPreview.querySelector('.preview-description').textContent = data.description;
    copyLinkPreview.querySelector('.preview-url').textContent = extractDomain(data.origin_url);
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

    const messageRow = renderMessageRow(isMine, Number(data.chatId));
    const messageDiv = renderMessageDiv();

    if (isMine) {
        // messageDiv.classList.add("bg-blue-200", "text-left");
        messageDiv.classList.add("text-left");
        // messageDiv.style.backgroundColor = '#fef01b'; // 노란색
        messageDiv.style.backgroundColor = '#fbe843'; // 옅은 노란색
    } else {
        if (data.underline !== 1 && openTimestamp < data.timestamp && isWithin1Min(openTimestamp, data.timestamp) && isNotificationOn) {
            vibrate();
        }
        // messageDiv.classList.add("bg-gray-200", "text-left");
        messageDiv.classList.add("text-left");
        messageDiv.style.backgroundColor = '#ffffff'; // 흰색 (카톡 기본테마)
        messageDiv.style.backgroundColor = '#303030'; // 어두운 회색 (카톡 다크모드)
        messageDiv.style.color = 'lightgray'; // 글자색 (카톡 다크모드)
    }

    // 스켈레톤 이미지 박스
    function imageRenderer() {
        // 이미지 첨부
        const img = document.createElement('img');
        // img.src = data.msg;
        img.src = '/static/no-image.png';
        img.dataset.src = data.msg; // preloadImage()가 지연 로딩 (태그가 뷰박스에 들어오면)
        img.alt = 'Image Url';
        img.style.width = '100%';
        img.style.height = 'auto'; // 비율 유지 (이미지가 찌그러지지 않게)
        img.onerror = () => {
            img.onerror = null;
            img.src = '/static/no-image.png';
            img.style.width = '200px';
        };
        messageDiv.appendChild(img);
        messageDiv.classList.remove('p-2');
        messageDiv.classList.add('border');
    }

    if (data.underline) { // 출입 알림
        if (!isMine) {
            renderEnterOrExit(data.msg);
        }
    } else { // 메세지 생성
        /* 경로/쿼리 포함 문자열에서 파일명과 확장자 추출 (…/파일명.확장자 형태를 찾아 파일명과 확장자를 뽑아내는 정규식)
           (?:^|\/) : 문자열 시작이거나 바로 앞이 슬래시여야 함. (경로의 “파일명”만 잡기 위한 경계)
           ([^\/?#]+) : 슬래시(/), ?, #를 제외한 문자 1자 이상 → **파일명(확장자 제외)**를 그룹1로 캡처
           (?=$|[?#&]) : 바로 뒤가 문자열 끝이거나 ?, #여야 함 → ?query=…나 #hash 앞까지만 매칭, 대소문자 무시 i */
        const imageExtRegex = /(?:^|\/)([^\/?#]+)\.(jpg|jpeg|png|gif|bmp|webp|tiff|jfif)(?=$|[?#&])/i;

        function isImagePathUrl(text) {
            if (!text) return;
            const s = String(text).trim();
             return s.match(imageExtRegex);
        }

        if (data.msg.trim().startsWith('https://chickchick.kr/image/images')) {
            imageRenderer();
        } else if (data.msg.trim().startsWith('https://chickchick.kr/video/temp-video/')) {
            // 비디오 첨부
            const video = document.createElement('video');
            video.classList.add('thumbnail');
            video.controls = true;
            // video.style.height = '500px';
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
        } else if (data.msg.trim().startsWith('https://chickchick.kr/file/files')) {
            // 파일 첨부
            const link = document.createElement('a');
            link.href = data.msg;
            link.innerText = getFilenameFromUrl(data.msg);
            link.target = '_blank';
            link.style.color = 'blue';
            messageDiv.innerHTML = '';
            messageDiv.appendChild(link);
        } else if (isImagePathUrl(data.msg.trim())) {
            imageRenderer();
        } else {
            const messageSpan = document.createElement("span");
            // const safeText = data.msg.replace(/ /g, "&nbsp;");
            const safeText = replaceSpacesOutsideTags(data.msg);
            messageSpan.innerHTML = safeText;
            messageDiv.appendChild(messageSpan);

            const urlRegex = /(https?:\/\/[^\s]+)/g;
            const matches = data.msg.match(urlRegex);

            if (matches) {
                fetch('/func/api/url-preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: matches[0], chat_id:data.chatId })
                })
                    .then(res => res.json())
                    .then(preview => {
                        if (preview) {
                            preview.msg = data.msg;
                            const previewEl = renderPreviewCard(preview);
                            messageDiv.innerHTML = '';
                            messageDiv.appendChild(previewEl);
                            messageDiv.classList.remove('p-2');
                            if (isScrollAtTheBottom2()) {
                                moveBottonScroll();
                            }
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
            if (peerLastReadChatId && peerLastReadChatId >= Number(data.chatId)) {
                checkIcon.style.setProperty("color", "green", "important");
            } else { // 읽지 않은 채팅만 아이콘 추가
                messageRow.appendChild(checkIcon);
            }
            messageRow.appendChild(messageDiv);
        } else {
            messageRow.appendChild(messageDiv);
            messageRow.appendChild(renderTimeDiv(timeStr));
        }
    }

    if (lastChatId < Number(data.chatId)) {
        lastChatId = Number(data.chatId);
    }
}

function addTypingBox(typingIndicator) {
    // typingIndicator.style.display = 'block';

    const messageRow = renderMessageRow(false, -1);
    const messageDiv = renderMessageDiv();
    // messageDiv.classList.add("bg-gray-200", "text-left");
    messageDiv.classList.add("text-left");
    messageDiv.style.backgroundColor = '#303030'; // 어두운 회색 (카톡 다크모드)

    const cloneTypingIndicator = typingIndicator.cloneNode(true);
    cloneTypingIndicator.style.display = '';
    cloneTypingIndicator.style.padding = '7px';
    messageDiv.appendChild(cloneTypingIndicator);

    const typingBox = document.querySelectorAll('.messageRow[data-chat-id="-1"]');
    if (typingBox.length === 0) {
        chatContainer.appendChild(messageRow);
    }
    if (isScrollAtTheBottom()) {
        moveBottonScroll();
    }

    messageRow.appendChild(messageDiv);
}

function removeTypingBox() {
    // typingIndicator.style.display = 'none';
    document.querySelector('.messageRow[data-chat-id="-1"]')?.remove();
    isTyping = false;
}


// 바깥 컨테이너: 메시지 한 줄을 구성
function renderMessageRow(isMine, chatId) {
    const messageRow = document.createElement("div");
    messageRow.style.display = "flex";
    messageRow.style.alignItems = "flex-end";
    messageRow.style.marginBottom = "2px";
    messageRow.style.maxWidth = "100%";
    messageRow.style.justifyContent = isMine ? "flex-end" : "flex-start";
    messageRow.classList.add('messageRow')
    messageRow.dataset.chatId = chatId;
    return messageRow;
}

// 메시지 박스
function renderMessageDiv() {
    const messageDiv = document.createElement("div");
    // - rounded-md → 0.375rem
    // - rounded-lg → 0.5rem
    // - rounded-xl → 0.75rem
    // - rounded-2xl → 1rem
    // - rounded-3xl → 1.5rem
    // - rounded-full → 완전한 원형
    messageDiv.classList.add(
        "px-[0.7rem]",
        "py-[0.4rem]",
        "rounded-xl",
        "max-w-[82%]",     // 최대 너비 82%
        "w-fit",
        "block",           // 내용에 맞게 크기 조정
        "break-words",     // 긴 단어가 자동으로 줄바꿈되도록 설정
        "messageDiv",
        "overflow-hidden", // 내부 이미지를 div의 border-radius 내부로 들어가도록
        "border-gray-500", // 어두운 회색 border색
        "font-[400]",      // 폰트 크기
        "leading-[1.3]",   // 줄 간 거리
        "flex",
        "items-center",    // 세로 가운데
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

function formatDateWithKoreanDay(dateStr) {
    const [year, month, day] = dateStr.split('.').map(s => s.trim()).map(Number);
    const date = new Date(year, month - 1, day);
    const weekKor = ['일요일', '월요일', '화요일', '수요일', '목요일', '금요일', '토요일'];
    const dayOfWeek = weekKor[date.getDay()];
    return `${dateStr} ${dayOfWeek}`;
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
        const divider = createDateDivider(formatDateWithKoreanDay(chatState.previousDate));
        chatContainer.prepend(divider);
        dateDividerPreviousDate = dateStr;
        chatState.previousDate = dateStr;
        dateDividerObserver.observe(divider);
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
    roomUserCount.textContent = number < 0 ? 1 : number;
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

// 이미지 스켈레톤 > 본 이미지 체인지
function preloadImage(img) {
    const src = img.getAttribute('data-src');
    if (src && img.src !== src) {
        img.src = src;
        img.removeAttribute('data-src');
    }
}

// 옵저버 정의
/**
 * IntersectionObserver
 * 브라우저에서 어떤 요소가 뷰포트(화면) 안에 들어왔는지 자동으로 감지하는 API
 * >> 스크롤을 감지해서 이미지 로딩, 애니메이션 트리거, 광고 노출 등을 실행
 *
 * observe(element); 관찰 대상 등록
 * unobserve(element); 관찰 대상 해제
 * disconnect(); 모든 관찰 중단
 */
const observer = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) { // 화면에 나타났을 때
            if (isVerifiedPassword) {
                preloadImage(entry.target);
                observer.unobserve(entry.target); // 한 번만 로드, 관찰 해제
            }
        }
    });
}, {
    root: null,        // 뷰포트 기준 (null 이면 window)
    // rootMargin: "0px", // 감지 범위 조절
    // rootMargin: "top right bottom left",
    rootMargin: "2000px 0px",     // 위/아래 200px, 좌/우 0px 미리 감지
    // threshold: 0.05     // 5%만 보이면 isIntersecting = true
    threshold: 0                 // 1픽셀만 보여도 감지
});

// DOM 추적 > 콜백 함수 실행
const mutationObserver = new MutationObserver(mutations => {
    mutations.forEach(mutation => {
        mutation.addedNodes.forEach(node => {
            if (node.nodeType === 1 && node.matches?.('img[data-src]')) {
                observer.observe(node);
            }
            // 자식 내부에 img[data-src]가 있는 경우
            if (node.nodeType === 1) {
                node.querySelectorAll?.('img[data-src]')?.forEach(img => observer.observe(img));
            }
        });
    });
});

// 관찰 범위
/**
 * childList        자식 노드가 추가/삭제되면 감지
 * attributes	    속성 변경 감지 (class, src, data-*, 등)
 * subtree	        하위 모든 자식 노드까지 감시
 * characterData	텍스트 노드 내용 변경 감지
 *
 */
mutationObserver.observe(document.body, {
    childList: true,
    subtree: true
});

const dateDividerObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
        if (entry.isIntersecting && !isScrollAtTheBottom()) { // 뷰포트에 나타났을 때
            showDebugToast(formatDateWithKoreanDay(dateDividerPreviousDate));
            observer.unobserve(entry.target); // 한 번만 실행하려면 옵저버 해제
        }
    });
}, {
    threshold: 0.1 // 10%만 보여도 감지 (필요에 따라 0~1 조정)
});


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
    // checkIcon.style.background = "#ddd"; // 밝은 회색 배경
    checkIcon.style.background = "#9bbbd4"; // 어두운 하늘색
    checkIcon.style.background = "#303030"; // 어두운 회색 (카톡 다크모드)
    checkIcon.style.borderRadius = "4px";
    checkIcon.style.fontWeight = "bold";

    return checkIcon;
}

// 파라미터 보다 낮은 채팅 ID들 모두 읽음 표시 전환
function setCheckIconsGreenUpTo() {
    const rows = document.querySelectorAll('.messageRow[data-chat-id]');
    rows.forEach(row => {
        const rowChatId = parseInt(row.dataset.chatId, 10);
        if (!isNaN(rowChatId) && rowChatId <= peerLastReadChatId) {
            const checkIcon = row.querySelector('.checkIcon');
            if (checkIcon) {
                checkIcon.style.setProperty("color", "green", "important");
                checkIcon.remove();
            }
        }
    });
}


///////////////////////////// Event Listener //////////////////////////////

// 채팅 입력 이벤트 함수
function enterEvent(event) {
    // debouncedUpdate();

    if (event.key === 'Enter') {
        if (event.shiftKey) {
            return; // 줄바꿈만 하고 종료
        }
        if (!isMobile) {
            event.preventDefault(); // 기본 Enter 줄바꿈 방지
            // sendMessage();
            sendButton.click();
        }
        localStorage.setItem("#tempChat-250706", '');
    } else {
        setTimeout(() => {
            if (chatInput.value.trim().length > 0) {
                socket.emit("typing", { room: roomName, username: username }); // 입력 중임을 알림
            }
            if (chatInput.value.trim().length === 0) {
                socket.emit("stop_typing", { room: roomName, username: username });
            }
        }, 100)

        clearTimeout(typingTimeout);
        typingTimeout = setTimeout(() => {
            socket.emit("stop_typing", { room: roomName, username: username }); // 일정 시간 입력 없으면 중단 알림
        }, 3000); // 3초간 입력 없으면 stop_typing

        localStorage.setItem("#tempChat-250706", chatInput.value);
    }
}

function renewChatSession() {
    let tempInterval = setInterval(() => {
        if (videoCallWindow) {
            updateChatSession();
        } else {
            clearInterval(tempInterval);
        }
    }, 1000 * 60)
}

// 영상통화 창 열기
function renderVideoCallWindow() {
    if (!videoCallWindow) {
        openVideoCallWindow();
        // trottledUpdate();
        renewChatSession();
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

// 알림 토글 버튼
function toggleNotification() {
    const i = toggleNotificationBtn.querySelector('i');
    if (i.classList.contains('fa-bell-slash')) {
        i.classList.replace('fa-bell-slash', 'fa-bell');
    } else {
        i.classList.replace('fa-bell', 'fa-bell-slash');
    }
    isNotificationOn = !isNotificationOn;
}

// 스크롤 이동 버튼 클릭 > 최하단
function moveBottonScroll() {
    requestAnimationFrame(() => {
        chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: "auto" });
    });
}

// 현재 스크롤 높이에 따른 스크롤 버튼 보여주기 유무
function handleChatScroll() {
    clearInterval(intervalId);
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

// 채팅중 ... 을 제일 아래로 이동시킨다; appendChild로 재할당 (이동)
function moveMinusOneToEnd() {
    const chatContainer = document.getElementById('chat-container');
    if (!chatContainer) return;

    // 모든 messageRow 중에서 data-chat-id="-1" 인 요소 찾기
    const rows = chatContainer.querySelectorAll('.messageRow');
    let minusOneRow = null;

    rows.forEach(row => {
        if (row.dataset.chatId === "-1") {
            minusOneRow = row;
        }
    });

    if (!minusOneRow) return; // 해당 요소 없음

    // 이미 마지막이면 아무 것도 안 함
    if (minusOneRow !== chatContainer.lastElementChild) {
        chatContainer.appendChild(minusOneRow);
    }
}


async function initPage() {
    const isValidSession = await checkVerified();
    if (!isValidSession) {
        console.log('return false');
        return false; // 세션 유효 시간이 끝났으면 요청 종료
    }
    renderBottomScrollButton(); // 스크롤 버튼 렌더링
    getPeerLastReadChatId('init'); // 상대가 마지막으로 읽은 채팅 ID 조회

    // 웹 소켓 최초 연결
    if (typeof socket !== "undefined") {
        if (!socket.connected) {
            connectSocket();
        }
    } else {
        connectSocket();
    }

    // keydown 에서만 event.preventDefault() 가 적용된다 !!
    chatInput.removeEventListener('keyup', enterEvent);
    chatInput.addEventListener('keyup', enterEvent)
    // 모바일에서 키보드가 사라질 때의 이벤트
    /*chatInput.addEventListener('blur', () => {
        let attempt = 0;
        const maxAttempts = 20;

        const intervalId = setInterval(() => {
            moveBottonScroll();

            attempt++;
            if (attempt >= maxAttempts) {
                clearInterval(intervalId);
            }
        }, 50);
    });*/

    // 채팅 전송
    sendButton.removeEventListener('click', sendMessage);
    sendButton.addEventListener('click', sendMessage);

    // 영상통화 버튼
    videoCallBtn?.removeEventListener('click', renderVideoCallWindow)
    videoCallBtn?.addEventListener('click', renderVideoCallWindow)

    // 알림 on/off
    toggleNotificationBtn?.removeEventListener('click', toggleNotification)
    toggleNotificationBtn?.addEventListener('click', toggleNotification)

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
    socket.emit("enter_room", {username: username, room: roomName});

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

        intervalId = setInterval(() => {
            moveBottonScroll();

            attempt++;
            if (attempt >= maxAttempts) {
                clearInterval(intervalId);
            }
        }, 30);
    }, 250)

    m_intervalId2 = setInterval(() => {
        moveMinusOneToEnd(); // 채팅중을 가장 아래로 이동
    }, 50);

    m_intervalId3 = setInterval(() => {
        getPeerLastReadChatId(); // 상대가 읽었는지 확인
        setCheckIconsGreenUpTo(); // 있었으면 읽음 표시
    }, 500);

    m_intervalId = setInterval(() => {
        const now = new Date();
        now.setHours(now.getHours() + 9);
        const timestamp = now.toISOString().slice(2, 19).replace(/[-T:]/g, "");
        socket.emit("polling_chat_user", { username: username, room: roomName, timestamp: timestamp }) // 채팅방 참여자 요청
    }, 500);

    chatInput.textContent = localStorage.getItem("#tempChat-250706");

    chatInput.focus();
    chatInput.setSelectionRange(chatInput.value.length, chatInput.value.length);
}

document.addEventListener("DOMContentLoaded", initPage);
