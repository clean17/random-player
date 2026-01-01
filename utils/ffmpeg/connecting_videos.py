import subprocess, tempfile, os

v1 = r"C:\a.mp4"
v2 = r"C:\b.mp4"
out = r"C:\merged.mp4"

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
