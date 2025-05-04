

const chatContainer = document.getElementById("chat-container"),
    chatInput = document.getElementById("chat-input"),
    textAreaOffsetHeight = 22,
    openDate = new Date(),
    fileInput = document.getElementById('file-input');

let offset = 0, // 가장 최근 10개는 이미 로드됨
    socket,
    isMine,
    isUnderline,
    isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent),
    loading = false,
    scrollHeight, // 전체 스크롤 높이
    scrollTop,    // 현재 스크롤 위치
    offsetX = 0,
    offsetY = 0,
    lastChatId = 0,
    submitted = false;

openDate.setHours(openDate.getHours() + 9);  // UTC → KST 변환
const openTimestamp = openDate.toISOString().slice(2, 19).replace(/[-T:]/g, "");

function loadMoreChats(event) {
    // 현재 스크롤 위치 저장
    const prevScrollHeight = chatContainer.scrollHeight;
    const prevScrollTop = chatContainer.scrollTop;

    const data = {
        "logs": [
            "12786 | 250504160929 | fkaus14 | \ubb38\uc790\uac00?\n",
            "12787 | 250504160934 | nh824 | \uce74\ud1a1\uc654\uc544 \u314e\u314e\n",
            "12788 | 250504160956 | fkaus14 | \uc790\ub3d9\uc815\uc0b0 \uadf8\ub780\uac70\ud558\uba04\n",
            "12789 | 250504160958 | fkaus14 | \ub0b4\uc9c0\ub294\uac70\uc57c?\n",
            "12790 | 250504161010 | nh824 | \uadfc\ub370 \ud654\uba74\uc5d0 \ub098 \ubcf4\uc5ec?\n",
            "12791 | 250504161043 | nh824 | \ub098 \ubcf4\uba74 \uc5b4\ub5bb\uac8c\ud558\uac8c\u2026.\n",
            "12792 | 250504161050 | nh824 | \uc800\uc5ec\uc790 \ub204\uad6c\ub2c8!\n",
            "12793 | 250504161114 | fkaus14 | \ub0b4\uc5ec\uc790\ub2c8\uae4c \uc2e0\uacbd\ub044\uc138\uc694\n",
            "12794 | 250504161443 | fkaus14 | \uac11\uc790\uae30 \uc0ac\ub77c\uc9c0\uba74 \uac71\uc815\ub3fc..\n",
            "12795 | 250504163141 | nh824 | \uac11\uc790\uae30 \uc640\uac00\uc9c0\uad6c\n",
            "12796 | 250504163152 | nh824 | \ubbf8\uc548\ud574 \n",
            "12797 | 250504163159 | nh824 | \ub9d0 \ud560 \ud2c8\uc774 \uc5c6\uc5c8\ub2e4 \n",
            "12798 | 250504163206 | fkaus14 | \uc548\ub4e4\ucf2f\uc9c0?\n",
            "12799 | 250504163208 | nh824 | \ud654\uc7a5\uc2e4 \uc640\uc11c \uc5f0\ub77d\ud558\ub294\uac70\uc57c\n",
            "12800 | 250504163210 | nh824 | \uc6c5\n",
            "12801 | 250504163221 | fkaus14 | \uc65c\u315c\uc5b4\ub514\uac00\uc790\uac70\ud574?\n",
            "12802 | 250504163229 | nh824 | \uc544\ub2c8 \uadf8\ub0e5 \uc606\uc5d0 \uacc4\uc18d \uc788\ub124..\n",
            "12803 | 250504163249 | nh824 | \uc774\ub807\uac8c \uc788\ub290\ub2c8 \ucc28\ub77c\ub9ac \uce74\ud398\uac00 \ub0ac\uaca0\uc5b4 \n",
            "12804 | 250504163313 | fkaus14 | \uc751.. \ud63c\uc790\uc787\uc5b4\uc57c\uc9c0\n",
            "12805 | 250504163400 | nh824 | \ubc25 \uba39\uc5c8\uc5b4?\n",
            "12806 | 250504163405 | nh824 | \ubc30\uace0\ud504\uaca0\ub2e4 \u3160\u3160\n",
            "12807 | 250504163412 | nh824 | \uc138\uc0c1\uc5d0\n",
            "12808 | 250504163419 | fkaus14 | \ud68c \uba39\uace0\uc787\uc5b4\n",
            "12809 | 250504163421 | nh824 | \uc0c1\ub2e4\ub9ac \ubd80\ub7ec\uc9c0\uaca0\ub2e4\n",
            "12810 | 250504163429 | nh824 | \ub9db\uc788\uac8c \uba39\uc5b4 \u314e\u314e\u314e\n",
            "12811 | 250504163433 | fkaus14 | \uc88b\uc544\ud558\ub2a5\uac74 \uc544\ub2c8\ub77c \u314e\u314e\n",
            "12812 | 250504163538 | nh824 | \uc65c \uc2ec\uac01\ud574?\n",
            "12813 | 250504163548 | fkaus14 | \uac16\uc790\uae30 \uc640\uc11c \ubb34\uc2a8 \uc598\uae30\ud574?\n",
            "12814 | 250504163559 | nh824 | \ubcc4\uc774\uc57c\uae30\uc548\ud558\uace0 \uac11\uc790\uae30 \uc640\uc11c\ub294\n",
            "12815 | 250504163608 | nh824 | \uc720\ud22c\ube0c\uc778\uc9c0 \uc778\uc2a4\ud0c0\uc778\uc9c0 \uc1fc\uce20\ubd10\n",
            "12816 | 250504163620 | nh824 | \uc548\uac00\uae38\ub798 \ud654\uc7a5\uc2e4\ub85c \ub3c4\ub9dd\uc654\uc9c0\n",
            "12817 | 250504163705 | fkaus14 | \ud3f0 \ub450\uace0 \uc65c\uadf8\ub7ec\uc9c0..\n",
            "12818 | 250504163713 | nh824 | \uc790\uae30 \ud3f0\uc73c\ub85c \ubcf4\ub294\uac70\uc57c\n",
            "12819 | 250504163720 | fkaus14 | \uc544\n",
            "12820 | 250504163728 | nh824 | \ub098\ub294 \ub0b4\ud3f0\uc73c\ub85c \uc778\uc2a4\ud0c0 \ubcf4\ub294\ucc99\ud558\uad6c\n",
            "12821 | 250504163739 | fkaus14 | \uadf8\ub807\uad6c\ub098\n",
            "12822 | 250504163844 | nh824 | \ub0b4 \uba38\ub9ac \uc9c4\uc9dc \uc6c3\uae30\ub2f9 \u314e\u314e\n",
            "12823 | 250504163917 | nh824 | \ub098\uac00\ubd10\uc57c\uaca0\ub2e4\u3160\u3160\u3160\n",
            "12824 | 250504163926 | fkaus14 | \uadf8\ub798\n",
            "12825 | 250504163941 | fkaus14 | \ub610 \ubcf4\uc790\n",
            "12826 | 250504164040 | nh824 | \uae30\uc5ec\uc6cc\n",
            "12827 | 250504164625 | nh824 | \uc5b4\uc81c \ucc0d\uc740 \uc601\uc0c1 \uc911\ub3c5\uc774\ub2e4 \u314e\u314e\n",
            "12828 | 250504164629 | nh824 | \uacc4\uc18d \ubd10 \u314e\u314e\n",
            "12829 | 250504164639 | nh824 | \uc6b0\ub9ac \uac19\uc774 \uc788\ub294\uac70 \ub9ce\uc774 \ucc0d\uc790!\n",
            "12830 | 250504164912 | fkaus14 | \uc751 \u314e\u314e\u314e\n",
            "12831 | 250504172337 | nh824 | \ub108\ubb34 \ub2f5\ub2f5\ud558\uace0 \ubd88\ud3b8\ud574\uc11c \uce74\ud398 \uac00\uc790\uace0 \ud588\uc5b4..\n",
            "12832 | 250504173830 | fkaus14 | \uac19\uc774 \uac14\uc5b4..\n",
            "12833 | 250504182216 | fkaus14 | \uce74\ud398\ub97c \ub108\uac00 \uac00\uc790\uace0 \ud55c\uac70\uc57c? \uac19\uc774 \uc544\ub2c8\uba74 \ubabb\uac00\ub294\uac70\uc57c?\n",
            "12834 | 250504182354 | fkaus14 | \uac19\uc774\uac00\uba74.. \uc606\uc5d0 \uc549\uc544\uc788\ub294\uac70\uc57c? \uacc4\uc18d \ub9d0\uac70\ub294\uac70\uc57c?\n",
            "12835 | 250504184536 | fkaus14 | \uce74\ud398\uac14\ub2e4\uac00 \uc800\ub141\ub3c4 \uba39\uace0 \uc624\ub294\uac70\uc57c... ?\n"
        ]
    }

    const tempArr = [];

    // 기존 코드 그대로 사용
    data.logs.map(log => {
        tempArr.push(log);
    });

    // console.log(tempArr);

    tempArr.reverse().slice(0,20).forEach(log => {
        const [chatId, timestamp, username, msg] = log.toString().split("|");
        chatObj = {chatId: chatId.trim(), timestamp: timestamp.trim(), username: username.trim(), msg: msg.replace('\n', '').trim() }
        addMessage(chatObj, true)
        if (event === "wheel") {
            chatContainer.scrollTop = chatContainer.scrollHeight - prevScrollHeight + prevScrollTop;
        }
    });

}



