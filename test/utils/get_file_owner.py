import win32com.client

def get_file_author(path):
    """
    파일의 만든이(author)를 가져오는 스크립트
    """
    shell = win32com.client.gencache.EnsureDispatch("Shell.Application")
    folder = shell.NameSpace(str(os.path.dirname(path)))
    item = folder.ParseName(str(os.path.basename(path)))
    # 20번 column이 일반적으로 'Authors' 필드
    return folder.GetDetailsOf(item, 20)

# 특정 디렉토리 모든 파일 작성자 배열 (중복 제거)
import os
def unique_authors(directory):
    authors = set()
    for filename in os.listdir(directory):
        path = os.path.join(directory, filename)
        if os.path.isfile(path):
            author = get_file_author(path)
            if author:
                authors.add(author)
    return list(authors)

# 예시
print(unique_authors(r"C:\Users"))
