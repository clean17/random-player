import os
import sys
import re
import gc
import json
import time
import hashlib
import urllib.request
import urllib.error
from copy import copy
from pathlib import Path
from datetime import datetime, timedelta
from difflib import SequenceMatcher

# =========================================================
# Windows CUDA DLL 경로
# =========================================================
DLL_HANDLES = []
SITE_PACKAGES = Path(sys.prefix) / "Lib" / "site-packages"

for dll_dir in [
    SITE_PACKAGES / "nvidia" / "cublas" / "bin",
    SITE_PACKAGES / "nvidia" / "cudnn" / "bin",
]:
    if dll_dir.exists() and hasattr(os, "add_dll_directory"):
        DLL_HANDLES.append(os.add_dll_directory(str(dll_dir)))
        os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ.get("PATH", "")

from faster_whisper import WhisperModel
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment


# =========================================================
# 설정
# =========================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CALL_DIR = Path(r"E:\통화녹음")

# v3 파일을 프로젝트 루트에 두는 것을 기본으로 함.
# 다른 위치라면 아래 경로만 수정하면 됨.
BASE_V3_FILE = PROJECT_ROOT / "inwoo.park_2026_main_커밋정리_v3.xlsx"
OUTPUT_FILE = CALL_DIR / "inwoo.park_2026_main_통화병합.xlsx"

CACHE_DIR = CALL_DIR / "_분석캐시"
TRANSCRIPT_DIR = CACHE_DIR / "녹취록"
# 기존 1.5B 분석결과와 섞이지 않도록 별도 캐시 사용
ANALYSIS_DIR = CACHE_DIR / "v3병합분석_v1"

AUDIO_EXTENSIONS = {
    ".m4a", ".mp3", ".wav", ".aac",
    ".flac", ".ogg", ".mp4", ".3gp"
}

# STT
WHISPER_MODEL = "small"
WHISPER_DEVICE = "cuda"
WHISPER_COMPUTE_TYPE = "float16"

# AI
# 1.5B보다 3B를 권장. 품질을 더 우선하면 qwen3:4b로 바꿔도 됨.
OLLAMA_MODEL = "qwen2.5:3b"
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_NUM_CTX = 8192
OLLAMA_TIMEOUT = 300

# 긴 녹취는 나눠 분석
MAX_CHUNK_CHARS = 6500
CHUNK_OVERLAP_LINES = 4

# 자동 병합 기준: 같은 이슈라고 AI가 매우 확신할 때만 기존 v3 행에 합침.
AUTO_MATCH_THRESHOLD = 85
# 신규 행 자동 추가 최소 신뢰도
AUTO_NEW_THRESHOLD = 75

# 기존 v3 후보를 AI에게 보여줄 개수
MAX_CANDIDATES = 8

ASSIGNEE = "박인우"

TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# 공통 유틸
# =========================================================
def format_duration(seconds):
    if seconds < 60:
        return f"{seconds:.2f}초"
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h:
        return f"{h}시간 {m}분 {s}초"
    return f"{m}분 {s}초"


def parse_filename(path: Path):
    stem = path.stem
    pattern = r"^(?:통화(?:\s*녹음)?\s*)?(.*?)_(\d{6}|\d{8})_(\d{6})$"
    match = re.match(pattern, stem)

    if match:
        person = match.group(1).strip()
        date_string = match.group(2)
        time_string = match.group(3)
        date_obj = datetime.strptime(
            date_string,
            "%y%m%d" if len(date_string) == 6 else "%Y%m%d"
        )
        time_obj = datetime.strptime(time_string, "%H%M%S")
        return {
            "person": person,
            "date": date_obj.strftime("%Y-%m-%d"),
            "time": time_obj.strftime("%H:%M:%S"),
        }

    modified = datetime.fromtimestamp(path.stat().st_mtime)
    return {
        "person": stem,
        "date": modified.strftime("%Y-%m-%d"),
        "time": modified.strftime("%H:%M:%S"),
    }


def get_cache_key(path: Path):
    value = str(path.resolve()).encode("utf-8")
    return hashlib.sha1(value).hexdigest()


