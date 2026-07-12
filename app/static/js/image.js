let nextImageElement = null,
    loading_size = 8,
    initialLoadComplete = false,
    startX, startY,
    imageItems,
    lazyImages,
    selectedIndex,
    selectedOption,
    dirText = undefined;

const nextBtn = document.getElementById('next-image-button'),
      previousBtn = document.getElementById('previous-image-button'),
      shuffleBtn = document.getElementById('shuffle-button'),
      delBtn = document.querySelector('.delete-button'),
      form = document.getElementById('delete-form'),
      emptyBinBtn = document.getElementById('empty-bin-button'),
      fetchImageBtn = document.getElementById('fetch-image-button'),
      TAP_THRESHOLD = 10, // 픽셀, 이 이하 이동이면 '탭'으로 간주
      delImages = [...document.querySelectorAll('input[name="images[]"]')].map(el => el.value),
      slideShowBtn = document.getElementById("slideshow-btn"),
      zipBtn = document.getElementById('download-zip-btn'),
      dropdownMenu = document.getElementById('dropdown-menu'),
      $dir = document.getElementById('dir-select'),
      empty_variable = ''  // 사용안함
;


if ($dir) {
    selectedOption = $dir.options[$dir.selectedIndex];
    // console.log('selectedOption', selectedOption)
    dirText = selectedOption.text;
}

// debounce
let lastScrollTop = 0;
let lastScrollTime = Date.now();
const SCROLL_DELAY = 40;
const SCROLL_THRESHOLD = 50_000;  // px per second
const THROTTLE_NEXT_IMG_SEC = 400

// slideShow
let slideShowTimer = null;
let slideShowImgs = [];
let slideShowIdx = 0;
let slideCountdownInterval = null;
let slideStartTime = 0;
const SLIDE_DURATION_MS = 10000;
let slideDurationMs = SLIDE_DURATION_MS;   // 현재 슬라이드의 실효 지속시간 (비디오일 경우 영상 길이)
let pendingMasonryScrollY = null;

function _preventTouchScroll(e) { e.preventDefault(); }

// masonry에 새로 렌더된 항목을 slideShowImgs에 추가 (data-index 순)
function extendSlideShowImgs() {
    const msr = document.getElementById('masonry');
    if (!msr) return;
    const existing = new Set(slideShowImgs);
    const imgItems = Array.from(msr.querySelectorAll('img.thumbnail[data-filename]'))
        .map(el => ({ fn: decodeURIComponent(el.dataset.filename), idx: Number(el.dataset.index) }));
    const vidItems = Array.from(msr.querySelectorAll('video[data-index] source[data-filename]'))
        .map(el => ({ fn: decodeURIComponent(el.dataset.filename), idx: Number(el.closest('video').dataset.index) }));
    const newItems = imgItems.concat(vidItems)
        .sort((a, b) => a.idx - b.idx)
        .map(item => item.fn)
        .filter(f => !existing.has(f));
    if (newItems.length > 0) slideShowImgs.push(...newItems);
}

function startSlideCountdown() {
    slideStartTime = Date.now();
    clearInterval(slideCountdownInterval);
    slideCountdownInterval = setInterval(() => {
        const el = document.getElementById('slideshow-countdown');
        if (!el) { clearInterval(slideCountdownInterval); return; }
        const remaining = Math.max(0, (slideDurationMs - (Date.now() - slideStartTime)) / 1000);
        el.textContent = remaining.toFixed(1) + 's';
    }, 100);
}

