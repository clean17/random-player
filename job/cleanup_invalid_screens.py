"""IG 스크랩 진단 스크린샷(logs/i/<YYMM>/invalid/*.png) 중 생성 후 30일 지난 것을 지운다 (2026-10-16).

job/scrap/scrap_gm_playwrigit.py 의 diagnose_invalid_account() 가 계정 확인에 실패할 때마다
스크린샷을 남겨 계속 쌓인다. 기준은 파일 생성 시각(Windows 에서 os.path.getctime = 생성 시각).
월 폴더(<YYMM>)·invalid 폴더 자체는 지우지 않는다(스크랩 스크립트가 다시 만든다).
"""
import glob
import os
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INVALID_SCREEN_GLOB = os.path.join(PROJECT_ROOT, "logs", "i", "*", "invalid", "*")
RETENTION_DAYS = 30


def cleanup_invalid_screens(retention_days=RETENTION_DAYS):
    cutoff = time.time() - retention_days * 86400
    deleted = 0
    failed = 0
    for path in glob.glob(INVALID_SCREEN_GLOB):
        if not os.path.isfile(path):
            continue
        try:
            if os.path.getctime(path) < cutoff:
                os.remove(path)
                deleted += 1
        except OSError as e:
            failed += 1
            print(f"invalid 스크린샷 삭제 실패: {path}: {e}")
    print(f"    ############################### cleanup_invalid_screens : "
          f"{retention_days}일 지난 {deleted}개 삭제, 실패 {failed}개 ###############################")
    return deleted


if __name__ == "__main__":
    cleanup_invalid_screens()
