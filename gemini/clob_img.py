"""CLOB(HTML) 에서 <img> 태그 추출 + alt 채우기 (Python 3.8 호환).

- src 가 "/common" 으로 시작하는 <img> 만 대상으로 한다.
- 상대경로이므로 BASE_URL 을 붙여 절대 URL 로 변환한다.
- fill_alts() 는 각 이미지를 Gemini 로 설명받아 alt 속성을 채운 뒤,
  수정된 HTML(문자열) 을 반환한다. -> 이 값을 다시 CLOB 에 UPDATE 하면 된다.
"""
from typing import Dict, List

from bs4 import BeautifulSoup

from img_alt import describe_image

BASE_URL = "https://mojarchives.go.kr:40080"
COMMON_PREFIX = "/common"


def to_absolute(src: str) -> str:
    """/common 상대경로를 절대 URL 로 변환한다."""
    return BASE_URL + src


def extract_common_imgs(clob: str) -> List[Dict[str, str]]:
    """/common 으로 시작하는 <img> 정보를 리스트로 반환한다.

    각 항목: {"src": 원본 src, "url": 절대 URL, "alt": 기존 alt}
    """
    soup = BeautifulSoup(clob, "html.parser")
    result = []  # type: List[Dict[str, str]]
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src.startswith(COMMON_PREFIX):
            result.append(
                {
                    "src": src,
                    "url": to_absolute(src),
                    "alt": img.get("alt", "") or "",
                }
            )
    return result


def fill_alts(clob: str, overwrite: bool = False) -> str:
    """/common <img> 들의 alt 를 Gemini 설명으로 채운 HTML 문자열을 반환한다.

    overwrite=False: 이미 alt 가 있는 이미지는 건너뛴다.
    overwrite=True : 기존 alt 도 새 설명으로 덮어쓴다.
    """
    soup = BeautifulSoup(clob, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not src.startswith(COMMON_PREFIX):
            continue
        if img.get("alt") and not overwrite:
            continue
        try:
            alt = describe_image(to_absolute(src))
            img["alt"] = alt
            print("[OK] {} -> {}".format(src, alt))
        except Exception as e:  # 한 이미지 실패가 전체를 막지 않도록
            print("[FAIL] {} : {} {}".format(src, type(e).__name__, e))
    return str(soup)


if __name__ == "__main__":
    sample_clob = (
        '<p>행사 사진</p>'
        '<img src="/common/thumbnailFile/kcDpWU09NKM1RFL0tEKTr/view">'
        '<img src="https://other.example.com/x.jpg" alt="외부이미지">'  # /common 아님 -> 제외
    )

    print("=== 추출 결과 ===")
    for item in extract_common_imgs(sample_clob):
        print(item)

    print("\n=== alt 채운 HTML ===")
    print(fill_alts(sample_clob))
