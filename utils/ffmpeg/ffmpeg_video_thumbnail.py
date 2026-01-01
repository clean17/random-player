import ffmpeg

target_dir = "F:\\test\\"
target_file = target_dir + "test.ts"
output_file = target_dir + "output.jpg"

probe = ffmpeg.probe(target_file)
video = next(
    (stream for stream in probe["streams"] if stream["codec_type"] == "video"), None
)
width = int(video["width"])
height = int(video["height"])
print("Width:", width)
print("Height:", height)

# ss 1프레임, vframes 프레임 1개 참고, update=1).run(overwrite_output=True) 덮어쓰기
ffmpeg.input(target_file, ss=1).output(output_file, vframes=1, update=1).run(overwrite_output=True)