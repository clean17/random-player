
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


// debounce 적용 (일정 시간동안의 마지막 요청만)
function debounce(func, delay) {
    let debounceTimer;
    return function (...args) {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => func.apply(this, args), delay);
    };
}

// throttle 적용 (짧은 시간에 여러 번 호출해도 일정 주기마다 한 번씩만 실행)
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