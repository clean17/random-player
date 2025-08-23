let nextImageElement = null,
    loading_size = 8,
    initialLoadComplete = false,
    startX, startY,
    mouseStartX, mouseStartY,
    imageItems,
    lazyImages;

const nextBtn = document.getElementById('next-image-button'),
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
    console.log('initialImageLoad');
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
    const centerImage = findCenterImageElement();
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
function playSingleVideo(targetVideo) {
    const videos = document.querySelectorAll('video');

    videos.forEach(video => {
        if (video !== targetVideo) {
            video.pause();
            // video.currentTime = 0;
        }
    });

    if (targetVideo.paused) {
        targetVideo.play();
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
