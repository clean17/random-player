/**
 *  WebRTC 연결 절차
 *
 * 1. Peer A: createOffer() → 세션 기술 프로토콜(SDP) 생성
 * 2. Peer A: setLocalDescription(offer)
 * 3. Peer A → Peer B: offer 전송 (socket.io 등 시그널링 서버 통해)
 *
 * 4. Peer B: setRemoteDescription(offer)
 * 5. Peer B: createAnswer()
 * 6. Peer B: setLocalDescription(answer)
 * 7. Peer B → Peer A: answer 전송
 *
 * 8. 서로 ICE candidate 교환 (네트워크 경로 협상)
 * 9. 연결 완료 (영상/음성/데이터 통신 가능)
 *
 * SDP: Session Description Protocol; 상대방에게 연결을 제안하기 위한 세션 설명 정보
 *     어떤 코덱을 지원하는지
 *     어떤 스트림이 준비돼 있는지 (영상/음성/데이터)
 *     ICE 후보 (후에 따로 전달)
 *     미디어 방향(sendrecv 등)
 *  --> "나랑 이렇게 연결할 수 있는데 괜찮아?"라는 제안서
 *
 *  ICE = Interactive Connectivity Establishment; 통신 가능한 경로 후보(candidate)
 *  연결을 위한 경로(IP + 포트 등)를 탐색하는 WebRTC 기술
 *  ICE는 가능한 모든 "연결 후보(IP 주소와 포트)"를 찾고
 * 이걸 상대방에게 보내서 서로 연결되는지 테스트하는 절차
 */

const myFace = document.getElementById('myFace');
const peerFace = document.getElementById("peerFace");
const recordCanvas = document.getElementById('recordCanvas');
const recordCtx = recordCanvas.getContext('2d');
const muteBtn = document.getElementById('mute');
const peerAudioBtn = document.getElementById("peerAudio");
const cameraBtn = document.getElementById('camera');
const audioInputSelect = document.getElementById('audioInputs');
const autdioSelectDiv = document.querySelector('.audio-select');
let switchCameraBtn = document.getElementById('switchCamera');
const captureBtn = document.getElementById('capture');
const recordBtn = document.getElementById('record');
const recordIcon = recordBtn.querySelector('i');
const roomName = 'nh';
const opacitySlider = document.getElementById('opacitySlider');

let myStream;
let muted = false;
let myPeerConnection;
let myDataChannel;
let peerLeftTimeout;
let cameraOn = true;
let audioOn = false;
let micOn = true; // mic 항상 on 수정 - 2026-01-30
let isDragging = false;
let offsetX = 0;
let offsetY = 0;
let currentFacingMode = "user"; // 기본은 전면 카메라 (user)
let currentMicrophoneDeviceId = null;
let globalRecoder = null;
let candidateQueue = [];


///////////////////////// Socket Code /////////////////////////////////////

const socket = io("https://chickchick.kr:3000", {
    secure: true, // HTTPS 사용
    transports: ["websocket", "polling"],
    reconnection: true,              // 자동 재연결 활성화
    reconnectionAttempts: 20,        // 최대 재시도 횟수
    reconnectionDelay: 1000,         // 1초 간격
});

// 내가 들어가면 다른 참가자들이 'welcome' 이벤트를 받는다
socket.on('welcome', async () => { // room에 있는 Peer들은 각자의 offer를 생성 및 제안
    if (peerLeftTimeout) {
        clearTimeout(peerLeftTimeout); // 타이머 취소
        peerLeftTimeout = null;
    }
    if (!myPeerConnection) {
        await makeConnection();
    }
    myDataChannel = myPeerConnection.createDataChannel('video/audio');
    myDataChannel.addEventListener('message', console.log); // message 이벤트 - send에 반응
    console.log('dataChannel 생성됨');
    const offer = await myPeerConnection.createOffer();
    myPeerConnection.setLocalDescription(offer); // 각자의 offer로 SDP(Session Description Protocol) 설정
    socket.emit('offer', offer, roomName); // 만들어진 offer를 전송
});

