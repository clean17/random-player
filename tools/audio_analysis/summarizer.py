"""대화록 → 구조화 분석(analysis.json) + 마크다운(result.md 요약 전체, minutes.md 회의록).

worker.py 가 받아쓰기·화자분리로 만든 발화 목록(utterances)을 받아 로컬 Ollama 로 분석한다.
7.8B 급 모델이 8k 컨텍스트에서 돌아가므로 한 번에 다 넣지 않는다.

  1. 구간 분석  대화록을 SUMMARY_CHUNK_CHARS 단위로 잘라 구간마다 세 번(CHUNK_PASSES: 주제·키워드 / 결정·조치·미결 /
                요청·이슈·일정) 나눠 JSON 으로 뽑는다
  2. 근거 검증  주제 외 항목은 근거 발언(quote)을 원문에서 그대로 베끼게 하고, 코드로 원문과 대조해 못 찾으면 버린다.
                항목 내용의 명사·날짜도 근거 발언 주변에 실제로 있어야 남긴다 (_ground_items)
  3. 통합       구간 결과를 압축해 넣고 제목·목적·핵심 요약·참여자·키워드만 JSON 으로 받는다
  4. 조립       주제 목록은 구간 결과를 시간순으로 이어 붙이고(인접한 같은 주제는 합침), 항목은 근거 시각으로 주제에 붙인다.
                회의록은 LLM 에게 다시 쓰게 하지 않고 이 구조에서 결정적으로 만든다 — 내용이 새거나 지어지지 않게

2026-10-17 사용자 피드백("요청·이슈·미결이 실제와 다르다, 일정은 맞는 것과 틀린 것이 섞였다, 검토 결과만 쓸만하다")으로
바꾼 것: 예전엔 통합 단계 LLM 이 원문 없이 구간 요약만 보고 요청·리스크·미결·일정 목록을 다시 썼고 그게 우선 채택돼
지어낸 항목이 그대로 나갔다. 또 리스크의 '예상 위험'·'대응' 이 필수 칸이라 모델이 추측으로 채웠다.
→ 목록은 원문을 본 구간 결과만 쓰고, 모든 항목에 원문 근거를 요구·검증하며, 말하지 않은 칸은 비운다.

LLM 출력은 Ollama 의 JSON 스키마 강제(format=<schema>)로 받는다. 작은 모델도 형식은 깨지지 않는다.
"""
import json
import os
import re
from typing import Callable, Dict, List, Optional, Tuple

