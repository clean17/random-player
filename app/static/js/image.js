let nextImageElement = null,
    loading_size = 8,
    initialLoadComplete = false,
    startX, startY,
    mouseStartX, mouseStartY,
    imageItems,
    lazyImages;

const nextBtn = document.getElementById('next-image-button'),
      previousBtn = document.getElementById('previous-image-button'),
      shuffleBtn = document.getElementById('shuffle-button'),
      delBtn = document.querySelector('.delete-button'),
      form = document.getElementById('delete-form'),
      page = "{{ page }}",
      currentUserName = '{{ current_user.get_id() }}',
      guestName = '{{ config.GUEST_USERNAME }}',
      emptyBinBtn = document.getElementById('empty-bin-button'),
      TAP_THRESHOLD = 10; // 픽셀, 이 이하 이동이면 '탭'으로 간주

// debounce
let lastScrollTop = 0;
let lastScrollTime = Date.now();
const SCROLL_DELAY = 100;
const SCROLL_THRESHOLD = 50000;  // px per second

// slideShow
let slideShowTimer = null;
let slideShowImgs = [];
let slideShowIdx = 0;


// 다음 이미지 함수 스로틀링
const throttledNextImage = throttle(() => nextImage(), 180);
const debouncedScrollEvent = debounce(handleScroll, SCROLL_DELAY);

/******************************************  Image  ****************************************/
nextBtn?.addEventListener('click', nextImage);

// 다음 Element를 세팅
function setNextImage(element) {
    nextImageElement = element.nextElementSibling;
}

// 화면 중앙의 이미지 Element, Index
function getCenterImage(index= '') {
    const centerY = window.innerHeight / 2; // 화면 뷰포트의 중앙(y 좌표
    let closestImage = null;
    let closestIndex = -1;
    let minDistance = Infinity;

    imageItems.forEach((img, index) => {
        const rect = img.getBoundingClientRect(); // 뷰포트 기준
        const itemCenterY = rect.top + rect.height / 2; // 뷰포트 내 이미지 중앙
        const distance = Math.abs(centerY - itemCenterY);

        if (distance < minDistance) {
            minDistance = distance;
            closestImage = img;
            closestIndex = index;
        }
    });

    if (index === 'index') return closestIndex;
    else return closestImage;
}


function nextImage() {
    const centerImage = getCenterImage();
    if (centerImage) {
        const nextImage = centerImage.nextElementSibling;
        if (nextImage && nextImage.classList.contains('image-item')) {
            nextImage.scrollIntoView({ behavior: 'auto', block: 'center' });
        }
    }
}

function previousImage() {
    const centerImage = getCenterImage();
    if (centerImage) {
        const previousImage = centerImage.previousElementSibling;
        if (previousImage && previousImage.classList.contains('image-item')) {
            previousImage.scrollIntoView({ behavior: 'auto', block: 'center' });
        }
    }
}

// data-src: 원본 이미지 경로
// 처음에는 스켈레톤 이미지만 보여준다
function preloadImage(img) {
    const src = img.getAttribute('data-src');
    if (src && img.src !== src) {
        img.src = src;
        img.removeAttribute('data-src'); // 이미 로드된 이미지는 data-src 속성 제거
    }
}

// 주어진 인덱스 기준으로 위 아래 이미지 로드
function loadImagesAroundIndex(index) {
    let minIndex = Math.max(index - loading_size, 0);
    let maxIndex = Math.min(index + loading_size, lazyImages.length - 1);
    for (let i = minIndex; i <= maxIndex; i++) {
        if (lazyImages[i] && lazyImages[i].hasAttribute('data-src')) {
            preloadImage(lazyImages[i]);
        }
    }
}

// 페이지 로드 직후 중앙 이미지 인덱스 찾기 및 해당 범위 이미지 로드
function initialImageLoad() {
    if (!initialLoadComplete) {
        let centerIndex = getCenterImage('index');
        loadImagesAroundIndex(centerIndex);
        initialLoadComplete = true;
    }
}

// 페이지 로드 직후 중앙 이미지 인덱스 찾기 및 해당 범위 이미지 로드
window.onload = initialImageLoad;

/******************************************  Image  ****************************************/
/******************************************  Video  ****************************************/

function playCenterVideo() {
    const centerImage = getCenterImage();
    const video = centerImage.querySelector('video');
    if (video) {
        if (video.paused) {
            video.play();
        } else {
            video.pause();
        }
        video.blur();
    }
}

// video태그 중 마지막으로 재생한 video만 재생되도록 함
function playSingleVideo(targetVideo, init= '') {
    const videos = document.querySelectorAll('video');

    videos.forEach(video => {
        if (video !== targetVideo) {
            safePause(video);
        }
    });

    if (targetVideo.paused) {
        if (init === 'init') targetVideo.currentTime = 0;
        targetVideo.play().catch(() => {/* 무시 */});
    }
}

