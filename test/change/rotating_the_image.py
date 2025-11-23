from PIL import Image

def rotate_image_90ccw(input_path, output_path):
    """
    이미지를 반시계 90도 회전 시키는 함수
    """
    image = Image.open(input_path)
    rotated = image.rotate(90, expand=True) # -90도(반시계 방향) 회전
    rotated.save(output_path)
    print(f"✅ 저장 완료: {output_path}")


image_src =  r'C:\Users\piw94\Downloads\20251118_200101_5ee0047bff14420e8b9c1dc0026422f7.webp'
# 사용 예
rotate_image_90ccw(image_src, "rotated_output.jpg")
