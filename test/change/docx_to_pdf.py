"""
pywin32 패키지에 있는 모듈.
Python에서 COM 객체(엑셀, 워드, 아웃룩 같은 MS Office 프로그램들)를 제어할 때 사용
"""
import win32com.client

def docx_to_pdf(input_path, output_path):
    """
    docx 파일에서 pdf 를 생성하는 함수
    """
    try:
        word = win32com.client.Dispatch('Word.Application')
        doc = word.Documents.Open(input_path)
        doc.SaveAs(output_path, FileFormat=17)  # 17은 PDF
    finally:
        doc.Close(False)
        word.Quit()

# 사용 예시
docx_to_pdf(r'C:\Users\user\Downloads\법무부 기록관 시스템(법무행정기록정보시스템) 구축(2차) 감리용역_성능점검결과보고서_v1.0.docx', r'C:\Users\user\Downloads\result.pdf')