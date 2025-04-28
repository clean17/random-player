/**
 *  WebRTC 연결 절차
 *
 * 1. Peer A: createOffer() → SDP 생성
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

const socket = io("https://chickchick.shop:3000", {
    secure: true, // HTTPS 사용
    transports: ["polling", "websocket"],
    // reconnection: true,              // 자동 재연결 활성화
    // reconnectionAttempts: 20,        // 최대 재시도 횟수
    // reconnectionDelay: 1000,         // 1초 간격
});

const myFace = document.getElementById('myFace');
const peerFace = document.getElementById("peerFace");
const muteBtn = document.getElementById('mute');
const peerAudioBtn = document.getElementById("peerAudio");
const cameraBtn = document.getElementById('camera');
const audioSelect = document.getElementById('audios');
const microphoneSelect = document.getElementById('microphones');
const swichCameraBtn = document.getElementById('switchCamera');
const roomName = 'nh';

let myStream;
let muted = false;
let cameraOff = false;
let myPeerConnection;
let myDataChannel;
let peerLeftTimeout;
let cameraOn = true;
let audioOn = false;
let micOn = false;
let isDragging = false;
let offsetX = 0;
let offsetY = 0;
let currentFacingMode = "user"; // 기본은 전면 카메라 (user)

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

// 연결된 오디오 리스트 option 렌더링
async function getAudios() {
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const audios = devices.filter(device => device.kind === 'audiooutput');
        const currentAudio = myStream.getAudioTracks()[0];
        audios.forEach(audio => {
            const option = document.createElement('option')
            option.value = audio.deviceId;
            option.innerText = audio.label;
            if (currentAudio.label == audio.label) {
                option.selected = true;
            }
            audioSelect?.appendChild(option);
        })
    } catch (err) {
        console.log(err);
        alert('오류발생 12 : '+ err)
    }
}

// 연결된 마이크 목록 렌더링
async function getMicrophones() {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const microphones = devices.filter(device => device.kind === "audioinput");

    microphoneSelect.innerHTML = ""; // 초기화

    microphones.forEach(device => {
        const option = document.createElement("option");
        option.value = device.deviceId;
        option.text = device.label || `Microphone ${microphoneSelect.length + 1}`;
        microphoneSelect.appendChild(option);
    });
}

async function getMedia(deviceId = null) {
    // 기존 스트림 종료
    if (myStream) {
        myStream.getTracks().forEach(track => track.stop());
        myStream = null;
    }

    // Constraints 설정
    let constraints;
    if (deviceId) {
        constraints = {
            audio: {
                deviceId: { exact: deviceId }
            },
            video: { facingMode: currentFacingMode }
        };
    } else {
        constraints = {
            audio: true,
            video: { facingMode: currentFacingMode }
        };
    }

    try {
        myStream = await navigator.mediaDevices.getUserMedia(constraints);
        console.log("myStream 연결 완료: ", myStream);

        myFace.srcObject = myStream;

        if (!deviceId) {
            await getAudios(); // 오디오 목록 갱신
            await getMicrophones();
        }

        // 처음 연결 시 마이크 off
        myStream.getAudioTracks().forEach(track => {
            track.enabled = false;
        });

        const videoTrack = myStream.getVideoTracks()[0];
        const settings = videoTrack.getSettings();

        const isFrontCamera = settings.facingMode === "user";
        const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);

        if (isFrontCamera && isMobile) {
            myFace.classList.add("mirror");
        } else {
            myFace.classList.remove("mirror");
        }

    } catch (err) {
        console.error("🎥 getMedia 에러:", err);
        alert("카메라 또는 마이크를 사용할 수 없습니다.\n권한 또는 다른 앱 확인이 필요합니다.");
    }
}

async function getMedia2(deviceId) {
    // 기존 스트림 종료
    if (myStream) {
        myStream.getTracks().forEach(track => track.stop());
        myStream = null;
    }

    const initialConstrains = { // false 로 설정하면 권한을 요청하지 않음 > 사용하지 않음
        audio: true,
        video: {
            facingMode: "user", // 전면 카메라
        },
    }
    const audioContrains = {
        audio: {
            deviceId: {
                exact: deviceId,
            },
        },
        video: true
    }

    try {
        // 웹캠은 사용중일때 접근 못함..
        myStream = await navigator.mediaDevices.getUserMedia(deviceId ? audioContrains : initialConstrains); // MediaStream
        console.log("myStream 보여줘 ---------------------- ",myStream);

        myFace.srcObject = myStream;
        if (!deviceId) {
            await getAudios();
        }
        // await getCameras() // 사용가능한 카메라 콘솔 출력

        /*myStream.getVideoTracks().forEach(track => {
            track.enabled = !track.enabled
        });*/
        // 처음 연결 시 마이크 off
        myStream.getAudioTracks().forEach(track => {
            track.enabled = false;
        });

        const videoTrack = myStream.getVideoTracks()[0];
        const settings = videoTrack.getSettings();

        // 전면 카메라 + 모바일인 경우에만 mirror 적용
        const isFrontCamera = settings.facingMode === "user";
        // const isMobile = /Mobi|Android/i.test(navigator.userAgent);
        const isMobile = /iPhone|iPad|iPod/i.test(navigator.userAgent);

        if (isFrontCamera && isMobile) {
            myFace.classList.add("mirror");
        } else {
            myFace.classList.remove("mirror");
        }
    } catch (err) {
        console.error("🎥 getMedia 에러:", err);
        alert("카메라 또는 마이크를 사용할 수 없습니다.\n권한 또는 다른 앱 확인이 필요합니다.");
    }
}

