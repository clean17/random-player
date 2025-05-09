import os
import subprocess


def convert_webm_to_mp4(webm_path, output_dir):
    base = os.path.splitext(os.path.basename(webm_path))[0]
    mp4_path = os.path.join(output_dir, f"{base}.mp4")

    # FFmpeg 명령어 실행
    # command = [
    #     "ffmpeg",
    #     "-i", webm_path,
    #     "-c:v", "libx264",
    #     "-c:a", "aac",
    #     "-strict", "experimental",
    #     "-y",  # overwrite
    #     mp4_path
    # ]
    command = [
        "ffmpeg",
        "-i", webm_path,
        "-c:v", "libx264",
        "-preset", "veryfast",              # 빠른 인코딩 (속도/품질 균형)
        "-crf", "23",                        # 품질 (0~51, 낮을수록 좋음, 23은 적절한 디폴트)
        "-pix_fmt", "yuv420p",               # ✅ 모든 플레이어 호환을 위해 필수
        "-c:a", "aac",
        "-b:a", "128k",                      # 오디오 비트레이트 명시 (권장)
        "-movflags", "+faststart",          # ✅ 모바일 스트리밍/seek 최적화
        "-y",                                # overwrite
        mp4_path
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode == 0:
        # return mp4_path
        # ✅ 변환 성공 시 원본 삭제
        try:
            os.remove(webm_path)
            pass
        except Exception as e:
            print(f"❗ 원본 삭제 실패: {e}")
        return mp4_path
    else:
        raise RuntimeError(f"FFmpeg error: {result.stderr.decode()}")
