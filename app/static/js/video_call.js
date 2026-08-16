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
const myFaceWrapper = document.getElementById('myFaceWrapper');
const peerFace = document.getElementById("peerFace");
const recordCanvas = document.getElementById('recordCanvas');
const recordCtx = recordCanvas.getContext('2d');
const muteBtn = document.getElementById('mute');
const peerAudioBtn = document.getElementById("peerAudio");
const cameraBtn = document.getElementById('camera');
const audioInputSelect = document.getElementById('audioInputs');
const autdioSelectDiv = document.querySelector('.audio-select');
const switchCameraBtn = document.getElementById('switchCamera');
const captureBtn = document.getElementById('capture');
const recordBtn = document.getElementById('record');
const recordIcon = recordBtn.querySelector('i');
const roomName = 'nh';
const opacitySlider = document.getElementById('opacitySlider');
const callStatusOverlay = document.getElementById('callStatusOverlay');
const callStatusText = document.getElementById('callStatusText');

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
let welcomeCount = 0;
let prevViewportW = window.innerWidth;
let prevViewportH = window.innerHeight;

const iceTypeCount = { host: 0, srflx: 0, relay: 0, unknown: 0 };

// 모바일은 스피커폰(화면 보며 통화)이라 마이크와의 거리가 멀어 AGC(자동 게인)로 게인을 올려줘야
// 목소리가 작게/멀게 들리지 않는다. 데스크톱은 반대로 AGC 워밍업 구간 때문에 꺼둔 상태를 유지한다.
const isMobileDevice = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);

function rtcLog(label, ...args) {
    const state = myPeerConnection
        ? `[sig:${myPeerConnection.signalingState}|ice:${myPeerConnection.iceConnectionState}|conn:${myPeerConnection.connectionState}]`
        : '[no-pc]';
    console.log(`[RTC] ${label} ${state}`, ...args);
}

// 연결이 오래 걸릴 때 "안 되는 줄" 알고 나가버리는 걸 막기 위한 상태 표시.
// subtle=true: 상대가 아직 없거나 재시도를 포기한 뒤의 "대기 중" — 화면을 가리지 않는 작은 배지.
// subtle=false(기본): welcome/offer를 실제로 받아 지금 협상 중일 때만 — 진한 오버레이+스피너.
// 이 둘을 구분하는 이유는, 이 화면이 계속 켜둔 채로 업무 중 가끔 들여다보는 용도로도 쓰이기 때문에
// 상대가 아예 없을 때도 "연결 중"처럼 보이는 문구를 계속 띄우면 실제 상황과 안 맞아서다.
function showCallStatus(text, { subtle = false } = {}) {
    if (!callStatusOverlay) return;
    if (callStatusText) callStatusText.textContent = text;
    callStatusOverlay.classList.toggle('subtle', subtle);
    callStatusOverlay.classList.remove('hidden');
    // 상대가 나가도 화면을 검은색으로 리셋하지 않고 마지막 프레임을 유지하되, 지금 라이브가
    // 아니라는 걸 알 수 있게 어둡게/탈색해서 보여준다 (완전 검은 화면은 고장처럼 보이고,
    // 그대로 생생하게 두면 멈춘 건지 헷갈리기 때문)
    peerFace.classList.add('dimmed');
}

function hideCallStatus() {
    if (!callStatusOverlay) return;
    callStatusOverlay.classList.add('hidden');
    peerFace.classList.remove('dimmed');
}


///////////////////////// Socket Code /////////////////////////////////////

const socket = io("https://chickchick.kr:3000", {
    secure: true, // HTTPS 사용
    transports: ["websocket", "polling"],
    reconnection: true,              // 자동 재연결 활성화
    reconnectionAttempts: 20,        // 최대 재시도 횟수
    reconnectionDelay: 1000,         // 1초 간격
});

///////////////////////// 연결 재협상/재시도 //////////////////////////////

const CONNECT_WATCHDOG_MS = 4000;      // offer/answer 보낸 뒤 연결 확인까지 기다리는 시간 (기존 8000)
const ICE_DISCONNECT_GRACE_MS = 2500;  // iceConnectionState=disconnected 후 자연 복구를 기다리는 시간
const NEGOTIATION_WAIT_MS = 3000;      // welcome/answer가 잘못된 state에서 온 경우 재시도 대기 시간 (기존 5000)
const MAX_NEGOTIATION_RETRY = 6;

