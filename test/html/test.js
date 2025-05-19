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
        const response = await fetch("https://chickchick.shop/auth/check-verified", {
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

checkVerified();