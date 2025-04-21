from PIL import Image
import os

# PNG 파일이 있는 디렉토리 경로
img_dir = r'C:\Users\piw94\Downloads\250422_page-1_files'  # 필요에 따라 경로 수정

# 확장자 필터
valid_extensions = ('.png', '.jpg', '.jpeg')

# 파일 이름순 정렬
img_files = sorted([f for f in os.listdir(img_dir) if f.lower().endswith(valid_extensions)])

# 이미지 리스트
img_list = []

for file_name in img_files:
    img_path = os.path.join(img_dir, file_name)
    try:
        img = Image.open(img_path).convert("RGB")
        img_list.append(img)
    except Exception as e:
        print(f"⚠️ 이미지 열기 실패: {file_name}, 오류: {e}")

# PDF로 저장
if img_list:
    pdf_path = os.path.join(img_dir, "output.pdf")
    img_list[0].save(pdf_path, save_all=True, append_images=img_list[1:])
    print(f"✅ PDF 생성 완료: {pdf_path}")
else:
    print("⚠️ 사용할 이미지가 없습니다.")