def normalize_person(value):
    if not value:
        return ""
    value = str(value)
    for word in [
        "디앤디기술", "디앤디", "디엔디", "법무부기록관", "법무부 기록관",
        "차장님", "선임님", "대리님", "차장", "선임", "대리", "님"
    ]:
        value = value.replace(word, " ")
    return re.sub(r"\s+", "", value)


def clean_text(value):
    if not value:
        return ""
    value = str(value).lower()
    value = re.sub(r"\[[^\]]*\]", " ", value)
    value = re.sub(r"[^0-9a-z가-힣]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def char_bigrams(text):
    text = re.sub(r"\s+", "", clean_text(text))
    if len(text) < 2:
        return {text} if text else set()
    return {text[i:i + 2] for i in range(len(text) - 1)}


def text_similarity(a, b):
    """STT 오탈자에 조금 강하도록 문자 유사도 + 2글자 조각 겹침을 혼합."""
    a = clean_text(a)
    b = clean_text(b)
    if not a or not b:
        return 0.0

    seq = SequenceMatcher(None, a[:4000], b[:4000]).ratio()
    ag = char_bigrams(a)
    bg = char_bigrams(b)
    if not ag or not bg:
        contain = 0.0
    else:
        contain = len(ag & bg) / max(1, min(len(ag), len(bg)))

    return (seq * 0.35 + contain * 0.65) * 100


def parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    text = str(value).replace(".", "-")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def safe_json_loads(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 모델이 ```json ... ``` 형태로 감쌌을 때 대비
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)


# =========================================================
# STT
# =========================================================
def transcript_cache_file(path):
    return TRANSCRIPT_DIR / f"{get_cache_key(path)}.txt"


def transcribe_audio(path: Path, model: WhisperModel):
    cache_file = transcript_cache_file(path)
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8"), True

    segments, _ = model.transcribe(
        str(path),
        language="ko",
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    lines = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            lines.append(text)

    transcript = "\n".join(lines)
    cache_file.write_text(transcript, encoding="utf-8")
    return transcript, False


def split_transcript(text):
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]

    lines = text.splitlines()
    chunks = []
    current = []
    current_len = 0

    for line in lines:
        if current and current_len + len(line) + 1 > MAX_CHUNK_CHARS:
            chunks.append("\n".join(current))
            current = current[-CHUNK_OVERLAP_LINES:]
            current_len = sum(len(x) + 1 for x in current)
        current.append(line)
        current_len += len(line) + 1

    if current:
        chunks.append("\n".join(current))
    return chunks


# =========================================================
# v3 읽기 / 후보선정
# =========================================================
def read_v3_records(ws):
    records = []
    for row in range(5, ws.max_row + 1):
        seq = ws.cell(row, 2).value
        if seq is None:
            continue

        records.append({
            "row": row,
            "num": int(seq),
            "request_date": ws.cell(row, 3).value,
            "request_type": ws.cell(row, 4).value,
            "request_item": ws.cell(row, 5).value,
            "request_detail": ws.cell(row, 6).value,
            "organization": ws.cell(row, 7).value,
            "requester": ws.cell(row, 8).value,
            "assignee": ws.cell(row, 9).value,
            "action": ws.cell(row, 10).value,
            "result_assignee": ws.cell(row, 11).value,
            "result": ws.cell(row, 12).value,
            "process_date": ws.cell(row, 13).value,
            "note": ws.cell(row, 14).value,
        })
    return records


def candidate_score(transcript, metadata, record):
    record_text = " ".join(str(x or "") for x in [
        record["request_item"],
        record["request_detail"],
        record["action"],
    ])

    # 긴 녹취 전체보다는 앞/뒤를 같이 사용
    compact_transcript = transcript[:5000]
    score = text_similarity(compact_transcript, record_text)

    call_date = parse_date(metadata["date"])
    req_date = parse_date(record["request_date"])
    if call_date and req_date:
        diff = abs((call_date - req_date).days)
        if diff == 0:
            score += 20
        elif diff <= 3:
            score += 15
        elif diff <= 7:
            score += 10
        elif diff <= 14:
            score += 6
        elif diff <= 30:
            score += 3

    call_person = normalize_person(metadata["person"])
    req_person = normalize_person(record["requester"])
    if call_person and req_person and (call_person in req_person or req_person in call_person):
        score += 15

    return score


def select_candidates(transcript, metadata, records):
    scored = [
        (candidate_score(transcript, metadata, record), record)
        for record in records
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [record for _, record in scored[:MAX_CANDIDATES]]


def candidates_to_prompt(candidates):
    blocks = []
    for r in candidates:
        blocks.append(
            f"[# {r['num']}]\n"
            f"요청일자: {r['request_date']}\n"
            f"요청구분: {r['request_type']}\n"
            f"요청사항: {r['request_item']}\n"
            f"요청상세: {r['request_detail']}\n"
            f"요청자: {r['requester'] or ''}\n"
            f"조치내용: {r['action'] or ''}"
        )
    return "\n\n".join(blocks)


# =========================================================
# Ollama
# =========================================================
def check_ollama():
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def call_ollama(prompt):
    body = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": """
당신은 LARIS 시스템 유지보수 요청사항 대장을 정리하는 담당자다.
목표는 통화 한 건을 '커밋 정리 v3'와 같은 이슈 단위로 정리하고,
이미 v3에 같은 이슈가 있으면 그 번호와 연결하고, 정말 새로운 이슈만 신규로 만드는 것이다.

매우 중요한 규칙:
1. 녹취에 없는 원인, 해결방법, 조치내용을 절대 만들어내지 않는다.
2. 녹취가 불명확하면 빈 문자열 또는 '확인 필요'로 둔다.
3. '안녕하세요', 자리/방문 위치, 전화 연결, 단순 인사·잡담·약속 시간만 있는 내용은 기록하지 않는다.
4. 실제 시스템 문의, 오류, 기능 변경, 사용 문의, 배포/운영 문의는 기록한다.
5. 같은 통화에서 같은 이슈를 표현만 바꿔 반복하면 하나로 합친다.
6. 기존 후보와 병합할 때는 화면/기능과 문제의 핵심이 모두 같아야 한다.
   날짜가 가깝거나 RFID/엑셀 같은 단어 하나가 같다는 이유만으로 병합하면 안 된다.
7. 기존과 같은 이슈인지 조금이라도 애매하면 match_no는 null로 둔다. 잘못 합치는 것보다 신규/검토가 낫다.
8. request_item은 v3처럼 짧고 구체적으로 쓴다. 메뉴 경로가 녹취에 명확하지 않으면 [메뉴]를 추측하지 않는다.
9. request_detail은 '무엇이 어떻게 안 됐는지/무엇을 원하는지'만 자연스럽게 정리한다.
10. action은 통화에서 실제로 답변·처리·약속한 것만 적는다. 없는 해결책을 지어내지 않는다.
11. result는 다음 중 하나다.
   - 완료: 통화에서 실제 수정/적용/해결/정상 확인이 명확함
   - 처리예정: 수정·확인·배포 등을 앞으로 하기로 함
   - 확인필요: 결론이 불명확함
12. request_type은 오류/버그/성능 문제 수정이면 '하자개선', 일반 운영지원/사용문의/단순 변경 요청이면 '유지보수'.
13. evidence에는 판단 근거가 된 녹취 표현을 짧게 적는다. 녹취에 없는 문장을 만들지 않는다.
14. confidence는 이슈 추출 자체의 신뢰도(0~100), match_confidence는 기존 번호가 같은 이슈라는 신뢰도(0~100)다.
15. 기존 후보에 같은 이슈가 없으면 match_no는 null이다.

반드시 다음 JSON 구조만 반환한다.
{
  "summary": "통화 핵심 1~2문장",
  "inquiries": [
    {
      "record": true,
      "match_no": 123,
      "match_confidence": 95,
      "confidence": 95,
      "request_type": "하자개선",
      "request_item": "프로젝트 검색 시 프로젝트명 부분 검색 요청",
      "request_detail": "프로젝트명 중간 단어로 검색하면 결과가 조회되지 않음.",
      "organization": "디엔디",
      "requester": "백현욱",
      "action": "부분 검색이 가능하도록 확인 후 수정하기로 함.",
      "result": "처리예정",
      "process_date": null,
      "evidence": "중간 단어로 검색이 안 돼요",
      "reason": "기존 #123과 같은 프로젝트 검색 문제"
    }
  ]
}

기록할 업무 문의가 없으면 inquiries는 빈 배열로 반환한다.
""",
            },
            {"role": "user", "content": prompt},
        ],
        "options": {
            "temperature": 0.0,
            "num_ctx": OLLAMA_NUM_CTX,
        },
    }

    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as response:
        result = json.loads(response.read().decode("utf-8"))

    return safe_json_loads(result["message"]["content"])


def analyze_call(path, metadata, transcript, records):
    cache_file = ANALYSIS_DIR / f"{get_cache_key(path)}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8")), True

    all_inquiries = []
    summaries = []
    chunks = split_transcript(transcript)

    for chunk_index, chunk in enumerate(chunks, start=1):
        candidates = select_candidates(chunk, metadata, records)
        candidate_text = candidates_to_prompt(candidates)

        prompt = f"""
[통화 정보]
일자: {metadata['date']}
시간: {metadata['time']}
상대방: {metadata['person']}
원본파일: {path.name}

[기존 v3 후보]
{candidate_text}

[통화 녹취 {chunk_index}/{len(chunks)}]
{chunk}
"""
        result = call_ollama(prompt)
        if result.get("summary"):
            summaries.append(result["summary"])
        all_inquiries.extend(result.get("inquiries", []))

    # 같은 통화 안에서 완전히 같은 제목/상세는 중복 제거
    unique = []
    seen = set()
    for item in all_inquiries:
        key = (
            clean_text(item.get("request_item", "")),
            clean_text(item.get("request_detail", "")),
            item.get("match_no"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    final = {
        "summary": " / ".join(dict.fromkeys(summaries)),
        "inquiries": unique,
    }
    cache_file.write_text(
        json.dumps(final, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return final, False


# =========================================================
# v3 병합
# =========================================================
def find_record(records, num):
    for record in records:
        if record["num"] == num:
            return record
    return None


def call_note(metadata, path):
    requester = normalize_person(metadata["person"]) or metadata["person"]
    return (
        f"통화근거 {metadata['date'].replace('-', '.')} "
        f"{metadata['time'][:5]} {requester} | {path.name}"
    )


def append_note(ws, record, note):
    cell = ws.cell(record["row"], 14)
    old = str(cell.value or "").strip()
    if note in old:
        return
    cell.value = f"{old}\n{note}" if old else note
    record["note"] = cell.value


def last_data_row(ws):
    last = 4
    for row in range(5, ws.max_row + 1):
        if ws.cell(row, 2).value is not None:
            last = row
    return last


def copy_row_style(ws, source_row, target_row):
    ws.row_dimensions[target_row].height = ws.row_dimensions[source_row].height
    for col in range(1, 15):
        src = ws.cell(source_row, col)
        dst = ws.cell(target_row, col)
        if src.has_style:
            dst._style = copy(src._style)
        if src.number_format:
            dst.number_format = src.number_format
        if src.alignment:
            dst.alignment = copy(src.alignment)
        if src.protection:
            dst.protection = copy(src.protection)


def write_new_record(ws, records, item, metadata, path):
    source_row = last_data_row(ws)
    target_row = source_row + 1
    next_num = max(r["num"] for r in records) + 1 if records else 1

    copy_row_style(ws, source_row, target_row)

    request_date = metadata["date"].replace("-", ".")
    process_date = item.get("process_date")
    process_dt = None
    if process_date:
        try:
            process_dt = datetime.strptime(str(process_date).replace(".", "-")[:10], "%Y-%m-%d")
        except ValueError:
            process_dt = None

    request_type = item.get("request_type")
    if request_type not in {"하자개선", "유지보수"}:
        request_type = "하자개선" if item.get("result") != "완료" else "유지보수"

    result = item.get("result")
    if result not in {"완료", "처리예정", "확인필요"}:
        result = "확인필요"

    note = call_note(metadata, path)

    values = {
        2: next_num,
        3: request_date,
        4: request_type,
        5: item.get("request_item") or "통화 문의",
        6: item.get("request_detail") or "확인 필요",
        7: item.get("organization") or None,
        8: item.get("requester") or normalize_person(metadata["person"]) or None,
        9: ASSIGNEE,
        10: item.get("action") or "확인 필요",
        11: ASSIGNEE,
        12: result,
        13: process_dt,
        14: note,
    }

    for col, value in values.items():
        ws.cell(target_row, col).value = value

    new_record = {
        "row": target_row,
        "num": next_num,
        "request_date": request_date,
        "request_type": request_type,
        "request_item": values[5],
        "request_detail": values[6],
        "organization": values[7],
        "requester": values[8],
        "assignee": ASSIGNEE,
        "action": values[10],
        "result_assignee": ASSIGNEE,
        "result": result,
        "process_date": process_dt,
        "note": note,
    }
    records.append(new_record)
    return new_record


def create_review_sheet(wb):
    if "통화 병합 검토" in wb.sheetnames:
        del wb["통화 병합 검토"]

    ws = wb.create_sheet("통화 병합 검토")
    headers = [
        "통화일자", "통화시간", "상대방", "원본파일",
        "판정", "매칭순번", "매칭확률", "추출신뢰도",
        "요청구분", "요청사항", "요청상세", "조치내용", "결과",
        "근거", "판정사유"
    ]
    ws.append(headers)

    fill = PatternFill("solid", fgColor="D9EAF7")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:O1"
    widths = [12, 10, 26, 45, 12, 10, 10, 10, 12, 45, 60, 60, 12, 50, 50]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + idx) if idx <= 26 else 'A'].width = width
    return ws


def add_review_row(ws, metadata, path, verdict, item, matched_num=None):
    ws.append([
        metadata["date"],
        metadata["time"],
        metadata["person"],
        path.name,
        verdict,
        matched_num,
        item.get("match_confidence"),
        item.get("confidence"),
        item.get("request_type"),
        item.get("request_item"),
        item.get("request_detail"),
        item.get("action"),
        item.get("result"),
        item.get("evidence"),
        item.get("reason"),
    ])
    row = ws.max_row
    for cell in ws[row]:
        cell.alignment = Alignment(vertical="top", wrap_text=True)


# =========================================================
# MAIN
# =========================================================
def main():
    started = time.perf_counter()
    print("=" * 70)
    print("통화녹음 → v3 요청사항 병합")
    print("=" * 70)
    print(f"통화 폴더 : {CALL_DIR}")
    print(f"기준 v3   : {BASE_V3_FILE}")
    print(f"결과 파일 : {OUTPUT_FILE}")
    print(f"AI 모델   : {OLLAMA_MODEL}")

    if not CALL_DIR.exists():
        print(f"통화 폴더가 없습니다: {CALL_DIR}")
        return
    if not BASE_V3_FILE.exists():
        print(f"v3 파일이 없습니다: {BASE_V3_FILE}")
        return
    if not check_ollama():
        print("Ollama에 연결할 수 없습니다.")
        print(f"먼저 실행/설치 확인 후: ollama pull {OLLAMA_MODEL}")
        return

    audio_files = sorted(
        p for p in CALL_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    )
    print(f"통화 파일 : {len(audio_files)}개")

    # -----------------------------------------------------
    # 1단계: STT만 먼저 끝냄
    # Whisper와 Ollama가 RTX 4050 6GB VRAM을 동시에 오래 점유하지 않게 하기 위함.
    # -----------------------------------------------------
    missing = [p for p in audio_files if not transcript_cache_file(p).exists()]
    if missing:
        print(f"\n[1/3] STT 필요 파일: {len(missing)}개")
        whisper = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )

        for i, path in enumerate(missing, start=1):
            t0 = time.perf_counter()
            try:
                transcript, _ = transcribe_audio(path, whisper)
                print(
                    f"  [{i}/{len(missing)}] {path.name} "
                    f"-> {format_duration(time.perf_counter() - t0)} "
                    f"({len(transcript):,}자)"
                )
            except Exception as e:
                print(f"  [{i}/{len(missing)}] STT 오류: {path.name} / {e}")

        del whisper
        gc.collect()
        print("Whisper 모델 해제 완료")
    else:
        print("\n[1/3] 모든 녹취 캐시가 있어 STT 생략")

    # -----------------------------------------------------
    # 2단계: v3 불러오기 + AI 분석/병합
    # -----------------------------------------------------
    print("\n[2/3] v3 대조 및 병합")
    wb = load_workbook(BASE_V3_FILE)
    ws = wb["요청사항 목록"]
    records = read_v3_records(ws)
    review_ws = create_review_sheet(wb)

    matched_count = 0
    new_count = 0
    hold_count = 0
    skipped_count = 0
    error_count = 0

    for idx, path in enumerate(audio_files, start=1):
        metadata = parse_filename(path)
        cache_file = transcript_cache_file(path)
        if not cache_file.exists():
            error_count += 1
            continue

        transcript = cache_file.read_text(encoding="utf-8").strip()
        if not transcript:
            continue

        t0 = time.perf_counter()
        try:
            analysis, cached = analyze_call(path, metadata, transcript, records)
            inquiries = analysis.get("inquiries", [])

            if not inquiries:
                skipped_count += 1
                print(f"  [{idx}/{len(audio_files)}] 제외: {path.name}")
                continue

            for item in inquiries:
                if item.get("record") is False:
                    skipped_count += 1
                    add_review_row(review_ws, metadata, path, "제외", item)
                    continue

                confidence = int(item.get("confidence") or 0)
                match_no = item.get("match_no")
                match_conf = int(item.get("match_confidence") or 0)

                if match_no is not None:
                    try:
                        match_no = int(match_no)
                    except (TypeError, ValueError):
                        match_no = None

                matched_record = find_record(records, match_no) if match_no else None

                # 기존 행 병합: 높은 확률일 때만
                if matched_record and match_conf >= AUTO_MATCH_THRESHOLD:
                    append_note(ws, matched_record, call_note(metadata, path))
                    matched_count += 1
                    add_review_row(
                        review_ws, metadata, path, "기존병합", item,
                        matched_num=matched_record["num"]
                    )

                # 모델이 기존 후보를 찍었지만 확률이 애매하면 자동으로 신규 생성하지 않고 검토
                elif matched_record:
                    hold_count += 1
                    add_review_row(
                        review_ws, metadata, path, "매칭검토", item,
                        matched_num=matched_record["num"]
                    )

                # 기존 번호 없음 + 이슈 추출 신뢰도 높음 => 신규 행
                elif confidence >= AUTO_NEW_THRESHOLD:
                    new_record = write_new_record(ws, records, item, metadata, path)
                    new_count += 1
                    add_review_row(
                        review_ws, metadata, path, "신규추가", item,
                        matched_num=new_record["num"]
                    )

                else:
                    hold_count += 1
                    add_review_row(review_ws, metadata, path, "추출검토", item)

            print(
                f"  [{idx}/{len(audio_files)}] {path.name} "
                f"({len(inquiries)}건, {'캐시' if cached else 'AI'}, "
                f"{format_duration(time.perf_counter() - t0)})"
            )

        except Exception as e:
            error_count += 1
            print(f"  [{idx}/{len(audio_files)}] 분석 오류: {path.name} / {e}")

    # -----------------------------------------------------
    # 3단계: 저장
    # -----------------------------------------------------
    print("\n[3/3] Excel 저장")
    wb.save(OUTPUT_FILE)

    print("=" * 70)
    print("완료")
    print(f"기존 v3에 병합 : {matched_count}건")
    print(f"신규 행 추가    : {new_count}건")
    print(f"검토 필요       : {hold_count}건")
    print(f"제외             : {skipped_count}건")
    print(f"오류             : {error_count}건")
    print(f"전체 소요        : {format_duration(time.perf_counter() - started)}")
    print(f"결과             : {OUTPUT_FILE}")
    print("※ '통화 병합 검토' 시트에서 자동 판정 근거를 확인할 수 있습니다.")
    print("=" * 70)


if __name__ == "__main__":
    main()
