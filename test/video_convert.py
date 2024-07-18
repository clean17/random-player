import subprocess
import os

def convert_to_h264(input_path, output_path):
    try:
        command = [
            'ffmpeg',
            '-i', input_path,
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-c:a', 'aac',
            output_path
        ]
        print(f"Executing command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(f"FFmpeg stdout: {result.stdout}")
        print(f"FFmpeg stderr: {result.stderr}")
        if result.returncode != 0:
            print(f"FFmpeg command failed with return code {result.returncode}")
        else:
            print(f"Conversion successful: {output_path}")
    except Exception as e:
        print(f"An error occurred: {e}")

# 테스트 변환
input_video = 'E:\sample.mp4'
output_video = 'E:\convert.mp4'

# 입력 파일이 실제로 있는지 확인
if not os.path.exists(input_video):
    print(f"Input file does not exist: {input_video}")
else:
    convert_to_h264(input_video, output_video)
