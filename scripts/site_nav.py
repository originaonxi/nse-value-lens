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
    ("★ Best", [
        ("best15.html", "Trade Nifty · EMA 21 / 105 · 15-min", "always in a trade; made money every year since Jul 2023"),
        ("fund.html", "Invest · Our Fund", "best 30 of the Nifty 100, rebalanced monthly"),
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
        ("dividends.html", "Dividends", "10-year records"),
        ("retirement.html", "Opus 2031", "the ₹5 crore plan"),
    ]),
    ("Market", [
        ("index.html", "Home · Nifty 2-hour chart", "the homepage"),
        ("orderflow.html", "Order Flow", "futures + option OI"),
        ("nifty-chain.html", "Nifty chain", "option chain"),
        ("options.html", "Options desk", "IV, OI walls"),
        ("market-brief.html", "Jev brief", "US + India context"),
        ("daily-market.html", "Daily market", "deals and breadth"),
        ("global-markets.html", "Global markets", "FX, gold, indices"),
    ]),
    ("Research", [
        ("crore.html", "₹1 crore test · 2-hour EMA 105", "did not hold up: +44% was picked after the fact"),
        ("ema921.html", "EMA 9/21 · 1-hour", "did not hold up: made less than holding Nifty"),
        ("intraday.html", "Intraday 15-min · EMA 9 or lower", "did not hold up: lost or made little"),
        ("cross.html", "EMA cross lab · 5/15/30-min", "did not hold up: lost or made little"),
        ("nifty.html", "Nifty 50 · one EMA lab", "did not hold up on short candles"),
        ("stocklab.html", "Formula lab · top 30 stocks", "did not hold up: holding the stocks won"),
        ("ema200.html", "EMA 200 desk · double fib", "did not hold up: lost on the second 100 sessions"),
        ("quantmath.html", "Bot Maths", "48 formulas, reference only"),
        ("indicator-lab.html", "Indicator lab", "top 100 rules"),
        ("strategy-lab.html", "Strategy lab", "backtests"),
        ("social-research.html", "Social research", "what traders say"),
    ]),
]

# Pages whose own setup did not hold up on years it had not seen: a note under the menu points to the two that did.
NOTE_WHY = {
    "index.html": "The 2-hour EMA 105 chart on this page is research: picked after seeing the data, it made far less on years it had not seen.",
    "crore.html": "The +44% here was picked after seeing the data; on years it had not seen it made about +2% to +7%.",
    "ema921.html": "EMA 9/21 on 1-hour candles made less than simply holding Nifty.",
    "intraday.html": "EMA 9 or lower on 15-minute candles lost money or made very little after costs.",
    "cross.html": "Fast intraday EMA crosses lost money or made very little after costs.",
    "nifty.html": "Close-above / close-below one EMA lost money on 10- and 15-minute candles in the 2,055-rule test.",
    "stocklab.html": "Every short-selling formula lost, and simply holding the 30 stocks beat every formula.",
    "ema200.html": "The rule picked on the first 100 sessions lost money on the next 100.",
    "quantmath.html": "This page is reference maths, not a trading setup.",
}
NOTE_RE = re.compile(r'\s*<p class="sn-note"[^>]*>.*?</p>', re.S)


def note(page):
    lead = "Start here." if page == "index.html" else "Research page."
    return ('<p class="sn-note" role="note"><b>' + lead + '</b> The two setups that held up on years they had not seen: '
            '<a href="best15.html">Trade Nifty · EMA 21 / 105 on 15-minute candles</a> and <a href="fund.html">Invest · Our Fund</a>. '
            + html.escape(NOTE_WHY[page]) + '</p>')

CSS_TAG = '<link rel="stylesheet" href="site-nav.css?v=2">'
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
    new = NOTE_RE.sub("", new)
    if path.name in NOTE_WHY:
        new = new.replace("</header>", "</header>\n" + note(path.name), 1)
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
