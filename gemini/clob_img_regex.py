"""CLOB(HTML) 에서 <img> 추출 + alt 채우기 - 정규식 버전 (Python 3.8 호환).

BeautifulSoup 은 str(soup) 로 되돌릴 때 태그를 재직렬화(self-closing, 속성 순서
변경 등)하므로 원본 CLOB 이 바뀐다. 이 버전은 정규식으로 대상 <img> 태그의
alt 속성만 삽입/치환하고, 그 외 모든 문자는 원본 그대로 보존한다.

- src 가 "/common" 으로 시작하는 <img> 만 대상.
- alt 값은 HTML 이스케이프하여 안전하게 삽입.

주의: 정규식은 속성값 안에 '>' 가 들어간 경우를 처리하지 못한다.
      일반적인 CLOB 에서는 문제되지 않지만, 그런 데이터가 있다면 BS 버전을 쓸 것.
"""
import re
from typing import Dict, List

from img_alt import describe_image

BASE_URL = "https://mojarchives.go.kr:40080"
COMMON_PREFIX = "/common"

_IMG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_SRC_RE = re.compile(r"""src\s*=\s*(["'])(.*?)\1""", re.IGNORECASE)
# group1=alt= , group2=따옴표 , group3=기존 alt 값
_ALT_RE = re.compile(r"""(alt\s*=\s*)(["'])(.*?)\2""", re.IGNORECASE)


def to_absolute(src: str) -> str:
    """/common 상대경로를 절대 URL 로 변환한다."""
    return BASE_URL + src


def extract_common_imgs(clob: str) -> List[Dict[str, str]]:
    """/common 으로 시작하는 <img> 정보를 리스트로 반환한다.

    각 항목: {"tag": 원본 태그, "src": src, "url": 절대 URL, "alt": 기존 alt}
    """
    result = []  # type: List[Dict[str, str]]
    for m in _IMG_RE.finditer(clob):
        tag = m.group(0)
        m_src = _SRC_RE.search(tag)
        if not m_src:
            continue
        src = m_src.group(2)
        if not src.startswith(COMMON_PREFIX):
            continue
        m_alt = _ALT_RE.search(tag)
        result.append(
            {
                "tag": tag,
                "src": src,
                "url": to_absolute(src),
                "alt": m_alt.group(3) if m_alt else "",
            }
        )
    return result


def _escape_attr(value: str) -> str:
    """큰따옴표로 감싸는 속성값 이스케이프. 작은따옴표는 건드리지 않아 CLOB 을 깔끔히 유지."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _insert_alt(tag: str, alt_value: str) -> str:
    """태그 문자열에 alt 속성만 삽입/치환한다. 나머지 문자는 원본 그대로 유지."""
    alt_esc = _escape_attr(alt_value)
    m_alt = _ALT_RE.search(tag)
    if m_alt:
        # 기존 alt 값만 교체 (alt= 와 따옴표 종류는 원본 유지)
        return (
            tag[: m_alt.start()]
            + m_alt.group(1)
            + m_alt.group(2)
            + alt_esc
            + m_alt.group(2)
            + tag[m_alt.end():]
        )
    # alt 가 없으면 닫는 '>' (또는 '/>') 직전에 삽입
    gt = tag.rfind(">")
    pos = gt - 1 if gt > 0 and tag[gt - 1] == "/" else gt
    return tag[:pos] + ' alt="{}"'.format(alt_esc) + tag[pos:]


def fill_alts(clob, overwrite=False, on_fail=None):
    """/common <img> 들의 alt 를 Gemini 설명으로 채운 HTML 을 반환한다.

    대상 <img> 태그의 alt 속성 외에는 원본 CLOB 을 그대로 보존한다.
    overwrite=False: 이미 alt 가 있는 이미지는 건너뛴다.
    overwrite=True : 기존 alt 도 새 설명으로 덮어쓴다.
    on_fail(src, url, exc): 이미지 처리 실패 시 호출되는 콜백(배치 실패 로깅용).
                            None 이면 콘솔에 [FAIL] 출력만 한다.
    """

    def _repl(m):
        tag = m.group(0)
        m_src = _SRC_RE.search(tag)
        if not m_src:
            return tag
        src = m_src.group(2)
        if not src.startswith(COMMON_PREFIX):
            return tag
        m_alt = _ALT_RE.search(tag)
        if m_alt and (m_alt.group(3).strip() != "") and not overwrite:
            return tag
        try:
            alt = describe_image(to_absolute(src))
            print("[OK] {} -> {}".format(src, alt))
            return _insert_alt(tag, alt)
        except Exception as e:  # 한 이미지 실패가 전체를 막지 않도록
            if on_fail is not None:
                on_fail(src, to_absolute(src), e)
            else:
                print("[FAIL] {} : {} {}".format(src, type(e).__name__, e))
            return tag

    return _IMG_RE.sub(_repl, clob)


if __name__ == "__main__":
    sample_clob = (
        '<p>행사 사진</p>\n'
        '<img src="/common/thumbnailFile/kcDpWU09NKM1RFL0tEKTr/view" width="300">\n'
        '<img src="https://other.example.com/x.jpg" alt="외부이미지">'  # /common 아님 -> 제외
    )

    print("=== 추출 결과 ===")
    for item in extract_common_imgs(sample_clob):
        print(item)

    print("\n=== alt 채운 HTML (원본 보존) ===")
    print(fill_alts(sample_clob))
