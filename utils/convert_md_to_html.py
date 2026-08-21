import re
import html
import markdown

# input_file = "E:/my/memo/laris/유지관리.md"
# output_file = "E:/my/memo/laris/유지관리.html"

input_file = "app/static/ANALYSIS.md"
output_file = "app/static/ANALYSIS.html"

with open(input_file, "r", encoding="utf-8") as f:
    text = f.read()


def make_slug(title: str, used: dict) -> str:
    """
    제목을 HTML id로 사용할 수 있게 변환.
    한글은 유지하고, 공백/특수문자는 - 로 치환.
    중복 제목은 -2, -3 형태로 처리.
    """
    slug = title.strip().lower()
    slug = re.sub(r"[^\w가-힣一-龥ぁ-んァ-ン]+", "-", slug)
    slug = slug.strip("-")

    if not slug:
        slug = "section"

    count = used.get(slug, 0) + 1
    used[slug] = count

    if count > 1:
        return f"{slug}-{count}"

    return slug


def add_heading_ids_and_build_toc(md_text: str):
    """
    #, ##, ### 제목에 id를 추가하고,
    왼쪽 네비게이션용 TOC HTML 생성.
    fenced code block 안의 # 은 제목으로 처리하지 않음.
    """
    used = {}
    toc_items = []
    new_lines = []
    in_code_block = False

    heading_pattern = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")

    for line in md_text.splitlines():
        stripped = line.strip()

        # ``` 코드블럭 내부 제목 제외
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            new_lines.append(line)
            continue

        if not in_code_block:
            match = heading_pattern.match(line)
            if match:
                hashes = match.group(1)
                title = match.group(2).strip()

                # 이미 {#id}가 붙은 경우 제거 후 다시 생성
                title = re.sub(r"\s*\{#[-\w가-힣一-龥ぁ-んァ-ン]+\}\s*$", "", title).strip()

                level = len(hashes)
                slug = make_slug(title, used)

                toc_items.append({
                    "level": level,
                    "title": title,
                    "id": slug
                })

                # attr_list 확장으로 heading id 부여
                new_lines.append(f"{hashes} {title} {{#{slug}}}")
                continue

        new_lines.append(line)

    toc_html = build_toc_html(toc_items)
    return "\n".join(new_lines), toc_html


def build_toc_html(toc_items):
    if not toc_items:
        return ""

    html_lines = [
        '<nav class="sidebar">',
        '  <div class="sidebar-title">목차</div>',
        '  <ul class="toc-list">'
    ]

    for item in toc_items:
        level = item["level"]
        title = html.escape(item["title"])
        section_id = html.escape(item["id"])

        html_lines.append(
            f'    <li class="toc-item toc-level-{level}">'
            f'<a href="#{section_id}">{title}</a></li>'
        )

    html_lines.extend([
        '  </ul>',
        '</nav>'
    ])

    return "\n".join(html_lines)


# 제목 id 추가 + TOC 생성
text_with_ids, toc_html = add_heading_ids_and_build_toc(text)

# 마크다운 → HTML 변환
html_body = markdown.markdown(
    text_with_ids,
    extensions=[
        "extra",
        "fenced_code",
        "tables",
        "sane_lists",
        "attr_list",
        "md_in_html",
    ]
)


# UNC 경로(`\\192.168...`)를 링크로 치환
def replace_unc_with_link(html_text: str) -> str:
    pattern = r"<code>(\\\\[^<]+)</code>"

    def repl(match):
        unc_path = match.group(1)
        href = "file:" + unc_path.replace("\\", "/")
        return f'<a href="{href}" class="unc-link">{unc_path}</a>'

    return re.sub(pattern, repl, html_text)


html_body = replace_unc_with_link(html_body)

