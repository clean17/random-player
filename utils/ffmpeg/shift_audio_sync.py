import subprocess
import shutil
from pathlib import Path

def shift_audio_sync(input_path: str, output_path: str, shift_sec: float,
                     audio_bitrate: str = "192k") -> None:
    """
    영상은 그대로 두고, 오디오만 shift_sec 만큼 앞/뒤로 이동시켜 저장
    shift_sec > 0  : 오디오를 늦춤(Delay)
    shift_sec < 0  : 오디오를 당김(Advance) - 앞부분 오디오가 잘림, 영상 싱크가 느려짐
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg가 PATH에 없습니다. ffmpeg 설치/환경변수(PATH) 설정이 필요합니다.")

    # ffmpeg 필터 구성
    if shift_sec > 0:
        # Delay audio by N ms + pad (길이 유지)
        ms = int(round(shift_sec * 1000))
        af = f"adelay={ms}|{ms},apad"
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-filter:a", af,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", audio_bitrate,
            "-movflags", "+faststart",
            output_path
        ]
    elif shift_sec < 0:
        # Advance audio: trim start, reset timestamps
        trim_s = abs(shift_sec)
        af = f"atrim=start={trim_s},asetpts=PTS-STARTPTS"
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-filter:a", af,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", audio_bitrate,
            "-movflags", "+faststart",
            output_path
        ]
    else:
        cmd = ["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path]

    # 실행 + 로그 출력(에러 포함)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise RuntimeError(p.stdout)


# ---------------- 사용 예시 ----------------
if __name__ == "__main__":
    input_path = r"X:\찐120\2025-09-27_01-14-46.SVP.mp4"
    # split_arr = input_path.split('\\')
    # file = split_arr[-1]
    # input_dir_path = input_path.replace(file, '')
    # ext = file.split('.')[-1]
    # filename = file.replace('.'+ext, '')
    # print(filename)
    # output_filename = filename+'_s'
    # print(input_dir_path)
    # print(output_filename)
    # output_path = input_dir_path+output_filename+'.'+ext
    '''
    p.stem : 확장자 뺀 파일명
    p.suffix : .mp4 같은 확장자(점 포함)
    with_name() : 같은 폴더에서 파일명만 바꾼 경로 생성
    '''
    p = Path(input_path)
    output_path = str(p.with_name(p.stem + "_s" + p.suffix))
    # output_path = r"X:\찐120\2025-09-27_01-14-46.SVP_s.mp4"

    # print(p.stem)          # filename
    # print(str(p.parent))   # input_dir_path
    # print(p.stem + "_s")   # output_filename (확장자 제외)
    # print(output_path)
    shift_sec = -0.2        # +0.1: 오디오 늦춤 / -0.1: 오디오 당김

    shift_audio_sync(input_path, output_path, shift_sec)
    print("완료:", output_path)