OLLAMA_URL = os.environ.get('AUDIO_OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
OLLAMA_MODEL = os.environ.get('AUDIO_OLLAMA_MODEL', 'exaone3.5:7.8b')
# Ollama 컨텍스트. 16k 로 잡으면 exaone3.5:7.8b 가 7.1GB 가 돼 RTX 3070(화면 등이 ~4GB 점유)에서 12% 가 CPU 로
# 밀리고 생성 속도가 9.9 tok/s 로 떨어진다. 8k 는 GPU 100% 에 47 tok/s (2026-10-12 측정, 약 5배)
OLLAMA_NUM_CTX = int(os.environ.get('AUDIO_OLLAMA_NUM_CTX', '8192'))
OLLAMA_SEED = 42
# 요청마다 모델을 내렸다 올려 빈 상태에서 시작한다. Ollama 는 직전 요청과 앞부분이 같은 프롬프트(공통 지시문)의
# 계산을 재사용하는데, 그러면 GPU 연산 순서가 달라져 temperature 0 이어도 긴 출력이 갈렸다 — 38분 회의를 두 번
# 돌리면 앞 주제 4개까지만 같고 이후가 달랐다 (2026-10-12). 요청당 모델 로딩 몇 초를 더 쓰고 같은 입력 → 같은 결과
OLLAMA_FRESH_CONTEXT = True
# 구간 크기. 한국어는 exaone 기준 약 1.4자/토큰 — 5000자 ≈ 3600토큰 + 지시문 ~800 + JSON 출력 ~3000 이 8k 에 들어가게.
# (2026-10-12 회의록 7개 항목으로 늘리면서 출력이 커져 6000 → 5000)
SUMMARY_CHUNK_CHARS = 5000
# 통합 단계 입력 상한 (구간 결과를 이만큼으로 줄여 넣는다)
MERGE_INPUT_CHARS = 7000

ProgressFn = Callable[[float, str], None]

SYSTEM = (
    '너는 통화 녹음과 회의 대화록을 분석해 회의록을 만드는 전문 비서다. 주어진 대화록만 근거로 한국어로 작성한다. '
    '대화록에 없는 사실, 이름, 숫자, 날짜는 절대 지어내지 않는다. 화자는 대화록 표기("화자 1" 등)를 그대로 쓰고, '
    '대화에서 이름이나 직함이 분명히 드러날 때만 괄호로 덧붙인다. '
    '받아쓰기 오류로 보이는 단어는 문맥상 확실할 때만 바로잡고, 숫자·일정·고유명사는 원문 그대로 보존한다. '
    '문장은 "~함", "~예정", "~요청" 같은 간결한 개조식으로 쓴다.'
)

_STR = {'type': 'string'}
_STR_LIST = {'type': 'array', 'items': _STR}
def _obj(*keys, optional=()):
    return {'type': 'object', 'properties': {k: _STR for k in keys + tuple(optional)}, 'required': list(keys)}


# 회의록 7개 항목(논의·결정·요청·조치·이슈및리스크·미결·일정)에 맞춘 구조 (2026-10-12).
# 주제 외 항목은 전부 quote(근거 발언 원문 그대로)·ts(그 줄 시각)를 함께 받아 원문과 대조한다 (2026-10-17)
_DECISION = _obj('content', 'quote', 'ts')                          # 결정사항
_ACTION = _obj('task', 'owner', 'due', 'quote', 'ts')               # 조치사항: 수행 작업, 담당자, 완료 기한
_REQUEST = _obj('content', 'recipient', 'quote', 'ts')              # 요청사항: 요청 내용, 수신자 (요청자 = 근거 발언 화자)
# 이슈 및 리스크: 말한 문제. 영향·대응은 말했을 때만 — 필수 칸이면 7.8B 가 추측으로 채운다
_RISK = _obj('issue', 'quote', 'ts', optional=('impact', 'response'))
_OPEN = _obj('content', 'quote', 'ts')                              # 미결사항
_SCHEDULE = _obj('item', 'date', 'quote', 'ts')                     # 일정사항 (예정/변경/마감은 코드가 원문으로 판정)

def _schema(**props):
    return {'type': 'object', 'properties': props, 'required': list(props)}


# 구간마다 세 번 나눠 묻는다 — 한 번에 8개 항목을 시키면 7.8B 는 주제만 성실히 쓰고 나머지는 몇 개 대충 채웠다
# (회의1012: 리스크 '티맥스 연락 없음'·'HTML 반입 안 열림' 을 아예 못 뽑음). 항목 2~3개씩 따로 물으면 찾는 데만 집중한다 (2026-10-18)
TOPIC_SCHEMA = _schema(
    topics={'type': 'array', 'items': {
        'type': 'object',
        'properties': {'title': _STR, 'start': _STR, 'points': _STR_LIST, 'conclusion': _STR, 'speakers': _STR_LIST},
        'required': ['title', 'start', 'points', 'conclusion', 'speakers']}},
    keywords=_STR_LIST,
)
AGREE_SCHEMA = _schema(decisions={'type': 'array', 'items': _DECISION},
                       action_items={'type': 'array', 'items': _ACTION},
                       issues={'type': 'array', 'items': _OPEN})
ASK_SCHEMA = _schema(requests={'type': 'array', 'items': _REQUEST},
                     risks={'type': 'array', 'items': _RISK},
                     schedule={'type': 'array', 'items': _SCHEDULE})

# 통합 단계는 원문을 못 보고 구간 요약만 본다 — 결정·요청·조치·이슈·미결·일정 목록은 여기서 다시 쓰게 하지 않는다.
# 예전엔 이 목록이 구간 결과보다 우선 채택돼 '은행에 함수 목록 요청'(실제로는 티맥스에 보냄) 같은 항목이 나갔다 (2026-10-17)
MERGE_SCHEMA = {
    'type': 'object',
    'properties': {
        'title': _STR,
        'type': _STR,
        'purpose': _STR,
        'overview': _STR,
        'summary_text': _STR,
        'participants': {'type': 'array', 'items': _obj('speaker', 'role')},
        'keywords': _STR_LIST,
    },
    'required': ['title', 'type', 'purpose', 'overview', 'summary_text', 'participants', 'keywords'],
}

COMPARE_SCHEMA = {
    'type': 'object',
    'properties': {
        'followups': {'type': 'array', 'items': _obj('item', 'status', 'note')},
        'changes': {'type': 'array', 'items': _obj('category', 'before', 'after')},
    },
    'required': ['followups', 'changes'],
}

_CHUNK_HEAD = """다음은 녹음 대화록의 {idx}/{total} 구간({start}~{end})이다. 각 줄은 "[시각] 화자: 발언" 형식이다.
"""

TOPIC_PROMPT = _CHUNK_HEAD + """이 구간에서 다룬 주제를 정리해 JSON 으로 답해라.

- topics: 이 구간에서 다룬 주제를 시간 순서대로 빠짐없이. 짧게 스쳐 간 주제도 별도로 적는다.
  - title: 주제 이름 (10~25자 명사형, 예: "UI/UX 표준 가이드 일정")
  - start: 그 주제가 시작되는 줄의 시각을 대화록 표기 그대로 (예: "12:34")
  - points: 구체적인 논의 내용 2~6개. 누가 무엇을 말했는지("화자 2: ~요청") 포함, 숫자·날짜·제품명 보존
  - conclusion: 그 주제의 결과 한 문장 — 무엇이 정해졌는지, 누가 무엇을 언제까지 하기로 했는지.
    "공유함", "논의함" 같은 과정 표현은 쓰지 않는다 (나쁜 예: "진행 상황 공유 및 계획 논의" / 좋은 예: "초안은 차주 화요일까지 화자 3이 보완")
    단순 보고였으면 "보고만 함 — 별도 결정 없음", 결론이 안 났으면 "결론 없음 — ○○ 추가 확인 필요"처럼 적는다
  - speakers: 그 주제에서 발언한 화자 표기 목록
- keywords: 이 구간의 핵심 용어 5~10개. 대화록에 실제로 등장한 표기 그대로 (일반적인 단어 말고 고유한 용어 위주)
{note}
[대화록]
{text}"""

# 항목 추출 공통 꼬리 — 코드(_ground_items)가 quote 를 원문과 대조하고, 항목 종류별 표현(_CUES)이 그 근처에 있는지 본다
_ITEM_TAIL = """
대화록을 처음부터 끝까지 한 줄씩 훑어 위 표현이 나오는 발언을 빠짐없이 찾는다. 각 항목에는 근거를 붙인다:
  quote: 근거 발언을 대화록에서 글자 그대로 복사한 15~40자 — 위의 표현이 들어간 부분을 고른다.
    시각·화자 표기는 빼고 발언 본문만, 한 발언 안에서만, 고쳐 쓰거나 요약하지 않는다
    (나쁜 예: "화자 10: 오늘 검토 요청 예정" / "추후 논의하기로 함 (30:55)" — 좋은 예: "오늘 검토 요청을 한번 드릴 예정이고")
  ts: 그 발언 줄의 시각 (대화록 표기 그대로)
content·task·issue·item 은 근거를 베끼지 말고 무엇이(누가) 어떻게 됐는지 드러나게 15~40자로 다시 쓴다
  (나쁜 예: "연락이 없다" / 좋은 예: "티맥스에 보낸 함수 목록 회신 없음").
대화록에서 그대로 복사할 근거가 없는 항목은 넣지 않는다. 날짜·이름·부서·숫자는 근거 발언에 있는 것만 쓴다.
해당 내용이 없으면 빈 배열이 정상이다 — 칸을 채우려고 만들어 내지 않는다.
{note}
[대화록]
{text}"""

AGREE_PROMPT = _CHUNK_HEAD + """이 구간에서 정해진 것·맡은 일·미뤄진 것을 찾아 JSON 으로 답해라.

- decisions: 그 자리에서 정해진 것. "~하는 걸로 하겠습니다", "그렇게 하시죠", "~로 가시죠", "확정", "합의"처럼 정했다는 말이
  있는 것만. 진행 상황 보고("~할 예정입니다")나 제안·질문은 넣지 않는다. content(결정 내용)
- action_items: 누가 "~하겠습니다", "~드리겠습니다", "제가 ~할게요"처럼 하겠다고 했거나 맡게 된 일.
  task(수행 작업), owner(맡은 화자 또는 이름, 모르면 "미정"), due(그 발언에 나온 기한 표현 그대로, 없으면 "미정")
- issues: 미결사항 — "확인해서 말씀드리겠다", "내일 정해서 알려드리겠다", "보시고 말해주세요", "더 고민해야", "아직 ~못 했다"처럼
  결정을 미루거나 확인이 남았다고 말한 것. content(무엇이 미결인지)
""" + _ITEM_TAIL

ASK_PROMPT = _CHUNK_HEAD + """이 구간에서 부탁한 것·문제로 말한 것·날짜가 나온 일정을 찾아 JSON 으로 답해라.

- requests: 한 화자가 다른 사람에게 직접 부탁한 것. "~해 주세요", "~주시면", "알려 주셔야", "보내 주세요", "올려 주시겠어요"
  같은 말이 있는 것. content(요청 내용), recipient(요청받은 사람 — 화자 표기나 대화에 나온 이름, 모르면 "미정")
- risks: 발언자가 문제·우려를 직접 말한 것. "안 돼요", "안 열려요", "못 하겠다", "연락이 없다", "늦어진다", "뒤로 갈 수도",
  "불가능", "어렵다", "이해가 안 간다" 같은 말이 있는 것. 네가 예상하거나 일반론으로 덧붙이지 않는다.
  issue(말한 문제), impact(그 영향을 발언에서 말했으면 적고 아니면 ""), response(대응을 발언에서 말했으면 적고 아니면 "")
- schedule: 날짜·기한·시기가 실제로 말해진 일정 ("10월 14일까지", "내일", "차주", "11월, 12월 정도").
  item(무엇의 일정), date(발언 표기 그대로, 예: "차주 화요일", "10월 14일", "11월~12월")
""" + _ITEM_TAIL

# (진행 표시, 지시문, 스키마) — 구간마다 이 순서로 묻는다
REFINE_SCHEMA = _schema(results={'type': 'array', 'items': _obj('no', 'text')})

# 대상이 빠진 항목을 앞뒤 대화를 보고 다시 쓰게 한다. 근거 발언만 보고 쓰면 '링크를 만들어서 공유해드리겠습니다'
# (무슨 링크인지 없음 — 실제로는 바로 앞에서 보여 준 안내사항 목업 화면) 처럼 대상이 빠진다는 피드백 (2026-10-18).
# 구간 전체를 주면 7.8B 는 대상을 못 찾고 입력 형식('[조치] … — … (화자 5)')을 따라 쓰거나 '11월 중순'을 지어내서,
# 항목마다 그 앞뒤 대화만 잘라 붙여 준다. 예시는 일부러 다른 회의 내용으로 (같은 회의 예시는 답을 알려 주는 셈)
REFINE_PROMPT = """아래 회의록 항목들은 무엇에 대한 것인지가 빠져 있다. 각 항목 아래 [앞뒤 대화]를 읽고, 회의록만 보는 사람도
알 수 있게 항목 문장을 다시 써라.

- "링크", "자료", "파일", "그거", "그 부분", "답이 없다"처럼 대상이 빠진 말은 앞뒤 대화에 나온 실제 대상
  (문서·화면·기능·시스템·업체·사람 이름)을 넣어 쓴다
  (예: 원래 "파일 보내드리겠습니다" → "요구사항 정의서 엑셀 파일 전달")
  (예: 원래 "아직 답이 없어요" → "보안팀에 요청한 방화벽 정책 승인 회신 없음")
- 15~50자 명사형 한 문장. 구분 표기·화자 표기·시각·괄호 설명은 넣지 않는다
- 앞뒤 대화에 있는 말만 쓴다. 날짜·숫자·이름을 새로 만들지 않는다. 대상을 찾을 수 없으면 원래 문장 그대로 쓴다
results: 모든 항목에 대해 no(항목 번호), text(다시 쓴 문장)

{items}"""

REFINE_BATCH = 6                                    # 한 번에 다시 쓰게 할 항목 수 (앞뒤 대화까지 8k 에 들어가게)
REFINE_CONTEXT_BEFORE, REFINE_CONTEXT_AFTER = 8, 1  # 대상은 근거보다 꽤 앞에서 나오곤 한다 (목업 화면 23:17 → 링크 25:19)
REFINE_LINE_CHARS = 160                             # 앞뒤 대화 한 줄 길이 상한
_REFINE_LABEL = {'decisions': '결정', 'requests': '요청', 'action_items': '조치', 'risks': '이슈', 'issues': '미결',
                 'schedule': '일정'}
# 다시 쓴 문장에 새로 들어가면 안 되는 표현 — 숫자·날짜어는 앞뒤 대화에 그대로 있어야 받는다 ('11월, 12월 정도' → '11월 중순')
_EXACT_TOKENS = re.compile(r'\d+\S*|중순|초순|하순|월말|연말|오전|오후|[월화수목금토일]요일|내일|오늘|모레|차주|금주|다음 ?주|이번 ?주')
# 이 명사만으로는 무엇에 대한 항목인지 알 수 없다 — 다시 쓴 뒤에도 이것뿐이면 버린다
_VAGUE_NOUNS = set('링크 자료 파일 문서 기능 작업 화면 건 거 것 쪽 그것 이것 데이터 업무 정보 의견 답변 연락 회신 일 부탁 '
                   '외부 내부 용 전체 일부 다음 기존 신규'.split())

CHUNK_PASSES = (
    ('주제', TOPIC_PROMPT, TOPIC_SCHEMA),
    ('결정·조치·미결', AGREE_PROMPT, AGREE_SCHEMA),
    ('요청·이슈·일정', ASK_PROMPT, ASK_SCHEMA),
)

MERGE_PROMPT = """다음은 하나의 녹음({kind_hint}, 길이 {duration})을 구간별로 분석한 결과다. 이를 통합해 JSON 으로 답해라.

- title: 이 녹음의 제목 (15~30자, 핵심 안건이 드러나게)
- type: 회의 / 통화 / 인터뷰 / 강의 / 기타 중 하나
- purpose: 이 대화의 목적 1~2문장
- overview: 다룬 안건을 한두 문장으로 나열
- summary_text: 핵심 요약 3~5문장의 줄글. 무엇을 논의했고, 무엇이 정해졌고, 앞으로 누가 무엇을 언제까지 하는지가
  드러나게. 숫자·일정 포함. 막연한 표현("다양한 논의가 있었다") 금지
- participants: 화자별 역할 추정 ({speakers}). 아래 [화자별 첫 발언]의 자기소개·호칭과 발언 내용으로 드러난 이름·소속·직함만
  (예: "박인호 대리, 법무부 교육관"), 근거 없으면 "불명"
- keywords: 전체 핵심 키워드 10~15개 (구간 키워드 중에서 중요한 것, 표기 그대로)
구간별 분석에 없는 사실·날짜·이름은 쓰지 않는다.
{note}
[화자별 첫 발언]
{intros}

[구간별 분석]
{data}"""

COMPARE_PROMPT = """두 회의를 비교한다. [이전 회의]({prev_title}, {prev_date})의 정리 내용과 [이번 회의]의 정리 내용을 보고 JSON 으로 답해라.

- followups: 이전 회의의 조치사항·요청사항 각각이 이번 회의에서 어떻게 되었는지.
  item(이전 조치 내용), status("완료" / "진행 중" / "지연" / "변경" / "언급 없음" 중 하나), note(근거가 된 이번 회의 내용 한 줄, 없으면 "")
- changes: 이전 회의와 달라진 결정·일정·담당. category("결정" / "일정" / "담당" / "이슈" 중 하나), before(이전 내용), after(이번 내용)
  새로 생긴 것은 before 를 "없음", 해소된 이슈는 after 를 "해소"로.
두 회의에 실제로 적힌 내용만 근거로 하고, 판단할 근거가 없으면 status 를 "언급 없음"으로 둔다.

[이전 회의]
{prev}

[이번 회의]
{cur}"""

NO_SPEAKER_NOTE = ('\n주의: 이 대화록은 화자 구분이 되어 있지 않다(모두 "화자"로 표기). 누가 말했는지 추측해서 배정하지 말고, '
                   'speakers·participants·owner 에는 대화에 이름이 명시된 경우만 쓰고 아니면 "미정"/"불명"으로 둔다.\n')


# ─────────────────────────── Ollama ───────────────────────────

def ollama_unload():
    """Ollama 는 마지막 호출 후 5분간 모델을 VRAM 에 올려 둔다 — 받아쓰기(Whisper)와 GPU 를 다투지 않게 내린다."""
    try:
        import requests
        requests.post(OLLAMA_URL + '/api/generate', json={'model': OLLAMA_MODEL, 'keep_alive': 0}, timeout=10)
    except Exception:
        pass


def ollama_available() -> Tuple[bool, str]:
    import requests
    try:
        tags = requests.get(OLLAMA_URL + '/api/tags', timeout=3).json()
    except Exception:
        return False, 'Ollama 서버({})에 연결할 수 없습니다'.format(OLLAMA_URL)
    names = {m.get('name') for m in tags.get('models', [])}
    if OLLAMA_MODEL not in names and OLLAMA_MODEL + ':latest' not in names:
        return False, 'Ollama 에 {} 모델이 없습니다 (`ollama pull {}`)'.format(OLLAMA_MODEL, OLLAMA_MODEL)
    return True, ''


def _ollama_json(prompt: str, schema: Dict, timeout: int = 900) -> Dict:
    import requests
    last_err = None
    for attempt in range(2):  # 출력이 num_ctx 에 걸려 잘리면 JSON 이 깨진다 — 한 번 더 시도
        if OLLAMA_FRESH_CONTEXT:
            ollama_unload()
        resp = requests.post(OLLAMA_URL + '/api/chat', json={
            'model': OLLAMA_MODEL,
            'stream': False,
            'format': schema,
            'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': prompt}],
            # 같은 대화록이면 같은 결과가 나오게 temperature 0 + 고정 seed — 0.2 였을 땐 재분석할 때마다
            # 주제 구분·결정/조치 분류·문장이 달라졌다 (2026-10-12). JSON 이 깨져 다시 할 때만 조금 흔든다
            'options': {'temperature': 0.0 if attempt == 0 else 0.3, 'seed': OLLAMA_SEED, 'num_ctx': OLLAMA_NUM_CTX},
        }, timeout=timeout)
        resp.raise_for_status()
        content = resp.json()['message']['content']
        try:
            return json.loads(content)
        except ValueError as e:
            last_err = e
            print('JSON 파싱 실패 (시도 {}): {} ... {}'.format(attempt + 1, e, content[-200:]), flush=True)
    raise RuntimeError('LLM 응답을 JSON 으로 읽지 못했습니다: {}'.format(last_err))


