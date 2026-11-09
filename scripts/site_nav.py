#!/usr/bin/env python3
"""One grouped menu for every page: 5 dropdowns instead of 18 links in a row.

Rewrites the <nav> inside each page's <header>, marks the current page and its group, and links
site-nav.css / site-nav.js. Safe to re-run: it always writes the same menu from GROUPS.

Run: python scripts/site_nav.py
"""
import html
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"

GROUPS = [
    ("Nifty 50", [
        ("index.html", "Best setup", "the homepage: buy / sell chart"),
        ("crore.html", "₹1 crore test", "every combination, real lots"),
        ("intraday.html", "Intraday 15-min", "EMA 9 or lower, ₹1 crore, 1 year"),
        ("nifty.html", "Nifty 50 chart", "EMA lab, day vs night"),
        ("orderflow.html", "Order Flow", "futures + option OI"),
        ("quantmath.html", "Bot Maths", "48 formulas"),
        ("nifty-chain.html", "Nifty chain", "option chain"),
        ("options.html", "Options desk", "IV, OI walls"),
    ]),
    ("Stocks", [
        ("confluence.html", "Top Picks", "7 systems agree"),
        ("setups.html", "Daily setups", "every stock in one category"),
        ("hhhl.html", "HH/HL scanner", "Nifty 200 + F&O, EMA 105"),
        ("dma.html", "DMA", "200-day average"),
        ("vcp.html", "VCP", "Minervini setups"),
        ("fno-play.html", "₹1 Play", "F&O futures"),
        ("kronos.html", "Kronos", "100-path forecast"),
    ]),
    ("Invest", [
        ("fund.html", "Our Fund", "best 30 of the Nifty 100"),
        ("dividends.html", "Dividends", "10-year records"),
        ("retirement.html", "Opus 2031", "the ₹5 crore plan"),
    ]),
    ("Market", [
        ("market-brief.html", "Jev brief", "US + India context"),
        ("daily-market.html", "Daily market", "deals and breadth"),
        ("global-markets.html", "Global markets", "FX, gold, indices"),
    ]),
    ("Research", [
        ("indicator-lab.html", "Indicator lab", "top 100 rules"),
        ("strategy-lab.html", "Strategy lab", "backtests"),
        ("social-research.html", "Social research", "what traders say"),
    ]),
]

CSS_TAG = '<link rel="stylesheet" href="site-nav.css?v=1">'
JS_TAG = '<script src="site-nav.js?v=1" defer></script>'


def menu(page):
    out = ['<nav class="sn" aria-label="Main menu">']
    for name, links in GROUPS:
        here = any(href == page for href, _, _ in links)
        out.append(f'<details class="sn-g{" sn-on" if here else ""}"><summary>{html.escape(name)}</summary><div class="sn-m">')
        for href, label, sub in links:
            cur = ' aria-current="page"' if href == page else ""
            out.append(f'<a href="{href}"{cur}><b>{html.escape(label)}</b><small>{html.escape(sub)}</small></a>')
        out.append("</div></details>")
    out.append("</nav>")
    return "".join(out)


def apply(path):
    text = path.read_text(encoding="utf-8")
    m = re.search(r"(<header[^>]*>)(.*?)(</header>)", text, re.S)
    if not m:
        return False
    inner = re.sub(r"<nav\b[^>]*>.*?</nav>", lambda _: menu(path.name), m.group(2), count=1, flags=re.S)
    if inner == m.group(2) and "<nav" not in m.group(2):
        inner = m.group(2) + menu(path.name)
    new = text[:m.start(2)] + inner + text[m.end(2):]
    for tag in (CSS_TAG, JS_TAG):
        stem = re.search(r'(?:href|src)="([^"?]+)', tag).group(1)
        new = re.sub(r'\s*<(link|script)[^>]*' + re.escape(stem) + r'[^>]*>(</script>)?', "", new)
        new = new.replace("</head>", tag + "\n</head>", 1)
    if new != text:
        path.write_text(new, encoding="utf-8")
    return True


def main():
    done, skipped = [], []
    for p in sorted(DOCS.glob("*.html")):
        (done if apply(p) else skipped).append(p.name)
    missing = [h for _, links in GROUPS for h, _, _ in links if not (DOCS / h).exists()]
    print(f"menu on {len(done)} pages; no <header>: {skipped}; links to missing pages: {missing}")
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
