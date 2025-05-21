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
        console.log(key, files[key]);
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
                        url = "https://chickchick.shop/image/images?filename="+filename+"&dir=temp&selected_dir=chat";
                    } else if (isVideo) { // videoExts.includes(ext)
                        url = "https://chickchick.shop/video/temp-video/"+filename+"?dir=temp&selected_dir=chat";
                    } else { // 파일
                        url = "https://chickchick.shop/file/files?filename="+filename+"&dir=temp&selected_dir=chat";
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