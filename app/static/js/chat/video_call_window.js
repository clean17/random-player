let videoCallWindow = null,
    isDragging = false,
    offsetX = 0,
    offsetY = 0,
    windowFullSizeOn = true;

////////////////////////// Video Call //////////////////////////////

function openVideoCallWindow() {
    if (!videoCallWindow) {
        videoCallWindow = document.createElement("div");
        videoCallWindow.style.position = "fixed";
        videoCallWindow.style.top = "15px";
        videoCallWindow.style.left = "15px";
        videoCallWindow.style.width = "380px";
        videoCallWindow.style.height = "530px";
        videoCallWindow.style.maxWidth = "100vw";
        videoCallWindow.style.maxHeight = "100vh";
        videoCallWindow.style.minWidth = "200px";
        videoCallWindow.style.minHeight = "300px";
        videoCallWindow.style.background = "#000";
        videoCallWindow.style.border = "2px solid #ccc";
        videoCallWindow.style.zIndex = "10";
        videoCallWindow.style.flexDirection = "column";
        videoCallWindow.style.boxShadow = "0 0 10px rgba(0,0,0,0.5)";
        videoCallWindow.style.resize = "both";
        videoCallWindow.style.overflow = "auto";
        videoCallWindow.style.display = "flex";
    }

    const topBar = document.createElement("div");
    topBar.style.display = "flex";
    topBar.style.justifyContent = "space-between";
    topBar.style.background = "#222";
    topBar.style.color = "#fff";
    topBar.style.padding = "4px 8px";


    const hideBtn = document.createElement("span");
    // hideBtn.innerHTML = '<i class="fas fa-chevron-down"></i>';  // 🔽 숨기기
    hideBtn.innerHTML = '<i id="expendWindowIcon" class="fas fa-compress"></i>';  // 🔽 숨기기
    hideBtn.style.cursor = "pointer";
    hideBtn.onclick = () => {
        // videoCallWindow.style.visibility = "hidden";
        // videoCallWindow.style.opacity = "0";

        windowFullSizeOn = !windowFullSizeOn;
        const icon = document.getElementById("expendWindowIcon");
        icon.className = windowFullSizeOn ? "fas fa-compress" : "fas fa-expand";
        videoCallWindow.style.width = windowFullSizeOn ? "380px" : "200px";
        videoCallWindow.style.height = windowFullSizeOn ? "530px" : "300px";
    };

    const closeBtn = document.createElement("span");
    closeBtn.innerHTML = '<i class="fas fa-times"></i>'; // ❌ 닫기
    closeBtn.style.cursor = "pointer";
    closeBtn.onclick = () => {
        if (videoCallWindow) {
            document.body.removeChild(videoCallWindow);
            videoCallWindow = null;

            // const msg = '<span style="color:green;"><i class="fa-solid fa-phone-slash" style="color: red;"></i></span>  통화종료';
            // if (msg !== "") {
            //     socket.emit("new_msg", { username, msg, room: roomName });
            //     socket.emit("stop_typing", {room: roomName, username: username });
            // }
        }
    };

    hideBtn.addEventListener("touchstart", function(e) {
        e.stopPropagation();
    }, { passive: false });

    closeBtn.addEventListener("touchstart", function(e) {
        e.stopPropagation();
    }, { passive: false });

    hideBtn.addEventListener("mousedown", function(e) {
        e.stopPropagation();
    });
    closeBtn.addEventListener("mousedown", function(e) {
        e.stopPropagation();
    });

    topBar.appendChild(hideBtn);
    topBar.appendChild(closeBtn);

    const iframe = document.createElement("iframe");
    iframe.src = "/func/video-call/window";
    // iframe.style.flex = "1";
    iframe.style.width = "100%";
    iframe.style.height = "100%";
    iframe.style.border = "none";

    // ✅ 마우스 이벤트
    topBar.addEventListener("mousedown", startDrag);
    document.addEventListener("mousemove", onDrag);
    document.addEventListener("mouseup", endDrag);

    // ✅ 터치 이벤트
    topBar.addEventListener("touchstart", startDrag, { passive: false });
    document.addEventListener("touchmove", onDrag, { passive: false });
    document.addEventListener("touchend", endDrag);

    videoCallWindow.appendChild(topBar);
    videoCallWindow.appendChild(iframe);

    document.body.appendChild(videoCallWindow);

    window.addEventListener("message", (event) => {
        if (event.data === "force-close") {
            closeBtn.click();
        }
    });


    // const msg = '<span style="font-size:2em; color:green;">📞 통화요청</span>';
    const msg = '<span style="color:green;"><i class="fa-solid fa-phone"></i></span>  통화요청';
    if (msg !== "") {
        socket.emit("new_msg", { username, msg, room: roomName });
        socket.emit("stop_typing", {room: roomName, username: username });
    }

    // closeBtn.click();
    // 소켓으로 컨트롤 해야할지도
}


///////////////////////////////// Drag Evnet //////////////////////////////

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
    if (e.target.tagName.toLowerCase() !== 'span') { // 터치 스크롤, 새로고침 방지
        e.preventDefault();
    }
    isDragging = true;
    const pos = getClientPosition(e);
    offsetX = pos.x - videoCallWindow.offsetLeft;
    offsetY = pos.y - videoCallWindow.offsetTop;
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