from flask import Blueprint, Flask, render_template, jsonify, request, send_file, abort
import ctypes
from flask_login import login_required
import zipfile
import os
import io
from app.image import get_images
from app.image import LIMIT_PAGE_NUM

func = Blueprint('func', __name__)

# Windows API 상수
SHERB_NOCONFIRMATION = 0x00000001  # 사용자 확인 대화 상자를 표시하지 않음
SHERB_NOPROGRESSUI = 0x00000002   # 진행 UI를 표시하지 않음
SHERB_NOSOUND = 0x00000004        # 소리를 재생하지 않음

# def empty_recycle_bin():
#     """휴지통 비우기 함수"""
#     try:
#         result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
#         if result == 0:
#             return {"status": "success", "message": "휴지통이 성공적으로 비워졌습니다."}
#         else:
#             return {"status": "error", "message": f"휴지통을 비우는 데 실패했습니다. 오류 코드: {result}"}
#     except Exception as e:
#         return {"status": "error", "message": f"예기치 않은 오류가 발생했습니다: {e}"}

def check_recycle_bin():
    """휴지통 상태 확인"""
    try:
        # SHQueryRecycleBinW 구조체 초기화
        class SHQUERYRBINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("i64Size", ctypes.c_longlong),
                ("i64NumItems", ctypes.c_longlong),
            ]

        rbinfo = SHQUERYRBINFO()
        rbinfo.cbSize = ctypes.sizeof(SHQUERYRBINFO)

        # 휴지통 상태 확인
        result = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(rbinfo))
        if result != 0:
            return {"status": "error", "message": f"휴지통 상태를 확인하는 데 실패했습니다. 오류 코드: {result}"}

        return {
            "is_empty": rbinfo.i64NumItems == 0,
            "size": rbinfo.i64Size,
            "items": rbinfo.i64NumItems
        }
    except Exception as e:
        return {"status": "error", "message": f"휴지통 상태 확인 중 예외가 발생했습니다: {e}"}

def empty_recycle_bin():
    """휴지통 비우기"""
    try:
        # 휴지통 상태 확인
        status = check_recycle_bin()
        if status.get("is_empty", False):
            return {"status": "info", "message": "휴지통이 이미 비워져 있습니다."}

        # 휴지통 비우기
        result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND)
        if result == 0:
            return {"status": "success", "message": "휴지통이 성공적으로 비워졌습니다."}
        else:
            return {"status": "error", "message": f"휴지통을 비우는 데 실패했습니다. 오류 코드: {result}"}
    except Exception as e:
        return {"status": "error", "message": f"예기치 않은 오류가 발생했습니다: {e}"}

@func.route('/empty-trash-bin', methods=['POST'])
@login_required
def handle_empty_recycle_bin():
    """휴지통 비우기 요청 처리"""
    result = empty_recycle_bin()
    return jsonify(result)

@func.route('/download-zip', methods=['GET'])
def download_zip():
    try:
        target_directory = request.args.get('dir')
        # print('target_directory', target_directory)
        page = int(request.args.get('page', 1))

        if not target_directory:
            return jsonify({"error": "Directo`ry path not provided"}), 400

        if not os.path.exists(target_directory) or not os.path.isdir(target_directory):
            return jsonify({"error": "Invalid or non-existent directory path"}), 400

        start = (page - 1) * LIMIT_PAGE_NUM
        images = get_images(start, LIMIT_PAGE_NUM, target_directory)

        if not images:
            return jsonify({"error": "No files found for the specified page"}), 404

        # ZIP 파일 이름 설정
        zip_filename = "files.zip"

        # 메모리에 ZIP 파일 생성
        zip_stream = io.BytesIO()
        with zipfile.ZipFile(zip_stream, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # for root, dirs, files in os.walk(target_directory): # 해당 디렉토리 모든 파일 압축
            #     for file in files:
            #         file_path = os.path.join(root, file)
            #         arcname = os.path.relpath(file_path, target_directory)  # 상대 경로로 추가
            #         zipf.write(file_path, arcname)
            for image in images: # 선택된 배열만 압축
                file_path = os.path.join(target_directory, image)
                zipf.write(file_path, image)  # 파일 이름만 추가 (상대 경로)

        # 스트림의 시작 위치로 이동
        zip_stream.seek(0)

        # 클라이언트에게 ZIP 파일 반환
        return send_file(
            zip_stream,
            as_attachment=True,
            download_name=zip_filename,
            mimetype='application/zip'
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500