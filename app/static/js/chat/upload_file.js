////////////////////////// File Upload /////////////////////////////

function uploadFile(event) {
    const files = event.target.files;

    if (!files || files.length === 0) {
        console.log("❌ 파일이 선택되지 않았습니다.");
        return;
    }

    // files 구조
    /*{
        "0": {},
        "1": {},
        "2": {}
    }*/
    Object.keys(files).forEach(key => {
        // console.log(key, files[key]);
    });

    const file = files[0];
    if (file) {
        const form = event.target.closest('form');  // 🔧 이걸 먼저 정의해줘야 아래에서 사용 가능

        if (submitted) {
            return;  // 이미 제출한 경우
        }
        submitted = true;

        // 버튼 비활성화해서 UI도 중복 방지
        const button = document.querySelector('label[for="file-input"]');
        if (button) {
            button.disabled = true;
        }

        const formData = new FormData(form);
        const xhr = new XMLHttpRequest();

        xhr.open('POST', '/upload/', true);

        // 진행률 표시
        xhr.upload.onprogress = function (e) {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                progressContainer.style.display = 'block';
                document.getElementById('progressBar').value = percent;
            }
        };

        // 완료 후 리다이렉트
        xhr.onload = function () {
            // submitted = false; // 다시 전송 가능하게
            if (xhr.status === 200) {
                submitted = false;
                progressContainer.style.display = 'none';

                const response = JSON.parse(xhr.responseText); // 서버 응답
                const files = response.files;

                // files는 서버에서 json 형태로 만들어줘야 한다
                files.forEach(file => {
                    const filename = file.name;
                    const isImage = file.type.startsWith("image/");
                    const isVideo = file.type.startsWith("video/");

                    /*const ext = file.split('.').pop().toLowerCase();

                    const imageExts = ["jpg", "jpeg", "png", "gif", "bmp", "webp"];
                    const videoExts = ["mp4", "webm", "mov", "ogg", "mkv"];*/

                    let url = '';
                    if (isImage) { // imageExts.includes(ext)
                        url = "https://chickchick.kr/image/images?filename="+filename+"&dir=temp&selected_dir=chat";
                    } else if (isVideo) { // videoExts.includes(ext)
                        url = "https://chickchick.kr/video/temp-video/"+filename+"?dir=temp&selected_dir=chat";
                    } else { // 파일
                        url = "https://chickchick.kr/file/files?filename="+filename+"&dir=temp&selected_dir=chat";
                    }

                    const msg = url.replace(/\n/g, "<br>").replace(/(<br>\s*)$/, "");  // 마지막 모든 <br> 제거
                    if (msg !== "") {
                        socket.emit("new_msg", { username, msg, room: roomName });
                    }
                })
            } else {
                submitted = false; // 다시 전송 가능하게
                alert('업로드 실패: ' + xhr.statusText);
                if (button) {
                    button.disabled = false;
                }
            }
        };

        xhr.onerror = function () {
            submitted = false;
            alert('서버에 연결할 수 없습니다.');
            if (button) {
                button.disabled = false;
                button.innerText = 'Start Upload';
            }
        };

        xhr.send(formData);
    }
}



