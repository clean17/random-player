// 토스트 메시지
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


// debounce 적용 (동일한 함수 호출이라면 마지막으로 호출한지 지정한 시간이 지났을 경우에만 실행, 중복으로 호출하면 시간은 계속 리셋)
function debounce(func, delay) {
    let debounceTimer;
    return function (...args) {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => func.apply(this, args), delay);
    };
}

// throttle 적용 (의도적으로 성능을 낮춤, 주어진 시간 간격 내에 특정 함수가 최대 한 번만 실행되도록 제한하는 기술)
function throttle(fn, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            fn.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

/*
    // 함수를 리턴하는 함수, 고차 함수(Higher-Order Function, HOF)
    function makeMultiplier(x) {
       return function(y) {
           return x * y;
       }
    }

const double = makeMultiplier(2);
console.log(double(5)); // 10
*/


// 현재 시간 19:52 반환
function getCurrentTimeStr() {
    const now = new Date();

    const hour = now.getHours().toString().padStart(2, "0");
    const minute = now.getMinutes().toString().padStart(2, "0");

    return `${hour}:${minute}`;
}

function getNowTimestamp() {
    const now = new Date();
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const dd = String(now.getDate()).padStart(2, '0');
    const hh = String(now.getHours()).padStart(2, '0');
    const mi = String(now.getMinutes()).padStart(2, '0');
    const ss = String(now.getSeconds()).padStart(2, '0');

    return `${yyyy}-${mm}-${dd}_${hh}${mi}${ss}`;
}

// "250622194841" → "2025-06-22 19:48:41"
// YYMMDDHHmmss
function parseTimestamp(ts) {
    const year = 2000 + parseInt(ts.slice(0, 2), 10);
    const month = parseInt(ts.slice(2, 4), 10) - 1; // JS는 0~11월
    const day = parseInt(ts.slice(4, 6), 10);
    const hour = parseInt(ts.slice(6, 8), 10);
    const min = parseInt(ts.slice(8, 10), 10);
    const sec = parseInt(ts.slice(10, 12), 10);
    return new Date(year, month, day, hour, min, sec);
}

function renderOverlay() {
    if (!document.getElementById('overlay')) {
        const overlay = document.createElement('div');
        overlay.id = 'overlay';
        overlay.style.display = 'none';
        overlay.innerHTML = '<img src="/static/overlay-loading.svg" alt="Loading...">';
        document.body.appendChild(overlay);
    }
}

// 휴지통 비우기 요청
async function emptyTrash() {
    const userConfirmed = confirm("휴지통을 비우시겠습니까?");
    if (!userConfirmed) return;

    try {
        renderOverlay();
        document.getElementById('overlay').style.display = 'block';
        document.body.style.pointerEvents = "none"; // 화면 이벤트 제거

        const response = await fetch("/func/empty-trash-bin", { method: "POST" });
        const result = await response.json();

        alert(result.message);
        document.getElementById('overlay').style.display = 'none';
        document.body.style.pointerEvents = "auto"; // 화면 이벤트 복원
    } catch (error) {
        alert("오류가 발생했습니다: " + error);
        document.getElementById('overlay').style.display = 'none';
        document.body.style.pointerEvents = "auto"; // 화면 이벤트 복원
    }
}

// 헬퍼: 한 번만 듣는 리스너
function once(el, type, fn) {
    el.addEventListener(type, fn, { once: true });
}