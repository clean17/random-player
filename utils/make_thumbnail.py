import os
import ffmpeg
from pathlib import Path
from PIL import Image, UnidentifiedImageError, ImageOps

# 변환할 이미지가 들어있는 디렉토리 경로
root_directory = r'F:\merci_server_file_dir'
# root_directory = r'F:\test'

# 허용할 확장자
VALID_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.webp', 'tiff', 'jfif')
VALID_VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.wmv', '.webm')

# 최대 썸네일 가로 너비
max_width = 720

def convert_file(file_path):
    file_lower = str(file_path).lower()
    if file_lower.endswith(VALID_IMAGE_EXTENSIONS):
        convert_image_file(file_path)
    elif file_lower.endswith(VALID_VIDEO_EXTENSIONS):
        convert_video_file(file_path)
    else:
        print(f"지원하지 않는 파일: {file_path}")


# 비디오 파일의 중간 프레임을 webp파일로 변환
def convert_video_file(file_path):
    dir_path = Path(file_path).parent
    thumb_dir = os.path.join(dir_path, 'thumb')
    os.makedirs(thumb_dir, exist_ok=True)

    filename = os.path.basename(file_path)
    base_name, _ = os.path.splitext(filename)
    save_path = os.path.join(thumb_dir, f"{base_name}.webp")

    # ffprobe로 영상 길이 구하기
    try:
        probe = ffmpeg.probe(str(file_path))
        duration = float(probe['format']['duration'])
        midpoint = duration / 2
    except Exception as e:
        print(f"⚠️ ffprobe 오류 ({filename}): {e}")
        return

    # ffmpeg로 썸네일 추출
    try:
        temp_jpg = os.path.join(dir_path, f"{base_name}.jpg")
        (
            ffmpeg
            .input(str(file_path), ss=midpoint)
            .output(temp_jpg, vframes=1)
            .overwrite_output()
            .run(quiet=True)
        )
        # 썸네일 이미지 후처리(리사이즈 등) 기존 이미지 로직 재사용
        convert_image_file(temp_jpg)
        # webp 변환 결과는 thumb 폴더에 같은 이름의 .webp로 생성됨
        os.remove(temp_jpg)  # 임시파일 삭제
    except Exception as e:
        print(f"⚠️ 썸네일 추출 오류 ({filename}): {e}")




# 이미지 파일을 webp파일로 변환
def convert_image_file(file_path):
    dir_path = Path(file_path).parent
    thumb_dir = os.path.join(dir_path, 'thumb')
    os.makedirs(thumb_dir, exist_ok=True) # ✅ thumb 디렉토리 먼저 생성 (없으면 생성)
    filename = os.path.basename(file_path)
    file_lower = filename.lower()

    # 확장자가 이미지가 아닌 경우 제외
    if not file_lower.endswith(VALID_IMAGE_EXTENSIONS):
        return

    # gif, 애니메이션 제외
    if file_lower.endswith('.gif'):
        return

    try:
        with Image.open(file_path) as img:
            # 움직이는 이미지 (animated) 제외
            # print(f"is_animated: {getattr(img, 'is_animated', False)}")
            if getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 10:
                print(f"{filename} → 프레임 수: {getattr(img, 'n_frames', 1)}")
                print(f"❌ 건너뜀 (움직이는 이미지): {filename}")
                return

            # 가로 길이 기준으로 리사이즈 (세로는 비율 유지)
            img = ImageOps.exif_transpose(img)  # ✅ EXIF 회전 자동 보정
            width, height = img.size
            if width > max_width:
                ratio = max_width / width
                new_size = (int(width * ratio), int(height * ratio))
                img = img.resize(new_size, Image.LANCZOS)

            # 저장 경로
            base_name, _ = os.path.splitext(filename)
            save_path = os.path.join(thumb_dir, f"{base_name}.webp")
            img.convert("RGB").save(save_path, "webp", quality=80)

            print(f"✅ 썸네일 생성: {save_path}")

    except UnidentifiedImageError:
        print(f"❌ 이미지 열기 실패: {filename}")
    except Exception as e:
        print(f"⚠️ 오류 발생 ({filename}): {e}")


def batch_convert_from_root(root_dir):
    # 루트 디렉토리 기준으로 하위 폴더들을 가져옴
    for sub_dir in os.listdir(root_dir):
        sub_dir_path = os.path.join(root_dir, sub_dir)
        if os.path.isdir(sub_dir_path):
            thumb_dir = os.path.join(sub_dir_path, 'thumb')
            os.makedirs(thumb_dir, exist_ok=True)
            for filename in os.listdir(sub_dir_path):
                file_path = os.path.join(sub_dir_path, filename)
                if os.path.isfile(file_path):
                    file_lower = str(file_path).lower()
                    if file_lower.endswith(VALID_VIDEO_EXTENSIONS):
                        convert_video_file(file_path)
                    # convert_file(file_path)

# 코드 만들고 최초에 실행했음
# batch_convert_from_root(root_directory)