# ─────────────────────────── 유틸 ───────────────────────────

def fmt_ts(sec: float) -> str:
    sec = int(sec)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return '{:d}:{:02d}:{:02d}'.format(h, m, s) if h else '{:02d}:{:02d}'.format(m, s)


def fmt_dur(sec: float) -> str:
    sec = int(round(sec))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    if h:
        return '{}시간 {}분 {}초'.format(h, m, s)
    if m:
        return '{}분 {}초'.format(m, s)
    return '{}초'.format(s)


def parse_ts(value: str) -> Optional[float]:
    m = re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?', value or '')
    if not m:
        return None
    a, b, c = m.group(1), m.group(2), m.group(3)
    return int(a) * 3600 + int(b) * 60 + int(c) if c else int(a) * 60 + int(b)


def utterance_line(u: Dict) -> str:
    return '[{}] {}: {}'.format(fmt_ts(u['start']), u['speaker'], u['text'])


def chunk_utterances(utterances: List[Dict], limit: int) -> List[List[Dict]]:
    chunks, buf, size = [], [], 0
    for u in utterances:
        n = len(utterance_line(u)) + 1
        if buf and size + n > limit:
            chunks.append(buf)
            buf, size = [], 0
        buf.append(u)
        size += n
    if buf:
        chunks.append(buf)
    return chunks


def _clean_list(items, limit: int = 0) -> List[str]:
    out, seen = [], set()
    for it in items or []:
        s = re.sub(r'\s+', ' ', str(it)).strip(' -•·')
        key = re.sub(r'\W', '', s)
        if s and key and key not in seen and s not in ('없음', '해당 없음', '미정'):
            seen.add(key)
            out.append(s)
    return out[:limit] if limit else out


def _norm_title(t: str) -> str:
    return re.sub(r'\W', '', t or '')


def _bigrams(s: str) -> set:
    s = re.sub(r'\W', '', s or '')
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def _similar(a: str, b: str, threshold: float = 0.4) -> bool:
    """글자 2-gram 겹침 비율 — '7월 12일까지 TAS 품질 검토 완료' 와 '…검토 및 추가 검토 요청 완료 예정' 을 같은 항목으로 본다."""
    x, y = _bigrams(a), _bigrams(b)
    return len(x & y) / max(1, min(len(x), len(y))) >= threshold * 1.5 or len(x & y) / max(1, len(x | y)) >= threshold


def split_sentences(text: str) -> List[str]:
    parts = re.split(r'(?<=[.?!])\s+', text.strip())
    return [p for p in parts if p]


def recorded_at_from_title(title: str) -> str:
    """'통화 홍길동_261008_162732' 같은 녹음 앱 파일명에서 녹음 일시를 꺼낸다."""
    m = re.search(r'(?<!\d)(\d{2})(\d{2})(\d{2})[_-](\d{2})(\d{2})(\d{2})(?!\d)', title or '')
    if m:
        yy, mo, dd, hh, mi, _ = m.groups()
        if 1 <= int(mo) <= 12 and 1 <= int(dd) <= 31 and int(hh) < 24:
            return '20{}-{}-{} {}:{}'.format(yy, mo, dd, hh, mi)
    m = re.search(r'(20\d{2})[-.]?(\d{2})[-.]?(\d{2})', title or '')
    if m:
        return '{}-{}-{}'.format(*m.groups())
    return ''


# 빈도 키워드용 — 형태소 분석기 없이 조사를 떼고 말버릇·대명사·용언을 거른다
_JOSA = sorted(['에서는', '으로는', '에서도', '이라고', '에서', '으로', '에게', '까지', '부터', '이랑', '하고', '처럼', '보다',
                '에는', '이나', '라고', '이라', '이요', '들이', '들은', '들을', '들도', '들', '은', '는', '이', '가', '을', '를',
                '에', '의', '로', '도', '만', '과', '와', '랑', '요'], key=len, reverse=True)
# '조회하는' → '조회' 처럼 명사 뒤에 붙은 하다/되다 활용을 뗀다
_VERBALIZERS = sorted(['했습니다', '합니다', '됩니다', '하는데', '했는데', '해야', '하는', '하고', '하면', '해서', '했고', '하기',
                       '하게', '한다', '되는', '되고', '되면', '된다', '시키', '해요', '했어', '하신', '하실', '했던', '할', '한', '된',
                       '됐'], key=len, reverse=True)
# 이 어미로 끝나면 용언·부사로 보고 버린다. 한 글자 어미('면', '지' 등)는 '화면', '메시지' 같은 명사까지 지워서 쓰지 않는다
_VERB_ENDINGS = ('습니다', '니다', '어요', '아요', '에요', '예요', '는데', '지만', '같아', '같은', '있는', '없는', '거예', '거죠',
                 '건데', '거고', '니까', '어서', '아서', '으면', '면서', '라서', '네요', '군요', '는지', '을지', '려고', '도록',
                 '다고', '라고', '이다', '였다', '었다', '겠다', '셔서', '은데', '건지', '고요', '구요', '셨', '했', '겠', '었',
                 '았', '다', '요', '죠')
_STOPWORDS = set('''이제 저희 그냥 일단 부분 지금 그거 그게 이거 이게 저거 저기 근데 그리고 그래서 그러면 그러니까 어떤 이런 그런
저런 조금 정도 우리 제가 저는 그럼 이렇게 그렇게 저렇게 사실 약간 다시 한번 전반적인 전반적 관련 경우 때문 거의 계속 진행 같은
이번 다음 혹시 아니 네네 맞아 거기 여기 그쪽 이쪽 저쪽 뭔가 무슨 하나 그다음 대해서 대한 대해 말씀 생각 얘기 좀더 많이 모든
일부 별도 그때 이후 이전 하면 해서 있는 없는 하는 되는 하시 가지 이거는 그거는 이런거 그런거 어떻게 왜냐하면 아마 정말 진짜
너무 되게 엄청 예를 들어 그래 그건 이건 저건 그걸 이걸 혹은 또는 그러나 하지만 오늘 내일 어제 이상 이하 당장 바로 원래 일반
기존 해당 각각 서로 먼저 나중 처음 마지막 지난 그대로 이대로 거고 건데 거죠 거예요 겁니다 건가 거는 거를 거에 것도 것이 것은
것을 거의 다들 다른 같이 함께 여러 몇몇 계속해서 이렇 그렇 대리님 과장님 차장님 부장님 이사님 팀장님 선생님 님
현재 따로 그것 이것 저것 아예 어차피 말씀하신 말씀드린 자체 실제 만약 그대 걸로 쪽에 중에 확인 정리 요청 사항 내용 상황 방식
문제 필요 가능 이유 방법 결과 뭐가 뭐든 이렇게요 그렇죠 그러면은 그니까 그러고 하여튼 어쨌든 아무튼 그래도 그러다 보니 왜냐면
일단은 지금은 이제는 거기서 여기서 그래가지고 가지고 해가지고 이렇게나 그렇다 저희가 저희는 우리가 제가요 그분 이분 저분
있고 없고 하고 같고 되고 아니면 그런데 그다음에 나머지 이렇게 사용 작성 해당 있어 없어 같아 되게 했어'''.split())


def _strip_josa(tok: str) -> str:
    for suffixes in (_VERBALIZERS, _JOSA):
        for j in suffixes:
            if tok.endswith(j) and len(tok) - len(j) >= 2:
                return tok[:-len(j)]
    return tok


_kiwi = None


def _get_kiwi():
    """한국어 형태소 분석기(Kiwi) — venv_audio 에 kiwipiepy 가 없으면 None (그때는 글자 규칙으로 대신한다)."""
    global _kiwi
    if _kiwi is None:
        try:
            from kiwipiepy import Kiwi
            _kiwi = Kiwi()
        except Exception as e:
            print('kiwipiepy 를 못 불러 키워드를 글자 규칙으로 뽑습니다: {}'.format(e), flush=True)
            _kiwi = False
    return _kiwi or None


# 명사여도 키워드로는 의미 없는 말
_GENERIC_NOUNS = set('''부분 정도 생각 말씀 경우 때문 얘기 내용 상황 방식 문제 필요 가능 이유 방법 결과 사항 관련 진행 확인
정리 요청 사용 작성 해당 이번 다음 지금 오늘 내일 어제 이후 이전 처음 마지막 자체 실제 기존 일반 전체 하나 사람 우리 저희
거기 여기 그쪽 이쪽 저쪽 대리님 과장님 차장님 부장님 이사님 팀장님 선생님 시간 이상 이하 정말 진짜 계속 다시
예정 여부 완료 예상 검토 논의 공유'''.split())


def _noun_counts_kiwi(kiwi, utterances: List[Dict]) -> Dict[str, int]:
    """형태소 분석으로 명사(NNG·NNP)와 영문(SL)만 센다 — '에서'(조사), '않나'(보조용언+어미),
    '제대'(부사 '제대로'를 조사 '로'로 잘못 떼던 것) 같은 게 키워드로 잡히던 문제 (2026-10-12)."""
    counts = {}
    for u in utterances:
        text = u['text']
        # 붙여 쓴 명사는 하나로 — Kiwi 는 '요구사항' 을 '요구'+'사항' 으로 쪼개 '요구' 가 따로 잡혔다.
        # 명사·영문·명사파생접미사(XSN: '사용자'의 '자')가 띄어쓰기 없이 이어지면 한 덩어리로 센다
        groups, cur, prev_end = [], [], -1
        for t in kiwi.tokenize(text):
            joinable = t.tag in ('NNG', 'NNP', 'SL', 'XSN')
            if joinable and cur and t.start == prev_end:
                cur.append(t)
            else:
                if cur:
                    groups.append(cur)
                cur = [t] if joinable and t.tag != 'XSN' else []
            prev_end = t.start + t.len
        if cur:
            groups.append(cur)
        for g in groups:
            term = text[g[0].start:g[-1].start + g[-1].len]
            if len(g) == 1 and g[0].tag == 'SL':
                if len(term) < 2:
                    continue
                term = term.upper() if len(term) <= 4 else term  # api / Api → API
            elif len(term) < 2 or term in _GENERIC_NOUNS or term in _STOPWORDS:
                continue
            elif g[-1].tag == 'XSN' and g[-1].form == '적':
                continue  # '전반적', '기본적' — 관형어라 키워드가 아니다
            counts[term] = counts.get(term, 0) + 1
    return counts


