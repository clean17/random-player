let videoCallWindow = null,
    isDragging = false,
    offsetX = 0,
    offsetY = 0;

////////////////////////// Video Call //////////////////////////////

function openVideoCallWindow() {
    if (!videoCallWindow) {
        videoCallWindow = document.createElement("div");
        videoCallWindow.style.position = "fixed";
        videoCallWindow.style.bottom = "140px";
        videoCallWindow.style.right = "30px";
        videoCallWindow.style.width = "350px";
        videoCallWindow.style.height = "500px";
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
    hideBtn.innerHTML = '<i class="fas fa-chevron-down"></i>';  // 🔽 숨기기
    hideBtn.style.cursor = "pointer";
    hideBtn.onclick = () => {
        videoCallWindow.style.visibility = "hidden";
        videoCallWindow.style.opacity = "0";
        isMinimized = true;
    };

    const closeBtn = document.createElement("span");
    closeBtn.innerHTML = '<i class="fas fa-times"></i>'; // ❌ 닫기
    closeBtn.style.cursor = "pointer";
    closeBtn.onclick = () => {
        if (videoCallWindow) {
            document.body.removeChild(videoCallWindow);
            videoCallWindow = null;
        }
    };

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