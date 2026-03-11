import re
import shutil
from pathlib import Path

# logs 디렉토리
logs_dir = Path("logs")

# app_yymmdd.log 형식만 매칭
pattern = re.compile(r"^app_(\d{6})\.log$")

for file_path in logs_dir.iterdir():
    if not file_path.is_file():
        continue

    match = pattern.match(file_path.name)
    if not match:
        continue

    yymmdd = match.group(1)   # 예: 260310
    yymm = yymmdd[:4]         # 예: 2603

    target_dir = logs_dir / yymm
    target_dir.mkdir(exist_ok=True)

    target_path = target_dir / file_path.name

    print(f"move: {file_path} -> {target_path}")
    shutil.move(str(file_path), str(target_path))