import os

def get_subdirectories(path):
    """
    지정한 경로(path)의 자식 디렉토리를 리스트로 반환합니다.
    """
    return [name for name in os.listdir(path)
            if os.path.isdir(os.path.join(path, name))]

# 사용 예시
directory_path = r"C:\Users\piw94\Pictures\4K Stogram"  # 원하는 디렉토리 경로로 변경
subdirs = get_subdirectories(directory_path)
print(subdirs)
