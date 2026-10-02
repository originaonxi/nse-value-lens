"""Mirror daily-market assets and additive stock-filter changes to Pages."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
(ROOT / 'public/DAILY_MARKET.md').write_text((ROOT / 'docs/DAILY_MARKET.md').read_text(encoding='utf-8'), encoding='utf-8')
for name in ('daily-market.html', 'daily-market.js', 'daily-market.css', 'daily-deals.js', 'daily-deals.css', 'hhhl.html', 'hhhl.js'):
    text = (ROOT / 'public' / name).read_text(encoding='utf-8')
    if name.endswith('.html'):
        text = text.replace('data-source="data/"', 'data-source=""').replace('href="data/', 'href="')
    (ROOT / 'docs' / name).write_text(text, encoding='utf-8')

# A single navigation link; keep the established homepage layout and stock charts.
for folder in ('public', 'docs'):
    for name in ('index.html', 'hhhl.html', 'vcp.html', 'global-markets.html'):
        path = ROOT / folder / name
        text = path.read_text(encoding='utf-8')
        if 'href="daily-market.html"' not in text.split('</nav>')[0]:
            text = text.replace('</nav>', '<a href="daily-market.html">Daily market &amp; deals</a></nav>', 1)
            path.write_text(text, encoding='utf-8')
