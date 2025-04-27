input_file = "data/chat.txt"    # 기존 파일 경로
output_file = "data/chat_2.txt"  # 수정된 결과를 저장할 파일 경로

with open(input_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

with open(output_file, "w", encoding="utf-8") as f:
    for idx, line in enumerate(lines, start=1):
        f.write(f"{idx} | {line.strip()}\n")