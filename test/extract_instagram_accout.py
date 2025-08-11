from urllib.parse import urlparse

data = """
https://www.instagram.com/dltnqls823?igsh=a3d0YzhhaWdyajZ0
https://www.instagram.com/joj._.uk?igsh=MTNteHhsNWc5Ymx1ZA==
https://www.instagram.com/_k.n0n?igsh=MWpkdzg3ampkdm15aQ==
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
# ['dltnqls823', 'joj._.uk', '_k.n0n', '92ddo', 'yeoni.524']

