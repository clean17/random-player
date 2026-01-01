import os
import subprocess

def convert_mp4_to_m4a(directory):
    """
    mp4 동영상 파일을 m4a 오디오 파일로 컨버팅
    """
    for filename in os.listdir(directory):
        if filename.lower().endswith('.mp4'):
            mp4_path = os.path.join(directory, filename)
            m4a_filename = os.path.splitext(filename)[0] + '.m4a'
            m4a_path = os.path.join(directory, m4a_filename)

            # ffmpeg 명령 실행
            command = [
                'ffmpeg',
                '-i', mp4_path,           # 입력 파일
                '-vn',                    # 비디오 제거
                '-acodec', 'copy',        # 오디오 그대로 복사
                m4a_path
            ]
            print(f'변환 중: {filename} → {m4a_filename}')
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("✅ 변환 완료")

# 사용 예시
convert_mp4_to_m4a(r"C:\Users\user\Downloads\증거")
