import win32com.client

def docx_to_pdf(input_path, output_path):
    word = win32com.client.Dispatch('Word.Application')
    doc = word.Documents.Open(input_path)
    doc.SaveAs(output_path, FileFormat=17)  # 17은 PDF
    doc.Close()
    word.Quit()

# 사용 예시
docx_to_pdf(r'C:\Users\user\Downloads\법무부 기록관 시스템(법무행정기록정보시스템) 구축(2차) 감리용역_성능점검결과보고서_v1.0.docx', r'C:\Users\user\Downloads\result.pdf')