let connectWatchdogTimer = null;
let iceDisconnectTimer = null;
let negotiationRetryCount = 0;
let restartInFlight = false;
// 실제로 재협상/재생성이 필요했던 "진짜" 끊김에서 복구했을 때만 채팅에 재연결을 알린다
// (아주 짧은 네트워크 흔들림까지 매번 알리면 그 자체가 스팸이 된다)
let announceReconnectOnNextConnect = false;

function clearConnectWatchdog() {
    clearTimeout(connectWatchdogTimer);
    connectWatchdogTimer = null;
}

function clearIceDisconnectTimer() {
    clearTimeout(iceDisconnectTimer);
    iceDisconnectTimer = null;
}

// 재시도 진입점 — 여러 감지 경로(watchdog/iceConnectionState/connectionState)가 겹쳐 들어와도
// 카운터 하나로 상한을 공유하고, 같은 순간 중복 재협상이 나가지 않도록 막는다
function tryRestartNegotiation(reason) {
    if (restartInFlight) return;
    if (negotiationRetryCount >= MAX_NEGOTIATION_RETRY) {
        rtcLog(`연결 재시도 포기 (${MAX_NEGOTIATION_RETRY}회 초과) — ${reason}`);
        // 상대가 나갔거나 연결이 아예 끊긴 상태일 수 있으니, "재연결 중"처럼 계속 진행 중인 척
        // 띄우지 않고 다시 조용한 대기 상태로 돌아간다 (새 welcome이 오면 그때 다시 활성 표시로 전환됨)
        showCallStatus('상대방을 기다리는 중', { subtle: true });
        return;
    }
    negotiationRetryCount++;
    restartInFlight = true;
    announceReconnectOnNextConnect = true;
    rtcLog(`재협상 시도 #${negotiationRetryCount} — ${reason}`);
    if (negotiationRetryCount === 1) {
        // 첫 재시도는 진짜 잠깐의 네트워크 문제일 수 있으니 "재연결 중"으로 활성 표시
        showCallStatus('연결이 불안정해요. 재연결 시도 중...');
    } else {
        // 한 번 재시도해도 안 됐다면 상대가 나갔을 가능성이 더 높다. 재시도는 백그라운드에서
        // 계속하되(최대 MAX_NEGOTIATION_RETRY회), 화면엔 "재연결 중"을 과장해서 계속 띄우지 않고
        // 조용한 대기 상태로 보여준다.
        showCallStatus('상대방을 기다리는 중', { subtle: true });
    }
    restartNegotiation().finally(() => {
        restartInFlight = false;
    });
}

// offer/answer를 보낸 뒤 CONNECT_WATCHDOG_MS 안에 연결이 안 되면 ICE 재시작으로 재시도한다.
// 단, iceConnectionState가 이미 connected/completed인데 connectionState만 아직 connecting인 건
// DTLS 핸드셰이크가 마무리되는 정상적인 지연이다 — 이때 재시작을 걸면 진행 중인 DTLS를 처음부터
// 다시 시작시켜서 영원히 connecting에 머무는 자기 폭주(양쪽이 서로 계속 재시작을 걸어 매초 offer가
// 오가는 상태)를 만든다. 그래서 ICE가 이미 붙었으면 재시작하지 않고 기다린다 — 진짜 실패하면
// connectionState=failed로 넘어가고 그건 connectionstatechange 핸들러가 따로 처리한다.
function armConnectWatchdog() {
    clearConnectWatchdog();
    connectWatchdogTimer = setTimeout(() => {
        if (!myPeerConnection) return;
        const connState = myPeerConnection.connectionState;
        const iceState = myPeerConnection.iceConnectionState;
        if (connState === 'connected') return;
        if (iceState === 'connected' || iceState === 'completed') {
            rtcLog(`connectionState=${connState}지만 iceConnectionState=${iceState} — DTLS 마무리 대기, 재협상 보류`);
            return;
        }
        tryRestartNegotiation(`연결 지연(connectionState=${connState})`);
    }, CONNECT_WATCHDOG_MS);
}

async function restartNegotiation() {
    if (!myPeerConnection || myPeerConnection.signalingState === 'closed') return;
    try {
        const offer = await myPeerConnection.createOffer({ iceRestart: true });
        await myPeerConnection.setLocalDescription(offer);
        rtcLog('재협상 offer 전송 (iceRestart)');
        socket.emit('offer', offer, roomName);
        armConnectWatchdog();
    } catch (err) {
        rtcLog('재협상 실패', err);
    }
}

