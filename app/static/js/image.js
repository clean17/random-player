let nextImageElement = null,
    loading_size = 8,
    initialLoadComplete = false,
    startX, startY,
    mouseStartX, mouseStartY,
    imageItems,
    lazyImages,
    selectedIndex,
    selectedOption,
    titleText = undefined;

const nextBtn = document.getElementById('next-image-button'),
      previousBtn = document.getElementById('previous-image-button'),
      shuffleBtn = document.getElementById('shuffle-button'),
      delBtn = document.querySelector('.delete-button'),
      form = document.getElementById('delete-form'),
      emptyBinBtn = document.getElementById('empty-bin-button'),
      TAP_THRESHOLD = 10, // 픽셀, 이 이하 이동이면 '탭'으로 간주
      delImages = [...document.querySelectorAll('input[name="images[]"]')].map(el => el.value),
      slideShowBtn = document.getElementById("slideshow-btn"),
      zipBtn = document.getElementById('download-zip-btn'),
      dropdownMenu = document.getElementById('dropdown-menu'),
      $title = document.getElementById('title-select'),
      empty_variable = ''
;


if ($title) {
    selectedOption = $title.options[$title.selectedIndex];
    titleText = selectedOption.text;
}

// debounce
let lastScrollTop = 0;
let lastScrollTime = Date.now();
const SCROLL_DELAY = 100;
const SCROLL_THRESHOLD = 100000;  // px per second
const THROTTLE_NEXT_IMG_SEC = 400

// slideShow
let slideShowTimer = null;
let slideShowImgs = [];
let slideShowIdx = 0;


// 다음 이미지 함수 스로틀링
const throttledNextImage = throttle(() => nextImage(), THROTTLE_NEXT_IMG_SEC);
const debouncedScrollEvent = debounce(handleScroll, SCROLL_DELAY);

/******************************************  Procress  ****************************************/
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
nextBtn?.addEventListener('click', nextImage);
delBtn?.addEventListener('click', deletePage)

// 다음 Element를 세팅
/*function setNextImage(element) {
    nextImageElement = element.nextElementSibling;
}*/

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

function moveImageToPreviousStep(event, imageItem) {
    let filename = (event instanceof MouseEvent) ? event.target.alt : imageItem.querySelector('.thumbnail')?.alt;
    if (imageItem) {
        if (!filename) {
            filename = imageItem.querySelector('source').dataset.filename;
        }
        let idx = 0;
        if (imageItem.hasAttribute("id")) {
            idx = imageItem.id.split('-')[1]
        }

        renderLoadingOverlay();
        fetch(`/image/move-image`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                imagepath: 'refine',
                filename: `${decodeURIComponent(filename)}`
            })
        })
            .then(response => response.json())
            .then(data => {
                removeLoadingOverlay();
                if (data.status === 'success') {
                    const imageElement = (event instanceof MouseEvent) ? event.target.closest('.image-item') : imageItem;
                    const nextImageElement = imageElement?.nextElementSibling;
                    // const imageElement = document.getElementById(`image-${index}`);
                    if (imageElement) {
                        imageElement.remove();
                        if (nextImageElement) {
                            nextImageElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }
                    }
                }
            })
            .catch(error => {
                console.error('Error:', error);
            });
    }
    isDelRunning = false;
}

function deleteItem(imageItem) {
    moveImageToPreviousStep(null, imageItem);
}

function handelDelBtn() {
    const imageItem = getCenterImage();
    deleteItem(imageItem);
}


