import os
import ffmpeg
from pathlib import Path
from utils.image_thumbs import make_thumb, make_video_thumb, probe, thumb_path, video_thumb_path, THUMB_WIDTH, SMALL_BYTES

# 변환할 이미지가 들어있는 디렉토리 경로
# root_directory = r'C:\Users\user\Downloads\파일업로드 테스트 데이터\webptest'
root_directory = r'E:\LARIS_DATA\FILE\ARCHIVES_REP\2025\07\30\912670\ORIGIN'
# root_directory = r'F:\test'

# 허용할 확장자
VALID_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', 'tiff', 'jfif')
VALID_VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.wmv', '.webm')

def convert_file(file_path, index=None, total=None):
    file_lower = str(file_path).lower()
    if file_lower.endswith(VALID_IMAGE_EXTENSIONS):
        convert_image_file(file_path, index, total)
    elif file_lower.endswith(VALID_VIDEO_EXTENSIONS):
        convert_video_file(file_path, index, total)
    else:
        print(f"지원하지 않는 파일: {file_path}")


# 비디오 파일의 중간 프레임을 webp파일로 변환
def convert_video_file(file_path, index=None, total=None):
    dir_path = Path(file_path).parent
    filename = os.path.basename(file_path)
    save_path = video_thumb_path(str(dir_path), filename)   # <폴더>/thumb/video_poster/<이름>.webp

    # ffprobe로 영상 길이 구하기
    try:
        probe = ffmpeg.probe(str(file_path))
        duration = float(probe['format']['duration'])
        midpoint = duration / 2
    except Exception as e:
        print(f"⚠️ ffprobe 오류 ({filename}): {e}")
        return

    # ffmpeg 로 프레임 JPEG → make_thumb 으로 webp (utils/image_thumbs.py make_video_thumb)
    if not make_video_thumb(str(file_path), save_path, seeks=(midpoint, 0)):
        print(f"⚠️ 썸네일 추출 오류 ({filename})")



# 이미지 파일을 webp파일로 변환 — 규칙·크기는 utils/image_thumbs.py(make_thumb) 와 같다.
def convert_image_file(file_path, index=None, total=None):
    try:
        if os.path.getsize(file_path) <= SMALL_BYTES:
            return
    except OSError:
        # 파일 접근/조회 불가 시 스킵
        return

    filename = os.path.basename(file_path)
    # 확장자가 이미지가 아닌 경우 제외 (gif 포함 — 애니메이션이 깨진다)
    if not filename.lower().endswith(VALID_IMAGE_EXTENSIONS) or filename.lower().endswith('.gif'):
        return

    _, _, animated, err = probe(str(file_path))
    if err:
        print(f"❌ 이미지 열기 실패: {filename}")
        return
    if animated:
        print(f"❌ 건너뜀 (움직이는 이미지): {filename}")
        return

    try:
        if _write_thumb(file_path):
            progress = f" ({index}/{total})" if index is not None and total is not None else ""
            print(f"✅ 썸네일 생성{progress}")
    except Exception as e:
        print(f"⚠️ 오류 발생 ({filename}): {e}")


def _write_thumb(file_path, width=THUMB_WIDTH):
    """<폴더>/thumb/<이름>.webp 로 저장. 썸네일이 원본보다 크면 만들지 않는다(False)."""
    data = make_thumb(str(file_path), width)
    if len(data) >= os.path.getsize(file_path):
        return False
    dir_path = Path(file_path).parent
    save_path = thumb_path(str(dir_path), os.path.basename(file_path))
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path + '.tmp', 'wb') as f:
        f.write(data)
    os.replace(save_path + '.tmp', save_path)
    return True


# def generate_thumbnails(root_dir):
#     thumb_dir = os.path.join(root_dir, 'thumb')
#     os.makedirs(thumb_dir, exist_ok=True)
#
#     # 루트 디렉토리 기준 파일 목록을 먼저 모아 총 개수를 구한 뒤 순회 (진행률 표시용)
#     file_paths = [
#         os.path.join(root_dir, name)
#         for name in os.listdir(root_dir)
#         if os.path.isfile(os.path.join(root_dir, name))
#     ]
#     total = len(file_paths)
#     for index, file_path in enumerate(file_paths, start=1):
#         convert_file(file_path, index, total)


# def batch_convert_from_root(root_dir):
#     # 루트 디렉토리 기준으로 하위 폴더들을 가져옴
#     for name in os.listdir(root_dir):
#         sub_dir_path = os.path.join(root_dir, name)
#         if os.path.isdir(sub_dir_path):
#             thumb_dir = os.path.join(sub_dir_path, 'thumb')
#             os.makedirs(thumb_dir, exist_ok=True)
#             print(sub_dir_path)
#             # 루트 하위 디렉토리의 파일 순회
#             for filename in os.listdir(sub_dir_path):
#                 print(filename)
#                 file_path = os.path.join(sub_dir_path, filename)
#                 if os.path.isfile(file_path):
#                     file_lower = str(file_path).lower()
#                     if file_lower.endswith(VALID_VIDEO_EXTENSIONS):
#                         convert_video_file(file_path)
#                     # convert_file(file_path)
#         else:
#             convert_file(sub_dir_path)

# 코드 만들고 최초에 실행했음
# batch_convert_from_root(root_directory)

# 하루에 한 번 썸네일 생성
# generate_thumbnails(r'')