async function sendOffer() {
    myDataChannel = myPeerConnection.createDataChannel('video/audio');
    myDataChannel.addEventListener('message', console.log); // message 이벤트 - send에 반응
    rtcLog('dataChannel 생성됨');
    const offer = await myPeerConnection.createOffer();
    await myPeerConnection.setLocalDescription(offer); // 각자의 offer로 SDP(Session Description Protocol) 설정
    rtcLog('offer 전송');
    socket.emit('offer', offer, roomName); // 만들어진 offer를 전송
    armConnectWatchdog();
}

// signalingState가 stable이 아니어서 offer를 바로 못 보낼 때, stable 전환을 기다렸다가 한 번 재시도한다
// (동시 입장 등으로 타이밍이 꼬여 welcome 처리 시점에 state가 잠깐 안정되지 않은 경우 대비)
// stable로 안 돌아오면 옛 offer가 죽은 협상일 가능성이 높으므로, 기다리다 포기하지 않고 바로 ICE 재시작으로 넘어간다
function retryOfferWhenStable() {
    let settled = false;
    const onStateChange = () => {
        if (settled || myPeerConnection.signalingState !== 'stable') return;
        settled = true;
        myPeerConnection.removeEventListener('signalingstatechange', onStateChange);
        sendOffer();
    };
    myPeerConnection.addEventListener('signalingstatechange', onStateChange);
    setTimeout(() => {
        if (settled) return;
        settled = true;
        myPeerConnection.removeEventListener('signalingstatechange', onStateChange);
        tryRestartNegotiation('welcome stable 대기 타임아웃');
    }, NEGOTIATION_WAIT_MS);
}

// 내가 들어가면 다른 참가자들이 'welcome' 이벤트를 받는다
socket.on('welcome', async () => { // room에 있는 Peer들은 각자의 offer를 생성 및 제안
    welcomeCount++;
    rtcLog(`welcome #${welcomeCount}`);

    // 이미 미디어가 정상적으로 흐르는 중이면(connectionState=connected) 이 welcome은 무시한다.
    // 상대의 "신호" 소켓이 백그라운드 복귀 등으로 재연결되면서 온 것일 뿐, 실제 미디어 연결은
    // 끊긴 적이 없는 경우가 많다. 이미 연결된 상태에서 다시 offer를 보내면, connectionState가
    // 계속 'connected'로 유지돼 값이 안 바뀌니 이걸 지워줄 이벤트도 다시 안 떠서 "연결 시도 중"
    // 표시가 영원히 고착되는 버그가 났었다.
    if (myPeerConnection && myPeerConnection.connectionState === 'connected') {
        rtcLog('welcome 수신 — 이미 연결되어 있어 무시');
        return;
    }

    showCallStatus('연결 시도 중...'); // 상대가 실제로 들어와서 협상을 시작하는 시점이므로 활성 표시로 전환

    if (peerLeftTimeout) {
        clearTimeout(peerLeftTimeout); // 타이머 취소
        peerLeftTimeout = null;
    }

    // 새 peer가 들어와서 온 신호이므로, 이전 시도에서 소진된 재시도 예산과 무관하게 새로 기회를 준다
    // (그래서 이전엔 재시도 상한에 걸리면 새로운 상대가 들어와도 영원히 무시됐다)
    negotiationRetryCount = 0;

    // 기존 연결이 오랫동안 failed/disconnected로 죽어있다면 되살리려 하지 말고 완전히 새로 만든다
    // (죽은 offer를 붙잡은 채 have-local-offer에 갇혀 새 피어의 welcome조차 처리 못 하는 좀비 상태 방지)
    const deadStates = ['failed', 'disconnected'];
    if (myPeerConnection && (deadStates.includes(myPeerConnection.connectionState) || deadStates.includes(myPeerConnection.iceConnectionState))) {
        rtcLog('기존 연결이 죽어있어 새로 생성');
        announceReconnectOnNextConnect = true;
        clearConnectWatchdog();
        clearIceDisconnectTimer();
        myPeerConnection.close();
        myPeerConnection = null;
    }

    if (!myPeerConnection) {
        await makeConnection();
    }

    // 이미 offer 진행 중이면 중복 welcome 무시하되, 타이밍이 꼬여 잠깐 stable이 아닐 수 있으니 재시도를 걸어둔다
    if (myPeerConnection.signalingState !== 'stable') {
        rtcLog(`welcome 무시 — 이미 signalingState=${myPeerConnection.signalingState}, stable 전환 시 재시도`);
        retryOfferWhenStable();
        return;
    }

    await sendOffer();
});

