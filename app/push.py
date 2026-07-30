import base64
import json
import os
from typing import Dict, List

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from filelock import FileLock, Timeout
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from py_vapid import Vapid02
from pywebpush import webpush, WebPushException

from utils.wsgi_midleware import logger

push_bp = Blueprint('push', __name__)

DATA_DIR = "data"
VAPID_PRIVATE_KEY_PATH = os.path.join(DATA_DIR, "vapid_private_key.pem")
SUBSCRIPTIONS_FILE_PATH = os.path.join(DATA_DIR, "push_subscriptions.json")
LOCK_PATH = SUBSCRIPTIONS_FILE_PATH + ".lock"
VAPID_CLAIMS_SUB = "mailto:admin@chickchick.kr"
PUSH_TTL_SECONDS = 60 * 60 * 24  # (1일) 기기가 오프라인이어도 푸시 서비스가 이 시간만큼 보관 후 재전달

os.makedirs(DATA_DIR, exist_ok=True)
# 파일이 없으면 자동 생성, 있으면 로드 (py_vapid.Vapid.from_file 동작)
_vapid = Vapid02.from_file(VAPID_PRIVATE_KEY_PATH)
VAPID_PUBLIC_KEY = base64.urlsafe_b64encode(
    _vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
).rstrip(b"=").decode("ascii")


def _load_subscriptions():
    # type: () -> Dict[str, List[dict]]
    lock = FileLock(LOCK_PATH, timeout=2)
    try:
        with lock:
            if not os.path.exists(SUBSCRIPTIONS_FILE_PATH):
                return {}
            with open(SUBSCRIPTIONS_FILE_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else {}
    except Timeout:
        logger.error("push_subscriptions.json 읽기 락 획득 실패")
        return {}
    except json.JSONDecodeError:
        logger.error("push_subscriptions.json 파싱 실패")
        return {}


def _save_subscriptions(subs):
    # type: (Dict[str, List[dict]]) -> None
    lock = FileLock(LOCK_PATH, timeout=2)
    tmp_path = SUBSCRIPTIONS_FILE_PATH + ".tmp"
    try:
        with lock:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(subs, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, SUBSCRIPTIONS_FILE_PATH)
    except Timeout:
        logger.error("push_subscriptions.json 저장 락 획득 실패")


@push_bp.route("/vapid-public-key", methods=["GET"])
def get_vapid_public_key():
    return jsonify({"publicKey": VAPID_PUBLIC_KEY})


@push_bp.route("/subscribe", methods=["POST"])
@login_required
def subscribe():
    subscription = request.get_json(silent=True) or {}
    endpoint = subscription.get("endpoint")
    if not endpoint:
        return jsonify({"status": "error", "message": "endpoint is required"}), 400

    username = current_user.get_id()
    subs = _load_subscriptions()
    user_subs = subs.setdefault(username, [])
    # 같은 endpoint(같은 기기/브라우저)면 최신 정보로 교체, 다르면 추가 (기기별 다중 구독 허용)
    user_subs[:] = [s for s in user_subs if s.get("endpoint") != endpoint]
    user_subs.append(subscription)
    _save_subscriptions(subs)

    return jsonify({"status": "success"})


@push_bp.route("/unsubscribe", methods=["POST"])
@login_required
def unsubscribe():
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")

    username = current_user.get_id()
    subs = _load_subscriptions()
    user_subs = subs.get(username)
    if user_subs and endpoint:
        user_subs[:] = [s for s in user_subs if s.get("endpoint") != endpoint]
        _save_subscriptions(subs)

    return jsonify({"status": "success"})


def send_push_to_user(username, title, body, url="/func/chat"):
    """
    특정 사용자의 모든 구독(기기)으로 웹 푸시 발송.
    만료/삭제된 구독(404, 410)은 자동으로 정리한다.
    """
    subs = _load_subscriptions()
    user_subs = subs.get(username) or []
    if not user_subs:
        return

    payload = json.dumps({"title": title, "body": body, "url": url})
    remaining = []
    changed = False

    for sub in user_subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY_PATH,
                vapid_claims={"sub": VAPID_CLAIMS_SUB},
                ttl=PUSH_TTL_SECONDS
            )
            remaining.append(sub)
        except WebPushException as e:
            status = e.response.status_code if e.response is not None else None
            if status in (404, 410):
                changed = True  # 만료/삭제된 구독은 제거
                continue
            logger.error("푸시 발송 실패 (status=%s): %s" % (status, e))
            remaining.append(sub)
        except Exception as e:
            logger.error("푸시 발송 중 예외: %s" % e)
            remaining.append(sub)

    if changed:
        subs[username] = remaining
        _save_subscriptions(subs)
