from urllib.parse import urlparse

data = """
https://www.instagram.com/_asianbunnyx_?igsh=N3BhcDRhems0czln
https://www.instagram.com/ejyoooou?igsh=bzlhbWs4M25ibDJ2
https://www.instagram.com/c8_rin?igsh=c2VncjJnZHhqbGt2
https://www.instagram.com/jumienne__?igsh=ZzBodXJudXh1Njgx
https://www.instagram.com/sux_eon?igsh=MWFwdjM5enl3bWhjeg==
https://www.instagram.com/seohyov?igsh=M2tzbjBudDR4Zzdy
https://www.instagram.com/museapparelll?igsh=MWs1N2E2MWNwcWcwdg==
https://www.instagram.com/leedahyung_?igsh=NW51bGxmc2ljM2w=
https://www.instagram.com/anna_misspeach?igsh=MWp1bHVxZDVxdWtlcw==
https://www.instagram.com/xsrinnz?igsh=MW14ZGkzNWNwNGdqeg==
https://www.instagram.com/1998_11_04?igsh=Yzc5dWtjbXFvcXZo
https://www.instagram.com/_asianbunnyx_?igsh=N3BhcDRhems0czln
https://www.instagram.com/janjira_cream29?igsh=MnV4d2JldzN0aHNj
https://www.instagram.com/xeuul_?igsh=MXM3aWg3ZGJmZ3o5ag==
https://www.instagram.com/4._.30ark___p?igsh=MXdrdmFxaGw3ZjRoeA==
https://www.instagram.com/olzlh_o?igsh=YWxrNG0zM3dlaGR1
https://www.instagram.com/leeesovelys2?igsh=MTV6cGp5bGFpcWtkcQ==
https://www.instagram.com/svvvnswan?igsh=NnZscTdoMHQ5dWZ0
https://www.instagram.com/k_e.hye?igsh=MWtmaXptNGpoYzk3bA==
https://www.instagram.com/yoom_96?igsh=b284ZmI0bzIwZnIz
https://www.instagram.com/sonyearin?igsh=djg4dG93ejRvMDdh
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
# ['_asianbunnyx_', 'ejyoooou', 'c8_rin', 'jumienne__', 'sux_eon', 'seohyov', 'museapparelll', 'leedahyung_', 'anna_misspeach', 'xsrinnz', '1998_11_04', '_asianbunnyx_', 'janjira_cream29', 'xeuul_', '4._.30ark___p', 'olzlh_o', 'leeesovelys2', 'svvvnswan', 'k_e.hye', 'yoom_96', 'sonyearin']