/**
 * WebRTC는 브라우저끼리 직접 연결을 하기 때문에
 * 브라우저 A가 "나는 이런 정보로 연결할 준비됐어"라고 알려줘야
 * 브라우저 B가 그에 맞춰 연결 정보를 세팅할 수 있다
 * 'offer-answer' SDP 핸드셰이크
 * 각 offer 마다 세션을 생성 -> 새로운 Web RTC 연결을 초기화
 * 세션 업데이트 : 원격 peer의 새로운 offer 정보로 업데이트
 */
socket.on('offer', async (offer) => {
    rtcLog('offer 수신');
    // offer 자체는 시그널링 정합성을 위해 항상 처리해야 하지만(무시하면 상대와 상태가 어긋남),
    // 이미 connected 상태면 화면에 "연결 시도 중"을 새로 띄우지 않는다 — 재협상 후에도 계속
    // connected로 유지되면 값이 안 바뀌어 지워줄 이벤트가 안 뜨고 표시가 고착되기 때문
    if (!(myPeerConnection && myPeerConnection.connectionState === 'connected')) {
        showCallStatus('연결 시도 중...'); // 상대가 실제로 offer를 보내온 시점이므로 활성 표시로 전환
    }
    // offer가 getMedia()/makeConnection() 완료보다 먼저 도착하는 레이스 대비
    if (!myPeerConnection) {
        await makeConnection();
    }
    myPeerConnection.addEventListener('datachannel', event => { // datachannel 감지
        myDataChannel = event.channel;
        myDataChannel.addEventListener('message', console.log);
    });
    await myPeerConnection.setRemoteDescription(offer);
    // remoteDescription 설정 전에 도착해 대기 중이던 ICE 후보를 흘려보낸다 (answer 쪽에서만 비우던 누락 보완)
    candidateQueue.forEach(c => myPeerConnection.addIceCandidate(c));
    candidateQueue = [];
    const answer = await myPeerConnection.createAnswer(); // offer를 받고 answer를 생성해 SDP 설정
    await myPeerConnection.setLocalDescription(answer); // 각자의 peer는 local, remote를 설정
    rtcLog('answer 전송');
    socket.emit('answer', answer, roomName);
    armConnectWatchdog();
});

socket.on('answer', async (answer) => {
    rtcLog('answer 수신');

    const applyAnswer = async () => {
        await myPeerConnection.setRemoteDescription(answer); // 각 peer는 자신의 SDP 연결된 room의 SDP를 설정한다.
        rtcLog('answer setRemoteDescription 완료');
        candidateQueue.forEach(c => myPeerConnection.addIceCandidate(c));
        candidateQueue = [];
    };

    if (myPeerConnection.signalingState === 'have-local-offer') {
        await applyAnswer();
        return;
    }

    // 우리 offer의 setLocalDescription이 아직 안 끝났거나 타이밍이 꼬인 경우, have-local-offer 전환을 잠깐 기다렸다가 재시도
    rtcLog(`answer 대기 — 잘못된 state: ${myPeerConnection.signalingState}, have-local-offer 전환 시 재시도`);
    let settled = false;
    const onStateChange = async () => {
        if (settled || myPeerConnection.signalingState !== 'have-local-offer') return;
        settled = true;
        myPeerConnection.removeEventListener('signalingstatechange', onStateChange);
        await applyAnswer();
    };
    myPeerConnection.addEventListener('signalingstatechange', onStateChange);
    setTimeout(() => {
        if (settled) return;
        settled = true;
        myPeerConnection.removeEventListener('signalingstatechange', onStateChange);
        tryRestartNegotiation('answer have-local-offer 대기 타임아웃');
    }, NEGOTIATION_WAIT_MS);
});

socket.on('ice', (ice) => {
    onIceCandidateReceived(ice);  // ICE(Interactive Connectivity Establishment); 서로 연결되는 경로를 찾아냄; 상대방의 후보 경로를 추가해서 연결을 시도
});

