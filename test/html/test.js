function extractFilename(url) {
    const cleanUrl = url.split('?')[0];
    const parts = cleanUrl.split('/');
    return parts[parts.length - 1];
}

const url = "/video/video/2024-06-26_03-30-20.mp4?directory=1";
const filename = extractFilename(url);
console.log(filename);  // 출력: 2024-06-26_03-30-20.mp4

async function checkVerified() {
    try {
        const response = await fetch("https://chickchick.kr/auth/check-verified", {
            method: "GET",
            headers: { "Content-Type": "application/json" }
        });

        if (response.status === 200) {
            const result = await response.json();
            if (result && result.success) {
                isVerifiedPassword = true;
            } else {
                isVerifiedPassword = false;
            }
        }
    } catch (e) {
        // console.error("❌ 서버 오류", e);
        isVerifiedPassword = false;
    }
}

// checkVerified();

function doMore() {
    console.log('4. doMore');
}

async function doSomething() {
    console.log('1. doSomething')
    const isValid = await checkVerified();
    if (!isValid) {
        console.log('2. return false')
        return false;  // 이 return은 콜백(람다)만 종료, doSomething은 계속됨
    }
    console.log('3. processing')
    doMore();    // 여기도 계속 실행됨!
}

doSomething();