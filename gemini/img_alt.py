"""이미지 URL -> Gemini -> alt 설명 텍스트 (Python 3.8 호환).

CLOB 안의 <img> 태그에서 뽑은 이미지 URL 을 받아,
Gemini 에 이미지를 보내 alt 속성에 넣을 설명 문구를 돌려받는다.

API 키는 프로젝트 루트 .env 의 GEMINI_API_KEY 에서 읽는다.
"""
import base64
import os
import threading
import time

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
MODEL = "gemini-2.5-flash"
GEN_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent".format(MODEL)

# --- 배치 실행용 재시도 / throttle 설정 --------------------------------------
MAX_RETRIES = 5          # 재시도 횟수 (일시적 오류 시)
BACKOFF_BASE = 2.0       # 지수 백오프 기준(초): 2, 4, 8, 16 ...
MIN_INTERVAL = 1.0       # Gemini 요청 간 최소 간격(초). 1.0 => 약 60 RPM. 티어에 맞게 조정.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}

_last_call = [0.0]
_throttle_lock = threading.Lock()


def _throttle() -> None:
    """Gemini 요청 사이에 MIN_INTERVAL 만큼 간격을 강제해 rate limit 을 피한다."""
    with _throttle_lock:
        wait = MIN_INTERVAL - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()


def _request_with_retry(method, url, throttle=False, **kwargs):
    """일시적 오류(429/5xx/네트워크)는 지수 백오프로 재시도한다.

    4xx(400/404 등)는 재시도 없이 즉시 예외를 던진다.
    """
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        if throttle:
            _throttle()
        delay = BACKOFF_BASE * (2 ** (attempt - 1))
        try:
            resp = requests.request(method, url, **kwargs)
        except requests.RequestException as e:
            last_err = e  # 네트워크/타임아웃 -> 재시도
        else:
            if resp.status_code in RETRYABLE_STATUS:
                last_err = "HTTP {}".format(resp.status_code)
                ra = resp.headers.get("Retry-After")
                if ra and ra.replace(".", "", 1).isdigit():
                    delay = float(ra)  # 서버가 지정한 대기시간 우선
            else:
                resp.raise_for_status()  # 그 외 4xx 는 여기서 즉시 예외 (재시도 안 함)
                return resp
        if attempt < MAX_RETRIES:
            time.sleep(delay)
    raise RuntimeError("요청 {}회 재시도 실패 ({}): {}".format(MAX_RETRIES, url, last_err))

# 일부 서버(mojarchives 등)는 브라우저 헤더가 없으면 400 을 반환한다.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}

ALT_PROMPT = (
    # "Describe this image in Korean as concise alt text for screen readers, "
    # "in a single sentence. Output only the description, no quotes or 'alt:' prefix."
    "Korean web accessibility alt text only."
)


def _detect_mime(data: bytes) -> str:
    """매직바이트로 이미지 MIME 타입을 판별한다 (content-type 이 부정확할 때 대비)."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def fetch_image(url: str) -> tuple:
    """이미지를 내려받아 (bytes, mime) 튜플로 반환한다."""
    resp = _request_with_retry("GET", url, headers=BROWSER_HEADERS, timeout=30)
    data = resp.content
    mime = _detect_mime(data)
    if mime == "application/octet-stream":
        # 매직바이트로 못 잡으면 응답 헤더의 content-type 을 신뢰
        ct = resp.headers.get("content-type", "")
        if ct.startswith("image/"):
            mime = ct.split(";")[0].strip()
    return data, mime


def alt_from_bytes(data: bytes, mime: str, prompt: str = ALT_PROMPT) -> str:
    """이미지 bytes + mime 을 받아 alt 설명 문자열을 반환한다 (로컬파일/URL 공통)."""
    if not API_KEY:
        raise SystemExit("GEMINI_API_KEY 환경변수(.env)가 설정되지 않았습니다.")

    b64 = base64.b64encode(data).decode("ascii")

    resp = _request_with_retry(
        "POST",
        GEN_URL,
        throttle=True,  # Gemini 요청만 rate limit 대상 -> throttle 적용
        headers={"x-goog-api-key": API_KEY, "Content-Type": "application/json"},
        json={
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": mime, "data": b64}},
                    ]
                }
            ]
        },
        timeout=120,
    )
    result = resp.json()
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()


def describe_image(url: str, prompt: str = ALT_PROMPT) -> str:
    """이미지 URL 을 받아 alt 설명 문자열을 반환한다."""
    data, mime = fetch_image(url)
    return alt_from_bytes(data, mime, prompt)


if __name__ == "__main__":
    import sys

    test_url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "https://mojarchives.go.kr:40080/common/thumbnailFile/kcDpWU09NKM1RFL0tEKTr/view"
    )
    # print("=== 생성된 alt 텍스트 ===")
    print("alt:", describe_image(test_url))
