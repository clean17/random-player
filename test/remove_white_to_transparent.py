from PIL import Image

def remove_white_to_transparent(
        input_path: str,
        output_path: str,
        threshold: int = 245,   # 245~255: 높을수록 "진짜 흰색"만 제거
        keep_rgb: bool = True   # True면 투명 픽셀도 RGB 유지(테두리 덜 깨짐)
):
    """
    PNG에서 흰색(또는 거의 흰색)을 투명 처리해서 저장.
    - threshold 이상이면 흰색으로 간주 (R,G,B 모두)
    - keep_rgb=True면 알파만 0으로 만들고 RGB는 유지 (안티앨리어싱 가장자리 품질↑)
    """
    img = Image.open(input_path).convert("RGBA")
    pixels = img.getdata()

    new_pixels = []
    for r, g, b, a in pixels:
        if r >= threshold and g >= threshold and b >= threshold:
            if keep_rgb:
                new_pixels.append((r, g, b, 0))
            else:
                new_pixels.append((255, 255, 255, 0))
        else:
            new_pixels.append((r, g, b, a))

    img.putdata(new_pixels)
    img.save(output_path, "PNG")
    print('completecd')


if __name__ == "__main__":
    remove_white_to_transparent(
        r"C:\Users\user\Downloads\moj_thumbnail.png",
        "output.png",
        threshold=245
    )