socket.on('offer', async (offer) => {
    myPeerConnection.addEventListener('datachannel', event => { // datachannel 감지
        myDataChannel = event.channel;
        myDataChannel.addEventListener('message', console.log);
    });
    /**
     * WebRTC는 브라우저끼리 직접 연결을 하기 때문에
     * 브라우저 A가 "나는 이런 정보로 연결할 준비됐어"라고 알려줘야
     * 브라우저 B가 그에 맞춰 연결 정보를 세팅할 수 있다
     * 'offer-answer' SDP 핸드셰이크
     * 각 offer 마다 세션을 생성 -> 새로운 Web RTC 연결을 초기화
     * 세션 업데이트 : 원격 peer의 새로운 offer 정보로 업데이트
     */
    await myPeerConnection.setRemoteDescription(offer);
    const answer = await myPeerConnection.createAnswer(); // offer를 받고 answer를 생성해 SDP 설정
    myPeerConnection.setLocalDescription(answer); // 각자의 peer는 local, remote를 설정
    socket.emit('answer', answer, roomName);
});

socket.on('answer', async (answer) => {
    await myPeerConnection.setRemoteDescription(answer); // 각 peer는 자신의 SDP 연결된 room의 SDP를 설정한다.
    candidateQueue.forEach(c => myPeerConnection.addIceCandidate(c));
    candidateQueue = [];
});

socket.on('ice', (ice) => {
    onIceCandidateReceived(ice);  // ICE(Interactive Connectivity Establishment); 서로 연결되는 경로를 찾아냄; 상대방의 후보 경로를 추가해서 연결을 시도
});

socket.on("peer_left", () => {
    // 비디오 정리만 하고 연결은 유지
    peerFace.srcObject = null;
    console.log("상대방이 나갔습니다");

    peerLeftTimeout = setTimeout(() => {
        console.log("10초 지남, 연결 닫음");
        myPeerConnection?.close();
        myPeerConnection = null;
    }, 10000); // 10초 대기
});

socket.on("force_disconnect", () => {
    console.log("⚠️ 다른 기기에서 로그인되어 연결 종료됨");

    // 연결 정리
    if (myPeerConnection) {
        myPeerConnection.close();
        myPeerConnection = null;
    }

    if (myDataChannel) {
        myDataChannel.close();
        myDataChannel = null;
    }

    socket.disconnect(); // 소켓도 끊기
    window.location.href = '/';

    // 부모에게 전송
    window.parent.postMessage("force-close", "*");
});

// ICE 후보가 먼저 도착했을 경우, 큐에 넣고 대기, 시그널링 순서가 뒤죽박죽이어도 오류 없음
function onIceCandidateReceived(candidate) {
    // if (remoteDescriptionSet) {
    if (myPeerConnection.signalingState === "stable" || myPeerConnection.remoteDescription) {
        myPeerConnection.addIceCandidate(candidate);
    } else {
        console.log("ICE 후보 대기열에 보관:", candidate);
        candidateQueue.push(candidate);
    }
}


//////////////////////////////// Web RTC ///////////////////////////////////

// 연결된 카메라 리스트 출력
async function getCameras() {
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const cameras = devices.filter(device => device.kind === 'videoinput');
        console.log(cameras);
    } catch (err) {
        console.log(err);
    }
}

// 연결된 오디오 입력 리스트 option 렌더링
async function getAudioInputs() {
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const audioInputs = devices.filter(device => device.kind === "audioinput");
        // console.log(audioInputs)

        const currentAudio = myStream.getAudioTracks()[0];
        audioInputSelect.innerHTML = ""; // 초기화

        audioInputs.forEach(audio => {
            const option = document.createElement('option')
            option.value = audio.deviceId;
            option.text = audio.label || `Microphone ${audioInputs.length + 1}`;
            if (currentAudio.label == audio.label) {
                option.selected = true;
            }
            audioInputSelect?.appendChild(option);
        })
    } catch (err) {
        console.log(err);
        alert('오류발생 : '+ err)
    }
}


