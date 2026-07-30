import os
import sys
import re
import requests
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from config.config import settings

IMAGE_DIR = settings['IMAGE_DIR']
COS_URL = settings['COS_URL']
SAVE_DIR = os.path.join(IMAGE_DIR, 'cos')
os.makedirs(SAVE_DIR, exist_ok=True)

LOG_ROOT = os.path.join(os.path.dirname(__file__), "../../logs/a")
PATTERN_FAILED = re.compile(r'Failed (https?://\S+): \d{3}')


def find_cos_log_files() -> list:
    result = []
    for month_dir in sorted(os.listdir(LOG_ROOT)):
        month_path = os.path.join(LOG_ROOT, month_dir)
        if not os.path.isdir(month_path):
            continue
        for fname in sorted(os.listdir(month_path)):
            if fname.startswith("scrap_cos") and fname.endswith(".log"):
                result.append(os.path.join(month_path, fname))
    return result


def extract_404_urls(log_path: str) -> list:
    urls = []
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            if 'Failed' not in line or '404' not in line:
                continue
            m = PATTERN_FAILED.search(line)
            if m:
                url = m.group(1)
                if '/1280/' in url:
                    urls.append(url)
    return urls


def download_with_fallback(orig_url: str) -> bool:
    fallback_url = orig_url.replace('/1280/', '/604/')
    basename = os.path.basename(fallback_url.split('?')[0])
    name, ext = os.path.splitext(basename)
    ts = datetime.now().strftime("%H%M%S%f")[:9]
    new_filename = f"retry_{name}_{ts}{ext}"
    save_path = os.path.join(SAVE_DIR, new_filename)
    try:
        resp = requests.get(fallback_url, timeout=30, headers={'Referer': COS_URL})
        resp.raise_for_status()
        with open(save_path, 'wb') as f:
            f.write(resp.content)
        print(f"  OK  {new_filename}")
        return True
    except Exception as e:
        print(f"  FAIL {fallback_url}: {e}")
        return False


def main():
    if len(sys.argv) > 1:
        log_paths = sys.argv[1:]
    else:
        log_paths = find_cos_log_files()
        if not log_paths:
            print("로그 파일을 찾을 수 없습니다.")
            return

    all_urls = []
    for path in log_paths:
        urls = extract_404_urls(path)
        print(f"{os.path.basename(path)}: 404 URL {len(urls)}개")
        all_urls.extend(urls)

    unique_urls = list(dict.fromkeys(all_urls))
    print(f"\n총 {len(unique_urls)}개 URL (중복 제거 후)\n")

    if not unique_urls:
        print("재시도할 URL이 없습니다.")
        return

    success, fail = 0, 0
    for i, url in enumerate(unique_urls, 1):
        print(f"[{i}/{len(unique_urls)}] {url}")
        if download_with_fallback(url):
            success += 1
        else:
            fail += 1

    print(f"\n완료: 성공={success}  실패={fail}  저장경로={SAVE_DIR}")


if __name__ == "__main__":
    main()
