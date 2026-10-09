-- /posts 공지(ADMIN 고정) / 개인 즐겨찾기 (2026-10-09)
-- posts 에 컬럼을 추가하지 않고 별도 테이블로 둔다: posts 조회는 `SELECT p.*` 를 PostDTO(**row) 로
-- 받기 때문에 컬럼이 늘면 DTO 를 같이 고친 코드로 재시작하기 전까지 목록/상세가 TypeError 로 깨진다.

CREATE TABLE IF NOT EXISTS post_pins (
    post_id    INTEGER PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
    pinned_by  INTEGER NOT NULL REFERENCES users(id),
    pinned_at  TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS post_bookmarks (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    post_id    INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, post_id)
);

-- 두 테이블 모두 SERIAL 이 없으므로 시퀀스 권한은 불필요.
-- 앱 계정(chick)이 아닌 계정으로 생성했을 때를 대비한 권한 부여 (소유자가 실행해도 무해)
GRANT ALL PRIVILEGES ON TABLE post_pins TO chick;
GRANT ALL PRIVILEGES ON TABLE post_bookmarks TO chick;
