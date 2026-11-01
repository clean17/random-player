"""토스증권 공식 Open API 클라이언트 (https://developers.tossinvest.com/docs).

2026-10-30: 비공식 wts-info-api(웹 프런트용 내부 API)가 서버 요청을 400 invalid-request로 막아서
공식 API로 옮겼다. 인증은 OAuth2 client credentials(.env의 TOSS_CLIENT_ID/TOSS_CLIENT_SECRET),
허용 IP에서만 토큰이 발급된다(그 외는 access_denied).

주의
- 클라이언트당 유효 토큰은 1개다(새로 발급하면 이전 토큰은 token-revoked). 그래서 토큰을 파일로
  다른 프로젝트와 공유하고(아래 _TOKEN_FILE), 401이면 파일을 다시 읽거나 한 번만 재발급해 재시도한다.
- 시세에는 거래대금·로고·섹터·뉴스가 없다(실측). lastPrice/종목명/거래량만 제공된다.
- 호출 한도: prices 15/s(MARKET_DATA), candles 20/s, stocks 5/s. 429면 Retry-After만큼 쉰다.
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://openapi.tossinvest.com"
_TOKEN_URL = BASE_URL + "/oauth2/token"
_TOKEN_MARGIN = 300          # 만료 5분 전에 미리 재발급
_PRICES_CHUNK = 200          # /api/v1/prices 한 번에 최대 200종목

# 토큰 파일 공유 (2026-10-30): 같은 키를 쓰는 다른 프로젝트(C:\my-project\AutoSales.py의
# toss_openapi.py)와 토큰을 공유한다. 클라이언트당 유효 토큰이 1개라 각자 발급하면 서로의 토큰을
# 무효화(token-revoked)하기 때문이다. 두 프로젝트 바깥(C:\my-project)에 두어 git에 안 들어간다.
# 토큰 로직을 고치면 AutoSales.py/toss_openapi.py도 같이 고칠 것.
_TOKEN_FILE = os.environ.get("TOSS_TOKEN_FILE") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".toss_openapi_token.json")
_LOCK_FILE = _TOKEN_FILE + ".lock"

_token_lock = threading.Lock()
_token = {"value": None, "expires_at": 0.0}


def _read_token_file() -> Optional[Dict]:
    try:
        with open(_TOKEN_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if d.get("value") and float(d.get("expires_at", 0)) > time.time() else None
    except Exception:
        return None


def _write_token_file(value: str, expires_at: float) -> None:
    tmp = _TOKEN_FILE + ".tmp%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"value": value, "expires_at": expires_at}, f)
    os.replace(tmp, _TOKEN_FILE)


def _acquire_file_lock(timeout: float = 20.0) -> None:
    """프로세스 간 락(O_EXCL 락파일). 30초 넘은 락파일은 죽은 프로세스의 것으로 보고 치운다."""
    deadline = time.time() + timeout
    while True:
        try:
            os.close(os.open(_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(_LOCK_FILE) > 30:
                    os.remove(_LOCK_FILE)
                    continue
            except OSError:
                pass
            if time.time() > deadline:
                raise TimeoutError("toss token lock timeout")
            time.sleep(0.1)


def _issue_token() -> str:
    res = requests.post(
        _TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["TOSS_CLIENT_ID"],
            "client_secret": os.environ["TOSS_CLIENT_SECRET"],
        },
        timeout=10,
    )
    res.raise_for_status()
    body = res.json()
    value = body["access_token"]
    expires_at = time.time() + int(body.get("expires_in", 3600)) - _TOKEN_MARGIN
    _write_token_file(value, expires_at)
    return value


def _get_token(bad: Optional[str] = None) -> str:
    """유효한 토큰. bad=방금 401을 받은 토큰이면 그걸 제외하고(다른 프로세스가 이미 새로 발급해
    파일에 써뒀으면 그걸 쓰고, 아니면 새로 발급)."""
    with _token_lock:
        if _token["value"] and _token["value"] != bad and time.time() < _token["expires_at"]:
            return _token["value"]
        d = _read_token_file()
        if not (d and d["value"] != bad):
            _acquire_file_lock()
            try:
                d = _read_token_file()          # 락 기다리는 사이 다른 프로세스가 발급했을 수 있다
                if not (d and d["value"] != bad):
                    _issue_token()
                    d = _read_token_file()
            finally:
                try:
                    os.remove(_LOCK_FILE)
                except OSError:
                    pass
        _token["value"], _token["expires_at"] = d["value"], float(d["expires_at"])
        return _token["value"]


def _get(path: str, params: Dict, timeout: int = 10) -> Dict:
    """GET + Bearer. 401이면 토큰을 다시 받아 1회, 429면 Retry-After 후 1회 재시도."""
    url = BASE_URL + path
    for attempt in range(3):
        token = _get_token()
        res = requests.get(
            url,
            params=params,
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
            timeout=timeout,
        )
        if res.status_code == 401 and attempt == 0:
            _get_token(bad=token)
            continue
        if res.status_code == 429 and attempt < 2:
            time.sleep(min(float(res.headers.get("Retry-After", 1)), 5))
            continue
        res.raise_for_status()
        return res.json()
    res.raise_for_status()
    return res.json()


def get_last_prices(symbols: List[str]) -> Dict[str, float]:
    """종목코드(6자리) 리스트 -> {종목코드: 현재가}. 응답에 없는 종목(거래정지 등)은 빠진다."""
    out: Dict[str, float] = {}
    for i in range(0, len(symbols), _PRICES_CHUNK):
        chunk = symbols[i:i + _PRICES_CHUNK]
        body = _get("/api/v1/prices", {"symbols": ",".join(chunk)})
        for it in body.get("result") or []:
            price = it.get("lastPrice")
            if price is not None:
                out[it["symbol"]] = float(price)
    return out


def get_today_candle(symbol: str) -> Optional[Dict]:
    """오늘(최신) 일봉 1개. 필드: openPrice/highPrice/lowPrice/closePrice/volume(문자열)."""
    body = _get("/api/v1/candles", {"symbol": symbol, "interval": "1d", "count": 1})
    candles = (body.get("result") or {}).get("candles") or []
    return candles[0] if candles else None


def get_stock_names(symbols: List[str]) -> Dict[str, str]:
    """종목코드 -> 한글 종목명 (최대 200개씩). 종목명은 거의 안 바뀌어 프로세스 동안 캐시한다."""
    out: Dict[str, str] = {}
    missing = []
    with _cache_lock:
        for s in symbols:
            if s in _name_cache:
                out[s] = _name_cache[s]
            else:
                missing.append(s)
    for i in range(0, len(missing), 200):
        chunk = missing[i:i + 200]
        body = _get("/api/v1/stocks", {"symbols": ",".join(chunk)})
        with _cache_lock:
            for it in body.get("result") or []:
                _name_cache[it["symbol"]] = it.get("name")
                out[it["symbol"]] = it.get("name")
    return out


# ── 오늘 거래대금 ────────────────────────────────────────────────────────────
# 공식 시세/캔들엔 거래대금 필드가 없다. 대신 랭킹(MARKET_TRADING_AMOUNT, duration=1d)이 거래대금
# 상위 100종목의 실제 tradingAmount를 준다(실측: 하이닉스 8.05조 = 웹 화면 값과 일치). 100위 밖은
# 일봉 거래량 x 대표가격((고+저+종)/3)으로 근사한다(실제 체결대금과 수 % 어긋날 수 있음).
# duration=realtime은 최근 구간 값이라 오늘 누적이 아니다(실측: 하이닉스 940억) — 쓰지 말 것.
_AMOUNT_TTL = 10.0
_cache_lock = threading.Lock()
_name_cache: Dict[str, str] = {}
_rank_cache = {"at": 0.0, "map": {}}
_candle_amount_cache: Dict[str, tuple] = {}   # code -> (timestamp, amount)


def _ranking_amounts() -> Dict[str, float]:
    now = time.time()
    with _cache_lock:
        if now - _rank_cache["at"] < _AMOUNT_TTL:
            return _rank_cache["map"]
    body = _get("/api/v1/rankings", {"type": "MARKET_TRADING_AMOUNT", "marketCountry": "KR",
                                     "duration": "1d", "count": 100})
    m = {it["symbol"]: float(it["tradingAmount"])
         for it in (body.get("result") or {}).get("rankings") or []}
    with _cache_lock:
        _rank_cache["at"] = now
        _rank_cache["map"] = m
    return m


def _candle_amount(code: str) -> Optional[float]:
    now = time.time()
    with _cache_lock:
        cached = _candle_amount_cache.get(code)
        if cached and now - cached[0] < _AMOUNT_TTL:
            return cached[1]
    candle = get_today_candle(code)
    if not candle:
        return None
    typical = (float(candle["highPrice"]) + float(candle["lowPrice"]) + float(candle["closePrice"])) / 3
    amount = float(candle["volume"]) * typical
    with _cache_lock:
        _candle_amount_cache[code] = (now, amount)
    return amount


def get_trading_amounts(codes: List[str]) -> Dict[str, float]:
    """종목코드 -> 오늘 거래대금(원). 조회 실패한 종목은 빠진다(표시용 부가 정보)."""
    out: Dict[str, float] = {}
    try:
        ranked = _ranking_amounts()
    except Exception as e:
        print(f"[WARN] toss rankings 실패: {e}")
        ranked = {}
    rest = []
    for c in codes:
        if c in ranked:
            out[c] = ranked[c]
        else:
            rest.append(c)

    def one(c):
        try:
            return c, _candle_amount(c)
        except Exception as e:
            print(f"[WARN] toss candle 실패: {c} {e}")
            return c, None

    if rest:
        with ThreadPoolExecutor(max_workers=8) as ex:
            for c, a in ex.map(one, rest):
                if a is not None:
                    out[c] = a
    return out


def get_quotes(codes: List[str]) -> Dict[str, Dict]:
    """관심종목 화면 폴링용: {종목코드: {name, price, amount}}. 일부 항목은 없을 수 있다."""
    prices = get_last_prices(codes)
    names = {}
    try:
        names = get_stock_names(list(prices.keys()))
    except Exception as e:
        print(f"[WARN] toss stocks 실패: {e}")
    amounts = get_trading_amounts(list(prices.keys()))
    return {c: {"name": names.get(c), "price": p, "amount": amounts.get(c)} for c, p in prices.items()}