function scheduleNextSlide() {
    clearTimeout(slideShowTimer);
    slideShowTimer = null;
    const filename = slideShowImgs[slideShowIdx];
    if (!filename) return;
    const videoExts = ['mp4', 'mov', 'mkv', 'avi'];
    const isVid = videoExts.includes(filename.split('.').pop().toLowerCase());

    function advance() {
        extendSlideShowImgs();
        slideShowIdx = (slideShowIdx + 1) % slideShowImgs.length;
        setSlide(slideShowImgs[slideShowIdx]);
        scheduleNextSlide();
    }

    if (isVid) {
        const videoEl = document.getElementById('slideshow-video');
        const applyDuration = function() {
            const dur = videoEl ? videoEl.duration : NaN;
            slideDurationMs = (dur && isFinite(dur) && dur > 0) ? Math.round(dur * 1000) : SLIDE_DURATION_MS;
            startSlideCountdown();
            slideShowTimer = setTimeout(advance, slideDurationMs);
        };
        if (videoEl && videoEl.readyState >= 1 && isFinite(videoEl.duration) && videoEl.duration > 0) {
            applyDuration();
        } else if (videoEl) {
            let applied = false;
            videoEl.addEventListener('loadedmetadata', function handler() {
                if (applied) return;
                applied = true;
                applyDuration();
            }, { once: true });
            // 3초 안에 메타데이터가 안 오면 기본값으로 진행
            setTimeout(function() {
                if (!applied) {
                    applied = true;
                    applyDuration();
                }
            }, 3000);
        } else {
            slideDurationMs = SLIDE_DURATION_MS;
            startSlideCountdown();
            slideShowTimer = setTimeout(advance, slideDurationMs);
        }
    } else {
        slideDurationMs = SLIDE_DURATION_MS;
        startSlideCountdown();
        slideShowTimer = setTimeout(advance, slideDurationMs);
    }
}

function stopSlideCountdown() {
    clearInterval(slideCountdownInterval);
    slideCountdownInterval = null;
    const el = document.getElementById('slideshow-countdown');
    if (el) el.textContent = '';
}

function setSlide(filename) {
    const imgEl = document.getElementById('slideshow-img');
    const videoEl = document.getElementById('slideshow-video');
    const videoSrcEl = document.getElementById('slideshow-video-source');
    const videoExts = ['mp4', 'mov', 'mkv', 'avi'];
    const imageBase = "https://chickchick.kr/image/images";
    const videoBase = "/video/temp-video";
    const enc = encodeURIComponent(filename);
    const isVid = videoExts.includes(filename.split('.').pop().toLowerCase());

    if (isVid) {
        imgEl.style.display = "none";
        videoEl.style.display = "block";
        videoSrcEl.src = `${videoBase}/${enc}?dir=refine`;
        videoEl.load();
        videoEl.play().catch(() => {});
    } else {
        videoEl.pause();
        videoEl.style.display = "none";
        imgEl.style.display = "block";
        imgEl.src = `${imageBase}?filename=${enc}&dir=refine`;
    }

    // 라벨 (masonry item-label과 동일 로직)
    const labelEl = document.getElementById('slideshow-label');
    if (labelEl) {
        const segment = filename.split('/')[0];
        const _i = segment.indexOf('_img_');
        const _r = segment.indexOf('_reel_');
        const cut = [_i, _r].filter(v => v !== -1).reduce((a, b) => Math.min(a, b), Infinity);
        const text = cut < Infinity ? segment.slice(0, cut) : segment.replace(/\.[^.]+$/, '');
        labelEl.textContent = text.slice(0, 40);
    }

    // 현재 인덱스
    const indexEl = document.getElementById('slideshow-index');
    if (indexEl) indexEl.textContent = `${slideShowIdx + 1} / ${slideShowImgs.length}`;

    // masonry에서 현재 슬라이드 아이템을 화면 가운데로 스크롤 (이미지 또는 비디오)
    // display:none 부모(#image-data)에 속한 요소는 offsetParent===null 로 제외
    const imgMatches = Array.from(document.querySelectorAll(`img.thumbnail[data-filename="${enc}"]`));
    const vidMatches = Array.from(document.querySelectorAll(`video source[data-filename="${enc}"]`))
        .map(el => el.closest('video')).filter(Boolean);
    const masonryEl = imgMatches.concat(vidMatches).find(el => el.offsetParent !== null);
    if (masonryEl) {
        const item = masonryEl.closest('.image-item');
        if (item) {
            const rect = item.getBoundingClientRect();
            const targetY = Math.max(0, window.scrollY + rect.top - (window.innerHeight / 2) + (rect.height / 2));
            pendingMasonryScrollY = targetY;
            window.scrollTo({ top: targetY, behavior: 'instant' });
        }
        // 현재 data-index 기준으로 미리 렌더
        const dataIndex = Number(masonryEl.dataset.index || 0);
        if (dataIndex > 0 && typeof preloadAheadOfSlide === 'function') {
            preloadAheadOfSlide(dataIndex);
        }
    }
}

