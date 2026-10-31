# CSRF 토큰 도입 가이드

## 1. 현재 상태 (코드 확인 결과)

| 항목 | 상태 |
|---|---|
| 프레임워크 | Flask 3.0.3, Flask-Login, Flask-SocketIO, **Flask-WTF 1.2.1 (이미 설치됨)** |
| 세션 | Flask 서명 쿠키 (`app.secret_key`), 만료는 Redis TTL로 별도 관리 |
| 쿠키 속성 | `HttpOnly`, `Secure`, `SameSite=Lax` (`app/__init__.py:158-160`) |
| 상태 변경 라우트 | POST/PUT/DELETE/PATCH `methods=` 선언 약 89개 |
| 프런트 요청 | `fetch(` 약 71곳, `XMLHttpRequest`/`sendBeacon`/`$.ajax` 약 9곳, `<form` 18곳 |
| CSRF 보호 | **없음** (SameSite=Lax가 유일한 방어) |

`SameSite=Lax`가 이미 크로스사이트 POST를 대부분 막아 주지만, 다음 경우는 못 막는다.
- 같은 사이트(서브도메인) 내 XSS/악성 페이지에서의 요청
- GET으로 상태를 바꾸는 라우트 (Lax는 top-level GET 이동에 쿠키를 보냄)
- 구형 브라우저 / 쿠키 정책 변경

따라서 **토큰 방식을 추가해 이중 방어**하는 것이 목표다.

## 2. 권장 방식: Flask-WTF `CSRFProtect` + 헤더 토큰

폼은 hidden input, fetch/XHR은 `X-CSRFToken` 헤더로 보낸다. 서버는 전역 `before_request` 수준에서 검증하므로 라우트마다 코드를 고칠 필요가 없다.

### 2-1. 서버 (`app/__init__.py`)

```python
from flask_wtf.csrf import CSRFProtect, CSRFError

csrf = CSRFProtect()   # 모듈 상단에 선언 (blueprint에서 @csrf.exempt 쓰려면 import 가능해야 함)

def create_app():
    app = Flask(__name__, static_folder='static')
    app.config.update(load_config())
    ...
    app.config['WTF_CSRF_TIME_LIMIT'] = None      # 세션 동안 유효 (세션 TTL은 Redis가 관리)
    app.config['WTF_CSRF_SSL_STRICT'] = True      # HTTPS Referer 검사 (프록시 뒤라면 ProxyFix 적용 확인)
    csrf.init_app(app)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        # fetch는 JSON, 일반 폼은 안내 페이지
        if request.accept_mimetypes.best == 'application/json' or request.is_json:
            return jsonify({'error': 'csrf', 'message': e.description}), 400
        return render_template('error.html', message='세션이 만료되었습니다. 새로고침 후 다시 시도하세요.'), 400
```

주의: 기존 `before_request`(인증/허용 경로 검사)와 **실행 순서**가 얽힌다. `CSRFProtect`는 `init_app` 시점에 자체 `before_request`를 등록하므로, 기존 훅보다 먼저 등록되도록 `csrf.init_app(app)`을 `@app.before_request` 정의보다 위에 둔다. (비로그인 요청은 인증에서 막히기 전에 CSRF 400이 나올 수 있음 — 의도한 동작인지 확인.)

### 2-2. 토큰 전달: 템플릿 공통 `<meta>`

공통 레이아웃(base 템플릿, 없다면 각 페이지 `<head>`)에 한 줄 추가:

```html
<meta name="csrf-token" content="{{ csrf_token() }}">
```

### 2-3. 폼 (`<form method="post">` 18곳)

```html
<form method="post" action="...">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  ...
</form>
```

### 2-4. fetch / XHR — **공통 래퍼 한 곳에서 처리** (`app/static/js/common.js`)

71곳을 일일이 고치지 않고 `window.fetch`를 감싼다.