html_template = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <title>조건식 백테스트</title>
  <style>
    * {{
      box-sizing: border-box;
    }}

    html {{
      scroll-behavior: smooth;
    }}

    body {{
      margin: 0;
      background: #ffffff;
      color: #24292f;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", sans-serif;
      line-height: 1.6;
    }}

    .layout {{
      display: flex;
      min-height: 100vh;
    }}

    .sidebar {{
      position: fixed;
      top: 0;
      left: 0;
      width: 280px;
      height: 100vh;
      padding: 24px 18px;
      overflow-y: auto;
      border-right: 1px solid #d0d7de;
      background: #f6f8fa;
    }}

    .sidebar-title {{
      margin-bottom: 14px;
      font-size: 18px;
      font-weight: 700;
    }}

    .toc-list {{
      list-style: none;
      margin: 0;
      padding: 0;
    }}

    .toc-item {{
      margin: 2px 0;
    }}

    .toc-item a {{
      display: block;
      padding: 5px 8px;
      color: #57606a;
      text-decoration: none;
      border-radius: 6px;
      font-size: 14px;
      line-height: 1.35;
      word-break: keep-all;
    }}

    .toc-item a:hover {{
      background: #eaeef2;
      color: #0969da;
      text-decoration: none;
    }}

    .toc-level-1 a {{
      margin-top: 8px;
      font-weight: 700;
      color: #24292f;
    }}

    .toc-level-2 a {{
      padding-left: 20px;
      font-size: 13px;
    }}

    .toc-level-3 a {{
      padding-left: 36px;
      font-size: 12px;
      color: #6e7781;
    }}

    .content {{
      width: 100%;
      margin-left: 280px;
      padding: 40px 28px;
    }}

    .container {{
      max-width: 960px;
      width: 100%;
      margin: 0 auto;
    }}

    h1, h2, h3, h4 {{
      margin-top: 28px;
      margin-bottom: 12px;
      font-weight: 700;
      line-height: 1.25;
      scroll-margin-top: 24px;
    }}

    h1 {{
      padding-bottom: 10px;
      border-bottom: 1px solid #d0d7de;
      font-size: 28px;
    }}

    h2 {{
      padding-bottom: 8px;
      border-bottom: 1px solid #d8dee4;
      font-size: 22px;
    }}

    h3 {{
      font-size: 18px;
    }}

    p {{
      margin: 10px 0;
    }}

    a {{
      color: #0969da;
      text-decoration: none;
    }}

    a:hover {{
      text-decoration: underline;
    }}

    .unc-link {{
      font-family: Consolas, Monaco, "Courier New", monospace;
      word-break: break-all;
    }}

    details {{
      margin: 16px 0;
      padding: 12px 16px;
      border: 1px solid #d0d7de;
      border-radius: 8px;
      background: #ffffff;
    }}

    details[open] {{
      background: #fdfdfd;
    }}

    summary {{
      cursor: pointer;
      font-weight: 600;
      font-size: 16px;
      padding: 4px 0;
      user-select: none;
    }}

    details > *:not(summary) {{
      margin-top: 12px;
    }}

    pre {{
      margin: 12px 0;
      padding: 16px;
      overflow-x: auto;
      background: #f6f8fa;
      border: 1px solid #d0d7de;
      border-radius: 8px;
    }}

    pre code {{
      display: block;
      padding: 0;
      background: transparent;
      border-radius: 0;
      color: #24292f;
      font-family: Consolas, Monaco, "Courier New", monospace;
      font-size: 14px;
      line-height: 1.5;
      white-space: pre;
    }}

    code {{
      padding: 2px 5px;
      background: #f6f8fa;
      border-radius: 4px;
      font-family: Consolas, Monaco, "Courier New", monospace;
      font-size: 85%;
    }}

    table {{
      width: 100%;
      margin: 16px 0;
      border-collapse: collapse;
    }}

    th, td {{
      padding: 8px 12px;
      border: 1px solid #d0d7de;
    }}

    th {{
      background: #f6f8fa;
      font-weight: 600;
    }}

    blockquote {{
      margin: 16px 0;
      padding: 0 16px;
      color: #57606a;
      border-left: 4px solid #d0d7de;
    }}

    ul, ol {{
      padding-left: 28px;
    }}

    img {{
      max-width: 100%;
      height: auto;
      border-radius: 6px;
    }}

    hr {{
      height: 1px;
      border: 0;
      background: #d0d7de;
      margin: 24px 0;
    }}

    @media (max-width: 900px) {{
      .sidebar {{
        position: static;
        width: 100%;
        height: auto;
        max-height: 300px;
        border-right: 0;
        border-bottom: 1px solid #d0d7de;
      }}

      .layout {{
        display: block;
      }}

      .content {{
        margin-left: 0;
        padding: 24px 16px;
      }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    {toc_html}

    <main class="content">
      <div class="container">
        {html_body}
      </div>
    </main>
  </div>
</body>
</html>
"""

with open(output_file, "w", encoding="utf-8") as f:
    f.write(html_template)

print(f"변환 완료: {output_file}")