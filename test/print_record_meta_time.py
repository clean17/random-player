import os
import time
import hashlib

try:
    from mutagen.mp4 import MP4
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False


TARGET_DIR = r"C:\Users\user\Downloads\m4a테스트\Call"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

for fn in os.listdir(TARGET_DIR):
    if not fn.lower().endswith(".m4a"):
        continue
    path = os.path.join(TARGET_DIR, fn)
    st = os.stat(path)

    print("="*70)
    print("파일:", fn)
    print("생성(ctime):", time.ctime(st.st_ctime))
    print("수정(mtime):", time.ctime(st.st_mtime))
    print("접근(atime):", time.ctime(st.st_atime))
    print("SHA256:", sha256(path))

    try:
        audio = MP4(path)
        tags = audio.tags
        if not tags:
            print("[내부 메타데이터] 없음(tags 없음)")
        else:
            print("[내부 메타데이터]")
            for k, v in tags.items():
                print(f"  {k}: {v}")
    except Exception as e:
        print("[메타데이터 읽기 실패]", e)

print("완료")