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
    windowFullSizeOn = true,
    keyboardShrunken = false,
    baseViewportH = 0;

const VCALL_W = 380, VCALL_H = 530;
const VCALL_RATIO = VCALL_W / VCALL_H;
const COMPACT_W = 200;
const COMPACT_H = Math.round(COMPACT_W / VCALL_RATIO);

// 최초 위치 (왼쪽 상단)
const HOME_TOP  = "calc(var(--app-header-height,56px) + env(safe-area-inset-top) + 14px)";
const HOME_LEFT = "15px";

////////////////////////// Video Call //////////////////////////////

function openVideoCallWindow() {
    if (videoCallWindow) return;

    videoCallWindow = document.createElement("div");
    videoCallWindow.style.cssText = [
        "position:fixed",
        "top:" + HOME_TOP,
        "left:" + HOME_LEFT,
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

    const topBar = document.createElement("div");
    topBar.style.cssText = "display:flex;justify-content:space-between;background:#222;color:#fff;padding:4px 8px;flex-shrink:0;cursor:move";

    const hideBtn = document.createElement("span");
    hideBtn.innerHTML = '<i id="expendWindowIcon" class="fas fa-compress"></i>';
    hideBtn.style.cursor = "pointer";
    hideBtn.onclick = () => {
        if (keyboardShrunken) return; // 키보드 모드 중엔 무시
        windowFullSizeOn = !windowFullSizeOn;
        const icon = document.getElementById("expendWindowIcon");
        icon.className = windowFullSizeOn ? "fas fa-compress" : "fas fa-expand";
        videoCallWindow.style.width  = windowFullSizeOn ? VCALL_W + "px" : COMPACT_W + "px";
        videoCallWindow.style.height = windowFullSizeOn ? VCALL_H + "px" : COMPACT_H + "px";
    };

    const closeBtn = document.createElement("span");
    closeBtn.innerHTML = '<i class="fas fa-times"></i>';
    closeBtn.style.cursor = "pointer";
    closeBtn.onclick = () => {
        if (videoCallWindow) {
            document.body.removeChild(videoCallWindow);
            videoCallWindow = null;
            vcallIframe = null;
            keyboardShrunken = false;
            document.removeEventListener("focusin",  onInputFocus);
            document.removeEventListener("focusout", onInputBlur);
            if (window.visualViewport) {
                window.visualViewport.removeEventListener("resize", onViewportResize);
            }
            window.removeEventListener("resize", onViewportResize);
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

    // 키보드 감지: focusin(선제) + viewport resize(보장)
    baseViewportH = window.visualViewport ? window.visualViewport.height : window.innerHeight;
    document.addEventListener("focusin",  onInputFocus);
    document.addEventListener("focusout", onInputBlur);
    if (window.visualViewport) {
        window.visualViewport.addEventListener("resize", onViewportResize);
    }
    window.addEventListener("resize", onViewportResize);
    // eslint-disable-next-line no-unused-vars (module-level timer)
    window._vcallPlaceTimer = null;

    const msg = '<span style="color:green;"><i class="fa-solid fa-phone"></i></span>  통화요청';
    socket.emit("new_msg", { username, msg, room: roomName });
    socket.emit("stop_typing", { room: roomName, username: username });
}

function setIframePointerEvents(enabled) {
    if (vcallIframe) vcallIframe.style.pointerEvents = enabled ? "auto" : "none";
}

///////////////////////////////// 드래그·리사이즈 //////////////////////////////

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
    const pos  = getClientPosition(e);
    const rect = videoCallWindow.getBoundingClientRect();
    offsetX = pos.x - rect.left;
    offsetY = pos.y - rect.top;
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
        const vpW = window.visualViewport ? window.visualViewport.width  : window.innerWidth;
        const vpH = window.visualViewport ? window.visualViewport.height : window.innerHeight;
        pendingX = Math.max(0, Math.min(pos.x - offsetX, vpW - videoCallWindow.offsetWidth));
        pendingY = Math.max(0, Math.min(pos.y - offsetY, vpH - videoCallWindow.offsetHeight));
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

///////////////////////////////// 키보드 감지 //////////////////////////////

function placeCompactWindow() {
    if (!videoCallWindow || !keyboardShrunken) return;
    const vv   = window.visualViewport;
    const vpW  = vv ? vv.width  : window.innerWidth;
    // visual viewport 기준 우상단: offsetTop = 키보드로 인해 스크롤된 양
    const offsetTop = vv ? vv.offsetTop : 0;
    videoCallWindow.style.top    = (offsetTop + 10) + "px";
    videoCallWindow.style.bottom = "auto";
    videoCallWindow.style.left   = (vpW - COMPACT_W - 10) + "px";
    videoCallWindow.style.right  = "auto";
}

function shrinkForKeyboard() {
    if (!videoCallWindow || keyboardShrunken) return;
    keyboardShrunken = true;
    windowFullSizeOn = false;
    const icon = document.getElementById("expendWindowIcon");
    if (icon) icon.className = "fas fa-expand";
    videoCallWindow.style.width  = COMPACT_W + "px";
    videoCallWindow.style.height = COMPACT_H + "px";
    placeCompactWindow(); // 크기와 동시에 위치도 즉시 변경
}

function restoreFromKeyboard() {
    if (!videoCallWindow || !keyboardShrunken) return;
    keyboardShrunken = false;
    windowFullSizeOn = true;
    const icon = document.getElementById("expendWindowIcon");
    if (icon) icon.className = "fas fa-compress";
    // 원래 크기·위치로 복원
    videoCallWindow.style.width  = VCALL_W + "px";
    videoCallWindow.style.height = VCALL_H + "px";
    videoCallWindow.style.top    = HOME_TOP;
    videoCallWindow.style.left   = HOME_LEFT;
    videoCallWindow.style.right  = "auto";
    videoCallWindow.style.bottom = "auto";
}

function onInputFocus(e) {
    const tag = e.target.tagName.toLowerCase();
    if (tag !== "input" && tag !== "textarea") return;
    shrinkForKeyboard();
}

function onInputBlur(e) {
    const tag = e.target.tagName.toLowerCase();
    if (tag !== "input" && tag !== "textarea") return;
    const next = e.relatedTarget;
    if (next && (next.tagName === "INPUT" || next.tagName === "TEXTAREA")) return;
    setTimeout(() => restoreFromKeyboard(), 150);
}

function onViewportResize() {
    if (!videoCallWindow) return;
    const currentH = window.visualViewport ? window.visualViewport.height : window.innerHeight;
    if (currentH < baseViewportH - 120) {
        shrinkForKeyboard();
        // 키보드 애니메이션 완료(~300ms) 후 최종 vpH로 위치 확정
        clearTimeout(window._vcallPlaceTimer);
        window._vcallPlaceTimer = setTimeout(() => requestAnimationFrame(placeCompactWindow), 350);
    } else {
        restoreFromKeyboard();
    }
}
