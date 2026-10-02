# -*- coding: utf-8 -*-
"""갤러리 썸네일(thumb/<이름>.webp) 생성 전 dry-run — 디스크에 아무것도 쓰지 않고 읽기만 한다.

배경: /image/images(app/image.py get_image)는 <base_dir>/thumb/<확장자 뺀 이름>.webp 가 있으면
그걸 보내고 없으면 원본을 보낸다. 지금은 모든 이미지 폴더에 thumb/ 가 없어 원본(평균 1~2MB,
최대 50MB)이 그대로 나간다. 이 스크립트는 "가로 WIDTH(기본 800px) webp 썸네일을 만들면 몇 장을,
얼마 용량으로, 얼마나 걸려 만드는지"를 본 변환 전에 추정한다.

하는 일(전부 읽기 전용):
  1) 폴더별 파일 전수 스캔 — 이미지 헤더만 열어 가로폭/움직임(gif·webp 애니) 판별
  2) 분류: 썸네일 필요(축소) / 필요(재압축만) / 불필요(이미 작음) / 건너뜀(영상·애니메이션·열기 실패)
  3) 필요 대상에서 무작위 표본을 메모리에서 실제로 변환해 평균 용량·시간을 재고 전체로 환산
  4) 같은 이름·다른 확장자(a.jpg / a.png)는 thumb/a.webp 로 충돌하므로 따로 보고
  5) --sample-out 을 주면 표본 썸네일 몇 장을 그 폴더(운영 폴더 아님)에 저장해 화질을 눈으로 비교

사용(venv 필수 — DB 설정/Pillow):
    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe utils/image_thumbs_dryrun.py
    ... --width 800 --compare-width 600 --sample-out C:\\Temp\\thumb_samples
    ... --only image,move          # 폴더 이름: image image2 cos move refine
"""
import argparse
import io
import os
import random
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from PIL import Image, ImageOps   # noqa: E402

Image.MAX_IMAGE_PIXELS = 250_000_000   # 초대형 이미지도 열어 보되, 그 이상은 실패로 보고

IMG_EXT = {'.jpg', '.jpeg', '.jfif', '.png', '.webp', '.bmp', '.gif'}
VIDEO_EXT = {'.mp4', '.webm', '.mov', '.mkv', '.avi'}
EXCLUDE_EXT = {'.zip', '.ini', '.identifier'}   # app/image.py EXCLUDE_SUFFIXES 와 같은 의미
SMALL_BYTES = 200 * 1024      # 가로가 WIDTH 이하이고 파일도 이 이하면 썸네일 불필요(원본 그대로)
QUALITY = 80
SAMPLE_PER_DIR = 120
SEED = 42


def vw(s):
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in str(s))


def print_table(title, headers, rows, aligns):
    widths = [max(vw(x) for x in col) for col in zip(headers, *rows)]

    def fmt(cells):
        out = []
        for c, w, al in zip(cells, widths, aligns):
            gap = ' ' * (w - vw(c))
            out.append(str(c) + gap if al == 'l' else gap + str(c))
        return '  '.join(out).rstrip()

    line = '-' * max(vw(fmt(headers)), 1)
    print()
    print(f'[{title}]')
    print(line)
    print(fmt(headers))
    print(line)
    for r in rows:
        print(fmt(r))
    print(line)


def human(n):
    n = float(n)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:,.1f}{unit}' if unit != 'B' else f'{n:,.0f}B'
        n /= 1024


def get_dirs(only):
    from config.config import settings
    cfg = {
        'image': settings.get('IMAGE_DIR'),
        'image2': settings.get('IMAGE_DIR2'),
        'cos': settings.get('COS_DIR'),
        'move': settings.get('MOVE_DIR'),
        'refine': settings.get('REF_IMAGE_DIR'),
    }
    names = [n.strip() for n in only.split(',')] if only else list(cfg)
    return [(n, cfg[n]) for n in names if cfg.get(n)]


def scan(base):
    """(이미지 후보 [(경로, 상대경로, 크기)], 영상 수, 기타 수). thumb/ 폴더는 건너뛴다."""
    imgs, videos, others = [], 0, 0
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d.lower() != 'thumb']
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in EXCLUDE_EXT:
                continue
            p = os.path.join(root, f)
            if ext in IMG_EXT:
                try:
                    imgs.append((p, os.path.relpath(p, base), os.stat(p).st_size))
                except OSError:
                    others += 1
            elif ext in VIDEO_EXT:
                videos += 1
            else:
                others += 1
    return imgs, videos, others


