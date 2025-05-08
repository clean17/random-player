import os
import subprocess
import shutil

def get_video_codec(file_path):
    try:
        # FFprobe를 사용하여 비디오 파일의 코덱 이름을 가져옵니다.
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        codec_name = result.stdout.strip()
        print(f"File: {file_path}, Codec: {codec_name}")  # 코덱 이름 출력
        return codec_name
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
        return None

def move_hevc_files(source_dir, target_dir):
    os.makedirs(target_dir, exist_ok=True)  # 새로운 디렉토리 생성
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            if file.endswith(('.mp4', '.mkv', '.mov', '.avi')):  # 비디오 파일 확장자
                file_path = os.path.join(root, file)
                codec = get_video_codec(file_path)
                if codec in ['hvc1', 'hev1', 'hevc']:  # HEVC 코덱 확인
                    shutil.move(file_path, os.path.join(target_dir, file))  # 파일을 새 디렉토리로 이동
                    print(f"Moved: {file_path} -> {os.path.join(target_dir, file)}")

if __name__ == "__main__":
    source_directory = input("원본 비디오 파일이 있는 디렉토리 경로를 입력하세요: ")
    target_directory = input("이동할 새 디렉토리 경로를 입력하세요: ")
    move_hevc_files(source_directory, target_directory)
    print("HEVC(H.265) 인코딩된 파일 이동 완료.")