// 상대 탭 비활성화 이벤트
/*socket.on("peer_left", () => {
    // 비디오 정리만 하고 연결은 유지
    peerFace.srcObject = null;
    console.log("상대방이 나갔습니다");

    peerLeftTimeout = setTimeout(() => {
        console.log("60초 지남, 연결 닫음");
        myPeerConnection?.close();
        myPeerConnection = null;
    }, 1000 * 60); // 60초 대기
});*/

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
async function onIceCandidateReceived(candidate) {
    // if (remoteDescriptionSet) {
    console.log("RECEIVE ICE type:", candidateTypeOf(candidate), candidate);

    if (!candidate) {
        console.log("remote ICE gathering complete");
        return;
    }

    if (!myPeerConnection) {
        console.log("ICE 후보 대기열에 보관(연결 생성 전):", candidate);
        candidateQueue.push(candidate);
        return;
    }

    try {
        if (myPeerConnection.signalingState === "stable" || myPeerConnection.remoteDescription) {
            await myPeerConnection.addIceCandidate(candidate);
        } else {
            console.log("ICE 후보 대기열에 보관:", candidate);
            candidateQueue.push(candidate);
        }
    } catch (err) {
        console.error("addIceCandidate failed:", err, candidate);
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

    // 데스크톱: autoGainControl(AGC) 워밍업 구간 때문에 "처음에만 잘 안 들린다" 증상이 있어 꺼둔다.
    // 모바일: 스피커폰으로 화면을 보며 통화하면 마이크와 거리가 있어 AGC로 게인을 올려줘야 한다.
    let constraints = {
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: isMobileDevice },
        video: true  // 비디오 사용하겠다
    };

    try {
        myStream = await navigator.mediaDevices.getUserMedia(constraints);
        // console.log("myStream 연결 완료: ", myStream);

        let audioTrack = myStream.getAudioTracks()[0];
        const audioSettings = audioTrack.getSettings();
        currentMicrophoneDeviceId = audioSettings.deviceId || null; // 필요없는지 테스트 필요
        console.log("🎤 현재 사용 중인 마이크 deviceId:", currentMicrophoneDeviceId);

        // deviceId 없이 잡은 최초 트랙은 OS 기본 통신 장치로 라우팅되어 먹먹하게 들리는 경우가 있어,
        // 실제 deviceId를 알아낸 뒤 그 deviceId로 다시 명시적으로 잡아 교체한다 (마이크 전환 후 되돌렸을 때와 동일한 경로)
        if (currentMicrophoneDeviceId) {
            try {
                const pinnedAudioStream = await navigator.mediaDevices.getUserMedia({
                    audio: {
                        deviceId: { exact: currentMicrophoneDeviceId },
                        echoCancellation: true,
                        noiseSuppression: true,
                        autoGainControl: isMobileDevice
                    },
                    video: false
                });
                const pinnedAudioTrack = pinnedAudioStream.getAudioTracks()[0];
                myStream.removeTrack(audioTrack);
                audioTrack.stop();
                myStream.addTrack(pinnedAudioTrack);
                audioTrack = pinnedAudioTrack;
            } catch (pinErr) {
                console.warn("마이크 deviceId 고정 재요청 실패, 기본 트랙 사용:", pinErr);
            }
        }

        const videoTrack = myStream?.getVideoTracks()[0];
        const videoSettings = videoTrack.getSettings();
        console.log("🎥 현재 사용 중인 카메라 deviceId:", videoSettings.deviceId);

        // enumerateDevices를 srcObject 설정 전에 호출 (일부 Android에서 카메라 스트림 표시 중 enumerateDevices가 카메라를 재초기화해 freeze 유발)
        await getAudioInputs();

        myFace.srcObject = myStream;

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

        if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError" || err.name === "SecurityError") {
            alert("카메라/마이크 권한이 꺼져 있어 영상통화를 시작할 수 없습니다.\n브라우저 주소창 옆 사이트 설정에서 카메라와 마이크 권한을 '허용'으로 바꾼 뒤 새로고침 해주세요.");
        } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
            alert("카메라 또는 마이크 장치를 찾을 수 없습니다.\n장치가 연결되어 있는지 확인해주세요.");
        } else if (err.name === "NotReadableError" || err.name === "TrackStartError") {
            alert("카메라 또는 마이크를 다른 앱이 사용 중입니다.\n해당 앱을 종료한 뒤 다시 시도해주세요.");
        } else {
            alert("카메라 또는 마이크를 사용할 수 없습니다.\n권한 또는 다른 앱 확인이 필요합니다.");
        }
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
        // STUN; 내 외부 IP를 알려주는 서버 (ICE 후보 생성을 도와줌)
        /*iceServers: [
            {
                urls: [
                    'stun:stun.l.google.com:19302',
                    'stun:stun1.l.google.com:19302',
                    'stun:stun2.l.google.com:19302',
                    'stun:stun3.l.google.com:19302'
                ]
            }
        ]*/

        // 디버깅
        /*iceTransportPolicy: "relay",
        iceServers: [
            {
                urls: [
                    // "turn:chickchick.kr:3478?transport=udp",
                    // "turn:chickchick.kr:3478?transport=tcp",
                    "turns:chickchick.kr:5349?transport=tcp"
                ],
                username: "test",
                credential: "1234"
            }
        ]*/

        // 안정적인 설계
        iceServers: [
            {
                urls: "stun:chickchick.kr:3478"
            },
            {
                urls: [
                    "turn:chickchick.kr:3478?transport=udp",
                    "turn:chickchick.kr:3478?transport=tcp",
                    "turns:chickchick.kr:5349?transport=tcp"
                ],
                username: "test",
                credential: "1234"
            }
        ]
    });

    // icecandidate; 연결 가능한 네트워크 경로(ICE candidate; IP + 포트)가 발견되면 발생하는 이벤트
    // 두 Peer사이의 가능한 모든 경로를 수집하고 다른 Peer에 전송
    myPeerConnection.addEventListener('icecandidate', handleIce);
    myPeerConnection.addEventListener('track', handleTrack);

    myPeerConnection.addEventListener('iceconnectionstatechange', () => {
        const iceState = myPeerConnection.iceConnectionState;
        rtcLog(`iceConnectionState → ${iceState}`);

        // connectionState=failed는 스펙상 감지까지 수십 초가 걸릴 수 있어, 훨씬 먼저 바뀌는
        // iceConnectionState를 보고 더 빨리 반응한다. disconnected는 순간적인 네트워크 끊김으로
        // 자연 복구되는 경우가 많아 짧게(ICE_DISCONNECT_GRACE_MS) 기다렸다가만 재시도한다.
        if (iceState === 'connected' || iceState === 'completed') {
            clearIceDisconnectTimer();
        } else if (iceState === 'disconnected') {
            clearIceDisconnectTimer();
            iceDisconnectTimer = setTimeout(() => {
                if (myPeerConnection && myPeerConnection.iceConnectionState === 'disconnected') {
                    tryRestartNegotiation('iceConnectionState=disconnected 지속');
                }
            }, ICE_DISCONNECT_GRACE_MS);
        } else if (iceState === 'failed') {
            clearIceDisconnectTimer();
            tryRestartNegotiation('iceConnectionState=failed');
        }
    });
    myPeerConnection.addEventListener('connectionstatechange', () => {
        rtcLog(`connectionState → ${myPeerConnection.connectionState}`);
        if (myPeerConnection.connectionState === 'connected') {
            clearConnectWatchdog();
            clearIceDisconnectTimer();
            negotiationRetryCount = 0;
            hideCallStatus();
            if (announceReconnectOnNextConnect) {
                announceReconnectOnNextConnect = false;
                // 채팅 소켓/방 이름은 부모창(chat.js)이 갖고 있으니, 여기서는 postMessage로
                // "재연결됐다"고만 알리고 실제 메세지 전송은 부모창이 담당한다
                window.parent.postMessage('video-call-reconnected', '*');
            }
        } else if (myPeerConnection.connectionState === 'failed') {
            tryRestartNegotiation('connectionState=failed');
        }
    });
    myPeerConnection.addEventListener('signalingstatechange', () => {
        rtcLog(`signalingState → ${myPeerConnection.signalingState}`);
    });

    // addTrack을 requestAnimationFrame으로 지연 — 영상 엘리먼트가 최소 1프레임 렌더한 뒤에
    // WebRTC 파이프라인이 트랙을 가져가도록 해 Android freeze 방지.
    // 단, makeConnection()을 await하는 호출자가 트랙이 실제로 붙기 전에 offer를 만들어버리는
    // 레이스를 막기 위해 프레임 하나를 Promise로 감싸서 여기서 기다린다.
    if (myStream) {
        await new Promise(resolve => requestAnimationFrame(resolve));
        myStream.getTracks().forEach(track => {
            myPeerConnection.addTrack(track, myStream);
        });
    }
};