def is_keyword_like(term: str) -> bool:
    """LLM 이 고른 키워드 검사 — 동사·형용사·어미·조사·부사가 섞이면 키워드가 아니다 ('하셔야', '있지' 등)."""
    kiwi = _get_kiwi()
    if not kiwi:
        return True
    tags = [t.tag for t in kiwi.tokenize(term)]
    if not tags or any(tag.startswith(('V', 'E', 'J')) or tag in ('MAG', 'MAJ', 'IC', 'XSV', 'XSA') for tag in tags):
        return False
    return any(tag.startswith('N') or tag in ('SL', 'SN', 'SH') for tag in tags)


def frequent_terms(utterances: List[Dict], limit: int = 20, min_count: int = 3) -> List[Tuple[str, int]]:
    """대화록에서 자주 나온 명사성 용어 — 클로바노트 '주요 키워드'처럼 '함수', '화면', 'API' 같은 업무 용어가 잡힌다."""
    kiwi = _get_kiwi()
    if kiwi:
        counts = _noun_counts_kiwi(kiwi, utterances)
        ranked = sorted((kv for kv in counts.items() if kv[1] >= min_count), key=lambda kv: -kv[1])
        return ranked[:limit]
    # kiwipiepy 가 없을 때의 대체 — 조사·어미를 글자 규칙으로 뗀다 (부정확: '제대로'→'제대')
    counts = {}
    for u in utterances:
        for tok in re.findall(r'[가-힣]{2,}|[A-Za-z][A-Za-z0-9]+', u['text']):
            if re.match(r'[A-Za-z]', tok):
                term = tok.upper() if len(tok) <= 4 else tok  # api / Api → API
            else:
                term = _strip_josa(tok)
                if term.endswith(_VERB_ENDINGS) or term in _STOPWORDS or len(term) < 2:
                    continue
            counts[term] = counts.get(term, 0) + 1
    ranked = sorted((kv for kv in counts.items() if kv[1] >= min_count), key=lambda kv: -kv[1])
    return ranked[:limit]


def count_keyword(keyword: str, haystack_lower: str) -> int:
    k = keyword.strip().lower()
    return haystack_lower.count(k) if k else 0


KW_FREQ_QUOTA = 16   # 자주 나온 업무 용어 ('화면', '함수', '차주' …)
KW_LLM_QUOTA = 10    # LLM 이 고른 핵심 용어 중 많이 나온 것 ('신용평가', '프로토타입' …)
KW_ACRONYM_MIN = 3   # 영문 약어는 이 횟수 이상이면 추가 ('PC', 'RWA' …)


def select_keywords(utterances: List[Dict], llm_keywords: List[str], user_terms: Optional[List[str]] = None) -> List[Dict]:
    """주요 키워드 = 단어장 용어 + 빈도 상위어 + LLM 핵심 용어 + 영문 약어. 대화록에 실제로 있는 표기만, 횟수순.

    - 단어장 용어(user_terms): 사용자가 중요하다고 등록한 것이라 한 번만 나와도 정원과 무관하게 넣는다.
      중요한 고유 용어일수록 자주 안 나오고('프로프레임' 4회 — 빈도 정원 밖), LLM 은 실행마다 고르는 게 달라서
      어떤 날은 빠졌다 (2026-10-12).
    - 나머지는 정원제: 한 출처를 '보호'하면 그쪽이 많을 때 다른 쪽이 통째로 밀려난다 — LLM 이 16개를 고른 날엔
      '차주', '파일', '엑셀' 같은 빈도 상위어가 사라졌다 (클로바노트 키워드와 일치 14/20 → 7/20).
    화면에서 누르면 대화록에서 하이라이트하므로 count 는 대화록 원문 기준 등장 횟수다.
    """
    haystack = '\n'.join(u['text'] for u in utterances).lower()
    found = {}
    pinned = set()
    for k in _clean_list(user_terms):
        n = count_keyword(k, haystack)
        if n:
            found[k] = n
            pinned.add(k)
    for term, _ in frequent_terms(utterances, limit=KW_FREQ_QUOTA, min_count=3):
        if not any(f.lower() == term.lower() for f in found):
            found[term] = count_keyword(term, haystack)
    llm = []
    for k in _clean_list(llm_keywords):
        n = count_keyword(k, haystack)
        if (n and len(k) >= 2 and is_keyword_like(k) and not any(f.lower() == k.lower() for f in found)
                and k not in {x for x, _ in llm}):
            llm.append((k, n))
    for k, n in sorted(llm, key=lambda kv: -kv[1])[:KW_LLM_QUOTA]:
        found[k] = n
    for term, n in frequent_terms(utterances, limit=300, min_count=KW_ACRONYM_MIN):
        if re.fullmatch(r'[A-Z0-9]{2,5}', term) and term not in found:
            found[term] = count_keyword(term, haystack)
    # '프레임' 이 대부분 '프로프레임' 의 일부로만 나왔으면 짧은 쪽을 뺀다
    terms = list(found)
    for short in terms:
        if short in pinned:
            # 단어장끼리 '박인우' ⊂ '박인우 대리' 처럼 겹치고 횟수도 같으면(=늘 붙어서만 나옴) 긴 쪽만 남긴다
            if any(short != long and long in pinned and short in long and found.get(long) == found.get(short)
                   for long in terms):
                found.pop(short, None)
            continue
        for long in terms:
            if short != long and short.lower() in long.lower() and found.get(short, 0) - found.get(long, 0) < 2:
                found.pop(short, None)
                break
    return sorted(({'word': k, 'count': n} for k, n in found.items() if n), key=lambda x: -x['count'])


# ─────────────────────────── 근거 검증 ───────────────────────────
# 7.8B 는 빈 목록을 그럴듯한 항목으로 채우는 경향이 강하다 — 지시문만으로는 못 막아서 코드로 걸러낸다 (2026-10-17)

QUOTE_MATCH_MIN = 0.6    # quote 의 글자 3-gram 중 이 비율 이상이 한 발화(+다음 발화)에 있어야 근거로 인정
SUPPORT_MIN = 0.6        # 항목 내용의 명사 중 이 비율 이상이 근거 발언 주변에 실제로 있어야 남긴다
CONTEXT_BEFORE, CONTEXT_AFTER = 3, 4   # '근거 발언 주변' = 앞 3 · 뒤 4 발화 (질문-답이 몇 발화에 걸친다)

# 항목 문장에 흔히 붙는 말 — 원문에 없어도 지어낸 내용은 아니므로 검사에서 뺀다
_META_NOUNS = set('''위험 리스크 지연 가능성 일정 대응 방안 조정 문제 우려 영향 결정 요청 예정 작업 담당 추가 협의 계획 마감
변경 차질 미정 화자 여부 시점 기간 준비 반영 이슈 미결 조치 수신 요청자 확정 합의 처리 제공 전달 관리 설정 보고 업무 담당자
불명확 명확 구체 일관성 접근성 프로세스 대한 방법 시기 사항 내용 진행 필요 확인 검토 공유 완료 예상 논의 결과'''.split())

# 예정/변경/마감은 LLM 에게 고르게 하지 않고 근거 발언의 표현으로 정한다
_KIND_CHANGE = re.compile(r'연기|미뤄|미루|늦어|뒤로|변경|바뀌|바꿔|조정|당겨|밀려')
_KIND_DUE = re.compile(r'까지|마감|기한|이내')
# 항목 종류별로 근거 문장(인용 문장 ±1)에 있어야 하는 표현. 7.8B 는 '오늘 검토 요청 드릴 예정'(보고)을 결정으로,
# '타 시스템은 접속을 막아요'(설명)를 리스크로 넣었다. 같은 모델에게 원문 대조 판정을 시켜 봤지만 '기한이 없어서 틀림'
# 처럼 기준을 못 지키고 정작 '은행에 요청'은 통과시켜서 접었다 (2026-10-17) — 표현 유무로 거른다
_CUES = {
    # '하면 될 것 같습니다'·'~할 예정입니다' 는 보고에도 늘 붙어서 뺐다 — '남기기로 했거든요' 처럼 '~기로' 는 넣었다 (2026-10-18)
    'decisions': re.compile(r'기로|걸로 ?하|걸로 ?가|걸로 ?정|것으로 ?하|확정|결정|정했|합의|그렇게 하|그렇게 진행|'
                            r'하시죠|가시죠|로 가죠|로 하죠'),
    # 맨 '요청' 은 '요청드린 상태입니다'(보고)에도 걸려서 뺐다
    'requests': re.compile(r'주세요|주시|주셔|주실|줘요|달라|부탁|요청 ?드립|요청 ?드릴게|올려 ?주|보내 ?주|알려 ?주|해 ?줄|'
                           r'드려도|해야 ?되거든'),
    'risks': re.compile(r'안 ?되|안 ?돼|안 ?열|안 ?맞|못 ?하|못 ?할|못 ?했|못 ?쓰|문제|어렵|어려|우려|걱정|늦어|늦게|지연|'
                        r'연락이 없|답을 안|불가능|막혀|부족|리스크|이슈|이해가 ?안|뒤로 갈|넘어가|미뤄|오래 걸|느려|느리|모르겠'),
    'issues': re.compile(r'확인해|확인하|확인 ?후|나중에|추후|다시|고민|정해|확정|알려|말씀드리|검토|모르|아직|결정|물어보|의견'),
}

# 결정·미결은 질문 뒤 답에서 정해지거나 미뤄진다('알림은 어떻게 관리하실 거예요?' → 두 발화 뒤 '그거는 한번 보시고
# 말해주세요') — 이 둘은 근거 다음 발화까지 표현을 찾는다
_CUE_IN_REPLY = ('decisions', 'issues')
CUE_REPLY_UTTS = 2

_DATE_FILLERS = {'까지', '경', '정도', '중', '쯤', '이내', '부터', '이후', '이전', '말', '초', '중순', '예정', '전', '안'}
_WEEKDAYS = '월화수목금토일'


def _norm(s: str) -> str:
    return re.sub(r'[\W_]', '', s or '').lower()


def _grams(s: str, n: int = 3) -> set:
    s = _norm(s)
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


_QUOTE_SPLIT = re.compile(r'\n|\[[\d:]+\]|화자\s?\d*\s*[:：]')
QUOTE_KEEP_CHARS = 80  # 화면에 보여 줄 근거 인용 길이


def _strip_quote(quote: str) -> str:
    """모델이 대화록 줄 모양대로 '[12:34] 화자 10: …' 를 붙이거나, 지시(15~40자)를 어기고 여러 발화를
    '…\\n화자 6: …' 로 이어 붙여 인용하곤 한다 (20261008 회의 34개 중 18개) — 첫 발화 조각만 쓴다."""
    for seg in _QUOTE_SPLIT.split(quote or ''):
        seg = seg.strip(' "\'“”')
        if len(_norm(seg)) >= 5:
            return seg[:QUOTE_KEEP_CHARS]
    return (quote or '').strip()[:QUOTE_KEEP_CHARS]


