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
    transports: ["websocket", "polling"],
    reconnection: true,              // 자동 재연결 활성화
    reconnectionAttempts: 20,        // 최대 재시도 횟수
    reconnectionDelay: 1000,         // 1초 간격
    timeout: 20000,                  // 서버로부터 응답 기다리는 시간 (기본값)
});

const myFace = document.getElementById('myFace');
const muteBtn = document.getElementById('mute');
const cameraBtn = document.getElementById('camera');
const audioSelect = document.getElementById('audios');
const roomName = 'nh';

let myStream;
let muted = false;
let cameraOff = false;
let myPeerConnection;
let myDataChannel;

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
        const audios = devices.filter(device => device.kind === 'audioinput');
        const currentAudio = myStream.getAudioTracks()[0];
        audios.forEach(audio => {
            const option = document.createElement('option')
            option.value = audio.deviceId;
            option.innerText = audio.label;
            if (currentAudio.label == audio.label) {
                option.selected = true;
            }
            audioSelect.appendChild(option);
        })
    } catch (err) {
        console.log(err);
        alert('오류발생 12 : '+ err)
    }
}

async function getMedia(deviceId) {
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
        // console.log("myStream 보여줘 ---------------------- ",myStream);
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

        /*const videoTrack = myStream.getVideoTracks()[0];
        const settings = videoTrack.getSettings();

        // 전면 카메라 + 모바일인 경우에만 mirror 적용
        const isFrontCamera = settings.facingMode === "user";
        const isMobile = /Mobi|Android/i.test(navigator.userAgent);

        if (isFrontCamera && isMobile) {
            myFace.classList.add("mirror");
        } else {
            myFace.classList.remove("mirror");
        }*/
    } catch (err) {
        console.error("🎥 getMedia 에러:", err);
        alert("카메라 또는 마이크를 사용할 수 없습니다.\n권한 또는 다른 앱 확인이 필요합니다.");
    }
}

function handleMuteClick() {
    myStream.getAudioTracks().forEach(track => {
        track.enabled = !track.enabled
    });
    if (!muted) {
        muteBtn.innerText = "Audio On"
        muted = true;
    } else {
        muteBtn.innerText = "Audio Off"
        muted = false;
    }
}

function handleCameraClick() {
    myStream.getVideoTracks().forEach(track => {
        track.enabled = !track.enabled
    });
    if (cameraOff) {
        cameraBtn.innerText = "Camera On"
        cameraOff = false;
    } else {
        cameraBtn.innerText = "Camera Off"
        cameraOff = true;
    }
}

/*async function handleCameraChange() {
    await getMedia(videoSelect.value);
    if (myPeerConnection) {
        const videoSender = myPeerConnection.getSenders()
            .find((sender) => sender.track.kind === "video");
        console.log(videoSender);
    }
}*/

async function handleAudioChange() {
    await getMedia(audioSelect.value);
    if (myPeerConnection) {
        const videoTrack = myStream?.getVideoTracks()[0]; // 변경된 myStream
        const audioSender = myPeerConnection.getSenders()
            .find((sender) => sender.track.kind === "audio");
        audioSender.replaceTrack(videoTrack);
    }
}

muteBtn.addEventListener('click', handleMuteClick);
cameraBtn.addEventListener('click', handleCameraClick);
audioSelect.addEventListener('input', handleAudioChange);

///////////////////////// Socket Code /////////////////////////////////////

socket.on('welcome', async () => { // room에 있는 Peer들은 각자의 offer를 생성 및 제안
    myDataChannel = myPeerConnection.createDataChannel('chat');
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
});

////////////////////////// RTC Code /////////////////////////////////////

function makeConnection() { // 연결을 만든다.
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
    // icecandidate; 연결 가능한 네트워크 경로(ICE candidate)가 발견
    myPeerConnection.addEventListener('icecandidate', handleIce); // 두 Peer사이의 가능한 모든 경로를 수집하고 다른 Peer에 전송
    myPeerConnection.addEventListener('addstream', handleAddStream);
    myPeerConnection.addEventListener('track', handleTrack);

    // 내 카메라/마이크 스트림을 WebRTC 연결에 추가
    myStream.getTracks().forEach(track => {
        myPeerConnection.addTrack(track, myStream); // 각각의 track(영상/음성)을 상대방에게 전송하도록 연결
    });
};

function handleIce(data) {
    socket.emit('ice', data.candidate, roomName); // data.candidate 안에는 이 브라우저가 사용할 수 있는 연결 정보가 들어 있음
}

function handleAddStream(data) {
    const peerFace = document.getElementById('peerFace');
    peerFace.srcObject = data.stream;

    // track 이벤트로 들어온 경우, 코드 분리
    /*if (data.streams && data.streams[0]) {
        peerFace.srcObject = data.streams[0];
        return;
    }

    // addstream 이벤트로 들어온 경우 (구형 브라우저 대응)
    if (data.stream) {
        peerFace.srcObject = data.stream;
    }*/
}

function handleTrack(event) {
    const peerFace = document.getElementById('peerFace');
    const [stream] = event.streams;
    peerFace.srcObject = stream;
}


/////////////////////////// Choose a room ///////////////////////////////
async function handleWelcomeSubmit(event) {
    await getMedia(); // myStream 초기화
    makeConnection();
    socket.emit('join_room', roomName);
}

document.addEventListener("DOMContentLoaded", () => {
    handleWelcomeSubmit();
})

window.addEventListener("beforeunload", () => {
    socket.emit("leave_room", roomName); // 서버에 방 나간다고 알림
});