async function getMedia(audioDeviceId = null, keepVideo = true,  switchCamera = false) {
    // 기존 스트림 종료
    if (myStream) {
        myStream.getTracks().forEach(track => track.stop());
        myStream = null;
    }

    /*let constraints = {
        audio: audioDeviceId ? { deviceId: { exact: audioDeviceId }} : false, // 모바일은 오디오 입출력 장치를 하나로 묶어서 관리한다 > 이어폰에서 폰으로 마이크를 변경하면 스피커도 묶여서 변경된다
        video: keepVideo ? { facingMode: currentFacingMode } : false
    };*/

    let constraints = {
        audio: true, // 오디오 사용하겠다
        video: true  // 비디오 사용하겠다
    };

    try {
        myStream = await navigator.mediaDevices.getUserMedia(constraints);
        // console.log("myStream 연결 완료: ", myStream);

        const audioTrack = myStream.getAudioTracks()[0];
        const audioSettings = audioTrack.getSettings();
        currentMicrophoneDeviceId = audioSettings.deviceId || null; // 필요없는지 테스트 필요
        console.log("🎤 현재 사용증인 마이크 deviceId:", currentMicrophoneDeviceId);

        const videoTrack = myStream?.getVideoTracks()[0];
        const videoSettings = videoTrack.getSettings();
        console.log("🎥 현재 사용 중인 카메라 deviceId:", videoSettings.deviceId);

        // makeConnection() 함수가 스트림을 보낸다.

        myFace.srcObject = myStream;

        /*if (audioDeviceId) {
            await getAudioInputs();
        }*/
        await getAudioInputs();

        // 처음 연결 시 마이크 off
        if (!switchCamera) {
            myStream.getAudioTracks().forEach(track => {
                // if (username !== 'nh824') {
                    track.enabled = true;  // 최초 mic on 변경 - 2026.02.06
                // }
            });
        }

        faceMirror(videoTrack);

    } catch (err) {
        console.error("🎥 getMedia 에러:", err);
        alert("카메라 또는 마이크를 사용할 수 없습니다.\n권한 또는 다른 앱 확인이 필요합니다.");
    }
}

async function updatePeerConnection() {
    if (myPeerConnection) {
        // 오디오 트랙 교체
        const audioTrack = myStream?.getAudioTracks()[0];
        const audioSender = myPeerConnection.getSenders()
            .find(sender => sender.track?.kind === "audio");
        if (audioSender && audioTrack) {
            await audioSender.replaceTrack(audioTrack);
        }

        // 비디오 트랙 교체
        const videoTrack = myStream?.getVideoTracks()[0];
        const videoSender = myPeerConnection.getSenders()
            .find(sender => sender.track?.kind === "video");
        if (videoSender && videoTrack) {
            await videoSender.replaceTrack(videoTrack);
        }
    }
}


/**
 * WebRTC 연결을 설정
 * 내 스트림(영상/음성)을 상대방에게 전송할 준비를 마친다
 */
async function makeConnection() { // 연결을 만든다.
    myPeerConnection = new RTCPeerConnection({
        iceServers: [ // STUN; 내 외부 IP를 알려주는 서버 (ICE 후보 생성을 도와줌)
            {
                urls: [
                    'stun:stun.l.google.com:19302',
                    'stun:stun1.l.google.com:19302',
                    'stun:stun2.l.google.com:19302',
                    'stun:stun3.l.google.com:19302'
                ]
            }
            /*{
                urls: "turn:your.turn.server:3478",
                username: "user",
                credential: "pass"
            }*/
        ]
    });
    // icecandidate; 연결 가능한 네트워크 경로(ICE candidate; IP + 포트)가 발견되면 발생하는 이벤트
    myPeerConnection.addEventListener('icecandidate', handleIce); // 두 Peer사이의 가능한 모든 경로를 수집하고 다른 Peer에 전송
    // myPeerConnection.addEventListener('addstream', handleAddStream);
    myPeerConnection.addEventListener('track', handleTrack);

    // 내 카메라/마이크 스트림을 WebRTC 연결에 추가
    if (myStream) {
        myStream.getTracks().forEach(track => {
            myPeerConnection.addTrack(track, myStream); // 각각의 track(영상/음성)을 상대방에게 전송하도록 연결
        });
    }
};