def _locate_quote(quote: str, utts: List[Dict], hint: Optional[float]) -> Optional[int]:
    """quote 가 나온 발화의 위치. 화자분리가 한 문장을 두 발화로 쪼개곤 해서 다음 발화까지 이어 붙여 본다."""
    q = _grams(_strip_quote(quote))
    if len(q) < 3:  # 다섯 글자도 안 되는 인용은 어디에나 맞는다
        return None
    best_key, best_i = None, None
    for i, u in enumerate(utts):
        nxt = utts[i + 1]['text'] if i + 1 < len(utts) else ''
        win = _grams(u['text'] + nxt)
        key = (round(len(q & win) / len(q), 3), len(q & _grams(u['text'])),
               -abs(u['start'] - hint) if hint is not None else 0)
        if best_key is None or key > best_key:
            best_key, best_i = key, i
    return best_i if best_key and best_key[0] >= QUOTE_MATCH_MIN else None


def _near_sentences(utts: List[Dict], quote: str) -> str:
    """인용과 가장 많이 겹치는 문장과 그 앞뒤 한 문장."""
    sents = [x for u in utts for x in split_sentences(u['text'])]
    if not sents:
        return ''
    q = _grams(quote)
    best = max(range(len(sents)), key=lambda k: len(q & _grams(sents[k])))
    return ' '.join(sents[max(0, best - 1):best + 2])


def _content_nouns(text: str) -> List[str]:
    text = re.sub(r'화자\s?\d+', ' ', text or '')
    kiwi = _get_kiwi()
    if kiwi:
        toks = [t.form for t in kiwi.tokenize(text) if t.tag in ('NNG', 'NNP', 'SL', 'SN')]
    else:
        toks = [_strip_josa(t) for t in re.findall(r'[가-힣]{2,}|[A-Za-z]{2,}|\d+', text)]
    skip = _GENERIC_NOUNS | _META_NOUNS | _STOPWORDS
    return [t for t in toks if (len(t) >= 2 or t.isdigit()) and t not in skip]


def _supported(text: str, ctx_norm: str) -> bool:
    """text 의 명사 대부분이 근거 주변 원문에 있는가 — '은행에 함수 목록 요청'처럼 원문에 없는 대상·사실을 지어낸 걸 잡는다."""
    nouns = _content_nouns(text)
    if not nouns:
        return True
    return sum(1 for n in nouns if _norm(n) in ctx_norm) / len(nouns) >= SUPPORT_MIN


def _canon_date_words(s: str) -> str:
    s = _norm(s)
    for a, b in (('이번주', '금주'), ('다음주', '차주'), ('금일', '오늘'), ('명일', '내일')):
        s = s.replace(a, b)
    return s


def _date_said(date: str, ctx_norm: str) -> bool:
    """날짜 표현의 숫자·날짜어가 근거 주변 원문에 그대로 있는가 — 다른 일정의 날짜가 붙은 걸 잡는다."""
    ctx = _canon_date_words(ctx_norm)
    for tok in re.findall(r'\d+[월일주년시분]?|[가-힣A-Za-z]+', _canon_date_words(date)):
        if tok not in _DATE_FILLERS and tok not in ctx:
            return False
    return True


def _is_unset(s: str) -> bool:
    return (s or '').strip() in ('', '-', '미정', '불명', '없음', '해당 없음', '없다')


def _person_ok(who: str, speakers_set: set, ctx_norm: str) -> bool:
    """담당·수신자 검사 — '화자 N' 은 실제 화자여야 하고, 이름·부서는 근거 주변 원문에 나와야 한다."""
    if _is_unset(who):
        return False
    m = re.match(r'^화자\s?(\d+)', who.strip())
    if m:
        return '화자 ' + m.group(1) in speakers_set
    nouns = _content_nouns(who) or [who]
    return all(_norm(n) in ctx_norm for n in nouns)


def schedule_kind(text: str) -> str:
    if _KIND_CHANGE.search(text or ''):
        return '변경'
    if _KIND_DUE.search(text or ''):
        return '마감'
    return '예정'


def resolve_date(expr: str, base: str) -> str:
    """'차주 화요일' → '10/20(화)' — base 는 녹음 일시('2026-10-12 …'). 못 풀면 ''.
    월 단위('11월~12월')·기간처럼 하루로 못 박을 수 없는 건 풀지 않는다."""
    import datetime
    if not expr or not base or not re.match(r'\d{4}-\d{2}-\d{2}', base):
        return ''
    b = datetime.date(int(base[:4]), int(base[5:7]), int(base[8:10]))
    s = _canon_date_words(expr)

    def fmt(d):
        return '{}/{}({})'.format(d.month, d.day, _WEEKDAYS[d.weekday()])

    m = re.search(r'(?<!\d)(\d{1,2})월(\d{1,2})일', s)
    if m:
        mo, dd = int(m.group(1)), int(m.group(2))
        try:
            return fmt(datetime.date(b.year + (1 if mo < b.month - 6 else 0), mo, dd))
        except ValueError:
            return ''
    # 월 단위('11월~12월')와 월 없는 날짜('12일까지')는 풀지 않는다 — 20261008 회의의 '12일까지'는 앞 문장의
    # '7월 8일' 에 이어진 7월 12일이었는데 녹음일 기준으로 10/12 로 풀렸다 (2026-10-18)
    if re.search(r'\d월|\d일', s):
        return ''
    for word, days in (('오늘', 0), ('내일', 1), ('모레', 2)):
        if word in s:
            return fmt(b + datetime.timedelta(days))
    wd = re.search('([월화수목금토일])요일', s)
    week = 0 if '금주' in s else 1 if '차주' in s else None
    if week is not None:
        monday = b - datetime.timedelta(b.weekday()) + datetime.timedelta(weeks=week)
        if wd:
            return fmt(monday + datetime.timedelta(_WEEKDAYS.index(wd.group(1))))
        return '{}~{}'.format(fmt(monday), fmt(monday + datetime.timedelta(4)))
    if wd:
        return fmt(b + datetime.timedelta((_WEEKDAYS.index(wd.group(1)) - b.weekday()) % 7 or 7))
    return ''


# 목록 → (본문 칸, 근거 확인이 필요한 보조 칸)
_GROUND_SPEC = (
    ('decisions', 'content'),
    ('requests', 'content'),
    ('action_items', 'task'),
    ('risks', 'issue'),
    ('issues', 'content'),
    ('schedule', 'item'),
)


def _ground_items(res: Dict, chunk: List[Dict], speakers_set: set, diarized: bool, stats: Dict) -> None:
    """구간 결과의 각 항목을 원문과 대조해 근거 없는 건 버리고, 근거 시각(ts)을 원문 기준으로 바로잡는다.
    stats 에 목록별 {kept, no_quote, unsupported, bad_date, no_cue} 를 센다."""
    for key, main in _GROUND_SPEC:
        st = stats.setdefault(key, {'kept': 0, 'no_quote': 0, 'unsupported': 0, 'bad_date': 0})
        kept = []
        for it in res.get(key) or []:
            if not isinstance(it, dict):
                continue
            text = re.sub(r'\s+', ' ', str(it.get(main) or '')).strip(' -•·')
            if _is_unset(text):
                continue
            i = _locate_quote(str(it.get('quote') or ''), chunk, parse_ts(str(it.get('ts') or '')))
            if i is None:
                st['no_quote'] += 1
                print('  버림[{} 근거 없음] {} ← "{}"'.format(key, text, it.get('quote')), flush=True)
                continue
            ctx = _norm(' '.join(u['text'] for u in chunk[max(0, i - CONTEXT_BEFORE):i + CONTEXT_AFTER + 1]))
            if not _supported(text, ctx):
                st['unsupported'] += 1
                print('  버림[{} 원문에 없는 내용] {} ← "{}"'.format(key, text, it.get('quote')), flush=True)
                continue
            u = chunk[i]
            row = {main: text, 'ts': u['start'], 'quote': _strip_quote(str(it.get('quote') or ''))}
            cue = _CUES.get(key)
            cue_text = _near_sentences(chunk[i:i + 2], row['quote'])
            if key in _CUE_IN_REPLY:
                cue_text += ' ' + ' '.join(u2['text'] for u2 in chunk[i + 1:i + 1 + CUE_REPLY_UTTS])
            if cue and not cue.search(cue_text):
                st['no_cue'] = st.get('no_cue', 0) + 1
                print('  버림[{} 해당 표현 없음] {} ← "{}"'.format(key, text, row['quote']), flush=True)
                continue
            if key == 'requests':
                row['requester'] = u['speaker'] if diarized else '미정'  # 요청한 사람 = 근거 발언을 한 사람
                rcp = str(it.get('recipient') or '').strip()
                same = re.sub(r'\D', '', rcp.split('(')[0]) == re.sub(r'\D', '', row['requester']) != ''
                row['recipient'] = rcp if _person_ok(rcp, speakers_set, ctx) and not same else '미정'
            elif key == 'action_items':
                owner = str(it.get('owner') or '').strip()
                due = str(it.get('due') or '').strip()
                row['owner'] = owner if _person_ok(owner, speakers_set, ctx) else '미정'
                row['due'] = due if not _is_unset(due) and _date_said(due, ctx) else '미정'
            elif key == 'risks':
                for src, dst in (('impact', 'risk'), ('response', 'response')):  # 'risk' 는 예전 결과와 같은 칸 이름
                    v = re.sub(r'\s+', ' ', str(it.get(src) or '')).strip()
                    row[dst] = v if not _is_unset(v) and _supported(v, ctx) else ''
            elif key == 'schedule':
                date = str(it.get('date') or '').strip()
                if _is_unset(date) or not _date_said(date, ctx):
                    st['bad_date'] += 1
                    print('  버림[schedule 날짜가 원문에 없음] {} {} ← "{}"'.format(text, date, it.get('quote')), flush=True)
                    continue
                row['date'] = date
                # '변경'은 인용 문장 앞뒤 한 문장까지('소프트웨어는 좀 더 뒤로 갈 수도 있어요. 운영 쪽은 … 11월, 12월'),
                # '마감'은 인용·날짜로만 본다 — 항목 이름('설치 완료 기한')의 '기한'으로 마감이 되거나,
                # 발언 전체를 보면 딴 얘기('메뉴 명칭 변경')로 변경이 되던 것 (2026-10-17)
                near = _near_sentences(chunk[i:i + 2], row['quote'])
                row['kind'] = '변경' if _KIND_CHANGE.search(near) else schedule_kind(row['quote'] + ' ' + date)
            kept.append(row)
        st['kept'] += len(kept)
        res[key] = kept


def _needs_refine(text: str, quote: str) -> bool:
    """대상이 없거나('링크 공유'), 너무 짧거나, 근거를 거의 그대로 베낀('연락이 없다') 항목."""
    g = _grams(text)
    return is_vague(text) or len(_norm(text)) < 8 or len(g & _grams(quote)) / max(1, len(g)) >= 0.7


def _clean_refined(t: str, old: str) -> str:
    """모델이 붙이곤 하는 '[조치] …', '… (화자 5)', '원래 문장 — 새 문장' 을 걷어낸다."""
    t = re.sub(r'\s+', ' ', t or '').strip(' -•·"')
    t = re.sub(r'^\[[^\]]{1,6}\]\s*', '', t)
    t = re.sub(r'\s*\((화자|담당)[^)]*\)\s*$', '', t)
    parts = [x.strip() for x in t.split(' — ') if x.strip()]
    if len(parts) > 1 and _similar(parts[0], old):
        t = parts[1]
    elif parts:
        t = parts[0]
    return t.strip()


