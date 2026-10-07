import os
import sys
from pathlib import Path

# DLL 디렉터리 핸들을 프로그램 종료까지 보관해야 함
dll_handles = []

site_packages = Path(sys.prefix) / "Lib" / "site-packages"

cublas_bin = site_packages / "nvidia" / "cublas" / "bin"
cudnn_bin = site_packages / "nvidia" / "cudnn" / "bin"

print("cuBLAS :", cublas_bin)
print("cuDNN  :", cudnn_bin)

# 실제 DLL 존재 여부 확인
cublas_dll = cublas_bin / "cublas64_12.dll"
cudnn_dll = cudnn_bin / "cudnn_ops64_9.dll"

print("cublas64_12.dll :", cublas_dll.exists())
print("cudnn_ops64_9.dll :", cudnn_dll.exists())

if not cublas_dll.exists():
    raise FileNotFoundError(cublas_dll)

if not cudnn_dll.exists():
    raise FileNotFoundError(cudnn_dll)

# 중요: 반환 핸들을 변수에 보관
dll_handles.append(
    os.add_dll_directory(str(cublas_bin))
)

dll_handles.append(
    os.add_dll_directory(str(cudnn_bin))
)

# PATH에도 추가해 둠
os.environ["PATH"] = (
        str(cublas_bin)
        + os.pathsep
        + str(cudnn_bin)
        + os.pathsep
        + os.environ["PATH"]
)

# DLL 경로 설정 후 import
from faster_whisper import WhisperModel

print("Whisper 로딩...")

model = WhisperModel(
    "small",
    device="cuda",
    compute_type="float16"
)

print("모델 로딩 성공")

audio_file = r"E:\통화녹음\통화 녹음 디앤디기술 백현욱차장님_260417_141615.m4a"

print("실제 CUDA STT 시작...")

segments, info = model.transcribe(
    audio_file,
    language="ko",
    beam_size=1,
    vad_filter=True,
    condition_on_previous_text=False,
)

for segment in segments:
    print(segment.text)

print("CUDA Whisper 실제 음성변환 성공")