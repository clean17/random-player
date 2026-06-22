import os
import subprocess


def _build_encode_args(input_flags: list, webm_path: str, mp4_path: str) -> list:
    return [
        "ffmpeg",
        *input_flags,
        "-i", webm_path,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-y",
        mp4_path
    ]


def convert_webm_to_mp4(webm_path, output_dir):
    base = os.path.splitext(os.path.basename(webm_path))[0]
    mp4_path = os.path.join(output_dir, f"{base}.mp4")

    # 1차 시도: 정상 변환
    result = subprocess.run(
        _build_encode_args([], webm_path, mp4_path),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    # EBML 헤더 손상 등 파일 오류 시 2차 시도: 오류 무시 플래그
    if result.returncode != 0:
        stderr_text = result.stderr.decode('utf-8', errors='replace')
        if 'EBML' in stderr_text or 'Invalid data' in stderr_text or 'misdetection' in stderr_text:
            print(f"⚠️ WebM 파일 손상 감지, 오류 무시 모드로 재시도: {webm_path}")
            result = subprocess.run(
                _build_encode_args(
                    ["-fflags", "+genpts+discardcorrupt", "-err_detect", "ignore_err"],
                    webm_path, mp4_path
                ),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )

    if result.returncode == 0:
        try:
            os.remove(webm_path)
        except Exception as e:
            print(f"❗ 원본 삭제 실패: {e}")
        return mp4_path
    else:
        stderr_text = result.stderr.decode('utf-8', errors='replace')
        error_lines = [l for l in stderr_text.splitlines() if l.strip() and not l.startswith(('ffmpeg version', 'built with', 'configuration:', 'lib', ' lib', 'Copyright'))]
        error_summary = '\n'.join(error_lines[-10:]) if error_lines else stderr_text[-300:]
        print(f"❗ FFmpeg stderr:\n{stderr_text}")
        raise RuntimeError(f"FFmpeg error: {error_summary}")