def _refine_items(res: Dict, chunk: List[Dict], stats: Dict) -> None:
    """대상이 빠진 항목만 앞뒤 대화와 함께 다시 쓰게 한다. 다시 쓴 문장의 명사 대부분과 숫자·날짜어 전부가
    그 앞뒤 대화에 있어야 바꾸고, 아니면 원래 문장을 둔다 — 구체화하다 지어내지 않게."""
    starts = [u['start'] for u in chunk]
    todo = []
    for key, main in _GROUND_SPEC:
        for x in res.get(key) or []:
            if _needs_refine(x[main], x['quote']):
                i = min(range(len(chunk)), key=lambda k: abs(starts[k] - x['ts']))
                todo.append((key, main, x, chunk[max(0, i - REFINE_CONTEXT_BEFORE):i + REFINE_CONTEXT_AFTER + 1]))
    for b in range(0, len(todo), REFINE_BATCH):
        batch = todo[b:b + REFINE_BATCH]
        blocks = []
        for n, (key, main, x, ctx_utts) in enumerate(batch, 1):
            who = (' (요청자 {})'.format(x['requester']) if key == 'requests' else
                   ' (담당 {})'.format(x['owner']) if key == 'action_items' else '')
            blocks.append('### 항목 {} [{}] {}{}\n근거: [{}] "{}"\n[앞뒤 대화]\n{}'.format(
                n, _REFINE_LABEL[key], x[main], who, fmt_ts(x['ts']), x['quote'],
                '\n'.join(utterance_line(u)[:REFINE_LINE_CHARS] for u in ctx_utts)))
        out = _ollama_json(REFINE_PROMPT.format(items='\n\n'.join(blocks)), REFINE_SCHEMA)
        texts = {}
        for r in out.get('results') or []:
            m = re.search(r'\d+', str(r.get('no') or ''))
            if m:
                texts[int(m.group())] = str(r.get('text') or '')
        for n, (key, main, x, ctx_utts) in enumerate(batch, 1):
            new = _clean_refined(texts.get(n, ''), x[main])
            if key == 'schedule':  # 날짜는 옆 칸에 있다 — '산출문 검토 완료 예정 (10월 14일까지)' 의 괄호를 뗀다
                new = re.sub(r'\s*\([^)]*\)$', '', new)
            if not new or _norm(new) == _norm(x[main]):
                continue
            ctx = _norm(' '.join(u['text'] for u in ctx_utts))
            cctx = _canon_date_words(ctx)
            exact_ok = all(_canon_date_words(tok) in cctx for tok in _EXACT_TOKENS.findall(new))
            if _supported(new, ctx) and exact_ok:
                print('  구체화[{}] {} → {}'.format(key, x[main], new), flush=True)
                x[main] = new
                stats[key]['refined'] = stats[key].get('refined', 0) + 1
            else:
                print('  구체화 거부[{} 원문에 없는 내용] {} → {}'.format(key, x[main], new), flush=True)
    # 그래도 '링크 공유', '연락이 없다'처럼 무엇에 대한 건지 모르는 항목은 버린다. 주제 이름을 앞에 붙여 봤지만
    # 주제 경계가 느슨해 '[시스템 접근 권한 설정] 연락이 없다'(실제로는 티맥스 회신) 처럼 오히려 틀린 맥락이 붙었다 (2026-10-18)
    for key, main in _GROUND_SPEC:
        kept = []
        for x in res.get(key) or []:
            if is_vague(x[main]):
                stats[key]['vague'] = stats[key].get('vague', 0) + 1
                stats[key]['kept'] -= 1
                print('  버림[{} 대상 불명] {} ← "{}"'.format(key, x[main], x['quote']), flush=True)
            else:
                kept.append(x)
        res[key] = kept


def is_vague(text: str) -> bool:
    """'링크 공유', '자료 전달'처럼 무엇에 대한 건지 알 수 있는 명사가 하나도 없는가."""
    return not [n for n in _content_nouns(text) if n not in _VAGUE_NOUNS]


# ─────────────────────────── 분석 ───────────────────────────

def _speaker_intros(utterances: List[Dict], per_speaker: int = 2, max_chars: int = 120) -> str:
    """화자별 처음 몇 발언 — 통합 단계는 원문을 못 보므로 '박인호 대리입니다' 같은 자기소개를 따로 넘긴다."""
    seen, lines = {}, []
    for u in utterances:
        n = seen.get(u['speaker'], 0)
        if n < per_speaker:
            seen[u['speaker']] = n + 1
            lines.append('{}: {}'.format(u['speaker'], u['text'][:max_chars]))
    return '\n'.join(lines)


def analyze(utterances: List[Dict], duration: float, diarized: bool, speakers: List[str],
            progress: ProgressFn, p_start: float, p_end: float, kind_hint: str = '',
            user_terms: Optional[List[str]] = None, base_date: str = '') -> Dict:
    """kind_hint: 파일명으로 알 수 있는 녹음 종류 (예: '통화 녹음') — 없으면 내용으로 판단한다.
    user_terms: 단어장·업로드 때 적은 용어 — 대화록에 나오면 키워드에 항상 넣는다.
    base_date: 녹음 일시('2026-10-08 16:27') — '차주 화요일' 같은 상대 날짜를 실제 날짜로 푸는 기준. 없으면 안 푼다."""
    note = '' if diarized else NO_SPEAKER_NOTE
    chunks = chunk_utterances(utterances, SUMMARY_CHUNK_CHARS)
    span = (p_end - p_start)
    valid_speakers = set(speakers)

    # 1. 구간 분석 + 근거 검증
    chunk_results = []
    grounding = {}  # type: Dict[str, Dict[str, int]]
    steps = len(chunks) * len(CHUNK_PASSES)
    for i, chunk in enumerate(chunks, 1):
        c_start, c_end = chunk[0]['start'], chunk[-1]['end']
        text = '\n'.join(utterance_line(u) for u in chunk)
        res = {}  # type: Dict
        for n, (label, prompt, schema) in enumerate(CHUNK_PASSES):
            done = (i - 1) * len(CHUNK_PASSES) + n
            progress(p_start + span * 0.8 * done / steps, '내용 분석 중 ({}/{} {})'.format(i, len(chunks), label))
            part = _ollama_json(prompt.format(idx=i, total=len(chunks), start=fmt_ts(c_start), end=fmt_ts(c_end),
                                              note=note, text=text), schema)
            for key in schema['required']:
                res[key] = part.get(key) or []
        res['_start'], res['_end'] = c_start, c_end
        _ground_items(res, chunk, valid_speakers, diarized, grounding)
        progress(p_start + span * 0.8 * (i - 0.1) / len(chunks), '내용 분석 중 ({}/{} 항목 구체화)'.format(i, len(chunks)))
        _refine_items(res, chunk, grounding)
        chunk_results.append(res)
    print('근거 검증(남음/전체): ' + ', '.join('{} {}/{}'.format(k, v['kept'], sum(v.values()))
                                         for k, v in grounding.items()), flush=True)

    # 주제: 시각 보정 후 시간순으로 이어 붙이고 인접한 같은 주제는 합친다
    topics = []
    for res in chunk_results:
        for t in res.get('topics') or []:
            title = re.sub(r'\s+', ' ', t.get('title') or '').strip()
            if not title:
                continue
            start = parse_ts(t.get('start'))
            if start is None or not (res['_start'] - 5 <= start <= res['_end'] + 5):
                start = topics[-1]['start'] if topics and topics[-1]['start'] >= res['_start'] else res['_start']
            spk = [s for s in _clean_list(t.get('speakers')) if s in valid_speakers]
            item = {'title': title, 'start': start, 'points': _clean_list(t.get('points')),
                    'conclusion': (t.get('conclusion') or '').strip(), 'speakers': spk}
            if topics and _norm_title(topics[-1]['title']) == _norm_title(title):
                prev = topics[-1]
                prev['points'] = _clean_list(prev['points'] + item['points'])
                prev['speakers'] = _clean_list(prev['speakers'] + item['speakers'])
                if item['conclusion'] and '결론 없음' not in item['conclusion']:
                    prev['conclusion'] = item['conclusion']
            else:
                topics.append(item)
    topics.sort(key=lambda t: t['start'])
    for i, t in enumerate(topics):
        t['end'] = topics[i + 1]['start'] if i + 1 < len(topics) else duration
        # 주제 구간 안에서 실제로 말한 화자 (LLM 이 빠뜨린 화자 보완, 발화 시간순)
        if diarized:
            inside = [u['speaker'] for u in utterances if t['start'] <= u['start'] < max(t['end'], t['start'] + 1)]
            t['speakers'] = _clean_list(t['speakers'] + sorted(set(inside), key=inside.index))

    # 2. 통합
    progress(p_start + span * 0.85, '전체 결론 정리 중')
    merge_data = _compact_for_merge(chunk_results)
    hint = ', '.join(x for x in (kind_hint, '화자 {}명'.format(len(speakers)) if diarized else '화자 구분 없음') if x)
    merged = _ollama_json(MERGE_PROMPT.format(
        kind_hint=hint, duration=fmt_dur(duration), speakers=', '.join(speakers) if diarized else '화자 구분 없음',
        note=note, intros=_speaker_intros(utterances), data=merge_data), MERGE_SCHEMA)
    if kind_hint == '통화 녹음':
        merged['type'] = '통화'  # 파일명이 통화 녹음이면 내용과 무관하게 통화 (작은 모델이 '회의'로 답하곤 한다)

    keywords = select_keywords(utterances, list(merged.get('keywords') or []) +
                               [k for r in chunk_results for k in (r.get('keywords') or [])], user_terms)

    def gathered(key):  # 근거 검증을 통과한 구간 결과만, 시간순
        return sorted((x for r in chunk_results for x in (r.get(key) or [])), key=lambda x: x['ts'])

    decisions = _dedupe_objects(gathered('decisions'), 'content', 15)
    issues = _dedupe_objects(gathered('issues'), 'content', 12)
    actions = _dedupe_objects(gathered('action_items'), 'task', 20)
    # 조치사항으로 이미 잡힌 요청은 요청사항에서 뺀다 — 같은 일이 두 항목에 반복되지 않게 (같은 대목일 때만)
    requests = [x for x in _dedupe_objects(gathered('requests'), 'content', 15)
                if not any(_similar(x['content'], a['task']) and abs(x['ts'] - a['ts']) <= 60 for a in actions)]
    risks = _dedupe_objects(gathered('risks'), 'issue', 12)
    # 같은 일의 일정이라도 날짜가 다르면(변경 등) 따로 남긴다
    schedule = _dedupe_objects(gathered('schedule'), 'item', 15, same=('date',))
    for s in schedule:
        s['resolved'] = resolve_date(s['date'], base_date)
    for x in actions:
        x['due_resolved'] = resolve_date(x['due'], base_date) if x['due'] != '미정' else ''

    # 항목을 근거 시각으로 주제에 붙인다 — 회의록에서 검토 결과 아래 세부로 보여 준다
    for x in decisions + issues + actions + requests + risks + schedule:
        x['topic'] = max([i for i, t in enumerate(topics) if t['start'] <= x['ts'] + 1] or [0]) if topics else -1

    participants = []
    for p in merged.get('participants') or []:
        if not diarized or p.get('speaker') in valid_speakers:
            participants.append({'speaker': p.get('speaker', ''), 'role': (p.get('role') or '불명').strip()})
    if diarized:  # LLM 이 빠뜨린 화자도 표에 남긴다
        known = {p['speaker'] for p in participants}
        participants += [{'speaker': s, 'role': '불명'} for s in speakers if s not in known]
        participants.sort(key=lambda p: _speaker_no(p['speaker']))

    progress(p_end, '분석 완료')
    return {
        'title': (merged.get('title') or '').strip(),
        'type': (merged.get('type') or '').strip(),
        'purpose': (merged.get('purpose') or '').strip(),
        'overview': (merged.get('overview') or '').strip(),
        # 3~5문장으로 시켜도 7.8B 는 10문장씩 쓴다 — 앞 5문장만 (중요한 순서로 쓰라고 시켰다)
        'summary_text': ' '.join(split_sentences(merged.get('summary_text') or '')[:5]),
        'participants': participants,
        'keywords': keywords,
        'topics': topics,
        'decisions': decisions,
        'requests': requests,
        'action_items': actions,
        'risks': risks,
        'issues': issues,
        'schedule': schedule,
        'grounding': grounding,
        'model': OLLAMA_MODEL,
    }


