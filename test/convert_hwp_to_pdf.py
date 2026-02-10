import os
from pathlib import Path
import win32com.client as win32

def hwp_to_pdf_win(input_hwp: str, output_pdf: str):
    input_hwp = str(Path(input_hwp).resolve())
    output_pdf = str(Path(output_pdf).resolve())

    hwp = win32.Dispatch("HWPFrame.HwpObject")  # 한글 COM
    hwp.RegisterModule("FilePathCheckDLL", "SecurityModule")  # 보안모듈/정책 환경에 따라 필요
    hwp.Open(input_hwp)

    # PDF 저장(환경마다 액션/파라미터가 다를 수 있음)
    # 가장 안정적인 방식은 "인쇄→PDF프린터" 경로를 쓰기도 합니다.
    hwp.SaveAs(output_pdf, "PDF")
    hwp.Quit()

if __name__ == "__main__":
    hwp_to_pdf_win(r"C:\Users\user\Downloads\보안교육_20260209_박인우_사인.hwp", r"C:\Users\user\Downloads\보안교육_20260209_박인우_사인.hwp")
