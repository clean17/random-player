import time
from typing import Callable, Iterable

import requests

# 운영 서버(run.py의 waitress). nginx를 거치지 않고 직접 붙는다 — /image/refresh-cache 는 로컬 요청만 받는다.
SERVER_URL = "http://127.0.0.1:8090"


def refresh_image_caches(dirs: Iterable[str], delay: int = 30, log: Callable[[str], None] = print) -> None:
    """스크랩 작업이 끝난 뒤 delay초 기다렸다가, 화면의 fetch-image-button을 누른 것과 같은 효과를 낸다.
    dirs 는 app/image.py 의 DIR_CONFIG 키('image', 'image2', 'cos' ...). 실패해도 예외를 던지지 않는다."""
    dirs = list(dirs)
    log(f"[INFO] 이미지 목록 갱신 {delay}초 후 호출: {dirs}")
    time.sleep(delay)
    for d in dirs:
        try:
            res = requests.get(f"{SERVER_URL}/image/refresh-cache", params={"dir": d}, timeout=120)
            log(f"[INFO] 이미지 목록 갱신 dir={d}: HTTP {res.status_code} {res.text.strip()[:120]}")
        except Exception as e:
            log(f"[WARN] 이미지 목록 갱신 실패 dir={d}: {e}")


def trigger_ai_screen(delay: int = 30, log: Callable[[str], None] = print) -> None:
    """delay초 기다렸다가 image2 갤러리의 'AI 1차 분류 → move 이동' 버튼을 누른 것과 같은 효과를 낸다.
    서버가 백그라운드로 분류·이동하고, 이동이 끝나면 2분 뒤 move·image2 목록을 스스로 갱신한다
    (app/image_curate.py). 여기서는 시작만 시키고 끝나기를 기다리지 않는다. 실패해도 예외를 던지지 않는다."""
    log(f"[INFO] AI 1차 분류(image2 → move) {delay}초 후 호출")
    time.sleep(delay)
    try:
        res = requests.post(f"{SERVER_URL}/image/curate/api/screen/run-local", timeout=30)
        log(f"[INFO] AI 1차 분류 시작 요청: HTTP {res.status_code} {res.text.strip()[:120]}")
    except Exception as e:
        log(f"[WARN] AI 1차 분류 시작 요청 실패: {e}")