def _shared_nouns(a: str, b: str) -> int:
    return len(set(_content_nouns(a)) & set(_content_nouns(b)))


def _dedupe_objects(items: List[Dict], key: str, limit: int, defaults: Optional[Dict[str, str]] = None,
                    same: Tuple[str, ...] = ()) -> List[Dict]:
    """key 필드가 비슷한(_similar) 항목은 앞의 것만 남긴다 (same 칸까지 같을 때만). 나머지 칸은 그대로 두고,
    defaults 에 있는 칸이 비면 채운다 ('불명' 도 '미정' 으로)."""
    out = []  # type: List[Dict]
    for it in items:
        it = it or {}
        main = re.sub(r'\s+', ' ', str(it.get(key) or '')).strip()
        # 같은 발언(ts)에서 나온 항목은 더 느슨하게 같다고 본다 — '함수 범위 재검토 요청' / '함수 범위에 대한 판단을 다시 해주시면'
        if not main or any((_similar(main, o[key]) or (it.get('ts') is not None and it.get('ts') == o.get('ts')
                                                       and _shared_nouns(main, o[key]) >= 2))
                           and all(_norm(str(it.get(k))) == _norm(str(o.get(k))) for k in same) for o in out):
            continue
        row = dict(it)
        row[key] = main
        for k, d in (defaults or {}).items():
            v = str(it.get(k) or '').strip()
            row[k] = d if v in ('', '불명', '없음') else v
        out.append(row)
    return out[:limit]


def item_text(x, key: str = 'content') -> str:
    """결정·미결은 예전 결과(2026-10-17 이전)에선 문자열, 지금은 {content, ts, quote} — 둘 다 읽는다."""
    return x if isinstance(x, str) else str((x or {}).get(key) or '')


def _digest(a: Dict) -> str:
    """이전 회의 비교용 요약 — 결정·조치·요청·일정·이슈만 짧게."""
    lines = ['제목: ' + (a.get('title') or '')]
    lines += ['결정: ' + item_text(d) for d in a.get('decisions') or []]
    lines += ['조치: {} (담당 {}, 기한 {})'.format(x['task'], x['owner'], x['due']) for x in a.get('action_items') or []]
    lines += ['요청: {} ({} → {})'.format(x['content'], x['requester'], x['recipient']) for x in a.get('requests') or []]
    lines += ['일정: {} {} ({})'.format(x['item'], x['date'], x['kind']) for x in a.get('schedule') or []]
    lines += ['이슈: ' + x['issue'] for x in a.get('risks') or []]
    lines += ['미결: ' + item_text(x) for x in a.get('issues') or []]
    return '\n'.join(lines)[:3500]


def compare_with_previous(prev: Dict, prev_meta: Dict, cur: Dict) -> Dict:
    """이전 회의 대비 변경사항 — 지난 조치·요청의 진행 상태와 바뀐 결정·일정·담당."""
    res = _ollama_json(COMPARE_PROMPT.format(
        prev_title=prev.get('title') or prev_meta.get('title', ''), prev_date=prev_meta.get('recorded_at') or '일시 미상',
        prev=_digest(prev), cur=_digest(cur)), COMPARE_SCHEMA)
    statuses = ('완료', '진행 중', '지연', '변경', '언급 없음')
    followups = _dedupe_objects(res.get('followups') or [], 'item', 20, defaults={'status': '언급 없음', 'note': ''})
    for f in followups:
        if f['status'] not in statuses:
            f['status'] = '언급 없음'
    changes = _dedupe_objects(res.get('changes') or [], 'after', 15, defaults={'category': '결정', 'before': '없음'})
    return {'followups': followups, 'changes': changes}


def _speaker_no(label: str) -> int:
    m = re.search(r'(\d+)$', label or '')
    return int(m.group(1)) if m else 0


def _compact_for_merge(chunk_results: List[Dict]) -> str:
    """구간 결과를 통합 단계 입력 한도 안으로 줄인다 — 넘치면 주제별 세부 내용부터 덜어낸다."""
    for max_points in (4, 2, 0):
        parts = []
        for i, r in enumerate(chunk_results, 1):
            lines = ['## 구간 {} ({}~{})'.format(i, fmt_ts(r['_start']), fmt_ts(r['_end']))]
            for t in r.get('topics') or []:
                lines.append('- 주제: {} | 결론: {}'.format(t.get('title', ''), t.get('conclusion', '')))
                for p in (t.get('points') or [])[:max_points]:
                    lines.append('  - ' + p)
            for key, label in (('decisions', '결정'), ('issues', '미결'), ('keywords', '키워드')):
                if r.get(key):
                    lines.append('- {}: {}'.format(label, ' / '.join(item_text(x) for x in r[key])))
            for a in r.get('action_items') or []:
                lines.append('- 조치: {} (담당 {}, 기한 {})'.format(a.get('task'), a.get('owner'), a.get('due')))
            for a in r.get('requests') or []:
                lines.append('- 요청: {} ({} → {})'.format(a.get('content'), a.get('requester'), a.get('recipient')))
            for a in r.get('risks') or []:
                lines.append('- 이슈: ' + ' / '.join(x for x in (a.get('issue'), a.get('risk'), a.get('response')) if x))
            for a in r.get('schedule') or []:
                lines.append('- 일정: {} {}'.format(a.get('item'), a.get('date')))
            parts.append('\n'.join(lines))
        text = '\n\n'.join(parts)
        if len(text) <= MERGE_INPUT_CHARS:
            return text
    return text[:MERGE_INPUT_CHARS]


# ─────────────────────────── 마크다운 ───────────────────────────

def speaker_stats(utterances: List[Dict]) -> List[Dict]:
    stats = {}
    for u in utterances:
        st = stats.setdefault(u['speaker'], {'speaker': u['speaker'], 'seconds': 0.0, 'count': 0, 'chars': 0})
        st['seconds'] += u['end'] - u['start']
        st['count'] += 1
        st['chars'] += len(u['text'])
    return sorted(stats.values(), key=lambda s: _speaker_no(s['speaker']))


def clean_role(role: str) -> str:
    """'불명' → '', '불명 (법무 관련 직원 추정)' → '법무 관련 직원' (화면 JS cleanRole 과 같은 규칙)."""
    role = (role or '').strip()
    m = re.match(r'^불명\s*[(（](.*)[)）]$', role)
    if m:
        role = re.sub(r'\s*추정$', '', m.group(1)).strip()
    return '' if role in ('', '불명', '-') else role


def _roles(a: Dict) -> Dict[str, str]:
    return {p['speaker']: clean_role(p.get('role')) for p in a.get('participants') or [] if clean_role(p.get('role'))}


def _owner_cell(owner: str, roles: Dict[str, str]) -> str:
    """표의 담당 칸 — '화자 2<br>디자인 리더' 두 줄로 (내용 칸이 폭을 더 가져가게)."""
    m = re.match(r'^화자\s?(\d+)', owner or '')
    if m and roles.get('화자 ' + m.group(1)):
        # 좁은 칸이라 역할은 첫 마디만 ('개발 파트 리더, 기술 전환 및 인프라 구축' → '개발 파트 리더')
        return '화자 {}<br>{}'.format(m.group(1), re.split(r'[,，/]', roles['화자 ' + m.group(1)])[0].strip())
    return owner or '미정'


def _due_cell(due: str) -> str:
    """기한 칸 — '차주 화요일' → '차주<br>화요일'."""
    parts = (due or '미정').split(None, 1)
    return '<br>'.join(parts)


def _md_cell(text: str) -> str:
    return (text or '').replace('|', '／').replace('\n', ' ')


def _speaker_cell(who: str, roles: Dict[str, str]) -> str:
    """표의 사람 칸(담당·요청자·수신자) — 화자면 '화자 2<br>디자인 리더' 두 줄."""
    return _owner_cell(who, roles) if re.match(r'^화자\s?\d', who or '') else _md_cell(who or '미정')


