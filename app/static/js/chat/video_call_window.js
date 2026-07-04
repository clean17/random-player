let videoCallWindow = null,
    vcallIframe = null,
    isDragging = false,
    isResizing = false,
    rafId = null,
    pendingX = 0, pendingY = 0,
    pendingW = 0, pendingH = 0,
    offsetX = 0,
    offsetY = 0,
    resizeStartX = 0,
    resizeStartW = 0,
    windowFullSizeOn = true;

const VCALL_W = 380, VCALL_H = 530;
const VCALL_RATIO = VCALL_W / VCALL_H;

////////////////////////// Video Call //////////////////////////////

function openVideoCallWindow() {
    if (!videoCallWindow) {
        videoCallWindow = document.createElement("div");
        videoCallWindow.style.cssText = [
            "position:fixed",
            "top:calc(var(--app-header-height,56px) + env(safe-area-inset-top) + 14px)",
            "left:15px",
            "width:"  + VCALL_W + "px",
            "height:" + VCALL_H + "px",
            "max-width:100vw",
            "max-height:100vh",
            "min-width:200px",
            "min-height:280px",
            "background:#000",
            "border:2px solid #ccc",
            "z-index:2147483000",
            "flex-direction:column",
            "box-shadow:0 0 10px rgba(0,0,0,.5)",
            "overflow:hidden",
            "display:flex",
            "will-change:transform",
            "user-select:none",
            "-webkit-user-select:none"
        ].join(";");
    }

    const topBar = document.createElement("div");
    topBar.style.cssText = "display:flex;justify-content:space-between;background:#222;color:#fff;padding:4px 8px;flex-shrink:0;cursor:move";

    const hideBtn = document.createElement("span");
    hideBtn.innerHTML = '<i id="expendWindowIcon" class="fas fa-compress"></i>';
    hideBtn.style.cursor = "pointer";
    hideBtn.onclick = () => {
        windowFullSizeOn = !windowFullSizeOn;
        const icon = document.getElementById("expendWindowIcon");
        icon.className = windowFullSizeOn ? "fas fa-compress" : "fas fa-expand";
        videoCallWindow.style.width  = windowFullSizeOn ? VCALL_W + "px" : "200px";
        videoCallWindow.style.height = windowFullSizeOn ? VCALL_H + "px" : Math.round(200 / VCALL_RATIO) + "px";
    };

    const closeBtn = document.createElement("span");
    closeBtn.innerHTML = '<i class="fas fa-times"></i>';
    closeBtn.style.cursor = "pointer";
    closeBtn.onclick = () => {
        if (videoCallWindow) {
            document.body.removeChild(videoCallWindow);
            videoCallWindow = null;
            vcallIframe = null;
        }
    };

    hideBtn.addEventListener("touchstart", e => e.stopPropagation(), { passive: false });
    closeBtn.addEventListener("touchstart", e => e.stopPropagation(), { passive: false });
    hideBtn.addEventListener("mousedown", e => e.stopPropagation());
    closeBtn.addEventListener("mousedown", e => e.stopPropagation());

    topBar.appendChild(hideBtn);
    topBar.appendChild(closeBtn);

    vcallIframe = document.createElement("iframe");
    vcallIframe.src = "/func/video-call/window";
    vcallIframe.style.cssText = "width:100%;height:100%;border:none;flex:1";

    // 비율 유지 리사이즈 핸들 (우하단)
    const resizeHandle = document.createElement("div");
    resizeHandle.style.cssText = [
        "position:absolute", "right:0", "bottom:0",
        "width:18px", "height:18px", "cursor:nwse-resize", "z-index:1",
        "background:linear-gradient(135deg,transparent 40%,#aaa 40%,#aaa 55%,transparent 55%,transparent 65%,#aaa 65%,#aaa 80%,transparent 80%)"
    ].join(";");

    resizeHandle.addEventListener("mousedown", startResize);
    resizeHandle.addEventListener("touchstart", startResize, { passive: false });

    topBar.addEventListener("mousedown", startDrag);
    topBar.addEventListener("touchstart", startDrag, { passive: false });

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onEnd);
    document.addEventListener("touchmove", onMove, { passive: false });
    document.addEventListener("touchend", onEnd);

    videoCallWindow.appendChild(topBar);
    videoCallWindow.appendChild(vcallIframe);
    videoCallWindow.appendChild(resizeHandle);
    document.body.appendChild(videoCallWindow);

    window.addEventListener("message", (event) => {
        if (event.data === "force-close") closeBtn.click();
    });

    const msg = '<span style="color:green;"><i class="fa-solid fa-phone"></i></span>  통화요청';
    socket.emit("new_msg", { username, msg, room: roomName });
    socket.emit("stop_typing", { room: roomName, username: username });
}

function setIframePointerEvents(enabled) {
    if (vcallIframe) vcallIframe.style.pointerEvents = enabled ? "auto" : "none";
}

///////////////////////////////// 공통 이벤트 //////////////////////////////

function getClientPosition(e) {
    if (e.touches && e.touches.length > 0) {
        return { x: e.touches[0].clientX, y: e.touches[0].clientY };
    }
    return { x: e.clientX, y: e.clientY };
}

function startDrag(e) {
    if (e.target.tagName.toLowerCase() !== "span") e.preventDefault();
    isDragging = true;
    setIframePointerEvents(false);
    const pos = getClientPosition(e);
    offsetX = pos.x - videoCallWindow.offsetLeft;
    offsetY = pos.y - videoCallWindow.offsetTop;
}

function startResize(e) {
    e.preventDefault();
    e.stopPropagation();
    isResizing = true;
    setIframePointerEvents(false);
    const pos = getClientPosition(e);
    resizeStartX = pos.x;
    resizeStartW = videoCallWindow.offsetWidth;
}

function onMove(e) {
    if (!isDragging && !isResizing) return;
    if (e.cancelable) e.preventDefault();

    const pos = getClientPosition(e);

    if (isDragging) {
        pendingX = Math.max(0, Math.min(pos.x - offsetX, window.innerWidth  - videoCallWindow.offsetWidth));
        pendingY = Math.max(0, Math.min(pos.y - offsetY, window.innerHeight - videoCallWindow.offsetHeight));
    } else {
        pendingW = Math.max(200, resizeStartW + (pos.x - resizeStartX));
        pendingH = Math.round(pendingW / VCALL_RATIO);
        if (pendingH < 280) return;
    }

    if (!rafId) {
        rafId = requestAnimationFrame(applyMove);
    }
}

function applyMove() {
    rafId = null;
    if (isDragging) {
        videoCallWindow.style.left   = pendingX + "px";
        videoCallWindow.style.top    = pendingY + "px";
        videoCallWindow.style.right  = "auto";
        videoCallWindow.style.bottom = "auto";
    } else if (isResizing) {
        videoCallWindow.style.width  = pendingW + "px";
        videoCallWindow.style.height = pendingH + "px";
    }
}

function onEnd() {
    if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
    isDragging = false;
    isResizing = false;
    setIframePointerEvents(true);
}