function decrementTotalCount() {
    const el = document.getElementById('total_count');
    if (!el) return;
    const n = parseInt(el.textContent, 10);
    if (isNaN(n) || n <= 0) return;
    el.textContent = n - 1;
    if (n - 1 === 0) {
        document.querySelectorAll('.pagination').forEach(p => p.remove());
        document.querySelectorAll('.delete-button').forEach(b => b.remove());
        const emptyState = document.getElementById('empty-state');
        if (emptyState) emptyState.style.display = 'flex';
    }
}

function slideShowDeleteCurrent() {
    if (!slideShowImgs.length) return;
    const filename = slideShowImgs[slideShowIdx];
    const enc = encodeURIComponent(filename);

    // DOM에서 찾아 즉시 제거 (현재 페이지에 있을 때만 적용)
    const mediaEls = document.querySelectorAll(`img[data-filename="${enc}"], source[data-filename="${enc}"]`);
    const removed = [...new Set([...mediaEls].map(el => el.closest('.image-item')).filter(Boolean))];
    removed.forEach(item => item.remove());
    if (removed.length) decrementTotalCount();
    if (typeof adjustColumnsIfNeeded === 'function') adjustColumnsIfNeeded();

    // API 직접 호출 (DOM 조회 성공 여부와 무관하게 항상 실행)
    fetch('/image/move-image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ imagepath: 'refine', filename })
    }).catch(err => console.error('slideShowDelete:', err));

    slideShowImgs.splice(slideShowIdx, 1);
    if (!slideShowImgs.length) {
        document.getElementById('slideshow-modal')?.querySelector('.close-modal')?.click();
        return;
    }
    if (slideShowIdx >= slideShowImgs.length) slideShowIdx = slideShowImgs.length - 1;
    clearTimeout(slideShowTimer);
    stopSlideCountdown();
    setSlide(slideShowImgs[slideShowIdx]);
    scheduleNextSlide();
}


// 다음 이미지 함수 스로틀링
const throttledNextImage = throttle(() => nextImage(), THROTTLE_NEXT_IMG_SEC);
const debouncedScrollEvent = debounce(handleScroll, SCROLL_DELAY);

/******************************************  Procress  ****************************************/
// 주식 예측 진행도

function updateProgressBar(data) {
    // console.log(data)
    const fill = document.getElementById('progress-fill');
    fill.style.width = data.percent + '%';
    const fillText = document.getElementById('progress-text');
    fillText.textContent = data.done ? data.percent + '%' : data.percent + '% ' + '(' + data.count + '/' + data.total_count + ')  ' + '[ '+ data.ticker + ' ] ' + data.stock_name;
    document.getElementById('progress-status').textContent = data.done ? '완료' : '';
}

function pollProgress(stock) {
    fetch('/stocks/progress/'+stock)
        .then(resp => {
            if (!resp.ok) throw new Error('네트워크 오류 또는 인증 필요');
            return resp.json();
        })
        .then(data => {
            updateProgressBar(data);
            if (!data.done) setTimeout(()=> pollProgress(stock), 1000);
            else document.getElementById('progress-status').textContent = '완료';
        })
        .catch(err => {
            document.getElementById('progress-status').textContent = '에러 발생: ' + err.message;
        });
}
/******************************************  Procress  ****************************************/
/******************************************  Image  ****************************************/

function clickCenterImage(target) {
    let centerImage;
    if (target) {
        centerImage = target
    } else {
        centerImage = getCenterImage();
    }
    // console.log('center', centerImage)

    if (centerImage) {
        let filename;
        let index;
        const imgTag = centerImage.querySelector('img');
        if (imgTag) {
            filename = imgTag.getAttribute('alt');
            index = imgTag.getAttribute('data-index');
        } else {
            const videoTag = centerImage.querySelector('video');
            filename = videoTag.getAttribute('alt');
            index = videoTag.getAttribute('data-index');
        }
        if (filename && index) {
            moveImage(filename, index);
        }
    }
}

function moveImage(filename, index) {
    // console.log('filename', filename);
    if (dir === 'stock' || dir === 'temp') return;

    renderLoadingOverlay();

    // console.log(filename, index)
    fetch(`/image/move-image`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            imagepath: dir,
            subpath: dirText,
            filename: filename
        })
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                const imageElement = document.getElementById(`image-${index}`);
                const nextImageElement = imageElement?.nextElementSibling;
                if (imageElement) {
                    nextImage(nextImageElement);
                    imageElement.remove();
                    // if (nextImageElement) {
                    //     nextImageElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    // }
                }
                // const total = document.getElementById('total_count').textContent
                // document.getElementById('total_count').textContent = Number(total) - 1;
            }
        })
        .catch(error => {
            console.error('Error:', error);
        }).finally(()=>{
        isDelRunning = false;
        removeLoadingOverlay();
    });
}

