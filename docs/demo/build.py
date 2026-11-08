"""Build docs/LifeGrid-Demo-Script.pdf from script.html (needs playwright and Microsoft Edge, like docs/manual/build.py)."""

from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE.parent / "LifeGrid-Demo-Script.pdf"
FOOTER = ('<div style="width:100%;font:8.5px Arial,sans-serif;color:#71717a;padding:0 15mm;display:flex;justify-content:space-between">'
          '<span>LifeGrid live demo · lifegrid01.vercel.app · Staff password: synthetic-demo-pass · Reset: step 0.1</span>'
          '<span>Page <span class="pageNumber"></span></span></div>')

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    page = b.new_page()
    page.goto((HERE / "script.html").resolve().as_uri())
    page.pdf(path=str(OUT), prefer_css_page_size=True, print_background=True, display_header_footer=True,
             header_template="<span></span>", footer_template=FOOTER)
    b.close()
print(f"wrote {OUT}")