// 바깥 컨테이너: 메시지 한 줄을 구성
function renderMessageRow(isMine, chatId) {
    const messageRow = document.createElement("div");
    messageRow.style.display = "flex";
    messageRow.style.alignItems = "flex-end";
    messageRow.style.marginBottom = "6px";
    messageRow.style.maxWidth = "100%";
    messageRow.style.justifyContent = isMine ? "flex-end" : "flex-start";
    messageRow.classList.add('messageRow')
    messageRow.dataset.chatId = chatId;
    return messageRow;
}

// 메시지 박스
function renderMessageDiv() {
    const messageDiv = document.createElement("div");
    messageDiv.classList.add(
        "p-2",
        "rounded-lg",
        "max-w-[75%]",  // 최대 너비 75%
        "w-fit",
        "block",        // 내용에 맞게 크기 조정
        "break-words",  // 긴 단어가 자동으로 줄바꿈되도록 설정
        "messageDiv",
    );
    return messageDiv;
}



// 메세지 추가
function addMessage(data, load = false) {
    isMine = data.username === username;
    isUnderline = data.underline;
    const now = new Date();

    if (data && !data.timestamp) { // 보낸 메세지는 timestemp가 없어서 만들어 준다. 채팅 로그를 node서버에 일임해야 할까 ?
        now.setHours(now.getHours() + 9);  // UTC → KST 변환
        const timestamp = now.toISOString().slice(2, 19).replace(/[-T:]/g, "");
        data.timestamp = timestamp;
    }

    if (Number(lastChatId) < Number(data.chatId)) { // 로드한 메세지가 아닌 추가된 메세지는 chatId가 없는데 ?
        lastChatId = data.chatId;
    }

    const messageRow = renderMessageRow(isMine, data.chatId);
    const messageDiv = renderMessageDiv();

    if (isMine) {
        messageDiv.classList.add("bg-blue-200", "text-left");
    } else {
        messageDiv.classList.add("bg-gray-200", "text-left");
    }

    const messageSpan = document.createElement("span");
    const safeText = data.msg.replace(/ /g, "&nbsp;");
    messageSpan.innerHTML = safeText;
    messageDiv.appendChild(messageSpan);


    chatContainer.prepend(messageRow);
    messageRow.appendChild(messageDiv);

}