nextBtn?.addEventListener('click', () => nextImage());
previousBtn?.addEventListener('click', () => previousImage());
delBtn?.addEventListener('click', () => deletePage())


// 화면 중앙의 이미지 Element, Index
function getCenterImage(index= '') {
    const centerY = window.innerHeight / 2; // 화면 뷰포트의 중앙(y 좌표
    let closestImage = null;
    let closestIndex = -1;
    let minDistance = Infinity;

    imageItems?.forEach((img, index) => {
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


function nextImage(nextImg) {
    const centerImage = getCenterImage();
    if (nextImg == null && centerImage) {
        const nextImgEl = centerImage.nextElementSibling;
        if (nextImgEl && nextImgEl.classList.contains('image-item')) {
            nextImgEl.scrollIntoView({ behavior: 'auto', block: 'center' });
            if (nextImgEl.querySelector('video') && (dir === 'refine' || dir === 'image2' || dir === 'image' || dir === 'move')) {
                const videoEl = nextImgEl.querySelector('video');
                videoEl.currentTime = 0;
            }
        } else {
            showDebugToast("마지막입니다.");
        }
    }
    if (nextImg) {
        if (nextImg && nextImg.classList.contains('image-item')) {
            nextImg.scrollIntoView({ behavior: 'auto', block: 'center' });
            if (nextImg.querySelector('video') && (dir === 'refine' || dir === 'image2' || dir === 'image' || dir === 'move')) {
                const videoEl = nextImg.querySelector('video');
                videoEl.currentTime = 0;
            }
        } else {
            showDebugToast("마지막입니다.");
        }
    }
}

function previousImage() {
    const centerImage = getCenterImage();
    if (centerImage) {
        const previousEL = centerImage.previousElementSibling;
        if (previousEL && previousEL.classList.contains('image-item')) {
            previousEL.scrollIntoView({ behavior: 'auto', block: 'center' });
            if (previousEL.querySelector('video') && (dir === 'refine' || dir === 'image2' || dir === 'image' || dir === 'move')) {
                const videoEl = previousEL.querySelector('video');
                videoEl.currentTime = 0;
            }
        } else {
            showDebugToast("처음입니다.");
        }
    }
}

// data-src: 원본 이미지 경로
// 처음에는 스켈레톤 이미지만 보여준다
function preloadImage(img) {
    // console.log('isConnected:', img.isConnected, 'index:', img.dataset.index);
    const src = img.getAttribute('data-src');
    const cur = img.getAttribute('src'); // 속성값 기준
    if (src && cur !== src) {
        img.setAttribute('src', src);
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

function moveImageToPreviousStep(imageItem) {
    const media = imageItem.querySelector('img[data-filename], source[data-filename]');
    let filename = media?.dataset.filename;
    if (!filename) {
        filename = imageItem.querySelector('.thumbnail')?.alt;
    }
    if (!imageItem || !filename) return;

    let idx = 0;
    if (imageItem.hasAttribute("id")) {
        idx = imageItem.id.split('-')[1];
    }

    renderLoadingOverlay();
    fetch(`/image/move-image`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            imagepath: 'refine',
            filename: decodeURIComponent(filename)
        })
    })
        .then(response => response.status === 404 ? { status: '404' } : response.json())
        .then(data => {
            removeLoadingOverlay();
            if (data.status === 'success' || data.status === '404') {
                const nextImageElement = imageItem.nextElementSibling;
                imageItem.remove();
                nextImage(nextImageElement);
                decrementTotalCount();
                if (typeof adjustColumnsIfNeeded === 'function') adjustColumnsIfNeeded();
            }
        })
        .catch(error => console.error('Error:', error));

    isDelRunning = false;
}


function handelDelBtn() {
    const imageItem = getCenterImage();
    moveImageToPreviousStep(imageItem);
}


function deletePage(e) {
    preventAll(e);

    // 이중요청 방지 + 화면 이벤트 차단 + 로딩 애니메이션
    renderLoadingOverlay();
    delBtn.disabled = true;
    delBtn.style.background = 'gray';

    axios.post("/image/delete-images?dir="+dir, {
        images: delImages,
        page: page
    })
        .then(res => {
            // 응답 JSON의 redirect 사용 (절대 URL로 보장)
            const url = new URL(res.data?.redirect, window.location.origin).href;
            window.location.replace(url); // 또는 window.location.href = url
        })
        .catch(err => console.error("삭제 실패", err))
        .finally(()=>{
            isDelRunning = false;
            removeLoadingOverlay();
        });

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

// 탭/클릭 vs 드래그 구분
function attachTapEventOnly(video, options = {}) {
    let startX, startY, mouseStartX, mouseStartY;

    video.addEventListener('click', preventAll, true); // capture=true

    video.addEventListener('touchstart', e => {
        if (e.touches.length === 1) {   // 화면에 손가락이 정확히 하나만 닿아 있는 상태
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

// IntersectionObserver를 통해 화면에 video태그가 보이면 실행
function lazyLoadVideos() {
    const videos = document.querySelectorAll("video.thumbnail");

    // 옵저버 정의
    /**
     * IntersectionObserver
     * 브라우저에서 어떤 요소가 뷰포트(화면) 안에 들어왔는지 자동으로 감지하는 API
     * >> 스크롤을 감지해서 이미지 로딩, 애니메이션 트리거, 광고 노출 등을 실행
     *
     * observe(element); 관찰 대상 등록
     * unobserve(element); 관찰 대상 해제
     * disconnect(); 모든 관찰 중단
     */
    const observer = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            const video = entry.target;
            const source = video.querySelector("source");

            if (entry.isIntersecting) { // 화면에 보이면 실행
                if (source && source.dataset.src && !source.src) {
                    source.src = source.dataset.src;     // 실제 src 할당
                    source.removeAttribute('data-src');
                    if (video.dataset.poster) video.poster = video.dataset.poster; // 썸네일 이미지 세팅
                    attachTapEventOnly(video, { autoPlay: true });
                }
                safePlay(video, { autoPlay: true, fromStart: true });

                // observer.unobserve(video); // 한 번 로딩되면 더 이상 감시 안 함, 주석 처리하여 다시 뷰포트로 들어오면 이벤트 동작하도록 함
            } else { // 화면 이탈
                safePause(video);
            }
        });
    }, {
        rootMargin: "0px 0px 1500px 0px",  // 약간 미리 로드 (실제 화면에 들어오기 전에 미리 감지 → 미리 로드 가능)
        // threshold: 0.1 // 요소가 10% 보일 때 트리거
    });

    videos.forEach(video => observer.observe(video));
}


/******************************************  Video  ****************************************/
/******************************************  Pagenation  ****************************************/
function goPage(page) {
    renderLoadingOverlay();
    const url = new URL("/image/pages", window.location.origin);
    url.searchParams.set("market", stock_name);
    url.searchParams.set("selected_dir", selected_dir);
    if (dir !== null && dir !== undefined && dir !== "") {
        url.searchParams.set("dir", dir);
    }
    url.searchParams.set("page", page);
    if (typeof currentSearch !== 'undefined' && currentSearch) {
        url.searchParams.set("search", currentSearch);
    }

    window.location.href = url.toString(); // 그냥 링크 이동
}

// 페이지 네이션
document.addEventListener('click', (e) => {
    const a = e.target.closest('.pagination a[data-page]');
    if (!a) return;

    e.preventDefault();
    const page = Number(a.dataset.page);
    goPage(page);
});

function goPrevPage () {
    if (page > 1) {
        const currentPageBtn = document.querySelector('.pagination .active')
        const previousBtn = currentPageBtn.previousElementSibling;
        previousBtn?.click();
    }
}

function goNextPage () {
    const currentPageBtn = document.querySelector('.pagination .active')
    const nextBtn = currentPageBtn.nextElementSibling;
    nextBtn?.click();
}

document.getElementById("prevButton")?.addEventListener("click", goPrevPage);
document.getElementById("nextButton")?.addEventListener("click", goNextPage);
/******************************************  Pagenation  ****************************************/


// 스크롤 이벤트 디바운스 적용
function handleScroll() {
    const currentScrollTop = window.scrollY;
    const currentTime = Date.now();
    const scrollDelta = Math.abs(currentScrollTop - lastScrollTop);
    const timeDelta = currentTime - lastScrollTime;
    const scrollSpeed = scrollDelta / (timeDelta / 1000);
    // console.log('scrollSpeed', scrollSpeed);

    // if (scrollSpeed < SCROLL_THRESHOLD) {
        let centerImageIndex = getCenterImage('index');
        loadImagesAroundIndex(centerImageIndex);
    // }

    lastScrollTop = currentScrollTop;
    lastScrollTime = currentTime;
}

window.addEventListener('scroll', () => {
    if (!initialLoadComplete) return; // 초기 로드가 완료되지 않았으면 실행하지 않음
    debouncedScrollEvent();
});



function moveStockImage(event) {
    const imgElement = event.target;
    const filename = imgElement.getAttribute('alt');
    const market = document.querySelector('#market-select');
    const marketName = market.options[market.selectedIndex].text.toLowerCase();

    fetch(`/image/move-stock-image/${encodeURIComponent(marketName)}/${encodeURIComponent(filename)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
    })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                const imageElement = imgElement.closest('.image-item');
                if (imageElement) {
                    const nextImageElement = imageElement.nextElementSibling;
                    imageElement.remove();
                    if (nextImageElement) {
                        nextImageElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }
            }
        })
        .catch(error => {
            console.error('Error:', error);
        }).finally(()=>{
            isDelRunning = false;
        });
}

function fetchImage() {
    renderLoadingOverlay();
    const url = new URL("/image/fetch", window.location.origin);
    if (dir) url.searchParams.set("dir", dir);
    window.location.href = url.toString(); // Flask가 스캔 후 /pages로 리다이렉트
}





function downloadThisPage() {
    const today = new Date();
    const formattedDate = `${today.getFullYear().toString().slice(-2)}${(today.getMonth() + 1).toString().padStart(2, '0')}${today.getDate().toString().padStart(2, '0')}`;
    const dirName = $dir.options[$dir.selectedIndex].textContent.trim();

   renderLoadingOverlay();

    // ZIP 파일 요청
    // fetch(`/func/download-zip?dir=${encodeURIComponent(dir)}`, {
    fetch(`/func/download-zip/page?dir=${encodeURIComponent(dir)}&page=${page}&dir=${encodeURIComponent(dirName)}`, {
        method: 'GET'
    })
        .then(response => {
            if (!response.ok) {
                throw new Error(response.status);
            }

            // 다운로드 처리
            return response.blob();
        })
        .then(blob => {
            removeLoadingOverlay();

            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.style.display = 'none';
            a.href = url;
            a.download = `${formattedDate}_page-${page}_files.zip`; // 파일 이름: 오늘 날짜 + _files.zip
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
        })
        .catch(error => {
            removeLoadingOverlay();
            alert('다운로드 중 문제가 발생했습니다: ' + error.message);
        });

    dropdownMenu.style.display = dropdownMenu.style.display === 'block' ? 'none' : 'block';
}

function downloadAllFiles() {
    const today = new Date();
    const formattedDate = `${today.getFullYear().toString().slice(-2)}${(today.getMonth() + 1).toString().padStart(2, '0')}${today.getDate().toString().padStart(2, '0')}`;
    const dirName = $dir.options[$dir.selectedIndex].textContent.trim();

    const url = `/func/download-zip/all?dir=${encodeURIComponent(dir)}&dir=${encodeURIComponent(dirName)}`;
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = `${formattedDate}_all_files.zip`; // 파일 이름: 오늘 날짜 + _files.zip
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
}



/******************************************  Slide Show  ****************************************/

function showSlideshowModal(fileList, startIdx = 0) {
    let modal = document.getElementById('slideshow-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = "slideshow-modal";
        modal.style.display = "flex";
        modal.innerHTML = `
            <button class="close-modal" title="닫기"><i class="fas fa-times" style="color:white"></i></button>
            <button class="slide-prev" title="이전">&#8249;</button>
            <img src="" alt="슬라이드" id="slideshow-img" style="display:none;">
            <video id="slideshow-video" class="slideshow-video" style="display:none;"
                   muted playsinline controls loop>
              <source id="slideshow-video-source" src="" type="video/mp4">
            </video>
            <button class="slide-next" title="다음">&#8250;</button>
            <div id="slideshow-countdown"></div>
            <div id="slideshow-label"></div>
            <div id="slideshow-index"></div>
        `;
        document.body.appendChild(modal);

        modal.querySelector('.close-modal').onclick = () => {
            clearTimeout(slideShowTimer);
            stopSlideCountdown();
            const v = modal.querySelector("#slideshow-video");
            v.pause();
            v.currentTime = 0;
            modal.style.display = "none";
            document.removeEventListener('touchmove', _preventTouchScroll);
            document.body.classList.remove('slideshow-active');
            if (pendingMasonryScrollY !== null) {
                window.scrollTo({ top: pendingMasonryScrollY, behavior: 'instant' });
                pendingMasonryScrollY = null;
            }
        };

        modal.querySelector('.slide-prev').onclick = () => {
            slideShowIdx = (slideShowIdx - 1 + slideShowImgs.length) % slideShowImgs.length;
            clearTimeout(slideShowTimer);
            setSlide(slideShowImgs[slideShowIdx]);
            scheduleNextSlide();
        };

        modal.querySelector('.slide-next').onclick = () => {
            extendSlideShowImgs();
            slideShowIdx = (slideShowIdx + 1) % slideShowImgs.length;
            clearTimeout(slideShowTimer);
            setSlide(slideShowImgs[slideShowIdx]);
            scheduleNextSlide();
        };

        // 슬라이드쇼 열려 있을 때 키보드 이벤트 전점 점유 (capture phase)
        document.addEventListener('keydown', (e) => {
            if (modal.style.display === 'none' || !modal.style.display) return;
            e.preventDefault();
            e.stopPropagation();
            switch (e.key) {
                case 'ArrowLeft':
                case 'ArrowUp':
                    modal.querySelector('.slide-prev').click();
                    break;
                case 'ArrowRight':
                case 'ArrowDown':
                    modal.querySelector('.slide-next').click();
                    break;
                case 'Escape':
                    modal.querySelector('.close-modal').click();
                    break;
                case 'Delete':
                case '`':
                    slideShowDeleteCurrent();
                    break;
            }
        }, true); // capture: true → 기존 bubble 핸들러보다 먼저 실행
    }
    modal.style.display = "flex";
    document.addEventListener('touchmove', _preventTouchScroll, { passive: false });
    document.body.classList.add('slideshow-active');

    // 슬라이드 쇼 상태 초기화
    slideShowIdx = Math.max(0, Math.min(startIdx, fileList.length - 1));
    slideShowImgs = fileList;

    // 첫 장 세팅
    setSlide(slideShowImgs[slideShowIdx]);

    // 기존 타이머 종료 후 다음 슬라이드 예약 (비디오면 영상 길이만큼 대기)
    if (slideShowTimer) clearTimeout(slideShowTimer);
    scheduleNextSlide();
}

