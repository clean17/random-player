import subprocess, tempfile, os

v1 = r"X:\찐120\붓잽\붓잽 트레인 모음 2025-05-18_00-18-04.SVP.SVP.1.mp4"
v2 = r"X:\찐120\붓잽\2025-06-29_00-32-33.SVP.mp4"
out = r"X:\찐120\붓잽\merged.mp4"

with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt", encoding="utf-8") as f:
    f.write(f"file '{v1}'\n")
    f.write(f"file '{v2}'\n")
    listfile = f.name

cmd = [
    "ffmpeg", "-y",
    "-f", "concat", "-safe", "0",
    "-i", listfile,
    "-c", "copy",
    out
]
subprocess.run(cmd, check=True)
os.remove(listfile)

print("saved:", out)
