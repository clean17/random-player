import os
from pathlib import Path
import win32com.client


def _hwp_open_compat(hwp, in_path: str) -> bool:
    """
    한글 COM 버전별 Open 시그니처 차이를 흡수.
    성공하면 True, 실패하면 마지막 예외 raise.
    """
    in_path = os.path.abspath(in_path)

    # 1) Open(path)
    try:
        return bool(hwp.Open(in_path))
    except Exception as e1:
        last = e1

    # 2) Open(path, format, arg)  (format은 빈 문자열로 두는 경우 많음)
    try:
        return bool(hwp.Open(in_path, "", ""))
    except Exception as e2:
        last = e2

    # 3) Open(path, format, arg, option) 형태인 버전도 있음
    try:
        return bool(hwp.Open(in_path, "", "", ""))
    except Exception as e3:
        last = e3

    raise last


def hwpx_to_hwp(in_path: str, out_path: str, visible: bool = False) -> None:
    in_path = os.path.abspath(in_path)
    out_path = os.path.abspath(out_path)

    if not os.path.exists(in_path):
        raise FileNotFoundError(in_path)

    hwp = win32com.client.Dispatch("HWPFrame.HwpObject")

    # 보안 모듈 등록(환경에 따라 필요)
    try:
        hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")
    except Exception:
        pass

    # 창 표시 여부
    try:
        hwp.XHwpWindows.Item(0).Visible = visible
    except Exception:
        pass

    # 파일 열기 (호환 Open)
    ok = _hwp_open_compat(hwp, in_path)
    if not ok:
        raise RuntimeError("한글에서 파일을 열지 못했습니다.")

    # 다른 이름으로 저장 (HWP)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    if not out_path.lower().endswith(".hwp"):
        out_path += ".hwp"

    saved = False
    # SaveAs 시그니처도 버전별 차이가 있어 여러 개 시도
    for args in [
        (out_path, "HWP", ""),
        (out_path, "HWP",),
        (out_path,),
    ]:
        try:
            hwp.SaveAs(*args)
            saved = True
            break
        except Exception:
            continue

    if not saved:
        raise RuntimeError("SaveAs에 실패했습니다. (한글 버전/권한/경로 확인)")

    # 종료
    try:
        hwp.Quit()
    except Exception:
        pass

    print(f"완료: {out_path}")


if __name__ == "__main__":
    hwpx_to_hwp(
        r"C:\Users\user\Downloads\★법무부 기록관 시스템 백업 계획(안)_백업 결과 보고 양식.hwpx",
        r"C:\Users\user\Downloads\output.hwp",
        visible=False
    )