function handleMuteClick() {
    myStream.getAudioTracks().forEach(track => {
        track.enabled = !track.enabled
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
    currentFacingMode = currentFacingMode === "user" ? "environment" : "user";
    await getMedia(); // facingMode 바꿔서 새 스트림 가져옴
    if (myPeerConnection) {
        const videoTrack = myStream?.getVideoTracks()[0]; // ✅ 새 비디오 트랙 가져오기
        const videoSender = myPeerConnection.getSenders()
            .find(sender => sender.track && sender.track.kind === "video");
        if (videoSender && videoTrack) {
            await videoSender.replaceTrack(videoTrack); // ✅ 새 비디오 트랙 교체
        }

        const audioTrack  = myStream?.getAudioTracks()[0]; // 변경된 myStream
        const audioSender = myPeerConnection.getSenders()
            .find((sender) => sender.track.kind === "audio");
        if (audioSender && audioTrack) {
            await audioSender.replaceTrack(audioTrack); // ✅ 올바르게 오디오 트랙 교체
        }
    }
}

async function handleAudioChange() {
    await getMedia(audioSelect?.value);
    if (myPeerConnection) {
        const audioTrack  = myStream?.getAudioTracks()[0]; // 변경된 myStream
        const audioSender = myPeerConnection.getSenders()
            .find((sender) => sender.track.kind === "audio");
        if (audioSender && audioTrack) {
            await audioSender.replaceTrack(audioTrack); // ✅ 올바르게 오디오 트랙 교체
        }

        const videoTrack = myStream?.getVideoTracks()[0]; // ✅ 새 비디오 트랙 가져오기
        const videoSender = myPeerConnection.getSenders()
            .find(sender => sender.track && sender.track.kind === "video");
        if (videoSender && videoTrack) {
            await videoSender.replaceTrack(videoTrack); // ✅ 새 비디오 트랙 교체
        }
    }
}

async function handleMicrophoneChange() {
    const selectedDeviceId = microphoneSelect?.value;
    if (!selectedDeviceId) return;

    try {
        // 새로 선택한 마이크로 스트림 얻기
        const newStream = await navigator.mediaDevices.getUserMedia({
            audio: { deviceId: { exact: selectedDeviceId } },
            video: false // 변경하지 않는다
        });

        const newAudioTrack = newStream.getAudioTracks()[0];
        if (!newAudioTrack) {
            console.warn("🎤 새 마이크 트랙이 없습니다.");
            return;
        }

        if (myPeerConnection) {
            const audioSender = myPeerConnection.getSenders()
                .find(sender => sender.track && sender.track.kind === "audio");

            if (audioSender) {
                await audioSender.replaceTrack(newAudioTrack);
                console.log("🎤 마이크 트랙 교체 완료!");
            }
        }

        // 기존 myStream에 새 오디오 트랙만 교체
        const oldAudioTracks = myStream.getAudioTracks();
        oldAudioTracks.forEach(track => myStream.removeTrack(track)); // 기존 오디오 제거
        myStream.addTrack(newAudioTrack); // 새 오디오 추가

    } catch (err) {
        console.error("🎤 마이크 변경 중 에러:", err);
        alert("마이크 변경 중 문제가 발생했습니다.");
    }
}
muteBtn.addEventListener('click', handleMuteClick);
cameraBtn.addEventListener('click', handleCameraClick);
peerAudioBtn.addEventListener('click', handlePeerAudio);
audioSelect?.addEventListener('change', handleAudioChange);
microphoneSelect?.addEventListener('change', handleMicrophoneChange);
swichCameraBtn.addEventListener("click", handleCameraChange);

///////////////////////// Socket Code /////////////////////////////////////

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
    myPeerConnection.setRemoteDescription(offer);
    const answer = await myPeerConnection.createAnswer(); // offer를 받고 answer를 생성해 SDP 설정
    myPeerConnection.setLocalDescription(answer); // 각자의 peer는 local, remote를 설정
    socket.emit('answer', answer, roomName);
});

socket.on('answer', (answer) => {
    myPeerConnection.setRemoteDescription(answer); // 각 peer는 자신의 SDP 연결된 room의 SDP를 설정한다.
});

socket.on('ice', (ice) => {
    console.log("상대방과 연결되었습니다.");
    myPeerConnection.addIceCandidate(ice); // ICE(Interactive Connectivity Establishment); 서로 연결되는 경로를 찾아냄; 상대방의 후보 경로를 추가해서 연결을 시도
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
});
////////////////////////// RTC Code /////////////////////////////////////

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
    myStream.getTracks().forEach(track => {
        myPeerConnection.addTrack(track, myStream); // 각각의 track(영상/음성)을 상대방에게 전송하도록 연결
    });
};

function handleIce(data) {
    socket.emit('ice', data.candidate, roomName); // data.candidate 안에는 이 브라우저가 사용할 수 있는 연결 정보가 들어 있음
}

/*function handleAddStream(data) {
    const peerFace = document.getElementById('peerFace');
    peerFace.srcObject = data.stream;
}*/

function handleTrack(event) {
    const peerFace = document.getElementById('peerFace');
    const [stream] = event.streams;
    peerFace.srcObject = stream;
}


/////////////////////////// Choose a room ///////////////////////////////
async function handleWelcomeSubmit(event) {
    await getMedia(); // myStream 초기화
    makeConnection();
    socket.emit('join_room', roomName, username);
}

document.addEventListener("DOMContentLoaded", () => {
    handleWelcomeSubmit();
})

window.addEventListener("beforeunload", () => {
    socket.emit("leave_room", roomName); // 서버에 방 나간다고 알림
});


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