def probe(item):
    """헤더만 열어 (가로, 세로, 애니메이션 여부) — 실패하면 예외 문자열."""
    p = item[0]
    try:
        with Image.open(p) as im:
            animated = bool(getattr(im, 'is_animated', False))
            return im.width, im.height, animated, None
    except Exception as e:   # noqa: BLE001 — 손상 파일 등은 보고만 한다
        return 0, 0, False, f'{type(e).__name__}: {e}'[:80]


def make_thumb(path, width):
    """app/image.py 가 그대로 서빙할 thumb webp 바이트. (바이트, 결과 가로, 결과 세로)."""
    with Image.open(path) as im:
        if im.format == 'JPEG':
            im.draft('RGB', (width, max(1, round(im.height * width / max(im.width, 1)))))   # 디코딩 가속
        im = ImageOps.exif_transpose(im)
        if im.width > width:
            im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
        has_alpha = im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info)
        im = im.convert('RGBA' if has_alpha else 'RGB')
        buf = io.BytesIO()
        im.save(buf, 'WEBP', quality=QUALITY, method=4)
        return buf.getvalue(), im.width, im.height


def sample_convert(path, widths):
    """표본 1장을 widths 각각으로 변환 → {width: (바이트, 초)}."""
    out = {}
    for w in widths:
        t = time.perf_counter()
        try:
            data, _, _ = make_thumb(path, w)
            out[w] = (len(data), time.perf_counter() - t, data)
        except Exception as e:   # noqa: BLE001
            out[w] = (None, time.perf_counter() - t, str(e)[:80])
    return out