function candidateTypeOf(c) {
    if (!c || !c.candidate) return "end";
    const m = c.candidate.match(/ typ (\w+)/);
    return m ? m[1] : "unknown";
}

function handleIce(event) {
    // data.candidate 안에는 이 브라우저가 사용할 수 있는 연결 정보가 들어 있음
    if (event.candidate) {
        const type = candidateTypeOf(event.candidate);
        iceTypeCount[type] = (iceTypeCount[type] || 0) + 1;
        console.log("SEND ICE type:", type, event.candidate.candidate);
        socket.emit('ice', event.candidate, roomName);
    } else {
        console.log("SEND ICE: null (수집 완료)", JSON.stringify(iceTypeCount));
        if (!iceTypeCount.srflx && !iceTypeCount.relay) {
            console.warn("⚠️ srflx/relay 없음 → STUN/TURN 미응답. host 후보만으로는 다른 네트워크 연결 불가");
        }
        socket.emit("ice", null);
    }
}

/*function handleAddStream(data) {
    const peerFace = document.getElementById('peerFace');
    peerFace.srcObject = data.stream;
}*/

function handleTrack(event) {
    const [stream] = event.streams;
    peerFace.srcObject = stream;
    hideCallStatus();

    peerFace.onloadedmetadata = () => {
        recordCanvas.width = peerFace.videoWidth || 1280;
        recordCanvas.height = peerFace.videoHeight || 720;
        startDrawingLoop(peerFace, peerFace.videoWidth, peerFace.videoHeight);
        startPeerFreezeDetection();

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

    currentFacingMode = currentFacingMode === "user" ? "environment" : "user";

    let newVideoStream;
    const isIphone = /iPhone|iPad|iPod/i.test(navigator.userAgent);
    try {
        if (isIphone) {
            newVideoStream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: currentFacingMode } });
        } else {
            const devices = await navigator.mediaDevices.enumerateDevices();
            const selectedCameraDeviceId = currentFacingMode === "user" ? devices[3].deviceId : devices[1].deviceId;
            newVideoStream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { deviceId: { exact: selectedCameraDeviceId } } });
        }
    } catch (err) {
        console.error("카메라 전환 실패:", err);
        currentFacingMode = currentFacingMode === "user" ? "environment" : "user";
        return;
    }

    const newVideoTrack = newVideoStream.getVideoTracks()[0];

    myStream.getVideoTracks().forEach(t => {
        myStream.removeTrack(t);
        t.stop();
    });
    myStream.addTrack(newVideoTrack);
    myFace.srcObject = myStream;

    await updatePeerConnection();
    faceMirror(newVideoTrack);
}

