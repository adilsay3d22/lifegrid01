"""Build LifeGrid-User-Manual.pdf from manual.html + img/ (run capture.py first).

Two passes: render once to find which page each heading lands on, then fill the contents page and render again.
The cover is rendered separately so it has no page footer, then merged in front.
"""

import re
from html import unescape
from io import BytesIO
from pathlib import Path

from playwright.sync_api import sync_playwright
from pypdf import PdfReader, PdfWriter

HERE = Path(__file__).parent
OUT = HERE.parent / "LifeGrid-User-Manual.pdf"
FOOTER = ('<div style="width:100%;font:8px Geist,Segoe UI,sans-serif;color:#71717a;padding:0 17mm;display:flex;justify-content:space-between">'
          '<span>LifeGrid User Manual · v1.0</span><span class="pageNumber"></span></div>')


def parts(src: str) -> tuple[str, str, str]:
    head = src[: src.index("<body>") + len("<body>")]
    cover = re.search(r'<section class="cover">.*?</section>', src, re.S).group(0)  # type: ignore[union-attr]
    body = src[src.index(cover) + len(cover): src.index("</body>")]
    return head, cover, body


def entries(body: str) -> list[tuple[str, str, int]]:
    """(id, text, level) for every chapter title and section heading after the contents page."""
    out = []
    for m in re.finditer(r'<section class="chapter" id="([^"]+)">\s*(?:<div class="num">[^<]*</div>\s*)?<h1>(.*?)</h1>|<h2 id="([^"]+)">(.*?)</h2>', body, re.S):
        if m.group(1) and m.group(1) != "contents":
            out.append((m.group(1), unescape(re.sub("<.*?>", "", m.group(2))), 1))
        elif m.group(3):
            out.append((m.group(3), unescape(re.sub("<.*?>", "", m.group(4))), 2))
    return out


def toc(items: list[tuple[str, str, int]], pages: dict[str, int]) -> str:
    rows = []
    for i, (hid, text, lvl) in enumerate(items):
        chapter_no = sum(1 for _, _, l in items[: i + 1] if l == 1)
        label = f"{chapter_no}&nbsp;&nbsp;{text}" if lvl == 1 else text
        rows.append(f'<li class="{"sub" if lvl == 2 else ""}"><a class="t" href="#{hid}">{label}</a><span class="pg">{pages.get(hid, "")}</span></li>')
    return "\n    ".join(rows)


def render(page, html: str, name: str, footer: bool) -> bytes:  # type: ignore[no-untyped-def]
    f = HERE / name
    f.write_text(html, encoding="utf-8")
    page.goto(f.resolve().as_uri())
    page.wait_for_load_state("networkidle")
    page.evaluate("document.fonts.ready")
    pdf = page.pdf(prefer_css_page_size=True, print_background=True, display_header_footer=footer,
                   header_template="<span></span>", footer_template=FOOTER if footer else "<span></span>")
    f.unlink()
    return pdf


def find_pages(pdf: bytes, items: list[tuple[str, str, int]]) -> dict[str, int]:
    texts = [p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages]
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()  # noqa: E731
    lines = [[norm(line) for line in t.splitlines()] for t in texts]
    pages, start = {}, 1  # page 0 is the contents page
    for hid, text, _ in items:
        want = norm(text)
        for i in range(start, len(lines)):
            if want in lines[i]:
                pages[hid], start = i + 1, i
                break
    return pages


def main() -> None:
    src = (HERE / "manual.html").read_text(encoding="utf-8")
    head, cover, body = parts(src)
    items = entries(body)
    body_head = head.replace("@page :first { margin: 0; }", "")
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge", headless=True)
        page = b.new_page()
        first = render(page, body_head + body.replace("{{TOC}}", toc(items, {})) + "</body></html>", "_body.html", True)
        pages = find_pages(first, items)
        missing = [t for h, t, _ in items if h not in pages]
        final = render(page, body_head + body.replace("{{TOC}}", toc(items, pages)) + "</body></html>", "_body.html", True)
        cover_pdf = render(page, head + cover + "</body></html>", "_cover.html", False)
        b.close()
    w = PdfWriter()
    for part in (cover_pdf, final):
        for p in PdfReader(BytesIO(part)).pages:
            w.add_page(p)
    w.add_metadata({"/Title": "LifeGrid User Manual", "/Author": "LifeGrid", "/Subject": "User manual, version 1.0"})
    with OUT.open("wb") as f:
        w.write(f)
    print(f"wrote {OUT} ({len(w.pages)} pages)" + (f"; headings not located: {missing}" if missing else ""))


if __name__ == "__main__":
    main()
