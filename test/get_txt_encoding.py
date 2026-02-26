from charset_normalizer import from_path

result = from_path(r"C:\Users\user\Downloads\202601_내비게이션용DB_전체분\match_build_jeju.txt").best()
print("추정 인코딩:", result.encoding)