function initPage() {
    loadMoreChats();

    chatInput.focus();
}


document.addEventListener("DOMContentLoaded", initPage);


// let controller = new AbortController();
//
// document.querySelectorAll('textarea[data-textarea-auto-resize]').forEach(textarea => {
//     const maxLines = Number(textarea.dataset.textareaAutoResize) || 5;
//     const maxHeight = maxLines * textAreaOffsetHeight;
//
//     const resize = () => {
//         textarea.style.height = '22px';  // ✅ 초기화
//         // const lineCount = textarea.value.split('\n').length;
//         // const newHeight = Math.min(lineCount * textAreaOffsetHeight, maxHeight);
//
//         const scrollHeight = textarea.scrollHeight - 10; // ✅ 실제 내용 높이
//         const newHeight = Math.min(scrollHeight, maxHeight);
//
//         textarea.style.height = `${newHeight}px`;
//     };
//
//     textarea.addEventListener('input', resize, { signal: controller.signal });
//
//     // 초기 설정
//     resize();
// });
//

const textarea = document.getElementById('chat-input');

textarea.addEventListener('touchmove', function (e) {
    const scrollTop = textarea.scrollTop;
    const scrollHeight = textarea.scrollHeight;
    const offsetHeight = textarea.offsetHeight;

    if (scrollHeight > offsetHeight) {
        // 내부에 스크롤이 생길 수 있는 상황
        e.stopPropagation(); // 부모 스크롤로 넘기지 않음
    }
}, { passive: true });
