import os
from PIL import Image, UnidentifiedImageError

# 변환할 이미지가 들어있는 디렉토리 경로
image_dir = r'F:\merci_server_file_dir\기타'  # ← 여기를 원하는 경로로 바꿔줘
thumb_dir = os.path.join(image_dir, 'thumb')
os.makedirs(thumb_dir, exist_ok=True)

# 허용할 이미지 확장자
valid_extensions = ('.jpg', '.jpeg', '.png', '.bmp', 'webp', 'tiff', 'jfif')

# 최대 썸네일 가로 너비
max_width = 720

for filename in os.listdir(image_dir):
    file_lower = filename.lower()

    # 확장자가 이미지가 아닌 경우 제외
    if not file_lower.endswith(valid_extensions):
        continue

    # gif, 애니메이션 제외
    if file_lower.endswith('.gif'):
        continue

    src_path = os.path.join(image_dir, filename)
    try:
        with Image.open(src_path) as img:
            # 움직이는 이미지 (animated) 제외
            if getattr(img, "is_animated", False):
                print(f"❌ 건너뜀 (움직이는 이미지): {filename}")
                continue

            # 가로 길이 기준으로 리사이즈 (세로는 비율 유지)
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