function handleIce(data) {
    socket.emit('ice', data.candidate, roomName); // data.candidate 안에는 이 브라우저가 사용할 수 있는 연결 정보가 들어 있음
}

/*function handleAddStream(data) {
    const peerFace = document.getElementById('peerFace');
    peerFace.srcObject = data.stream;
}*/

function handleTrack(event) {
    const [stream] = event.streams;
    peerFace.srcObject = stream;

    peerFace.onloadedmetadata = () => {
        recordCanvas.width = peerFace.videoWidth || 1280;
        recordCanvas.height = peerFace.videoHeight || 720;
        startDrawingLoop(peerFace, peerFace.videoWidth, peerFace.videoHeight);

        const videoTrack = stream.getVideoTracks()[0];
        const settings = videoTrack.getSettings();
        const originalFps = settings.frameRate || 30;
        const canvasStream = recordCanvas.captureStream(originalFps);

        // 무음이면 노이즈 삽입 ? 테스트
        if (stream.getAudioTracks().length === 0) {
            // 무음 트랙을 강제로 삽입하는 코드 예시
            const audioCtx = new AudioContext();
            const oscillator = audioCtx.createOscillator();
            const dst = audioCtx.createMediaStreamDestination();
            oscillator.connect(dst);
            oscillator.start();
            canvasStream.addTrack(dst.stream.getAudioTracks()[0]);
            // oscillator.stop()은 필요에 따라 적절히 관리
        }

        // 1. 오디오 트랙이 있다면 canvasStream에 추가
        /*stream.getAudioTracks().forEach(track => {
            canvasStream.addTrack(track);
        });*/

        //✅ 2. 대안: MediaStreamAudioDestinationNode를 사용해 오디오 수동 믹싱
        const audioContext = new AudioContext();
        const dest = audioContext.createMediaStreamDestination();

        const source = audioContext.createMediaStreamSource(stream);
        source.connect(dest); // 상대 음성

        // canvas stream과 믹스
        dest.stream.getAudioTracks().forEach(track => {
            canvasStream.addTrack(track);
        });

        if (!globalRecoder) {
            globalRecoder = new BufferedRecorder(canvasStream, {
                chunkDuration: 5,
                bufferDuration: 30
            });
            globalRecoder.start();
        }
    };
}

/////////////////////////// Button Event ////////////////////////////

function handleMuteClick() {
    myStream.getAudioTracks().forEach(track => {
        // if (username !== 'nh824') {
            track.enabled = !track.enabled;
        // }
    });
    micOn = !micOn;
    const micIcon = document.getElementById("micIcon");
    micIcon.className = micOn ? "fas fa-microphone" : "fas fa-microphone-slash";
}

function handleCameraClick() {
    myStream.getVideoTracks().forEach(track => {
        track.enabled = !track.enabled
    });
    cameraOn = !cameraOn;
    const cameraIcon = document.getElementById("cameraIcon");
    cameraIcon.className = cameraOn ? "fas fa-video" : "fas fa-video-slash";
}

function handlePeerAudio() {
    audioOn = !audioOn;
    peerFace.muted = !audioOn;

    const icon = document.getElementById("audioIcon");
    icon.className = audioOn ? "fas fa-volume-up" : "fas fa-volume-mute";
}

async function handleCameraChange() {
    if (myStream) {
        myStream.getVideoTracks().forEach(track => track.stop());
    }

    let newVideoStream;

    currentFacingMode = currentFacingMode === "user" ? "environment" : "user";
    const isIphone = /iPhone|iPad|iPod/i.test(navigator.userAgent);
    if (isIphone) {
        newVideoStream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: currentFacingMode }});
    } else {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const selectedCameraDeviceId = currentFacingMode === "user" ? devices[3].deviceId : devices[1].deviceId;
        newVideoStream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { deviceId: { exact: selectedCameraDeviceId } }});
    }

    const newVideoTrack = newVideoStream.getVideoTracks()[0];

    // 기존 스트림에서 교체
    myStream.getVideoTracks().forEach(t => {
        myStream.removeTrack(t);
        t.stop();
    });
    myStream.addTrack(newVideoTrack);

    await updatePeerConnection();
    faceMirror(newVideoTrack);
}

