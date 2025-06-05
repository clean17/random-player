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
function throttle(func, delay) {
    let throttleTimer = null;
    return function (...args) {
        if (throttleTimer) return;  // 타이머가 돌아가는 중이면 아무 것도 하지 않음
        throttleTimer = setTimeout(() => {
            func.apply(this, args);
            throttleTimer = null;   // 타이머 초기화 > 다음 실행 허용
        }, delay);
    };
}