function deletePage(e) {
    e?.preventDefault();

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
        .finally(()=>{isDelRunning = false;});

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






function downloadThisPage() {
    const today = new Date();
    const formattedDate = `${today.getFullYear().toString().slice(-2)}${(today.getMonth() + 1).toString().padStart(2, '0')}${today.getDate().toString().padStart(2, '0')}`;
    const titleName = $title.options[$title.selectedIndex].textContent.trim();

   renderLoadingOverlay();

    // ZIP 파일 요청
    // fetch(`/func/download-zip?dir=${encodeURIComponent(dir)}`, {
    fetch(`/func/download-zip/page?dir=${encodeURIComponent(dir)}&page=${page}&title=${encodeURIComponent(titleName)}`, {
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
    const titleName = $title.options[$title.selectedIndex].textContent.trim();

    const url = `/func/download-zip/all?dir=${encodeURIComponent(dir)}&title=${encodeURIComponent(titleName)}`;
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = `${formattedDate}_all_files.zip`; // 파일 이름: 오늘 날짜 + _files.zip
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
}



/******************************************  Slide Show  ****************************************/

function showSlideshowModal(fileList) {
    let modal = document.getElementById('slideshow-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = "slideshow-modal";
        modal.style.display = "flex";
        modal.innerHTML = `
            <button class="close-modal" title="닫기" ><i class="fas fa-times" style="color:white"></i></button>
            <!--<button class="close-modal" title="닫기" aria-label="닫기">✕</button>-->
            <img src="" alt="슬라이드" id="slideshow-img" style="display:none;">
      
            <video id="slideshow-video" class="slideshow-video" style="display:none;"
                   muted playsinline controls loop>
              <source id="slideshow-video-source" src="" type="video/mp4">
            </video>
        `;
        document.body.appendChild(modal);

        modal.querySelector('.close-modal').onclick = () => {
            clearInterval(slideShowTimer);
            // 영상 재생 중이면 멈추기
            const v = modal.querySelector("#slideshow-video");
            v.pause();
            v.currentTime = 0;
            modal.style.display = "none";
        };
    }
    modal.style.display = "flex";

    const imgEl = modal.querySelector("#slideshow-img");
    const videoEl = modal.querySelector("#slideshow-video");
    const videoSrcEl = modal.querySelector("#slideshow-video-source");

    // 확장자 판별용
    const videoExts = ['mp4', 'mov', 'mkv', 'avi']; // 필요시 webm 추가
    const imageBase = "https://chickchick.shop/image/images";
    const videoBase = "/video/temp-video"; // 템플릿에서 쓰던 경로와 맞추기

    function isVideo(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        return videoExts.includes(ext);
    }

    function setSlide(filename) {
        const enc = encodeURIComponent(filename);

        if (isVideo(filename)) {
            // IMG 숨기고 VIDEO 표시
            imgEl.style.display = "none";
            videoEl.style.display = "block";

            // 영상 src 세팅 (템플릿과 동일하게 dir/selected_dir를 필요하면 추가)
            // 기존 렌더링: /video/temp-video/{{ image }}?dir={{ dir }}&selected_dir={{ selected_dir }}
            videoSrcEl.src = `${videoBase}/${enc}?dir=refine`;
            videoEl.load();
            videoEl.play().catch(()=>{ /* 자동재생 막히면 무시 */ });

        } else {
            // VIDEO 숨기고 IMG 표시
            videoEl.pause();
            videoEl.style.display = "none";
            imgEl.style.display = "block";

            imgEl.src = `${imageBase}?filename=${enc}&dir=refine`;
        }
    }

    // 슬라이드 쇼 상태 초기화
    slideShowIdx = 0;
    slideShowImgs = fileList;

    // 첫 장 세팅
    setSlide(slideShowImgs[0]);

    // 기존 타이머 종료
    if (slideShowTimer) clearInterval(slideShowTimer);

    slideShowTimer = setInterval(() => {
        slideShowIdx = (slideShowIdx + 1) % slideShowImgs.length;
        setSlide(slideShowImgs[slideShowIdx]);
    }, 10000);
}

async function slideShow() {
    try {
        const resp = await fetch("/image/pages?slide=y&dir=refine");
        const imgList = await resp.json();  // 서버에서 JSON 배열로 이미지 URL 목록 반환한다고 가정

        if (!Array.isArray(imgList['slide_show_images']) || imgList['slide_show_images'].length === 0) {
            alert("이미지가 없습니다.");
            return;
        }
        showSlideshowModal(imgList['slide_show_images']);
    } catch (e) {
        alert("이미지 목록을 가져오는 데 실패했습니다.");
    }
}

// 슬라이드쇼 버튼 클릭 이벤트
slideShowBtn?.removeEventListener('click', slideShow)
slideShowBtn?.addEventListener('click', slideShow)


function shuffleImage() {
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

