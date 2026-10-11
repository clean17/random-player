"""단어장 교정 — 받아쓰기 결과에서 단어장 단어와 발음이 비슷한 부분을 찾아 단어장 표기로 바꾼다.

처음엔 Whisper hotwords(받아쓰기 힌트)로 했는데, faster-whisper 가 30초 창마다 힌트를 프롬프트로 붙이는 탓에
조용하거나 불분명한 구간에서 힌트 목록을 그대로 받아 적었다 — 38분 회의에 통화용 단어장을 걸었더니
'이루다 계장' 11회가 끼어들었다. 누출을 글자 패턴으로 지우려 했지만 실제 자기소개
'법무부 기록관, 퍼스트정보, 박인우 대리입니다' 가 누출과 똑같은 모양이라 구분이 불가능했다 (2026-10-12).

그래서 받아쓰기는 힌트 없이 하고, 받아쓴 글자를 자모 단위로 비교해 고친다.
  '박인호' → '박인우'      자모 8개 중 2개 차이 (0.25)
  '버스정보' → '퍼스트정보'  11개 중 3개 (0.27)
  '법무부 교육관' → '법무부 기록관'  17개 중 3개 (0.18)
없는 말을 만들어 넣지 않고(받아쓴 자리에서만 바꾼다), 단어장을 고치면 받아쓰기 없이 바로 반영된다.
"""
import re
from typing import Dict, List, Tuple

# 자모 거리 / 긴 쪽 자모 수 — 이 이하면 같은 말로 본다
MAX_RATIO = 0.3
# 이보다 짧은 단어(글자 수, 공백 제외)는 비슷한 말이 너무 많아 유사 교정을 하지 않는다 (정확히 일치할 때만 키워드로)
MIN_SYLLABLES = 3

_CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
_JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'
_JONG = ' ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ'


def jamo(text: str) -> List[str]:
    out = []
    for ch in text:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out.append(_CHO[code // 588])
            out.append(_JUNG[(code % 588) // 28])
            if code % 28:
                out.append(_JONG[code % 28])
        elif not ch.isspace():
            out.append(ch.lower())
    return out


def _lev(a: List[str], b: List[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, y in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y))
        prev = cur
    return prev[-1]


def _ratio(a: List[str], b: List[str]) -> float:
    return _lev(a, b) / max(1, len(a), len(b))


def fuzzy_correct_text(text: str, terms: List[str]) -> Tuple[str, List[Tuple[str, str]]]:
    """text 안에서 terms 와 발음이 비슷한 부분을 term 표기로 바꾼다. returns (새 text, [(바꾼 원문, term), ...])

    후보는 '어절 시작'에서 시작하는 글자 묶음만 본다(단어 중간에서 맞추지 않게). 끝은 어절 중간이어도 된다 —
    '박인호가' 의 '박인호' 처럼 조사가 붙어 있으니까. 길이는 term 글자 수 ±1.
    """
    changes = []
    for term in sorted({t.strip() for t in terms if t.strip()}, key=len, reverse=True):
        compact = re.sub(r'\s+', '', term)
        if len(compact) < MIN_SYLLABLES or not re.search(r'[가-힣]', compact):
            continue
        tj = jamo(compact)
        # 공백 없는 문자열과 원문 위치 대응표
        chars, pos = [], []
        for i, ch in enumerate(text):
            if not ch.isspace():
                chars.append(ch)
                pos.append(i)
        word_starts = {k for k, i in enumerate(pos) if i == 0 or text[i - 1].isspace()}
        best = []  # (ratio, start_k, end_k)
        for k in sorted(word_starts):
            for length in (len(compact) - 1, len(compact), len(compact) + 1):
                if length < 2 or k + length > len(chars):
                    continue
                cand = ''.join(chars[k:k + length])
                if not re.fullmatch(r'[가-힣A-Za-z0-9]+', cand):
                    continue
                r = _ratio(tj, jamo(cand))
                if r <= MAX_RATIO:
                    best.append((r, k, k + length))
        # 가장 비슷한 것부터, 겹치지 않게 고른다
        taken, picked = set(), []
        for r, a, b in sorted(best):
            if any(x in taken for x in range(a, b)):
                continue
            taken.update(range(a, b))
            picked.append((a, b))
        # 뒤에서부터 바꿔야 앞쪽 위치가 안 밀린다
        for a, b in sorted(picked, reverse=True):
            start, end = pos[a], pos[b - 1] + 1
            original = text[start:end]
            if re.sub(r'\s+', '', original) == compact:
                continue  # 이미 맞는 표기
            text = text[:start] + term + text[end:]
            changes.append((original, term))
    return text, changes


def apply_vocabulary(utterances: List[Dict], corrections: List[Tuple[str, str]], terms: List[str]) -> List[Dict]:
    """교정 규칙(정확히 일치 치환) → 단어장 유사 교정 순으로 적용. returns [{'from', 'to', 'count'}, ...] (화면 표시용)"""
    tally = {}  # type: Dict[Tuple[str, str], int]
    for u in utterances:
        for wrong, right in corrections:
            if wrong and wrong in u['text']:
                tally[(wrong, right)] = tally.get((wrong, right), 0) + u['text'].count(wrong)
                u['text'] = u['text'].replace(wrong, right)
        if terms:
            u['text'], changes = fuzzy_correct_text(u['text'], terms)
            for c in changes:
                tally[c] = tally.get(c, 0) + 1
    return [{'from': a, 'to': b, 'count': n} for (a, b), n in sorted(tally.items(), key=lambda kv: -kv[1])]
