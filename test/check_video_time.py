import os
from moviepy.editor import VideoFileClip

directory_path = 'E:\laris_data\\test'

video_extensions = ('.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', 'ts')

def get_video_length(file_path):
    try:
        clip = VideoFileClip(file_path)
        duration = clip.duration # 길이를 초 단위로 반환
        clip.close()
        return duration
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None
    
def delete_short_videos(directory, min_length):
    '''비디오 파일의 길이를 출력하고 30초보다 짧은 파일을 삭제'''
    for filename in os.listdir(directory):
        if filename.lower().endswith(video_extensions):
            file_path = os.path.join(directory, filename)
            duration = get_video_length(file_path)
        if duration is not None:
            # print(f"{filename} - {duration} seconds")
            if duration < min_length:
                os.remove(file_path)
                print(f"Deleted [ {filename} ] as it is shorter than {min_length} seconds.")
        # else:
        #     os.remove(file_path)
        #     print(f"Deleted {filename} as it is shorter than {min_length} seconds.")
            
        
delete_short_videos(directory_path, 60)