from urllib.parse import urlparse

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
