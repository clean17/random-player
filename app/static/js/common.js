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