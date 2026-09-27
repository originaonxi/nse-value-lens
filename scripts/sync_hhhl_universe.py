"""Mirror only the stock-universe UI assets to GitHub Pages."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for name in ('hhhl.html', 'hhhl.js', 'hhhl-universe.js', 'hhhl-universe.css'):
    text = (root/'public'/name).read_text(encoding='utf-8')
    if name.endswith('.html'):
        text = text.replace('data-source="data/"', 'data-source=""').replace('href="data/', 'href="')
    (root/'docs'/name).write_text(text, encoding='utf-8')