(() => {
    const container = document.querySelector('.container');
    const plusLabel = container.querySelector('label[for="file-input"]'); // 기존 ＋ 라벨
    const fileInput = container.querySelector('#file-input');

    // 팝오버 엘리먼트 동적 추가(원하는 버튼만 수정해서 사용)
    const pop = document.createElement('div');
    pop.id = 'plusPopover';
    pop.setAttribute('role', 'menu');
    pop.innerHTML = `
    <div class="menu-scroll">
      <button class="pp-btn" data-action="upload">📁 파일 업로드</button>
      <button class="pp-btn" data-action="open-search">🔎 채팅 검색 열기</button>
      <hr style="border:none;height:1px;background:#eee;margin:6px 0;">
<!--      <button class="pp-btn" data-action="paste">📋 붙여넣기 업로드</button>-->
    <div class="pp-btn-row">
      <button class="pp-btn" data-action="good">👍</button>
      <button class="pp-btn" data-action="ok">👌</button>
      <button class="pp-btn" data-action="no">❌</button>
      <button class="pp-btn" data-action="question">❓</button>
    </div>
    </div>
  `;
    container.appendChild(pop);
    const menuScroll = pop.querySelector('.menu-scroll');

    const GAP = 8;    // 버튼과 팝오버 사이 간격
    let isOpen = false;

    // 팝오버 위치/크기 보정: 컨테이너 경계 내
    function placePopover() {
        const cRect = container.getBoundingClientRect();
        const bRect = plusLabel.getBoundingClientRect();

        // 1) 기본 배치: 버튼(라벨) 왼쪽 정렬, 버튼 위에 뜨게
        let left = bRect.left - cRect.left;
        pop.style.left = left + 'px';
        pop.style.top  = (bRect.top - cRect.top - GAP - pop.offsetHeight) + 'px';

        // 2) 우측 넘침 보정
        const pRect1 = pop.getBoundingClientRect();
        let overflowRight = pRect1.right - cRect.right;
        if (overflowRight > 0) {
            left -= overflowRight;
            if (left < 0) left = 0;
            pop.style.left = left + 'px';
        }
        // 3) 좌측 넘침 보정
        const pRect2 = pop.getBoundingClientRect();
        const overflowLeft = cRect.left - pRect2.left;
        if (overflowLeft > 0) {
            left += overflowLeft;
            pop.style.left = left + 'px';
        }

        // 4) 세로(위쪽 공간) 보정: 위 공간이 부족하면 내부 스크롤로 높이 제한
        const spaceAbove = (bRect.top - cRect.top) - GAP;
        const maxH = Math.max(80, Math.floor(spaceAbove - 12)); // 여유 조금
        menuScroll.style.maxHeight = maxH + 'px';

        // 높이 재계산 후 최종 top
        const newH = pop.offsetHeight;
        let top = (bRect.top - cRect.top) - GAP - newH;
        if (top < 0) top = 0; // 컨테이너 위로 못 나가게
        pop.style.top = top + 'px';
    }

    function openPopover() {
        // 먼저 표시해 크기 측정
        pop.classList.add('open');
        placePopover();
        isOpen = true;

        document.addEventListener('click', onDocClick, true);
        window.addEventListener('resize', placePopover);
        // 내부 스크롤 변화를 반영(채팅 영역 스크롤 포함)
        window.addEventListener('scroll', placePopover, true);
    }

    function closePopover() {
        pop.classList.remove('open');
        isOpen = false;

        document.removeEventListener('click', onDocClick, true);
        window.removeEventListener('resize', placePopover);
        window.removeEventListener('scroll', placePopover, true);
    }

    function onDocClick(e) {
        if (!isOpen) return;
        if (!pop.contains(e.target) && e.target !== plusLabel) {
            closePopover();
        }
    }

    // ＋ 라벨 클릭 시: 기본 파일열기 막고 팝오버 토글
    plusLabel.addEventListener('click', (e) => {
        e.preventDefault();       // label → file-input 기본 클릭 방지
        e.stopPropagation();
        isOpen ? closePopover() : openPopover();
    });

    // 메뉴 액션 연결(예시)
    pop.addEventListener('click', (e) => {
        const btn = e.target.closest('.pp-btn');
        if (!btn) return;
        const action = btn.dataset.action;

        if (action === 'upload') {
            fileInput?.click(); // 이때만 실제 파일 선택창 열기
        } else if (action === 'open-search') {
            const wrap = document.getElementById('chat-search-wrap');
            const panel = document.getElementById('chat-search-panel');
            if (wrap) wrap.style.display = 'block';
            if (panel) panel.hidden = false;
            document.getElementById('chat-search-input')?.focus();
        } else if (action === 'paste') {
            console.log('붙여넣기 업로드 트리거'); // 필요 시 구현
        } else if (action === 'good') {
            const msg = '<span style="color:green;">👍</span>';
            socket.emit("new_msg", { username, msg, room: roomName });
            socket.emit("stop_typing", {room: roomName, username });
        } else if (action === 'ok') {
            const msg = '<span style="color:blue;">👌</span>';
            socket.emit("new_msg", { username, msg, room: roomName });
            socket.emit("stop_typing", {room: roomName, username });
        } else if (action === 'no') {
            const msg = '<span style="color:red;">❌</span>';
            socket.emit("new_msg", { username, msg, room: roomName });
            socket.emit("stop_typing", {room: roomName, username });
        } else if (action === 'question') {
            const msg = '<span style="color:orange;">❓</span>';
            socket.emit("new_msg", { username, msg, room: roomName });
            socket.emit("stop_typing", {room: roomName, username });
        }

        closePopover();
    });

    // 키보드 접근성: 라벨에서 Enter/Space로 열기
    plusLabel.setAttribute('tabindex', '0');
    plusLabel.addEventListener('keydown', (e) => {
        if ((e.key === 'Enter' || e.key === ' ') && !isOpen) {
            e.preventDefault();
            openPopover();
        }
    });
})();