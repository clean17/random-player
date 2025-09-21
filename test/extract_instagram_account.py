from urllib.parse import urlparse

# 주어진 링크에서 계정명만 추출
data = """

"""


usernames = set()
for line in data.strip().splitlines():
    url = line.strip()
    if not url:
        continue
    p = urlparse(url)
    parts = [seg for seg in p.path.split('/') if seg]
    if parts:
        usernames.add(parts[0])


print(usernames)
# ['aaaaaaaaaaa', 'bbbbbbbbbbb']












from pathlib import Path

BASE = Path(r"C:\Users\piw94\Pictures\dir_name")  # r''로 백슬래시 이스케이프 방지

# 폴더명 리스트 (상위 경로 바로 아래만)
folder_names = sorted([p.name for p in BASE.iterdir() if p.is_dir()], key=str.casefold)

# 디렉토리의 하위 디렉토리명을 배열로 리턴
print(folder_names)


"""
['추출됨']
"""