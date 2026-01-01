import subprocess
import os

def generate_webp_with_ffmpeg(input_path, output_path, max_width=720):
    # FFmpeg 명령어 (Java와 동일하게 구성)
    command = [
        "ffmpeg",
        "-f", "image2",            # 입력 포맷
        "-i", input_path,
        "-vf", f"scale={max_width}:-1:flags=lanczos",  # 비율 유지 + LANCZOS 리사이즈
        "-c:v", "libwebp",         # WebP 코덱
        "-lossless", "0",          # 손실 압축 (색상 보존)
        "-quality", "80",          # 품질
        "-pix_fmt", "yuv420p",
        "-preset", "picture",      # 이미지 최적화 preset
        "-f", "webp",              # 출력 포맷
        "-y",                      # 덮어쓰기
        output_path
    ]

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
        print("✅ 썸네일 생성 완료:", output_path)
    except subprocess.CalledProcessError as e:
        print("❌ FFmpeg 변환 실패")
        print(e.stderr)

# 확장자 없이 변활할 경우 >> "-i", input_path, "-f", "webp", 필요
# input_file = r'E:\LARIS_DATA\FILE\ARCHIVES_REP\2025\07\30\912670\ORIGIN\20250730153712220000000'
input_file = r'C:\Users\user\Downloads\파일업로드 테스트 데이터\webptest\test_webp_image'
output_file = r'C:\Users\user\Downloads\파일업로드 테스트 데이터\webptest\output2'
generate_webp_with_ffmpeg(input_file, output_file)
