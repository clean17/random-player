import os
import re
from datetime import datetime

def rename_m4a_files(directory):
    """
    directory 안에 있는 .m4a 파일들의 이름을
    음성 YYMMDD_HHMMSS.m4a 형식으로 일괄 변경하는 스크립트
    """
    for filename in os.listdir(directory):
        if filename.lower().endswith('.m4a'):
            # 날짜와 시간 추출 (예: 20250422_162433)
            match = re.search(r'(\d{8})_(\d{6})', filename)
            if match:
                full_date, time = match.groups()
                short_date = full_date[2:]  # 20250422 → 250422
                new_name = f"음성 {short_date}_{time}.m4a"
                old_path = os.path.join(directory, filename)
                new_path = os.path.join(directory, new_name)

                print(f"🔁 {filename} → {new_name}")
                os.rename(old_path, new_path)

    print("✅ 이름 변경 완료")


def rename_mp4_files(directory):
    """
    2025-05-09T10-05-16-123Z >> 2025-05-09_100516
    """
    pattern = re.compile(r'(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})-\d{3}Z')

    for filename in os.listdir(directory):
        if filename.lower().endswith('.mp4'):
            match = pattern.search(filename)
            if match:
                date_part = match.group(1)
                hour = match.group(2)
                minute = match.group(3)
                second = match.group(4)
                new_timestamp = f"{date_part}_{hour}{minute}{second}"
                # 파일명에서 원래 타임스탬프 부분을 새로운 포맷으로 교체
                new_filename = pattern.sub(new_timestamp, filename)
                # 파일 경로
                src = os.path.join(directory, filename)
                dst = os.path.join(directory, new_filename)
                print(f'Renaming: {filename} → {new_filename}')
                os.rename(src, dst)


def add_prefix_to_images(directory, prefix='video-call_'):
    """
    이미지 파일명 앞에 prefix 붙이기
    """
    image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff')
    for filename in os.listdir(directory):
        lower = filename.lower()
        if lower.endswith(image_extensions) and not filename.startswith(prefix):
            src = os.path.join(directory, filename)
            dst = os.path.join(directory, prefix + filename)
            print(f'Renaming: {filename} → {prefix + filename}')
            os.rename(src, dst)


def reorder_video_call_files(directory):
    """
    video-call_recording_2025-05-09_100516_abcd1234.mp4
    video-call_screenshot_2025-05-09_100516_deadbeef.png
    에서 recording|screenshot 을 마지막으로 파일명 변경
    """
    pattern = re.compile(
        r"^(video-call)_(recording|screenshot)_(\d{4}-\d{2}-\d{2}_\d{6}_[a-f0-9]+)(.*)$"
    )
    for filename in os.listdir(directory):
        match = pattern.match(filename)
        if match:
            prefix, type_str, mid, rest = match.groups()
            # .ext 붙는 경우(확장자)도 rest로 자동 분리
            new_name = f"{prefix}_{mid}_{type_str}{rest}"
            src = os.path.join(directory, filename)
            dst = os.path.join(directory, new_name)
            print(f"Renaming: {filename} → {new_name}")
            os.rename(src, dst)


# rename_mp4_files(r'F:\merci_server_file_dir\video-call')

# add_prefix_to_images(r'F:\merci_server_file_dir\video-call')

reorder_video_call_files(r'F:\merci_server_file_dir\video-call')

rename_m4a_files(r"C:\Users\user\Downloads\증거")
