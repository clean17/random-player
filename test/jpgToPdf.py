from PIL import Image
import os

# PNG 파일이 있는 디렉토리 경로
img_dir = r'C:\Users\piw94\Downloads\250422_page-1_files'  # 필요에 따라 경로 수정

# PNG 파일만 필터링하고 이름순 정렬
png_files = sorted([f for f in os.listdir(img_dir) if f.lower().endswith('.jpg')])

# 이미지 리스트 생성
img_list = []

for file_name in png_files:
    img_path = os.path.join(img_dir, file_name)
    img = Image.open(img_path).convert("RGB")  # PNG는 RGBA일 수 있으므로 RGB로 변환
    img_list.append(img)

# 첫 이미지를 기준으로 PDF 저장
if img_list:
    pdf_path = os.path.join(img_dir, "output.pdf")
    img_list[0].save(pdf_path, save_all=True, append_images=img_list[1:])
    print(f"✅ PDF 생성 완료: {pdf_path}")
else:
    print("⚠️ PNG 파일이 없습니다.")
