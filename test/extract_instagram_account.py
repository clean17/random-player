from urllib.parse import urlparse

data = """
https://www.instagram.com/aaaaaaaaaaa
https://www.instagram.com/bbbbbbbbbbb
"""

usernames = []
for line in data.strip().splitlines():
    url = line.strip()
    if not url:
        continue
    p = urlparse(url)
    parts = [seg for seg in p.path.split('/') if seg]
    if parts:
        usernames.append(parts[0])

print(usernames)
# ['aaaaaaaaaaa', 'bbbbbbbbbbb']