async function handleAudioInputChange() {
    if (myStream) {
        // myStream.getAudioTracks().forEach(track => track.stop());
    }

    const newAudioStream = await navigator.mediaDevices.getUserMedia({ audio: { deviceId: { exact: audioInputSelect?.value } }, video: false });
    const newAudioTrack = newAudioStream.getAudioTracks()[0];

    // 기존 스트림에서 교체
    myStream.getAudioTracks().forEach(t => {
        myStream.removeTrack(t);
        t.stop();
    });
    myStream.addTrack(newAudioTrack);

    await updatePeerConnection();
    await getAudioInputs();
}

function recordPeerStream() {
    recordBtn.classList.add('clicked');
    recordIcon.className = 'fas fa-circle text-red-500';
    setTimeout(() => {
        recordBtn.classList.remove('clicked')
        recordIcon.className = 'fas fa-circle-dot';
    }, 500);

    globalRecoder.uploadBufferedBlob('/upload', 'video-call').then(() => {});
}

function faceMirror(videoTrack) {
    const videoSettings = videoTrack.getSettings();
    const isFrontCamera = videoSettings.facingMode === "user";
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);

    if (isFrontCamera && isMobile) {
        myFace.classList.add("mirror");
    } else {
        myFace.classList.remove("mirror");
    }
}

muteBtn.addEventListener('click', handleMuteClick); // 내 마이크 on/off
cameraBtn.addEventListener('click', handleCameraClick); // 내 카메라 on/off
peerAudioBtn.addEventListener('click', handlePeerAudio); // 상대 오디오 on/off

captureBtn.addEventListener('click', captureAndUpload); // 캡쳐
recordBtn.addEventListener('click', recordPeerStream); // 녹화

audioInputSelect?.addEventListener('change', handleAudioInputChange); // 내 마이크 전환 (모바일에서는 마이크랑 같이 묶여 있음)


/////////////////////////// Drag Event //////////////////////////////////

// 📱 공통 좌표 추출 함수 (마우스 or 터치 구분)
function getClientPosition(e) {
    if (e.touches && e.touches.length > 0) {
        return {
            x: e.touches[0].clientX,
            y: e.touches[0].clientY
        };
    } else {
        return {
            x: e.clientX,
            y: e.clientY
        };
    }
}

function startDrag(e) {
    isDragging = true;
    const pos = getClientPosition(e);
    offsetX = pos.x - myFace.offsetLeft;
    offsetY = pos.y - myFace.offsetTop;
    e.preventDefault(); // 터치 스크롤 방지
}


function onDrag(e) {
    if (!isDragging) return;
    const pos = getClientPosition(e);

    const x = pos.x - offsetX;
    const y = pos.y - offsetY;

    const windowWidth = window.innerWidth;
    const windowHeight = window.innerHeight;

    const elemWidth = myFace.offsetWidth;
    const elemHeight = myFace.offsetHeight;

    // ✅ 화면(뷰포트)을 벗어나지 않도록 제한
    const clampedX = Math.max(0, Math.min(x, windowWidth - elemWidth));
    const clampedY = Math.max(0, Math.min(y, windowHeight - elemHeight));

    myFace.style.left = `${clampedX}px`;
    myFace.style.top = `${clampedY}px`;
    myFace.style.right = "auto";
    myFace.style.bottom = "auto";

    // 버튼을 myFace의 좌하단에 위치시키기
    const btnWidth = switchCameraBtn.offsetWidth;
    const btnHeight = switchCameraBtn.offsetHeight;
    switchCameraBtn.style.left = `${clampedX-15}px`;
    switchCameraBtn.style.top = `${clampedY-15}px`;
    // switchCameraBtn.style.top = `${clampedY + elemHeight - btnHeight - 10}px`;
    switchCameraBtn.style.right = "auto";
    switchCameraBtn.style.bottom = "auto";
    switchCameraBtn.style.position = "absolute";
}

