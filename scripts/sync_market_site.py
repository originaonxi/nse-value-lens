"""Keep static Pages assets identical to the Express site's canonical public files."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for name in ("market-brief.html", "market-brief.css", "market-brief.js", "market-context.js", "index.html", "hhhl.html", "hhhl.js", "vcp.html", "vcp.js"):
    text = (ROOT / "public" / name).read_text(encoding="utf-8")
    if name.endswith(".html"):
        text = text.replace('data-source="data/"', 'data-source=""')
        text = text.replace('href="data/', 'href="')
    (ROOT / "docs" / name).write_text(text, encoding="utf-8")
(ROOT / "public" / "MARKET_BRIEF.md").write_text((ROOT / "docs" / "MARKET_BRIEF.md").read_text(encoding="utf-8"), encoding="utf-8")
