from PIL import Image
import os

def compress_image_to_target_size(input_path, output_path, target_size_kb=1000):
    img = Image.open(input_path)

    # JPEG이 가장 압축률이 좋음 (투명도 필요 없으면 변환)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # 초기 품질 설정
    quality = 85

    while quality > 10:
        img.save(output_path, format="JPEG", quality=quality)
        size_kb = os.path.getsize(output_path) / 1024

        if size_kb <= target_size_kb:
            print(f"✅ 압축 성공: {int(size_kb)} KB, quality={quality}")
            return

        quality -= 5  # 품질 단계적으로 낮춤

    print("❗ 목표 크기까지 줄이지 못했습니다.")

# 사용 예
compress_image_to_target_size(r"C:\Users\piw94\Downloads\프로필\20250323_081527.jpg", r"C:\Users\piw94\Downloads\프로필\20250323_081527_2.jpg", target_size_kb=1000)