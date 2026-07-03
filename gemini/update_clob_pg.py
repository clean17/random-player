"""PostgreSQL 의 CLOB(text) 컬럼에서 /common <img> 의 alt 를 채워 UPDATE 하는 배치.

- HTML 처리: clob_img_regex.fill_alts (원본 보존 정규식 버전)
- 재시도 / throttle: img_alt._request_with_retry / _throttle 에서 처리
- 실패 로깅: logs/alt_failures.jsonl 에 한 줄씩(JSONL) 기록 -> 나중에 재처리 가능
- 진행상황: logs/alt_progress.log 에 처리 완료 row_id 기록 (재실행 시 skip => 이어하기)

DB 접속정보는 .env 의 PG_DSN 에서 읽는다:
    PG_DSN=host=127.0.0.1 port=5432 dbname=mydb user=postgres password=secret

아래 TABLE / ID_COL / CLOB_COL 을 실제 스키마에 맞게 수정할 것. (psycopg 3 기준)
"""
import json
import os
import time
from datetime import datetime

import psycopg
from dotenv import load_dotenv

from clob_img_regex import fill_alts

load_dotenv()

DSN = os.environ.get("PG_DSN")

# ↓↓↓ 실제 스키마에 맞게 수정 ↓↓↓
TABLE = "board"
ID_COL = "id"
CLOB_COL = "content"
# ↑↑↑ 실제 스키마에 맞게 수정 ↑↑↑

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
FAIL_LOG = os.path.join(LOG_DIR, "alt_failures.jsonl")
DONE_LOG = os.path.join(LOG_DIR, "alt_done.log")


def _ensure_log_dir():
    if not os.path.isdir(LOG_DIR):
        os.makedirs(LOG_DIR)


def _log_failure(row_id, src, url, exc):
    """실패 이미지를 JSONL 로 기록한다 (나중에 재처리용)."""
    _ensure_log_dir()
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "row_id": row_id,
        "src": src,
        "url": url,
        "error": "{}: {}".format(type(exc).__name__, exc),
    }
    with open(FAIL_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print("  [FAIL] id={} src={} : {}".format(row_id, src, record["error"]))


def _mark_done(row_id):
    _ensure_log_dir()
    with open(DONE_LOG, "a", encoding="utf-8") as f:
        f.write("{}\n".format(row_id))


def _load_done():
    """이미 처리 완료한 row_id 집합 (재실행 시 skip 해서 이어하기)."""
    if not os.path.isfile(DONE_LOG):
        return set()
    with open(DONE_LOG, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def process_all(overwrite=False, dry_run=False, resume=True):
    """/common <img> 를 포함한 모든 행을 처리한다.

    dry_run=True : UPDATE 하지 않고 변경 대상만 출력.
    resume=True  : alt_done.log 에 기록된 row 는 건너뛰어 이어서 처리.
    """
    if not DSN:
        raise SystemExit("PG_DSN 환경변수(.env)가 설정되지 않았습니다.")

    done = _load_done() if resume else set()

    with psycopg.connect(DSN) as conn:
        select_sql = 'SELECT "{id}", "{clob}" FROM "{tbl}" WHERE "{clob}" LIKE %s ORDER BY "{id}"'.format(
            id=ID_COL, clob=CLOB_COL, tbl=TABLE
        )
        with conn.cursor() as cur:
            cur.execute(select_sql, ["%/common%"])
            rows = cur.fetchall()

        total = len(rows)
        print("대상 행: {}개 (이미 완료 {}개 skip)".format(total, len(done)))
        update_sql = 'UPDATE "{tbl}" SET "{clob}" = %s WHERE "{id}" = %s'.format(
            tbl=TABLE, clob=CLOB_COL, id=ID_COL
        )

        started = time.time()
        for idx, (row_id, clob) in enumerate(rows, 1):
            if resume and str(row_id) in done:
                continue
            if not clob:
                continue

            print("[{}/{}] id={} 처리 중...".format(idx, total, row_id))
            new_html = fill_alts(
                clob,
                overwrite=overwrite,
                on_fail=lambda src, url, exc, rid=row_id: _log_failure(rid, src, url, exc),
            )

            if new_html == clob:
                print("  id={} : 변경 없음".format(row_id))
                if not dry_run:
                    _mark_done(row_id)
                continue
            if dry_run:
                print("  id={} : [dry-run] 변경됨 (미저장)".format(row_id))
                continue

            with conn.cursor() as cur:
                cur.execute(update_sql, [new_html, row_id])
            conn.commit()
            _mark_done(row_id)
            print("  id={} : UPDATE 완료".format(row_id))

        elapsed = time.time() - started
        print("완료. 경과 {:.1f}초".format(elapsed))


def process_one(row_id, overwrite=False, dry_run=False):
    """특정 행 하나만 처리한다 (테스트용)."""
    if not DSN:
        raise SystemExit("PG_DSN 환경변수(.env)가 설정되지 않았습니다.")

    with psycopg.connect(DSN) as conn:
        select_sql = 'SELECT "{clob}" FROM "{tbl}" WHERE "{id}" = %s'.format(
            clob=CLOB_COL, tbl=TABLE, id=ID_COL
        )
        with conn.cursor() as cur:
            cur.execute(select_sql, [row_id])
            got = cur.fetchone()
        if not got or not got[0]:
            print("id={} : 내용 없음".format(row_id))
            return

        new_html = fill_alts(
            got[0],
            overwrite=overwrite,
            on_fail=lambda src, url, exc: _log_failure(row_id, src, url, exc),
        )
        if new_html == got[0]:
            print("id={} : 변경 없음".format(row_id))
            return
        if dry_run:
            print("id={} : [dry-run] 변경됨\n{}".format(row_id, new_html))
            return

        update_sql = 'UPDATE "{tbl}" SET "{clob}" = %s WHERE "{id}" = %s'.format(
            tbl=TABLE, clob=CLOB_COL, id=ID_COL
        )
        with conn.cursor() as cur:
            cur.execute(update_sql, [new_html, row_id])
        conn.commit()
        print("id={} : UPDATE 완료".format(row_id))


if __name__ == "__main__":
    # 실제 실행 전 dry_run 으로 대상/결과를 먼저 확인할 것.
    process_all(dry_run=True)
