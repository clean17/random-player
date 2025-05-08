function extractFilename(url) {
    const cleanUrl = url.split('?')[0];
    const parts = cleanUrl.split('/');
    return parts[parts.length - 1];
}

const url = "/video/video/2024-06-26_03-30-20.mp4?directory=1";
const filename = extractFilename(url);
console.log(filename);  // 출력: 2024-06-26_03-30-20.mp4