async function slideShow() {
    try {
        console.log('$1')
        const resp = await fetch("/image/pages?slide=y&dir=refine");
        const imgList = await resp.json();  // 서버에서 JSON 배열로 이미지 URL 목록 반환한다고 가정
        console.log('imgList', imgList);

        if (!Array.isArray(imgList['slide_show_images']) || imgList['slide_show_images'].length === 0) {
            alert("이미지가 없습니다.");
            return;
        }
        showSlideshowModal(imgList['slide_show_images']);
    } catch (e) {
        console.error(e)
        alert("이미지 목록을 가져오는 데 실패했습니다.");
    }
}

// 슬라이드쇼 버튼 클릭 이벤트
slideShowBtn?.removeEventListener('click', slideShow)
slideShowBtn?.addEventListener('click', slideShow)


function shuffleImage() {
    renderLoadingOverlay()
    fetch(`/image/shuffle/ref-images?dir=`+dir, { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            console.log(data)
            /*if (data.status === 'success') {
                window.location.href = "{{ url_for('image.image_list', dir=dir) }}";
            }*/
            // 응답 JSON의 redirect 사용 (절대 URL로 보장)
            const url = new URL(data?.redirect, window.location.origin).href;
            window.location.replace(url); // 또는 window.location.href = url
        })
        .catch(error => {
            console.error('Error:', error);
        });
}


document.addEventListener("touchstart", (e) => {
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
});

document.addEventListener("touchend", (e) => {
    let endX = e.changedTouches[0].clientX;
    let endY = e.changedTouches[0].clientY;
    let diffX = endX - startX;
    let diffY = endY - startY;

    if (diffX > 50 && Math.abs(diffY) < 20) {
        previousImage();
    } else if (diffX < -50 && Math.abs(diffY) < 20) {
        throttledNextImage();
    }
});


