import os
import re
from datetime import datetime

def rename_mp4_files(directory):
    pattern = re.compile(r'(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})-\d{3}Z')

    for filename in os.listdir(directory):
        if filename.lower().endswith('.mp4'):
            match = pattern.search(filename)
            if match:
                date_part = match.group(1)
                hour = match.group(2)
                minute = match.group(3)
                second = match.group(4)
                # 새로운 포맷: 2025-05-09_100516
                new_timestamp = f"{date_part}_{hour}{minute}{second}"
                # 파일명에서 원래 타임스탬프 부분을 새로운 포맷으로 교체
                new_filename = pattern.sub(new_timestamp, filename)
                # 파일 경로
                src = os.path.join(directory, filename)
                dst = os.path.join(directory, new_filename)
                print(f'Renaming: {filename} → {new_filename}')
                os.rename(src, dst)

def add_prefix_to_images(directory, prefix='video-call_'):
    image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff')
    for filename in os.listdir(directory):
        lower = filename.lower()
        if lower.endswith(image_extensions) and not filename.startswith(prefix):
            src = os.path.join(directory, filename)
            dst = os.path.join(directory, prefix + filename)
            print(f'Renaming: {filename} → {prefix + filename}')
            os.rename(src, dst)


def reorder_video_call_files(directory):
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

# 사용 예시
# rename_mp4_files(r'F:\merci_server_file_dir\video-call')

# add_prefix_to_images(r'F:\merci_server_file_dir\video-call')

reorder_video_call_files(r'F:\merci_server_file_dir\video-call')