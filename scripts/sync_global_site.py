"""Publish only the separate commodity/forex UI assets to GitHub Pages."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for name in ['global-markets.html', 'global-markets.css', 'global-markets.js']:
    text = (ROOT/'public'/name).read_text(encoding='utf-8')
    if name.endswith('.html'):
        text = text.replace('data-source="data/"', 'data-source=""')
    (ROOT/'docs'/name).write_text(text, encoding='utf-8')
