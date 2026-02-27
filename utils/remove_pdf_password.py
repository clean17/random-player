from pathlib import Path
from pypdf import PdfReader, PdfWriter

def remove_pdf_password(input_path: str, output_path: str, password: str) -> None:
    input_path = str(Path(input_path))
    output_path = str(Path(output_path))

    reader = PdfReader(input_path)

    if reader.is_encrypted:
        ok = reader.decrypt(password)
        if ok == 0:  # 0이면 실패
            raise ValueError("비밀번호가 틀렸거나(또는 권한 부족) 복호화에 실패했습니다.")
    else:
        # 암호가 없으면 그대로 저장해도 됨
        pass

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    # 중요: encrypt()를 호출하지 않으면 결과물은 암호 없이 열림
    with open(output_path, "wb") as f:
        writer.write(f)

    print(f"완료: {output_path}")

if __name__ == "__main__":
    # 예시
    remove_pdf_password(
        input_path=r"C:\Users\piw94\Downloads\2026년 2월 kt M모바일 명세서(문서열기암호：주민번호 앞 6자리).pdf",
        output_path=r"C:\Users\piw94\Downloads\2026년 2월 kt M모바일 명세서 (박인우).pdf",
        password="940317"
    )
