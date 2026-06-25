# 프로젝트 환경

## Python 버전: 3.8.10

Python 코드 작성 시 아래 규칙을 반드시 준수한다.

### 사용 금지 (3.9+ 문법)
- `list[str]`, `dict[str, int]`, `tuple[str, ...]` → `List`, `Dict`, `Tuple` from `typing` 사용
- `str.removeprefix()`, `str.removesuffix()` → 직접 슬라이싱으로 대체

### 사용 금지 (3.10+ 문법)
- `match` 문 → `if/elif` 사용
- `X | Y` 타입 유니온 → `Union[X, Y]` from `typing` 사용
- `int | None` → `Optional[int]` from `typing` 사용

### 타입 힌트 작성 규칙
```python
# ❌ 3.9+
def foo(x: list[str]) -> dict[str, int]: ...

# ✅ 3.8
from typing import List, Dict, Optional, Union, Tuple
def foo(x: List[str]) -> Dict[str, int]: ...
```
