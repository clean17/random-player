# cp949 → utf-8 변환

input_path = r"C:\Users\user\Downloads\202601_내비게이션용DB_전체분\match_build_jeju.txt"
output_path = r"C:\Users\user\Downloads\202601_내비게이션용DB_전체분\match_build_jeju_utf8.txt"

with open(input_path, "r", encoding="cp949") as src:
    with open(output_path, "w", encoding="utf-8") as dst:
        for line in src:
            dst.write(line)

print("변환 완료")