```js
(function () {
  const meta = document.querySelector('meta[name="csrf-token"]');
  const token = meta ? meta.content : '';
  const SAFE = new Set(['GET', 'HEAD', 'OPTIONS']);
  const origFetch = window.fetch;

  window.fetch = function (input, init) {
    init = init || {};
    const method = (init.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    // 같은 오리진 요청에만 토큰 첨부 (외부 URL로 토큰 유출 방지)
    const url = new URL(input instanceof Request ? input.url : input, location.href);
    if (!SAFE.has(method) && url.origin === location.origin) {
      const headers = new Headers(init.headers || (input instanceof Request ? input.headers : {}));
      headers.set('X-CSRFToken', token);
      init.headers = headers;
    }
    return origFetch.call(this, input, init);
  };

  // XMLHttpRequest (uppy 등 업로드 라이브러리 포함)
  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this._csrfNeeded = !SAFE.has(String(method).toUpperCase()) &&
                       new URL(url, location.href).origin === location.origin;
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    if (this._csrfNeeded) this.setRequestHeader('X-CSRFToken', token);
    return origSend.apply(this, arguments);
  };
})();
```

이 스크립트는 **다른 JS보다 먼저** 로드되어야 한다. `common.js`를 쓰지 않는 페이지(예: `login.html`, `video_call.html`)는 따로 포함시킨다.

### 2-5. `navigator.sendBeacon` — 헤더를 못 붙인다

`sendBeacon`은 커스텀 헤더 불가. 해당 호출은 FormData에 `csrf_token` 필드를 넣어 보내거나, `fetch(..., {keepalive: true})`로 바꾼다. (`grep -rn sendBeacon app/static app/templates`로 위치 확인)

### 2-6. Socket.IO

`Flask-SocketIO`의 WebSocket 핸드셰이크는 `CSRFProtect` 대상이 아니다(HTTP 폴링 POST는 `/socket.io/` 경로 — 아래 면제 참고). 대신 **Origin 검증**을 켠다.

```python
socketio = SocketIO(cors_allowed_origins=["https://내도메인"])
```

## 3. 면제/주의가 필요한 곳

| 대상 | 처리 |
|---|---|
| `/socket.io/` | `csrf.exempt` 불가(Blueprint 아님) → `WTF_CSRF_METHODS`는 그대로 두고, `before_request`에서 `request.path.startswith('/socket.io')`면 건너뛰도록 `@csrf.exempt`가 아닌 `app.config['WTF_CSRF_CHECK_DEFAULT']=False` + 수동 `csrf.protect()` 방식 검토 |
| 외부 콜백 (`/oauth/...`) | GET 콜백이면 무관. POST 웹훅이면 `@csrf.exempt` + 서명 검증 |
| API 클라이언트/앱 (`/api`) | 쿠키 세션이 아닌 토큰(JWT) 인증이면 `csrf.exempt(api)` 가능 |
| `/ffmpeg` 의 `@cross_origin()` | CORS는 CSRF와 별개. `supports_credentials`가 켜져 있지 않은지만 확인 |
| 로그인 POST | 로그인 CSRF 방지를 위해 **보호 대상에 포함**(`login.html` 폼/`fetch`에 토큰 필요) |

`CSRFProtect`는 기본이 "전체 보호"이므로 위 항목에서 400이 나는지 부터 확인하는 식으로 진행하면 누락이 적다.

## 4. 그 외 병행 권장 사항

1. **GET으로 상태를 바꾸는 라우트 점검** — 삭제/이동/비우기 등이 GET이면 POST로 바꾼다. CSRF 토큰은 GET을 검증하지 않는다.
   `grep -rn "@.*route(" app/*.py`에서 `methods` 없는 라우트 중 `delete`, `move`, `empty`, `shuffle` 등 이름 확인.
2. **Origin/Referer 헤더 검사** — nginx 또는 `before_request`에서 POST의 `Origin`이 자기 도메인인지 확인 (토큰과 이중 방어).
3. **SameSite 유지** — 현재 `Lax` 유지. `None`으로 바꾸지 않는다.
4. **세션 고정 방지** — 로그인 성공 시 `session.clear()` 후 재발급하면 토큰도 새로 만들어진다.

## 5. 웹서버(nginx)에서 할 일

CSRF 토큰 검증 자체는 애플리케이션 레벨이라 nginx에서 대체할 수 없다. nginx는 **보조 방어와 헤더 통과** 역할만 한다.