def build_minutes(meta: Dict, a: Dict) -> str:
    """구조화 분석에서 결재·공유용 회의록(통화 기록)을 만든다.

    머리 표 + 7개 항목: 논의 · 결정 · 요청 · 조치 · 이슈 및 리스크 · 미결 · 일정 (2026-10-12 사용자 제안 구성)
    """
    kind = '통화 기록' if a.get('type') == '통화' else '회의록'
    roles = _roles(a)
    lines = ['# {}'.format(kind), '']
    lines += ['| 항목 | 내용 |', '|---|---|']
    lines.append('| 제목 | {} |'.format(_md_cell(a.get('title') or meta['title'])))
    lines.append('| 일시 | {} |'.format(meta.get('recorded_at') or '녹음 파일 기준 (일시 미상)'))
    lines.append('| 소요 시간 | {} |'.format(fmt_dur(meta['duration'])))
    if a.get('participants'):
        lines.append('| 참석자 | {} |'.format(', '.join(
            p['speaker'] + ('({})'.format(clean_role(p.get('role'))) if clean_role(p.get('role')) else '') for p in a['participants'])))
    if a.get('purpose'):
        lines.append('| 목적 | {} |'.format(_md_cell(a['purpose'])))
    lines.append('| 작성 | 녹음 자동 분석 ({}) — 검토 필요 |'.format(meta['analyzed_at']))
    lines.append('')

    by_topic = _items_by_topic(a)
    lines += ['## 1. 논의사항', '']
    for i, t in enumerate(a.get('topics') or [], 1):
        lines += ['### 1.{} {} ({}~{})'.format(i, t['title'], fmt_ts(t['start']), fmt_ts(t['end'])), '']
        # 검토 결과를 헤드라인으로 맨 위에, 그 아래 근거가 되는 논의·결정·조치… 를 정리한다 (2026-10-17 피드백)
        if t.get('conclusion'):
            lines += ['> **검토 결과:** ' + t['conclusion'], '']
        if t['points']:
            lines.append('- **논의 내용**')
            lines += ['  - ' + p for p in t['points']]
        lines += ['- **{}** {}'.format(label, text) for label, text in by_topic.get(i - 1, [])]
        lines.append('')
    if not a.get('topics'):
        lines += ['- 없음', '']

    lines += ['## 2. 결정사항', '']
    lines += ['{}. {}{}'.format(i, item_text(d), ts_tag(d)) for i, d in enumerate(a.get('decisions') or [], 1)] or ['- 없음']
    lines.append('')

    lines += ['## 3. 요청사항', '']
    if a.get('requests'):
        lines += ['| No | 요청 내용 | 요청자 | 수신자 | 시각 |', '|---|---|---|---|---|']
        lines += ['| {} | {} | {} | {} | {} |'.format(i, _md_cell(x['content']), _speaker_cell(x['requester'], roles),
                                                     _speaker_cell(x['recipient'], roles), ts_tag(x).strip())
                  for i, x in enumerate(a['requests'], 1)]
    else:
        lines.append('- 없음')
    lines.append('')

    lines += ['## 4. 조치사항', '']
    if a.get('action_items'):
        lines += ['| No | 수행 작업 | 담당 | 기한 | 시각 |', '|---|---|---|---|---|']
        lines += ['| {} | {} | {} | {} | {} |'.format(i, _md_cell(x['task']), _speaker_cell(x['owner'], roles),
                                                     _date_cell(x['due'], x.get('due_resolved')), ts_tag(x).strip())
                  for i, x in enumerate(a['action_items'], 1)]
    else:
        lines.append('- 없음')
    lines.append('')

    lines += ['## 5. 이슈 및 리스크', '']
    if a.get('risks'):
        for i, x in enumerate(a['risks'], 1):
            lines.append('{}. **{}**{}'.format(i, x['issue'], ts_tag(x)))
            if not _is_unset(x.get('risk')):
                lines.append('   - 영향: ' + x['risk'])
            if not _is_unset(x.get('response')):
                lines.append('   - 대응: ' + x['response'])
    else:
        lines.append('- 없음')
    lines.append('')

    lines += ['## 6. 미결사항', '']
    lines += ['- {}{}'.format(item_text(x), ts_tag(x)) for x in a.get('issues') or []] or ['- 없음']
    lines.append('')

    lines += ['## 7. 일정사항', '']
    if a.get('schedule'):
        lines += ['| 구분 | 일정 | 날짜 | 시각 |', '|---|---|---|---|']
        lines += ['| {} | {} | {} | {} |'.format(x['kind'], _md_cell(x['item']), _date_cell(x['date'], x.get('resolved')),
                                                ts_tag(x).strip())
                  for x in a['schedule']]
    else:
        lines.append('- 없음')
    lines.append('')
    return '\n'.join(lines)


def ts_tag(x) -> str:
    """근거 시각 — 마크다운에는 `@12:34` 로 넣고, 화면(audio_analysis.js)이 이걸 대화록 이동 버튼으로 바꾼다."""
    return ' `@{}`'.format(fmt_ts(x['ts'])) if isinstance(x, dict) and x.get('ts') is not None else ''


def _date_cell(date: str, resolved: Optional[str]) -> str:
    """'차주 화요일' + '10/20(화)' → '차주<br>화요일<br>(10/20(화))'."""
    return _due_cell(date) + ('<br>({})'.format(resolved) if resolved else '')


def _with_date(date: str, resolved: Optional[str]) -> str:
    return date + (' ({})'.format(resolved) if resolved else '')


def _items_by_topic(a: Dict) -> Dict[int, List[Tuple[str, str]]]:
    """주제 번호 → [(구분, 내용)] — 회의록 논의사항에서 각 주제의 검토 결과 아래에 붙인다.
    topic 칸은 근거 시각으로 붙인 것이라 예전 결과(근거 없음)에는 없다 → 빈 dict."""
    out = {}  # type: Dict[int, List[Tuple[str, str]]]

    def add(x, label, text):
        if isinstance(x, dict) and isinstance(x.get('topic'), int) and x['topic'] >= 0:
            out.setdefault(x['topic'], []).append((x.get('ts') or 0, label, text + ts_tag(x)))

    for x in a.get('decisions') or []:
        add(x, '결정', item_text(x))
    for x in a.get('action_items') or []:
        due = '' if _is_unset(x.get('due')) else ' · 기한 ' + _with_date(x['due'], x.get('due_resolved'))
        add(x, '조치', '{} — {}{}'.format(x['task'], x['owner'], due))
    for x in a.get('requests') or []:
        add(x, '요청', '{} ({} → {})'.format(x['content'], x['requester'], x['recipient']))
    for x in a.get('schedule') or []:
        add(x, '일정', '{}: {} [{}]'.format(x['item'], _with_date(x['date'], x.get('resolved')), x['kind']))
    for x in a.get('risks') or []:
        extra = ' / '.join(p + x[k] for k, p in (('risk', '영향: '), ('response', '대응: ')) if not _is_unset(x.get(k)))
        add(x, '이슈', x['issue'] + (' — ' + extra if extra else ''))
    for x in a.get('issues') or []:
        add(x, '미결', item_text(x))
    return {k: [(label, text) for _, label, text in sorted(v, key=lambda r: r[0])] for k, v in out.items()}


def build_summary(meta: Dict, a: Dict, compare: Optional[Dict]) -> List[str]:
    """요약 6개 항목: 회의 개요 · AI 핵심 요약 · 결정사항 · 조치사항 · 이슈 및 미결사항 · 이전 회의 대비 변경사항."""
    roles = _roles(a)
    lines = ['## 회의 개요', '']
    if meta.get('recorded_at'):
        lines.append('- 일시: ' + meta['recorded_at'])
    lines.append('- 길이: ' + fmt_dur(meta['duration']))
    if a.get('participants'):
        lines.append('- 참석: ' + ', '.join(
            p['speaker'] + ('({})'.format(clean_role(p.get('role'))) if clean_role(p.get('role')) else '') for p in a['participants']))
    if a.get('purpose'):
        lines.append('- 목적: ' + a['purpose'])
    if a.get('overview'):
        lines.append('- 안건: ' + a['overview'])
    lines.append('')

    lines += ['## AI 핵심 요약', '', a.get('summary_text') or '-', '']

    lines += ['## 결정사항', ''] + (['- {}{}'.format(item_text(d), ts_tag(d)) for d in a.get('decisions') or []]
                                  or ['- 없음']) + ['']

    lines += ['## 조치사항', '']
    if a.get('action_items'):
        lines += ['| 담당 | 수행 작업 | 기한 |', '|---|---|---|']
        lines += ['| {} | {}{} | {} |'.format(_speaker_cell(x['owner'], roles), _md_cell(x['task']), ts_tag(x),
                                             _date_cell(x['due'], x.get('due_resolved')))
                  for x in a['action_items']]
    else:
        lines.append('- 없음')
    lines.append('')

    lines += ['## 이슈 및 미결사항', '']
    lines += ['- ⚠️ {}{}{}'.format(x['issue'], '' if _is_unset(x.get('response')) else ' — 대응: ' + x['response'], ts_tag(x))
              for x in a.get('risks') or []]
    lines += ['- ❓ {}{}'.format(item_text(x), ts_tag(x)) for x in a.get('issues') or []]
    if not a.get('risks') and not a.get('issues'):
        lines.append('- 없음')
    lines.append('')

    lines += ['## 이전 회의 대비 변경사항', '']
    if not compare:
        lines += ['- 이전 회의를 지정하지 않았습니다 (결과 화면에서 이전 회의를 고르면 비교합니다)', '']
    else:
        prev = compare.get('previous') or {}
        lines.append('비교 대상: {} ({})'.format(prev.get('title', ''), prev.get('recorded_at') or prev.get('created_at', '')))
        lines.append('')
        if compare.get('followups'):
            lines += ['| 이전 조치 | 상태 | 근거 |', '|---|---|---|']
            lines += ['| {} | {} | {} |'.format(_md_cell(f['item']), f['status'], _md_cell(f['note'])) for f in compare['followups']]
            lines.append('')
        lines += ['- [{}] {} → {}'.format(c['category'], c['before'], c['after']) for c in compare.get('changes') or []]
        if not compare.get('followups') and not compare.get('changes'):
            lines.append('- 변경사항 없음')
        lines.append('')
    return lines


def build_markdown(meta: Dict, a: Optional[Dict], utterances: List[Dict], diarized: bool,
                   diar_skip: str, summary_skip: str, compare: Optional[Dict] = None) -> str:
    stats = speaker_stats(utterances)
    total_speech = sum(s['seconds'] for s in stats) or 1.0
    title = (a or {}).get('title') or meta['title']

    lines = ['# {}'.format(title), '']
    lines += ['| 항목 | 값 |', '|---|---|']
    lines.append('| 원본 파일 | {} |'.format(meta['title']))
    lines.append('| 화자 수 | {} |'.format('{}명'.format(len(stats)) if diarized else '구분 안 함'))
    lines.append('| 분석 | {} · 받아쓰기 {}{}{} · {} 소요 |'.format(
        meta['analyzed_at'], meta['whisper_model'], ' · 화자분리 pyannote' if diarized else '',
        ' · 요약 {}'.format(a['model']) if a else '', fmt_dur(meta['elapsed'])))
    lines.append('')

    if not diarized:
        lines += ['> ⚠️ 화자분리를 하지 못했습니다 ({}). 화자 구분이 없습니다.'.format(
            diar_skip.splitlines()[0] if diar_skip else '원인 불명'), '']
    if not a:
        lines += ['> ⚠️ 요약을 생성하지 못했습니다: {}'.format(summary_skip), '']
    else:
        lines += build_summary(meta, a, compare)
        if a.get('keywords'):
            lines += ['## 키워드', '', ' · '.join('`{}` ({})'.format(k['word'], k['count']) for k in a['keywords']), '']

    if diarized:
        lines += ['## 화자별 발화', '', '| 화자 | 역할(추정) | 발화 시간 | 비율 | 발화 수 |', '|---|---|---|---|---|']
        roles = _roles(a or {})
        for s in stats:
            lines.append('| {} | {} | {} | {:.0%} | {} |'.format(
                s['speaker'], roles.get(s['speaker'], '-'), fmt_dur(s['seconds']), s['seconds'] / total_speech, s['count']))
        lines.append('')

    if a:
        # 회의록을 본문 섹션으로 넣을 때 제목 수준을 한 단계씩 내린다 (# 회의록 → ## 회의록, ## 1. → ### 1.)
        lines += ['---', '', re.sub(r'^(#+) ', r'#\1 ', build_minutes(meta, a), flags=re.M), '---', '']

    lines += ['## 전체 대화록', '']
    for u in utterances:
        # 문장마다 줄을 바꾼다 (마크다운 줄바꿈 = 줄 끝 공백 두 칸)
        lines += ['**{}** `{}`  '.format(u['speaker'], fmt_ts(u['start'])),
                  '  \n'.join(split_sentences(u['text'])), '']
    return '\n'.join(lines)