function endDrag() {
    isDragging = false;
}

// ✅ 마우스 이벤트
myFace.addEventListener("mousedown", startDrag);
document.addEventListener("mousemove", onDrag);
document.addEventListener("mouseup", endDrag);

// ✅ 터치 이벤트
myFace.addEventListener("touchstart", startDrag, { passive: false });
document.addEventListener("touchmove", onDrag, { passive: false });
document.addEventListener("touchend", endDrag);

function setSwitchCameraPos() {
    if (!switchCameraBtn) {
        switchCameraBtn = document.createElement('button');
        switchCameraBtn.id = 'switchCamera';
        switchCameraBtn.title = 'Switch Camera';
        switchCameraBtn.className = 'circle-button';

        const icon = document.createElement('i');
        icon.id = 'switchCameraIcon';
        icon.className = 'fas fa-sync-alt';
        switchCameraBtn.appendChild(icon);

        document.body.appendChild(switchCameraBtn);
    }

    const rect = myFace.getBoundingClientRect();
    const btnWidth = switchCameraBtn.offsetWidth;
    const btnHeight = switchCameraBtn.offsetHeight;
    switchCameraBtn.style.left = rect.left - 15 + "px";
    switchCameraBtn.style.top = rect.top - 15 + "px";
    // switchCameraBtn.style.top = (rect.top + myFace.offsetHeight - btnHeight - 10) + "px";
    switchCameraBtn.style.position = "absolute";
    switchCameraBtn.style.zIndex = '10';
    switchCameraBtn.addEventListener("click", handleCameraChange); // 내 카메라 전환
    setVideoCallButtonsOpacity(0.5);
}

/////////////////////////////// SAVE SCREENSHOT /////////////////////////////////


// 캔버스에 그려서 녹화
function startDrawingLoop(video, width, height) {
    function loop() {
        recordCtx.drawImage(video, 0, 0, width, height);
        requestAnimationFrame(loop);
    }
    loop();
}

function showFlashEffect() {
    const flash = document.getElementById("flash");
    flash.classList.add("active");
    setTimeout(() => flash.classList.remove("active"), 100);
}

function captureAndUpload() {
    const canvas = document.createElement('canvas');
    canvas.width = peerFace.videoWidth;
    canvas.height = peerFace.videoHeight;

    const ctx = canvas.getContext('2d');
    ctx.drawImage(peerFace, 0, 0, canvas.width, canvas.height);

    showFlashEffect();
    captureBtn.classList.add("clicked");
    setTimeout(() => captureBtn.classList.remove("clicked"), 300);

    canvas.toBlob(blob => {
        const formData = new FormData();
        formData.append('files[]', blob, `video-call_`+getNowTimestamp()+`_screenshot.png`);
        formData.append('title', 'video-call');

        fetch('/upload', {
            method: 'POST',
            body: formData
        }).then(res => {
            if (res.ok) {
                showDebugToast('✅ 캡쳐 성공');
            } else {
                showDebugToast('❌ 캡쳐 실패');
            }
        });
    }, 'image/png');
}

/////////////////////// Control Buttons Opacity ///////////////////////

function setVideoCallButtonsOpacity(opacity) {
    document.querySelectorAll('.fas').forEach(btn => {
        btn.closest('button').style.opacity = opacity;
    });
    autdioSelectDiv.style.opacity = opacity;
}

opacitySlider.addEventListener('input', (e) => {
    const opacity = e.target.value;
    setVideoCallButtonsOpacity(opacity)
});




document.addEventListener("DOMContentLoaded", async () => {
    setVideoCallButtonsOpacity(0.5);
    await getMedia(); // stream 초기화, RTCrtpSender에 stream track 추가, 카메라 설정, 마이크 설정
    await makeConnection();
    socket.emit('join_room', roomName, username);
    setSwitchCameraPos();


    // console.log('sender', myPeerConnection.getSenders())
})

window.addEventListener("beforeunload", () => {
    socket.emit("leave_room", roomName, username); // 서버에 방 나간다고 알림
    if (globalRecoder) globalRecoder.stop();
});