### 5-1. 커스텀 헤더 통과 확인
`X-CSRFToken` 헤더는 기본적으로 nginx가 그대로 전달한다. 단, `underscores_in_headers` 문제는 없다(하이픈 사용). 별도 `proxy_set_header` 허용 목록이 있다면 확인만 하면 된다.

### 5-2. Origin 검사 (보조 방어)
```nginx
# http 블록
map $http_origin $origin_ok {
    default                0;
    ""                     1;   # 같은 오리진 일부 요청은 Origin이 없음
    "https://내도메인"      1;
}

server {
    ...
    location / {
        if ($request_method !~ ^(GET|HEAD|OPTIONS)$) {
            set $csrf_block "${origin_ok}";
        }
        if ($csrf_block = "0") { return 403; }
        proxy_pass http://127.0.0.1:5000;
        ...
    }
}
```
`Origin`이 비어 있으면 통과시키므로 완전하진 않다. 토큰 검증이 주 방어이고 이건 보조다.

### 5-3. 프록시 헤더 (필수 확인)
`WTF_CSRF_SSL_STRICT=True`는 HTTPS에서 `Referer`를 검사하므로, Flask가 요청을 https로 인식해야 한다.
```nginx
proxy_set_header Host              $host;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
```
앱은 이미 `ProxyFix`/`ReverseProxied`를 쓰고 있으니 위 헤더와 일치하는지만 확인한다.

### 5-4. 보안 헤더
```nginx
add_header Referrer-Policy "strict-origin-when-cross-origin" always;  # 같은 오리진 Referer 유지
add_header X-Frame-Options "SAMEORIGIN" always;                       # 클릭재킹 방지
```
`Referrer-Policy: no-referrer`로 설정돼 있으면 SSL_STRICT 검사가 실패하니 피한다.

### 5-5. 캐시 주의
토큰이 들어간 HTML이 nginx/CDN에 **캐시되면 다른 사용자의 토큰이 노출**된다. 동적 HTML 페이지는 캐시하지 않는다.
```nginx
location / {
    proxy_no_cache 1;
    proxy_cache_bypass 1;
}
# 정적 파일(/static/, 영상, 썸네일)만 캐시 허용
```

## 6. 적용 순서 (권장)

1. `CSRF_GUIDE.md` 2-4의 JS 래퍼를 `common.js`에 추가하고 모든 템플릿에 `<meta csrf-token>` 삽입 (서버 검증 켜기 **전**에 배포해도 무해)
2. 폼 18곳에 hidden input 추가
3. `sendBeacon` 호출 수정
4. 서버에 `CSRFProtect` 추가 — 처음엔 **로컬/dev(`rundev.py`)에서** 모든 페이지를 눌러 400이 나는 곳을 찾는다
5. 면제 대상(Socket.IO, 외부 콜백 등) 정리
6. nginx 보조 설정 적용
7. 운영 반영 후 로그에서 `CSRFError` 모니터링

## 7. 테스트 체크리스트

- [ ] 토큰 없이 `curl -X POST https://도메인/func/empty-trash-bin -b cookie` → 400
- [ ] 로그인 / 로그아웃 / 2차 비밀번호 인증 정상
- [ ] 영상 삭제·좋아요, 이미지 이동, 게시글 작성/수정, 메모, 채팅 전송 정상
- [ ] 파일 업로드(uppy) 정상 — XHR 헤더 경로
- [ ] 채팅 Socket.IO 연결/메시지 정상
- [ ] 세션 만료 후 첫 요청 → 안내 메시지(무한 400 루프 없음)
- [ ] 여러 탭 동시 사용 시 토큰 불일치 없음 (`WTF_CSRF_TIME_LIMIT=None`이라 무관해야 함)
- [ ] 스케줄러(`run.py`)가 내부적으로 앱 POST 엔드포인트를 호출하는 곳이 없는지 확인

## 8. 롤백
`csrf.init_app(app)` 한 줄을 주석 처리하면 서버 검증이 꺼진다. 프런트의 meta/래퍼는 남겨도 무해하다.