async function handleAudioInputChange() {
    if (myStream) {
        // myStream.getAudioTracks().forEach(track => track.stop());
    }

    const newAudioStream = await navigator.mediaDevices.getUserMedia({
        audio: {
            deviceId: { exact: audioInputSelect?.value },
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: isMobileDevice
        },
        video: false
    });
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
    if (e.target.closest('button')) return;
    isDragging = true;
    const pos = getClientPosition(e);
    offsetX = pos.x - myFaceWrapper.offsetLeft;
    offsetY = pos.y - myFaceWrapper.offsetTop;
    e.preventDefault();
}

function onDrag(e) {
    if (!isDragging) return;
    const pos = getClientPosition(e);

    const x = pos.x - offsetX;
    const y = pos.y - offsetY;

    // 화면(뷰포트)을 벗어나지 않도록 제한
    const clampedX = Math.max(0, Math.min(x, window.innerWidth  - myFaceWrapper.offsetWidth));
    const clampedY = Math.max(0, Math.min(y, window.innerHeight - myFaceWrapper.offsetHeight));

    myFaceWrapper.style.left   = `${clampedX}px`;
    myFaceWrapper.style.top    = `${clampedY}px`;
    myFaceWrapper.style.right  = "auto";
    myFaceWrapper.style.bottom = "auto";
}

function endDrag() {
    isDragging = false;
}

// 마우스 이벤트
myFaceWrapper.addEventListener("mousedown", startDrag);
document.addEventListener("mousemove", onDrag);
document.addEventListener("mouseup", endDrag);

// 터치 이벤트
myFaceWrapper.addEventListener("touchstart", startDrag, { passive: false });
document.addEventListener("touchmove", onDrag, { passive: false });
document.addEventListener("touchend", endDrag);

function setSwitchCameraPos() {
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
    if (!isMobile) {
        switchCameraBtn.style.display = 'none';
        return;
    }
    switchCameraBtn.addEventListener("click", handleCameraChange);
}

// 뷰포트 크기 변화 시 myFace 위치를 비율 기준으로 재조정
function clampMyFacePosition() {
    const left = parseFloat(myFaceWrapper.style.left);
    const top  = parseFloat(myFaceWrapper.style.top);
    if (isNaN(left) || isNaN(top)) return; // CSS bottom/right 방식이면 건드리지 않음

    const newW = window.innerWidth;
    const newH = window.innerHeight;

    // 이전 viewport 대비 비율로 위치 스케일
    const scaledLeft = left * (newW / prevViewportW);
    const scaledTop  = top  * (newH / prevViewportH);

    const maxX = newW - myFaceWrapper.offsetWidth;
    const maxY = newH - myFaceWrapper.offsetHeight;
    myFaceWrapper.style.left = Math.max(0, Math.min(scaledLeft, maxX)) + "px";
    myFaceWrapper.style.top  = Math.max(0, Math.min(scaledTop,  maxY)) + "px";

    prevViewportW = newW;
    prevViewportH = newH;
}