def main():
    ap = argparse.ArgumentParser(description='썸네일 생성 dry-run(읽기 전용)')
    ap.add_argument('--width', type=int, default=800)
    ap.add_argument('--compare-width', type=int, default=0, help='이 폭으로도 표본을 변환해 용량을 비교')
    ap.add_argument('--only', default='', help='쉼표 구분: image,image2,cos,move,refine')
    ap.add_argument('--sample', type=int, default=SAMPLE_PER_DIR, help='폴더당 변환 표본 수')
    ap.add_argument('--workers', type=int, default=4, help='본 변환 시 병렬 수(시간 환산용)')
    ap.add_argument('--sample-out', default='', help='표본 썸네일 저장 폴더(운영 폴더가 아니어야 함)')
    args = ap.parse_args()

    W = args.width
    widths = [W] + ([args.compare_width] if args.compare_width and args.compare_width != W else [])
    random.seed(SEED)
    if args.sample_out:
        os.makedirs(args.sample_out, exist_ok=True)

    summary, notes = [], []
    grand = {'create': 0, 'orig': 0, 'est': 0, 'sec': 0.0}

    for name, base in get_dirs(args.only):
        t0 = time.perf_counter()
        if not os.path.isdir(base):
            notes.append(f'{name}: 폴더를 열 수 없음 — {base}')
            continue
        imgs, videos, others = scan(base)
        with ThreadPoolExecutor(max_workers=8) as pool:
            probed = list(pool.map(probe, imgs))

        cls = {'resize': [], 'recompress': [], 'small': [], 'animated': [], 'fail': []}
        for item, (w, h, anim, err) in zip(imgs, probed):
            if err:
                cls['fail'].append((item, err))
            elif anim:
                cls['animated'].append(item)
            elif w <= W and item[2] <= SMALL_BYTES:
                cls['small'].append(item)
            elif w > W:
                cls['resize'].append(item)
            else:
                cls['recompress'].append(item)

        create = cls['resize'] + cls['recompress']

        # 같은 이름·다른 확장자는 thumb/<이름>.webp 로 충돌한다(대소문자 무시)
        seen, collide = {}, []
        for item in create:
            key = os.path.splitext(item[1])[0].lower()
            if key in seen:
                collide.append((seen[key][1], item[1]))
            else:
                seen[key] = item

        # 표본 변환 → 평균 용량/시간 → 전체 환산
        pick = random.sample(create, min(args.sample, len(create))) if create else []
        res = {w: [] for w in widths}
        conv_fail = 0
        for i, item in enumerate(pick):
            r = sample_convert(item[0], widths)
            if r[W][0] is None:
                conv_fail += 1
                continue
            for w in widths:
                if r[w][0] is not None:
                    res[w].append((item[2], r[w][0], r[w][1]))
            if args.sample_out and i < 8:
                stem = os.path.splitext(os.path.basename(item[1]))[0][:40]
                for w in widths:
                    if r[w][0] is not None:
                        with open(os.path.join(args.sample_out, f'{name}__{stem}__w{w}.webp'), 'wb') as f:
                            f.write(r[w][2])

        def est(w):
            rows = res[w]
            if not rows or not create:
                return 0, 0, 0.0, 0.0
            # 썸네일이 원본보다 크면 원본을 그대로 쓰는 편이 낫다 → 생성 대상에서 뺀다
            keep = [r for r in rows if r[1] < r[0]]
            frac_keep = len(keep) / len(rows)
            n_keep = round(len(create) * frac_keep)
            mean_thumb = sum(r[1] for r in keep) / len(keep) if keep else 0
            mean_sec = sum(r[2] for r in rows) / len(rows)
            return n_keep, n_keep * mean_thumb, mean_thumb, mean_sec

        n_keep, est_bytes, mean_thumb, mean_sec = est(W)
        orig_bytes_create = sum(i[2] for i in create)
        mean_orig_sample = (sum(r[0] for r in res[W]) / len(res[W])) if res[W] else 0
        sec_total = len(create) * mean_sec / max(args.workers, 1)

        summary.append([
            name, f'{len(imgs):,}', f'{len(cls["small"]):,}', f'{len(cls["resize"]):,}',
            f'{len(cls["recompress"]):,}', f'{len(cls["animated"]):,}', f'{len(cls["fail"]):,}',
            f'{videos:,}', f'{len(collide):,}',
        ])
        grand['create'] += n_keep
        grand['orig'] += orig_bytes_create
        grand['est'] += est_bytes
        grand['sec'] += sec_total

        detail = [f'{name}: 폴더 {base}',
                  f'    스캔 {time.perf_counter() - t0:.0f}초 / 표본 {len(res[W])}장(변환 실패 {conv_fail}장)']
        if res[W]:
            detail.append(f'    표본 평균: 원본 {human(mean_orig_sample)} → {W}px webp {human(mean_thumb)} '
                          f'({mean_thumb / mean_orig_sample:.1%}), 장당 {mean_sec * 1000:.0f}ms')
            detail.append(f'    생성 대상 {len(create):,}장 중 썸네일이 원본보다 작은 {n_keep:,}장만 생성 → '
                          f'예상 {human(est_bytes)} (대상 원본 합계 {human(orig_bytes_create)}), '
                          f'병렬 {args.workers} 기준 약 {sec_total / 60:.1f}분')
            for w in widths[1:]:
                nk, eb, mt, ms = est(w)
                detail.append(f'    비교 {w}px: 평균 {human(mt)}, 예상 합계 {human(eb)} ({W}px 대비 {eb / max(est_bytes, 1):.0%})')
        notes.extend(detail)
        for item, err in cls['fail'][:5]:
            notes.append(f'    열기 실패: {item[1]} — {err}')
        for a, b in collide[:5]:
            notes.append(f'    이름 충돌(thumb 파일명 동일): {a}  <->  {b}')

    print_table(f'dry-run 요약 (폭 {W}px, webp q{QUALITY}) — 디스크 쓰기 없음',
                ['폴더', '이미지', '불필요(작음)', '축소 생성', '재압축 생성', '애니(제외)', '열기실패', '영상', '이름충돌'],
                summary, ['l'] + ['r'] * 8)
    print()
    for n in notes:
        print(n)
    print()
    print(f'전체 합계: 생성 {grand["create"]:,}장 / 대상 원본 {human(grand["orig"])} → 썸네일 약 {human(grand["est"])} '
          f'/ 예상 소요 약 {grand["sec"] / 60:.1f}분 (병렬 {args.workers})')
    print('※ 표본 추정치다. 영상(mp4/webm)·애니메이션 gif/webp는 썸네일을 만들지 않는다(thumb 이 있으면 서버가 그걸 우선 보내므로).')


if __name__ == '__main__':
    main()
