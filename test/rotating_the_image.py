from PIL import Image

def rotate_image_90ccw(input_path, output_path):
    # 이미지 열기
    image = Image.open(input_path)

    # -90도(반시계 방향) 회전
    rotated = image.rotate(90, expand=True)

    # 저장
    rotated.save(output_path)
    print(f"✅ 저장 완료: {output_path}")


image_src =  r'C:\Users\piw94\Downloads\IMG_1493_fa968590ee5642e992947243150f649d.webp'
# 사용 예
rotate_image_90ccw(image_src, "rotated_output.jpg")