// ResizeObserver: 특정 HTML 요소의 크기 변화를 감지하는 객체 > 콜백함수
new ResizeObserver(clampMyFacePosition).observe(document.documentElement);

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

/////////////////////// Freeze Detection ///////////////////////

function startFreezeDetection() {
    if ('requestVideoFrameCallback' in HTMLVideoElement.prototype) {
        let lastFrameTime = 0;

        const onFrame = () => {
            lastFrameTime = performance.now();
            myFace.requestVideoFrameCallback(onFrame);
        };
        myFace.requestVideoFrameCallback(onFrame);

        setInterval(() => {
            if (!myStream || !myStream.active || lastFrameTime === 0) return;
            if (performance.now() - lastFrameTime > 1000) {
                console.warn('[freeze] 1초간 새 프레임 없음 → 복구');
                lastFrameTime = performance.now();
                myFace.srcObject = myStream;
                myFace.play().catch(() => {});
                myFace.requestVideoFrameCallback(onFrame);
            }
        }, 500);
    } else {
        // requestVideoFrameCallback 미지원 브라우저 폴백
        setInterval(() => {
            if (myFace.paused && myStream && myStream.active) {
                console.warn('[freeze] paused 감지 → 복구');
                myFace.play().catch(() => {});
            }
        }, 2000);
    }
}

// 상대가 홈 화면으로 이동하면 모바일 브라우저가 카메라 캡처를 멈춰버려서(OS/브라우저의
// 백그라운드 카메라 차단 정책 — 코드로 우회 불가) 상대 화면이 멈춘다. 막을 수는 없지만,
// 조용히 멈춘 화면만 보여주는 대신 "지금 라이브가 아니다"를 알려줄 수는 있다.
let peerFreezeIntervalId = null;
let peerFaceFrozen = false;

function startPeerFreezeDetection() {
    clearInterval(peerFreezeIntervalId);
    peerFaceFrozen = false;
    if (!('requestVideoFrameCallback' in HTMLVideoElement.prototype)) return;

    let lastFrameTime = performance.now();
    const onFrame = () => {
        lastFrameTime = performance.now();
        if (peerFaceFrozen) {
            peerFaceFrozen = false;
            rtcLog('상대 영상 프레임 재개');
            hideCallStatus();
        }
        peerFace.requestVideoFrameCallback(onFrame);
    };
    peerFace.requestVideoFrameCallback(onFrame);

    peerFreezeIntervalId = setInterval(() => {
        if (!myPeerConnection || myPeerConnection.connectionState !== 'connected') return;
        if (performance.now() - lastFrameTime > 3000) {
            if (!peerFaceFrozen) {
                peerFaceFrozen = true;
                rtcLog('상대 영상 프레임 정지 감지 (백그라운드 이동 추정)');
                showCallStatus('상대방 화면이 멈췄어요', { subtle: true });
            }
            // 트랙 자체는 살아있는데 <video> 재생만 멈춰있는 경우가 있어(백그라운드 복귀 후 등) 재생을 다시 시도
            if (peerFace.paused) {
                peerFace.play().catch(() => {});
            }
        }
    }, 1000);
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
    showCallStatus('상대방을 기다리는 중', { subtle: true });
    await getMedia();
    await makeConnection();
    socket.emit('join_video_socket', roomName, username);
    setSwitchCameraPos();
    startFreezeDetection();
})

// 탭 전환/화면 잠금 후 foreground 복귀 시 내 화면 + 상대 화면 resume.
// 모바일 브라우저는 백그라운드에서 돌아오면 <video>가 재생을 자동으로 이어가지 않는 경우가 있어
// (미디어 연결 자체는 안 끊겼어도) srcObject는 그대로인데 화면만 마지막 프레임에 멈춰있게 된다.
document.addEventListener('visibilitychange', () => {
    if (document.hidden) return;
    if (myFace.paused && myStream && myStream.active) {
        myFace.play().catch(() => {});
    }
    if (peerFace.paused && peerFace.srcObject) {
        peerFace.play().catch(() => {});
    }
});

// beforeunload: 브라우저가 닫히거나 새로고침되기 직전
window.addEventListener("beforeunload", () => {
    socket.emit("leave_room", roomName, username); // 서버에 방 나간다고 알림
    if (globalRecoder) globalRecoder.stop();
});