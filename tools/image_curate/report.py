"""캐시된 임베딩으로 점수를 매기고 dry-run 리포트를 만든다 (1단계). 파일은 옮기지 않는다.

    PYTHONIOENCODING=utf-8 venv/Scripts/python.exe tools/image_curate/report.py [--top 150] [--k 10]

출력(logs/image_curate/ — gitignore):
  scores.csv   전체 이미지 점수
  report.html  하위 후보 썸네일(동떨어짐 / 미적 / 종합 / 근접중복)

점수:
  knn_sim   가장 비슷한 이웃 k장과의 평균 코사인 유사도. 낮을수록 컬렉션 경향에서 동떨어진 이미지.
  aes       LAION aesthetic predictor(대략 1~10). 일반 사진 기준이라 이 컬렉션 취향과는 어긋날 수 있다.
  combined  두 점수의 백분위 순위 평균(0=좋음 ~ 1=후보). 2단계에서 개인 취향 점수가 추가될 자리.
"""
import argparse
import base64
import csv
import html
import io
import os
import sys
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
from PIL import Image, ImageFile

from tools.image_curate.common import PROJECT_ROOT, load_cache, resolve_ref_dir, utf8_stdout
from tools.image_curate.scoring import base_scores, dup_groups, normalize

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None
OUT_DIR = os.path.join(PROJECT_ROOT, 'logs', 'image_curate')


_thumb_cache: Dict[str, str] = {}


def thumb_b64(path: str, size: int = 220) -> str:
    if path in _thumb_cache:
        return _thumb_cache[path]
    try:
        with Image.open(path) as im:
            im.draft('RGB', (size * 2, size * 2))
            im.seek(0)
            im = im.convert('RGB')
            im.thumbnail((size, size))
            buf = io.BytesIO()
            im.save(buf, 'JPEG', quality=78)
            s = 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        s = ''
    _thumb_cache[path] = s
    return s


def card(ref_dir: str, name: str, sub: str) -> str:
    src = thumb_b64(os.path.join(ref_dir, name))
    return ('<figure><img loading="lazy" src="%s" title="%s"><figcaption>%s<br><span>%s</span></figcaption></figure>'
            % (src, html.escape(name), sub, html.escape(name[:40])))


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument('--dir', default=None)
    ap.add_argument('--top', type=int, default=150, help='섹션별 후보 수')
    ap.add_argument('--k', type=int, default=10, help='kNN 이웃 수')
    ap.add_argument('--dup', type=float, default=0.97, help='근접중복 유사도 기준')
    args = ap.parse_args()

    c = load_cache()
    if c is None or len(c['names']) == 0:
        raise SystemExit('캐시 없음 — 먼저 embed.py 실행')
    ref_dir = resolve_ref_dir(args.dir)
    top_level = np.array(['/' not in str(n) for n in c['names']])   # 보관함(_review/) 제외
    c = {k: v[top_level] for k, v in c.items()}
    names = [str(n) for n in c['names']]
    aes = c['aes'].astype(np.float64)
    sc = base_scores(normalize(c["emb"]), aes, args.k, args.dup)
    n = len(names)

    os.makedirs(OUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUT_DIR, 'scores.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['name', 'aes', 'knn_sim', 'nn_max', 'outlier_rank', 'aes_rank', 'combined'])
        for i in np.argsort(-sc['combined']):
            w.writerow([names[i], round(aes[i], 3), round(float(sc['knn_sim'][i]), 4),
                        round(float(sc['nn_max'][i]), 4), round(sc['outlier_r'][i], 4),
                        round(sc['aes_r'][i], 4), round(sc['combined'][i], 4)])

    def q(a):
        return ' / '.join('%.3f' % v for v in np.percentile(a, [5, 25, 50, 75, 95]))

    print('이미지', n)
    print('aes      p5/25/50/75/95:', q(aes))
    print('knn_sim  p5/25/50/75/95:', q(sc['knn_sim']))

    sections = []

    def section(title: str, desc: str, idx, sub_fn):
        cards = ''.join(card(ref_dir, names[i], sub_fn(i)) for i in idx)
        sections.append('<h2>%s <small>(%d)</small></h2><p>%s</p><div class="grid">%s</div>'
                        % (title, len(idx), desc, cards))

    def sub(i):
        return 'aes %.2f · sim %.3f · 종합 %.2f' % (aes[i], sc['knn_sim'][i], sc['combined'][i])

    top = min(args.top, n)
    print('썸네일 생성 중...')
    not_gif = np.array([not nm.lower().endswith('.gif') for nm in names])   # 2026-11-02 사용자: 후보에서 gif 제외
    section('종합 하위', '동떨어짐 순위와 미적 점수 순위의 평균이 가장 나쁜 순(gif 제외). _review 로 옮길 후보의 기본안.',
            [i for i in np.argsort(-sc['combined']) if not_gif[i]][:top], sub)
    section('동떨어짐', 'k=%d 이웃과의 평균 유사도가 가장 낮은 순 — 컬렉션의 다른 이미지들과 닮은 게 없는 이미지.' % args.k,
            np.argsort(sc['knn_sim'])[:top], sub)
    section('미적 점수 하위', 'LAION aesthetic predictor 최하위 순. 일반 사진 기준이라 취향과 어긋날 수 있음.',
            np.argsort(aes)[:top], sub)

    groups = dup_groups(sc["pairs"], n)
    dup_html = []
    for g in groups[:60]:
        g = sorted(g, key=lambda i: -aes[i])
        dup_html.append('<div class="grid dup">%s</div>' % ''.join(card(ref_dir, names[i], sub(i)) for i in g[:8]))
    in_dup = sum(len(g) for g in groups)
    print('근접중복 그룹', len(groups), '/ 포함 이미지', in_dup)
    sections.append('<h2>근접중복 <small>(%d그룹, %d장)</small></h2><p>유사도 ≥ %.2f. 그룹 안은 미적 점수 높은 순.</p>%s'
                    % (len(groups), in_dup, args.dup, ''.join(dup_html)))

    page = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>refine 정리 후보</title>
<style>
body{margin:0;padding:16px;background:#141414;color:#ddd;font:13px/1.4 system-ui,sans-serif}
h1{font-size:20px}h2{margin-top:32px;border-bottom:1px solid #333;padding-bottom:4px}small,p,span{color:#888}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:8px}
.dup{margin:8px 0;padding:8px;background:#1d1d1d;border-radius:6px}
figure{margin:0;background:#1d1d1d;border-radius:6px;overflow:hidden}
img{width:100%%;aspect-ratio:1;object-fit:cover;display:block;cursor:zoom-in}
img.big{position:fixed;inset:0;margin:auto;width:auto;height:auto;max-width:96vw;max-height:96vh;aspect-ratio:auto;object-fit:contain;z-index:9;box-shadow:0 0 0 100vmax #000c;cursor:zoom-out}
figcaption{padding:4px 6px;font-size:11px;word-break:break-all}
</style></head><body>
<h1>refine 정리 후보 — dry-run</h1>
<p>%d장 분석 · 파일은 옮기지 않았습니다 · 전체 점수: logs/image_curate/scores.csv · 썸네일 클릭 = 확대</p>
%s
<script>document.addEventListener('click',e=>{if(e.target.tagName==='IMG')e.target.classList.toggle('big')})</script>
</body></html>""" % (n, '\n'.join(sections))
    html_path = os.path.join(OUT_DIR, 'report.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(page)
    print('CSV :', csv_path)
    print('HTML:', html_path)


if __name__ == '__main__':
    main()