function preventAll(e) {
    e.preventDefault();
    e.stopPropagation();
}

// 탭/클릭 vs 드래그 구분
function attachTapOnly(video, options = {}) {
    let startX, startY, mouseStartX, mouseStartY;

    video.addEventListener('click', preventAll, true); // capture=true

    video.addEventListener('touchstart', e => {
        if (e.touches.length === 1) {
            startX = e.touches[0].clientX;
            startY = e.touches[0].clientY;
        }
    });
    video.addEventListener('touchend', e => {
        if (e.changedTouches.length === 1) {
            const dx = Math.abs(e.changedTouches[0].clientX - startX);
            const dy = Math.abs(e.changedTouches[0].clientY - startY);
            if (dx < TAP_THRESHOLD && dy < TAP_THRESHOLD) {
                togglePlayPauseVideo(video, options);
            }
        }
    });

    video.addEventListener('mousedown', e => {
        mouseStartX = e.clientX; mouseStartY = e.clientY;
    });
    video.addEventListener('mouseup', e => {
        const dx = Math.abs(e.clientX - mouseStartX);
        const dy = Math.abs(e.clientY - mouseStartY);
        if (dx < TAP_THRESHOLD && dy < TAP_THRESHOLD) {
            togglePlayPauseVideo(video, options);
        }
    });
}

// 토글: 현재 상태에 따라 재생/일시정지
function togglePlayPauseVideo(video, options = {}) {
    if (!video) return;

    if (video.paused || video.ended) {
        safePlay(video, options);
    } else {
        safePause(video);
    }
}

function safePause(video) {
    if (video instanceof HTMLMediaElement && typeof video.pause === 'function' && !video.paused) {
        video.pause();
    }
}

// 사용자 상호작용
function safePlay(video, { autoPlay = false, fromStart= false } = {}) {
    if (!(video instanceof HTMLMediaElement)) return;

    video.controls = true;
    // 자동재생 안정화(모바일)
    video.muted = true;
    video.playsInline = true;

    // 소스가 없으면 종료
    const hasSrc = video.src || video.querySelector('source[src]') || video.querySelector('source[data-src]');
    if (!hasSrc) return;

    // 중복 호출/경합 방지 플래그
    if (video._pendingPlay) return;
    video._pendingPlay = true;

    const start = () => {
        video._pendingPlay = false;
        if (autoPlay) {
            // 0초부터 원하면 활성화
            if (fromStart) video.currentTime = 0;
            video.play().catch(() => { /* 정책/경합 실패는 조용히 무시 */ });
        }
    };

    if (video.readyState >= 2) {
        start();
    } else {
        // canplay/loadeddata 중 먼저 오는 쪽에서 1회만 재생 시도
        once(video, 'loadeddata', start);
        once(video, 'canplay', start);

        // load()는 요소 상태를 리셋하며 내부적으로 pause를 유발할 수 있으므로
        // '대기 이벤트를 건 다음' 호출해야 경합을 줄임
        video.load();
    }
}



/******************************************  Video  ****************************************/
/******************************************  Pagenation  ****************************************/
document.getElementById("prevButton")?.addEventListener("click", () => {
    if (page > 1) {
        const previousBtn = document.querySelector('.pagination').children[1]
        previousBtn.click();
    }
});

document.getElementById("nextButton")?.addEventListener("click", () => {
    const btnCount = document.querySelector('.pagination').childElementCount
    const nextBtn = document.querySelector('.pagination').children[btnCount - 2];
    if (nextBtn.textContent === '>') {
        nextBtn.click();
    }
});
/******************************************  Pagenation  ****************************************/


// 스크롤 이벤트 디바운스 적용
function handleScroll() {
    const currentScrollTop = window.scrollY;
    const currentTime = Date.now();
    const scrollDelta = Math.abs(currentScrollTop - lastScrollTop);
    const timeDelta = currentTime - lastScrollTime;
    const scrollSpeed = scrollDelta / (timeDelta / 1000);
    /*if (scrollSpeed> 10000) {
        console.log('scrollSpeed', scrollSpeed);
    }*/

    if (scrollSpeed < SCROLL_THRESHOLD) {
        let centerImageIndex = getCenterImage('index');
        loadImagesAroundIndex(centerImageIndex);
    }

    lastScrollTop = currentScrollTop;
    lastScrollTime = currentTime;
}

window.addEventListener('scroll', () => {
    if (!initialLoadComplete) return; // 초기 로드가 완료되지 않았으면 실행하지 않음
    debouncedScrollEvent();
});
