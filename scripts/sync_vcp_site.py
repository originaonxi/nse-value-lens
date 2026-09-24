"""Keep the GitHub Pages VCP assets and dated report in sync with public/."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
for name in ('vcp.html', 'vcp.css', 'vcp.js'):
    text = (ROOT/'public'/name).read_text(encoding='utf-8')
    if name.endswith('.html'):
        text = text.replace('data-source="data/"', 'data-source=""').replace('href="data/vcp_scan.json"', 'href="vcp_scan.json"')
    (ROOT/'docs'/name).write_text(text, encoding='utf-8')

# Keep the report's relative downloads and chart links working on both hosts.
for directory in ('public', 'docs'):
    dest = ROOT/directory/'vcp-research'
    dest.mkdir(exist_ok=True)
    for source in (ROOT/'research/vcp').iterdir():
        if source.is_file():
            shutil.copyfile(source, dest/source.name)
    for name in ('index.html', 'hhhl.html'):
        path = ROOT/directory/name
        text = path.read_text(encoding='utf-8')
        if 'href="vcp.html"' not in text:
            if name == 'index.html':
                text = text.replace('<main>', '<main>\n<p class="muted"><a href="vcp.html"><strong>Minervini VCP scanner: all Nifty 200 stocks, weekly charts and backtest evidence</strong></a></p>', 1)
            else:
                text = text.replace('<nav>', '<nav><a href="vcp.html">VCP scanner</a>', 1)
            path.write_text(text, encoding='utf-8')
print('VCP assets, navigation and dated research synchronized for both websites.')
