# Nifty 50 research record

Generated 2026-11-10 23:43 IST from the live engines (`nifty_ema.py`, `nifty_combo.py`, `nifty_daynight.py`). Re-run `python scripts/nifty_research_md.py` to refresh. Paper research, not advice.

**Data:** NIFTY 50 index (^NSEI, Yahoo Finance). 2-hour candles 2024-03-19 → 2026-11-09 (2,590 candles). Daily candles 2016 → 2026-11-09. Hourly 2023 → today, 5-minute last ~60 sessions.

**Costs:** every trade pays 0.035% of price (≈ 9 Nifty points at 25,000).

**Honesty split:** rules are tested on 2024-03-19 → 2025-12-19 (the *tested part*) and judged on 2025-12-19 → 2026-11-09 (the *unseen part*, never used to pick). A rule is *robust* only if it makes money in both.

## The maths used everywhere

| Term | Formula |
|---|---|
| Points of a trade | (exit close − entry close) × direction − 0.035% × entry price |
| Win rate | winning trades ÷ all trades |
| Profit factor (PF) | sum of winning points ÷ sum of losing points (PF > 1 = makes money) |
| Net | sum of all trade points after costs |
| Worst drawdown (DD) | biggest fall of the running points total from its previous peak |
| Robust score | the WEAKER of the two parts: 35% PF (capped 5) + 35% win rate + 30% net ÷ drawdown (capped 6) |

## Top 3 setups for Nifty 50

All three: **2-hour candles, buy only.** BUY when a 2-hour candle closes above EMA 105 and the listed indicators agree. TOP = sell when RSI(14) reaches the level and then falls 5 points; after a TOP, buy again only when price is back within 1 ATR of EMA 105. EXIT = a 2-hour close below EMA 105.

| # | Setup | Why | Part | Trades | Win % | PF | Net pts | Worst DD |
|---|---|---|---|---|---|---|---|---|
| **1** | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 68 | Best overall (the page's winner) | whole | 32 | 68.8% | 4.03 | +6,020 | 1,088 |
|  |  |  | tested | 23 | 69.6% | 3.40 | +4,242 | 1,088 |
|  |  |  | **unseen** | 9 | 66.7% | 9.13 | +1,778 | 174 |
| **2** | EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 70 | Best on the unseen part (70% win) | whole | 31 | 67.7% | 3.24 | +5,075 | 1,088 |
|  |  |  | tested | 21 | 66.7% | 3.00 | +3,394 | 1,088 |
|  |  |  | **unseen** | 10 | 70.0% | 3.92 | +1,681 | 245 |
| **3** | EMA 105 + ADX>20 + Daily>EMA50 · TOP exit RSI 70 | Fewest conditions, smallest drawdown | whole | 47 | 46.8% | 3.13 | +6,355 | 564 |
|  |  |  | tested | 33 | 45.5% | 3.25 | +4,586 | 564 |
|  |  |  | **unseen** | 14 | 50.0% | 2.88 | +1,769 | 331 |
| ref | EMA 105 alone · exit on close below | the starting point | whole | 56 | 25.0% | 1.72 | +3,284 | 1,785 |

**Worked maths for setup 1:** 32 trades, 22 winners → win rate 22 ÷ 32 = **68.8%**. Winners made 8,007.9 points, losers lost 1,988.3 → PF 8,007.9 ÷ 1,988.3 = **4.03**. Net 8,007.9 − 1,988.3 = **+6,019.5 points** ≈ ₹451,463 per lot of 75.

## How the win rate climbs toward 70% (one step at a time)

Each row adds one thing to the row above. Whole period, buy only, after costs.

| Step | Rule | Trades | Win % | PF | Net pts | Worst DD | Unseen win % | Unseen PF |
|---|---|---|---|---|---|---|---|---|
| 0 | EMA 105 · exit on close below | 56 | 25.0% | 1.72 | +3,284 | 1,785 | 18.2% | 1.21 |
| 1 | EMA 105 + ADX>20 · exit on close below | 48 | 25.0% | 1.71 | +3,138 | 1,558 | 23.5% | 1.29 |
| 2 | EMA 105 + ADX>20 + Daily>EMA50 · exit on close below | 34 | 23.5% | 1.49 | +1,946 | 1,566 | 18.2% | 0.90 |
| 3 | EMA 105 + ADX>20 + Daily>EMA50 + Supertrend · exit on close below | 26 | 26.9% | 1.37 | +1,494 | 1,458 | 12.5% | 1.01 |
| 4 | EMA 105 + ADX>20 + Daily>EMA50 + Supertrend · TOP exit RSI 70 | 31 | 67.7% | 3.56 | +5,678 | 1,088 | 77.8% | 5.38 |
| 5 | EMA 105 + ADX>20 + Daily>EMA50 + Supertrend · TOP exit RSI 68 | 32 | 68.8% | 4.03 | +6,020 | 1,088 | 66.7% | 9.13 |

What moves the number: **ADX > 20** removes trades in sideways markets (most of EMA 105's small losses). **Daily close above daily EMA 50** keeps only buys in a rising bigger trend. **Supertrend** removes late entries. The **RSI TOP exit** books the gain near the top instead of giving it back on the way down to EMA 105 - this step lifts the win rate the most.

**Best win rate by number of confirmations** (robust rules only, 20+ trades):

| Confirmations | Robust rules | Best win % | Rule |
|---|---|---|---|
| 0 | 37 | 42.9% | EMA 105 · target 2 ATR |
| 1 | 253 | 49.0% | EMA 105 + DI+>DI- · target 2 ATR |
| 2 | 884 | 60.5% | EMA 105 + Daily>EMA50 + DI+>DI- · TOP exit RSI 68 |
| 3 | 2,019 | 68.8% | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 68 |

## Where the win rate goes above 70%

- Rules with **70%+ over the whole period** and at least 10 trades: **0** of 8,056.
- Rules with **70%+ on the unseen part** (8+ trades) that also made money on the tested part: **3**:

| Rule | Tested part | Unseen part | Whole period |
|---|---|---|---|
| EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 70 | 22 tr · 63.6% · PF 3.15 · +3,921 | **9 tr · 77.8% · PF 5.38 · +1,757** | 31 tr · 67.7% · PF 3.56 · +5,678 |
| EMA 105 + ADX>20 + Supertrend + 2 closes · TOP exit RSI 70 | 27 tr · 48.1% · PF 2.48 · +3,755 | **10 tr · 70.0% · PF 4.27 · +2,100** | 37 tr · 54.1% · PF 2.84 · +5,856 |
| EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 70 | 21 tr · 66.7% · PF 3.00 · +3,394 | **10 tr · 70.0% · PF 3.92 · +1,681** | 31 tr · 67.7% · PF 3.24 · +5,075 |

- Rules that showed **70%+ on the tested part** (12+ trades): **16**. What they did next on the unseen part:

| Rule | Tested part | Unseen part |
|---|---|---|
| EMA 105 + RSI>50 + Daily>EMA50 + 0.5 ATR buffer · TOP exit 3 ATR | 25 tr · 76.0% · PF 4.04 · +2,613 | 16 tr · 43.8% · PF 0.46 · -973 |
| EMA 105 + RSI>50 + Daily>EMA50 + 2 closes · TOP exit 3 ATR | 25 tr · 76.0% · PF 3.87 · +2,352 | 16 tr · 43.8% · PF 0.50 · -836 |
| EMA 105 + RSI>50 + ADX>25 + Daily>EMA50 · TOP exit 4 ATR | 16 tr · 75.0% · PF 6.08 · +2,560 | 8 tr · 50.0% · PF 0.40 · -452 |
| EMA 105 + RSI>50 + Daily>EMA50 + DI+>DI- · TOP exit 3 ATR | 23 tr · 73.9% · PF 3.49 · +1,832 | 14 tr · 50.0% · PF 0.63 · -499 |
| EMA 105 + Daily>EMA50 + 0.5 ATR buffer + DI+>DI- · TOP exit 3 ATR | 23 tr · 73.9% · PF 2.99 · +1,828 | 14 tr · 50.0% · PF 0.58 · -588 |
| EMA 105 + RSI>50 + Daily>EMA50 + EMA slope · TOP exit 3 ATR | 26 tr · 73.1% · PF 3.61 · +2,395 | 16 tr · 43.8% · PF 0.46 · -877 |
| EMA 105 + MACD hist + Daily>EMA50 + DI+>DI- · TOP exit 3 ATR | 22 tr · 72.7% · PF 3.86 · +1,776 | 13 tr · 53.8% · PF 0.47 · -694 |
| EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 68 | 22 tr · 72.7% · PF 3.26 · +3,714 | 10 tr · 60.0% · PF 5.33 · +1,703 |
| EMA 105 + RSI>50 + ADX>25 + Daily>EMA50 · target 2 ATR | 18 tr · 72.2% · PF 1.90 · +1,833 | 7 tr · 42.9% · PF 0.55 · -681 |
| EMA 105 + ADX>25 + Supertrend + Daily>EMA50 · target 2 ATR | 18 tr · 72.2% · PF 1.90 · +1,846 | 7 tr · 42.9% · PF 0.55 · -681 |
| EMA 105 + Daily>EMA50 + DI+>DI- · TOP exit 3 ATR | 24 tr · 70.8% · PF 3.24 · +1,898 | 14 tr · 50.0% · PF 0.63 · -499 |
| EMA 105 + Daily>EMA50 + EMA slope + DI+>DI- · TOP exit 3 ATR | 24 tr · 70.8% · PF 2.59 · +1,586 | 14 tr · 50.0% · PF 0.54 · -614 |
| EMA 105 + Daily>EMA50 + 2 closes + DI+>DI- · TOP exit 3 ATR | 24 tr · 70.8% · PF 2.65 · +1,601 | 14 tr · 50.0% · PF 0.60 · -572 |
| EMA 105 + ADX>25 + Daily>EMA50 + DI+>DI- · target 2 ATR | 17 tr · 70.6% · PF 1.32 · +770 | 7 tr · 42.9% · PF 0.55 · -681 |
| EMA 105 + ADX>25 + Daily>EMA50 + DI+>DI- · Bollinger top | 17 tr · 70.6% · PF 2.49 · +3,034 | 7 tr · 28.6% · PF 1.37 · +515 |

Of those 16, **0** stayed at 70%+ on unseen data and **14** lost money. So 70%+ is reachable on a stretch of data, and the setups above did hit 70-78% on the unseen part, but no rule held 70%+ over the whole period with enough trades. ~65-69% is the honest level.

## 30 combinations side by side

Same data, same costs. Tested part / unseen part / whole period. Long only unless marked.

| # | Rule | Tested: trades · win · PF · net | Unseen: trades · win · PF · net | Whole: trades | Win % | PF | Net pts | DD | Both parts profit |
|---|---|---|---|---|---|---|---|---|---|
| 1 | EMA 105 · exit on close below | 34 · 29.4% · 2.10 · +2,871 | 22 · 18.2% · 1.21 · +413 | 56 | 25.0% | 1.72 | +3,284 | 1,785 | ✓ |
| 2 | EMA 105 · exit on close below · buy+sell | 69 · 23.2% · 1.24 · +1,588 | 43 · 20.9% · 1.47 · +1,744 | 112 | 22.3% | 1.32 | +3,332 | 1,894 | ✓ |
| 3 | EMA 105 · TOP exit RSI 70 | 44 · 34.1% · 2.76 · +5,489 | 26 · 30.8% · 2.11 · +2,339 | 70 | 32.9% | 2.50 | +7,828 | 1,124 | ✓ |
| 4 | EMA 105 · target 2 ATR | 48 · 41.7% · 2.28 · +3,530 | 29 · 44.8% · 2.30 · +2,178 | 77 | 42.9% | 2.29 | +5,708 | 861 | ✓ |
| 5 | EMA 105 · TOP exit 4 ATR | 43 · 34.9% · 2.34 · +3,632 | 26 · 30.8% · 1.29 · +608 | 69 | 33.3% | 1.88 | +4,240 | 1,252 | ✓ |
| 6 | EMA 105 · trail 3 ATR | 44 · 31.8% · 2.36 · +4,356 | 27 · 33.3% · 1.56 · +1,188 | 71 | 32.4% | 2.05 | +5,544 | 1,428 | ✓ |
| 7 | EMA 105 + RSI>50 · exit on close below | 30 · 33.3% · 1.83 · +2,339 | 19 · 10.5% · 0.98 · -45 | 49 | 24.5% | 1.44 | +2,294 | 2,244 | ✗ |
| 8 | EMA 105 + MACD hist · exit on close below | 33 · 30.3% · 1.46 · +1,546 | 18 · 11.1% · 0.85 · -399 | 51 | 23.5% | 1.19 | +1,147 | 2,597 | ✗ |
| 9 | EMA 105 + ADX>20 · exit on close below | 31 · 25.8% · 2.01 · +2,598 | 17 · 23.5% · 1.29 · +539 | 48 | 25.0% | 1.71 | +3,138 | 1,558 | ✓ |
| 10 | EMA 105 + ADX>25 · exit on close below | 24 · 33.3% · 2.21 · +2,700 | 10 · 30.0% · 0.77 · -509 | 34 | 32.4% | 1.50 | +2,191 | 1,910 | ✗ |
| 11 | EMA 105 + Supertrend · exit on close below | 28 · 35.7% · 1.63 · +1,887 | 16 · 12.5% · 0.90 · -267 | 44 | 27.3% | 1.29 | +1,620 | 2,509 | ✗ |
| 12 | EMA 105 + Daily>EMA50 · exit on close below | 26 · 30.8% · 1.83 · +2,128 | 14 · 14.3% · 0.69 · -639 | 40 | 25.0% | 1.32 | +1,489 | 2,141 | ✗ |
| 13 | EMA 105 + Daily>EMA200 · exit on close below | 32 · 28.1% · 1.54 · +1,778 | 11 · 18.2% · 0.40 · -1,053 | 43 | 25.6% | 1.14 | +725 | 1,821 | ✗ |
| 14 | EMA 105 + EMA slope · exit on close below | 29 · 34.5% · 1.92 · +2,368 | 18 · 11.1% · 1.01 · +20 | 47 | 25.5% | 1.52 | +2,388 | 2,153 | ✓ |
| 15 | EMA 105 + 2 closes · exit on close below | 29 · 34.5% · 1.95 · +2,511 | 20 · 15.0% · 1.03 · +74 | 49 | 26.5% | 1.52 | +2,585 | 2,170 | ✓ |
| 16 | EMA 105 + DI+>DI- · exit on close below | 26 · 38.5% · 1.83 · +2,018 | 18 · 11.1% · 0.97 · -65 | 44 | 27.3% | 1.40 | +1,953 | 2,263 | ✗ |
| 17 | EMA 105 + ADX>20 · TOP exit RSI 70 | 41 · 34.1% · 2.73 · +4,805 | 20 · 40.0% · 2.72 · +2,474 | 61 | 36.1% | 2.72 | +7,279 | 1,032 | ✓ |
| 18 | EMA 105 + ADX>20 + Daily>EMA50 · exit on close below | 23 · 26.1% · 1.90 · +2,112 | 11 · 18.2% · 0.90 · -166 | 34 | 23.5% | 1.49 | +1,946 | 1,566 | ✗ |
| 19 | EMA 105 + ADX>20 + Daily>EMA50 · TOP exit RSI 70 | 33 · 45.5% · 3.25 · +4,586 | 14 · 50.0% · 2.88 · +1,769 | 47 | 46.8% | 3.13 | +6,355 | 564 | ✓ |
| 20 | EMA 105 + ADX>20 + Supertrend · TOP exit RSI 70 | 29 · 44.8% · 2.59 · +3,957 | 11 · 63.6% · 5.33 · +2,707 | 40 | 50.0% | 3.14 | +6,664 | 1,088 | ✓ |
| 21 | EMA 105 + RSI>50 + ADX>20 · TOP exit RSI 70 | 30 · 43.3% · 2.88 · +4,598 | 14 · 50.0% · 3.68 · +2,654 | 44 | 45.5% | 3.11 | +7,251 | 1,088 | ✓ |
| 22 | EMA 105 + Daily>EMA50 + DI+>DI- · TOP exit RSI 68 | 25 · 64.0% · 2.92 · +3,992 | 13 · 53.8% · 2.06 · +1,198 | 38 | 60.5% | 2.62 | +5,190 | 1,088 | ✓ |
| 23 | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · exit on close below | 18 · 33.3% · 1.56 · +1,486 | 8 · 12.5% · 1.01 · +8 | 26 | 26.9% | 1.37 | +1,494 | 1,458 | ✓ |
| 24 | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 68 | 23 · 69.6% · 3.40 · +4,242 | 9 · 66.7% · 9.13 · +1,778 | 32 | 68.8% | 4.03 | +6,020 | 1,088 | ✓ |
| 25 | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 70 | 22 · 63.6% · 3.15 · +3,921 | 9 · 77.8% · 5.38 · +1,757 | 31 | 67.7% | 3.56 | +5,678 | 1,088 | ✓ |
| 26 | EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 70 | 21 · 66.7% · 3.00 · +3,394 | 10 · 70.0% · 3.92 · +1,681 | 31 | 67.7% | 3.24 | +5,075 | 1,088 | ✓ |
| 27 | EMA 105 + RSI>50 + ADX>20 + Daily>EMA50 · TOP exit RSI 68 | 23 · 69.6% · 3.45 · +4,025 | 11 · 54.5% · 4.11 · +1,587 | 34 | 64.7% | 3.61 | +5,612 | 1,088 | ✓ |
| 28 | EMA 105 + ADX>20 + Supertrend + EMA slope · TOP exit RSI 68 | 27 · 63.0% · 3.14 · +4,473 | 10 · 50.0% · 5.76 · +1,885 | 37 | 59.5% | 3.56 | +6,358 | 1,088 | ✓ |
| 29 | EMA 105 + RSI>50 + ADX>25 + Daily>EMA50 · TOP exit 4 ATR | 16 · 75.0% · 6.08 · +2,560 | 8 · 50.0% · 0.40 · -452 | 24 | 66.7% | 2.68 | +2,108 | 1,008 | ✗ |
| 30 | EMA 105 + MACD hist + Daily>EMA200 + EMA slope · TOP exit 3 ATR · buy+sell | 36 · 58.3% · 2.71 · +3,314 | 19 · 57.9% · 1.88 · +975 | 55 | 58.2% | 2.41 | +4,289 | 711 | ✓ |

## Sensitivity: is the winner a lucky setting?

EMA 105 + ADX>a + Supertrend + Daily>EMA50, TOP exit at RSI r. Whole-period win % (PF).

| ADX > | RSI 65 | RSI 68 | RSI 70 | RSI 72 | RSI 75 | RSI 80 |
|---|---|---|---|---|---|---|
| 15 | 48.8% (1.66) | 57.5% (2.22) | 53.8% (2.16) | 48.6% (1.80) | 37.1% (1.32) | 33.3% (1.66) |
| 18 | 50.0% (2.23) | 59.5% (3.02) | 58.3% (2.87) | 51.4% (2.14) | 39.4% (1.52) | 35.5% (1.94) |
| 20 | 54.5% (2.79) | 68.8% (4.03) | 67.7% (3.56) | 56.7% (2.36) | 42.9% (1.63) | 38.5% (2.12) |
| 22 | 53.1% (2.51) | 67.7% (3.67) | 63.3% (3.31) | 58.6% (2.19) | 44.4% (1.52) | 40.0% (1.97) |
| 25 | 46.4% (1.57) | 55.6% (2.20) | 50.0% (2.18) | 56.0% (2.03) | 43.5% (1.51) | 42.9% (1.96) |
| 30 | 45.5% (1.49) | 45.5% (1.44) | 47.6% (1.44) | 50.0% (1.31) | 44.4% (1.12) | 50.0% (1.91) |

The best area is ADX 18-22 with an RSI top at 68-70; results fade smoothly away from it rather than jumping, so the setting is not a single lucky point.

## Independent check: daily candles 2017-11-22 → 2023-11-22 (years the 2-hour test never saw)

| Rule | Trades | Win % | PF | Net pts | Worst DD |
|---|---|---|---|---|---|
| Daily EMA 26 alone (≈ 2-hour EMA 105) | 80 | 25.0% | 2.06 | +8,146 | 1,648 |
| + ADX>20 + Supertrend + trend gate, RSI-70 TOP exit | 42 | 45.2% | 1.83 | +3,626 | 1,298 |
| + ADX>20 + Supertrend + trend gate, exit on close below | 27 | 48.1% | 2.34 | +3,653 | 532 |

The same confirmations roughly double the win rate and cut the drawdown in a completely different period, but they do not reach 70% there.

## After a TOP: does Nifty go back toward EMA 105?

24 TOP signals. Within the next 10 two-hour candles: fell at least 1 ATR **66.7%**, reached EMA 105 **37.5%**, median move back **66.0%** of the gap.

## Sell side (close below EMA 105)

| Sell rule | Tested part | Unseen part | Whole period |
|---|---|---|---|
| Sell below EMA 105 | exit: cross | 35 · 17.1% · PF 0.68 · -1,282 | 21 · 23.8% · PF 1.77 · +1,331 | 56 · 19.6% · PF 1.01 · +49 |
| Sell below EMA 105 | exit: rsi 70 | 44 · 27.3% · PF 0.91 · -420 | 24 · 29.2% · PF 1.33 · +674 | 68 · 27.9% · PF 1.04 · +254 |
| Sell below EMA 105 | exit: tp 3 | 42 · 28.6% · PF 1.03 · +116 | 26 · 30.8% · PF 1.35 · +789 | 68 · 29.4% · PF 1.13 · +906 |
| Sell below EMA 105 + Supertrend + 0.5 ATR buffer + 2 closes | exit: cross | 18 · 22.2% · PF 0.75 · -695 | 12 · 25.0% · PF 2.05 · +1,347 | 30 · 23.3% · PF 1.16 · +652 |
| Sell below EMA 105 + Supertrend + 0.5 ATR buffer + 2 closes | exit: rsi 70 | 25 · 44.0% · PF 1.16 · +411 | 14 · 42.9% · PF 1.55 · +775 | 39 · 43.6% · PF 1.30 · +1,187 |
| Sell below EMA 105 + Supertrend + 0.5 ATR buffer + 2 closes | exit: tp 3 | 22 · 50.0% · PF 1.85 · +2,074 | 14 · 42.9% · PF 1.56 · +782 | 36 · 47.2% · PF 1.74 · +2,856 |
| Sell below EMA 105 + MACD hist + 0.5 ATR buffer + 2 closes | exit: cross | 19 · 21.1% · PF 0.62 · -1,225 | 13 · 23.1% · PF 2.15 · +1,426 | 32 · 21.9% · PF 1.04 · +201 |
| Sell below EMA 105 + MACD hist + 0.5 ATR buffer + 2 closes | exit: rsi 70 | 23 · 39.1% · PF 0.96 · -103 | 14 · 42.9% · PF 1.93 · +1,071 | 37 · 40.5% · PF 1.26 · +968 |
| Sell below EMA 105 + MACD hist + 0.5 ATR buffer + 2 closes | exit: tp 3 | 21 · 52.4% · PF 1.70 · +1,790 | 14 · 50.0% · PF 2.41 · +1,538 | 35 · 51.4% · PF 1.91 · +3,327 |
| Sell below EMA 105 + Daily>EMA200 + Supertrend | exit: cross | 5 · 40.0% · PF 0.77 · -267 | 14 · 21.4% · PF 0.95 · -92 | 19 · 26.3% · PF 0.89 · -358 |
| Sell below EMA 105 + Daily>EMA200 + Supertrend | exit: rsi 70 | 5 · 60.0% · PF 1.47 · +409 | 16 · 37.5% · PF 0.66 · -725 | 21 · 42.9% · PF 0.90 · -316 |
| Sell below EMA 105 + Daily>EMA200 + Supertrend | exit: tp 3 | 5 · 80.0% · PF 8.81 · +2,020 | 17 · 35.3% · PF 1.27 · +605 | 22 · 45.5% · PF 2.06 · +2,625 |
| Sell below EMA 105 + ADX>20 + Daily>EMA50 + Supertrend | exit: cross | 13 · 30.8% · PF 0.48 · -1,716 | 13 · 23.1% · PF 0.74 · -677 | 26 · 26.9% · PF 0.59 · -2,392 |
| Sell below EMA 105 + ADX>20 + Daily>EMA50 + Supertrend | exit: rsi 70 | 15 · 40.0% · PF 0.75 · -556 | 14 · 21.4% · PF 0.34 · -1,528 | 29 · 31.0% · PF 0.54 · -2,084 |
| Sell below EMA 105 + ADX>20 + Daily>EMA50 + Supertrend | exit: tp 3 | 13 · 38.5% · PF 0.62 · -1,187 | 13 · 23.1% · PF 0.61 · -1,009 | 26 · 30.8% · PF 0.62 · -2,196 |

No sell rule was profitable and consistent in both parts, so the setups are buy only: a close below EMA 105 means stay out.

## Test 1: which single EMA? (every EMA 3-200 × 7 timeframes)

1,267 rules: close above EMA = up, close below = down, held to the opposite close. All timeframes ranked on the same 61 sessions (2026-08-12 → 2026-11-09); rules had to make money on BOTH up and down signals to score fully. Final = 60% numbers + 40% Jev.

| # | Candles | EMA | Signals | Up signals: hit · pts | Down signals: hit · pts | PF | Net pts | 140 sessions PF · net | Jev | Final |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2h | 105 | 10 | 20.0% · +1,805 | 40.0% · +996 | 6.57 | +2,802 | 1.62 · +1,426 | weak | 58.6 |
| 2 | 1h | 185 | 14 | 14.3% · +1,793 | 42.9% · +1,015 | 5.83 | +2,808 | 1.54 · +1,391 | weak | 58.6 |
| 3 | 15m | 77 | 51 | 23.1% · +1,703 | 40.0% · +876 | 2.28 | +2,578 | 2.28 · +2,578 | weak | 55.1 |
| 4 | 15m | 75 | 51 | 26.9% · +1,756 | 40.0% · +929 | 2.39 | +2,685 | 2.39 · +2,685 | weak | 54.2 |
| 5 | 15m | 76 | 51 | 26.9% · +1,738 | 40.0% · +910 | 2.36 | +2,648 | 2.36 · +2,648 | weak | 54.1 |
| 6 | 15m | 88 | 46 | 21.7% · +1,732 | 39.1% · +894 | 2.37 | +2,626 | 2.37 · +2,626 | weak | 54.1 |
| 7 | 30m | 81 | 21 | 18.2% · +2,061 | 30.0% · +417 | 3.95 | +2,478 | 3.95 · +2,478 | weak | 54.0 |
| 8 | 1D | 12 | 8 | 25.0% · +1,540 | 50.0% · +931 | 3.06 | +2,470 | 0.75 · -1,337 | weak | 47.8 |
| 9 | 75m | 31 | 15 | 25.0% · +1,995 | 42.9% · +331 | 3.32 | +2,326 | 3.32 · +2,326 | weak | 46.3 |
| 10 | 5m | 178 | 120 | 15.0% · +1,257 | 20.0% · +443 | 1.52 | +1,700 | 1.52 · +1,700 | weak | 44.0 |

Your EMAs 5, 6, 9, 10, 11 (same rule, same dates):

| Candles | EMA 5 | EMA 6 | EMA 9 | EMA 10 | EMA 11 |
|---|---|---|---|---|---|
| 5m | -6,665 | -5,986 | -5,009 | -4,496 | -4,244 |
| 15m | -2,063 | -2,082 | -2,413 | -1,820 | -1,510 |
| 30m | -904 | -1,134 | -1,443 | -1,157 | -1,338 |
| 75m | -527 | -20 | +1,178 | +1,779 | +1,779 |
| 1h | -2,303 | -1,523 | -1,243 | -481 | -540 |
| 2h | +8 | -339 | +1,318 | +1,883 | +2,218 |
| 1D | +1,593 | +1,767 | +2,234 | +1,469 | +2,447 |

## Test 3: day vs night (last 200 sessions, 2026-01-16 → 2026-11-09)

Night (close → next open) **+124** points, day (open → close) **-745**, close to close **-621**. Check: night + day = close to close on every session (max error 0.0).

| Year | Night pts | Day pts | Night % | Day % |
|---|---|---|---|---|
| 2016 | -39 | -272 | -0.2% | -3.1% |
| 2017 | +3,864 | -1,519 | +40.5% | -14.9% |
| 2018 | +2,417 | -2,085 | +22.4% | -18.3% |
| 2019 | +4,070 | -2,764 | +35.6% | -23.3% |
| 2020 | +5,054 | -3,241 | +46.1% | -27.0% |
| 2021 | +7,321 | -3,949 | +46.3% | -23.5% |
| 2022 | +1,261 | -510 | +7.8% | -2.0% |
| 2023 | +5,884 | -2,258 | +31.3% | -12.6% |
| 2024 | +5,491 | -3,578 | +24.0% | -14.5% |
| 2025 | +2,243 | +242 | +9.1% | +1.7% |
| 2026 | +23 | -1,108 | +0.6% | -3.8% |

Where the EMA 105 trades made their points:

| Rule | Trades | Overnight pts | Daytime pts |
|---|---|---|---|
| EMA 105 (buy above, sell below) | 112 | +3,960 | +320 |
| EMA 105 buy only | 56 | +5,972 | -2,215 |
| EMA 105 + confirmations (the winner) | 32 | +4,852 | +1,439 |

All 49 session rules (sorted by points after costs; ✓ = profit in both 100-session halves):

| Idea | Rule | Side | Trades | Win % | PF | Net | 1st 100 | Last 100 | Holds |
|---|---|---|---|---|---|---|---|---|---|
| 5 Where it closed | Closed in top ¼ of the day's range → night buy | BUY | 69 | 47.8% | 1.65 | +2,089 | +2,397 | -308 |  |
| 3 Day of the week | Monday night sell | SELL | 41 | 48.8% | 1.65 | +1,512 | +2,036 | -524 |  |
| 3 Day of the week | Tuesday night buy (previous close → Tuesday open) | BUY | 38 | 42.1% | 1.93 | +1,268 | +1,438 | -170 |  |
| 5 Where it closed | Closed in bottom ¼ → night sell | SELL | 57 | 50.9% | 1.40 | +1,064 | +1,796 | -732 |  |
| 3 Day of the week | Tuesday day sell | SELL | 38 | 60.5% | 1.37 | +827 | +444 | +382 | ✓ |
| 3 Day of the week | Wednesday night buy (previous close → Wednesday open) | BUY | 42 | 45.2% | 1.36 | +735 | +1,103 | -368 |  |
| 3 Day of the week | Monday day buy (open → close) | BUY | 41 | 53.7% | 1.24 | +624 | +811 | -187 |  |
| 3 Day of the week | Thursday day sell | SELL | 40 | 52.5% | 1.16 | +356 | +509 | -153 |  |
| 4 Gaps | Gap up > ¼ normal range → sell the open (fade) | SELL | 64 | 46.9% | 1.09 | +354 | +612 | -258 |  |
| 6 After an up / down day | Up day → next day sell | SELL | 100 | 52.0% | 1.04 | +252 | +1,162 | -910 |  |
| 4 Gaps | Gap down > ¼ normal range → sell the open (follow) | SELL | 55 | 52.7% | 1.05 | +204 | -187 | +391 |  |
| 9 After a wide / quiet day | Range > 1.5× normal → next day buy | BUY | 34 | 55.9% | 1.07 | +164 | -108 | +272 |  |
| 2 With the EMA 105 trend | Night buy only when 2h close > EMA 105 | BUY | 84 | 47.6% | 1.01 | +20 | -590 | +610 |  |
| 3 Day of the week | Friday night sell | SELL | 39 | 43.6% | 1.01 | +16 | +308 | -292 |  |
| 3 Day of the week | Thursday night sell | SELL | 40 | 42.5% | 1.01 | +15 | +689 | -675 |  |
| 7 Inside the day | First hour up → buy 10:15, sell at close | BUY | 95 | 51.6% | 1.00 | -7 | -697 | +690 |  |
| 7 Inside the day | 09:15→15:15 up → buy the last 15 minutes | BUY | 94 | 46.8% | 0.99 | -12 | -485 | +473 |  |
| 8 Turn of the month | Last day + first 3 days: night buy | BUY | 44 | 50.0% | 0.96 | -144 | -732 | +587 |  |
| 3 Day of the week | Wednesday day buy (open → close) | BUY | 42 | 54.8% | 0.93 | -150 | +517 | -667 |  |
| 8 Turn of the month | Last day + first 3 days: day buy | BUY | 44 | 50.0% | 0.95 | -175 | -666 | +491 |  |
| 3 Day of the week | Friday day sell | SELL | 39 | 38.5% | 0.91 | -253 | +1,248 | -1,501 |  |
| 2 With the EMA 105 trend | Night sell only when 2h close < EMA 105 | SELL | 115 | 48.7% | 0.96 | -312 | -98 | -214 |  |
| 8 Turn of the month | Other days: day sell | SELL | 156 | 47.4% | 0.96 | -369 | -112 | -258 |  |
| 2 With the EMA 105 trend | Day sell only when EMA 105 is down | SELL | 115 | 46.1% | 0.95 | -378 | -506 | +128 |  |
| 3 Day of the week | Friday day buy (open → close) | BUY | 39 | 53.8% | 0.86 | -404 | -1,589 | +1,185 |  |
| 6 After an up / down day | Down day → next day buy | BUY | 100 | 50.0% | 0.93 | -484 | +171 | -655 |  |
| 3 Day of the week | Wednesday day sell | SELL | 42 | 42.9% | 0.78 | -555 | -874 | +319 |  |
| 3 Day of the week | Friday night buy (previous close → Friday open) | BUY | 39 | 51.3% | 0.67 | -673 | -650 | -23 |  |
| 3 Day of the week | Thursday night buy (previous close → Thursday open) | BUY | 40 | 47.5% | 0.73 | -687 | -1,014 | +327 |  |
| 9 After a wide / quiet day | Range > 1.5× normal → next day sell | SELL | 34 | 41.2% | 0.73 | -733 | -183 | -550 |  |
| 7 Inside the day | First hour down → sell 10:15, buy back at close | SELL | 104 | 47.1% | 0.87 | -781 | -1,115 | +334 |  |
| 2 With the EMA 105 trend | Day buy only when EMA 105 is up | BUY | 84 | 44.0% | 0.83 | -883 | -1,315 | +432 |  |
| 1 Day vs night | Sell at open, buy back at close (day) | SELL | 200 | 47.0% | 0.93 | -935 | +163 | -1,098 |  |
| 3 Day of the week | Thursday day buy (open → close) | BUY | 40 | 37.5% | 0.65 | -1,028 | -833 | -196 |  |
| 4 Gaps | Gap down > ¼ normal range → buy the open (fade) | BUY | 55 | 43.6% | 0.75 | -1,118 | -330 | -787 |  |
| 6 After an up / down day | Down day → night buy | BUY | 100 | 44.0% | 0.83 | -1,212 | -1,119 | -93 |  |
| 3 Day of the week | Monday day sell | SELL | 41 | 41.5% | 0.63 | -1,311 | -1,164 | -146 |  |
| 9 After a wide / quiet day | Range < 0.7× normal → night buy | BUY | 30 | 33.3% | 0.42 | -1,363 | -1,324 | -39 |  |
| 4 Gaps | Gap up > ¼ normal range → buy the open (follow) | BUY | 64 | 48.4% | 0.70 | -1,430 | -1,156 | -275 |  |
| 3 Day of the week | Wednesday night sell | SELL | 42 | 45.2% | 0.54 | -1,439 | -1,459 | +20 |  |
| 3 Day of the week | Tuesday day buy (open → close) | BUY | 38 | 39.5% | 0.58 | -1,466 | -768 | -698 |  |
| 1 Day vs night | Buy at close, sell next open (night) | BUY | 200 | 46.5% | 0.87 | -1,556 | -1,514 | -43 |  |
| 1 Day vs night | Sell at close, buy back next open (night) | SELL | 200 | 46.0% | 0.85 | -1,804 | -186 | -1,618 |  |
| 3 Day of the week | Tuesday night sell | SELL | 38 | 50.0% | 0.35 | -1,907 | -1,760 | -146 |  |
| 5 Where it closed | Closed in bottom ¼ → night buy (bounce) | BUY | 57 | 43.9% | 0.52 | -2,014 | -2,333 | +319 |  |
| 10 Opening-range breakout | Break of the first-hour high (buy) or low (sell), hold to close | BOTH | 194 | 47.9% | 0.80 | -2,036 | -1,143 | -893 |  |
| 7 Inside the day | 09:15→15:15 down → sell the last 15 minutes | SELL | 105 | 27.6% | 0.20 | -2,081 | -994 | -1,087 |  |
| 3 Day of the week | Monday night buy (previous close → Monday open) | BUY | 41 | 46.3% | 0.47 | -2,200 | -2,391 | +191 |  |
| 1 Day vs night | Buy at open, sell at close (day) | BUY | 200 | 48.0% | 0.83 | -2,425 | -1,862 | -563 |  |

Opening-range breakout, checked twice:

| Version | Trades | Win % | PF | Net | DD |
|---|---|---|---|---|---|
| Hourly, first hour, 200 sessions | 194 | 47.9% | 0.80 | -2,036 | 3,838 |
| … first 100 | 97 | 48.5% | 0.80 | -1,143 | 1,737 |
| … last 100 | 97 | 47.4% | 0.80 | -893 | 2,134 |
| Hourly, same days as 5-min | 60 | 55.0% | 1.36 | +763 | 477 |
| 5-minute, first hour | 60 | 55.0% | 1.34 | +729 | 477 |
| 5-minute, first 15 min | 61 | 50.8% | 1.37 | +1,045 | 768 |
| 5-minute, first 30 min | 60 | 53.3% | 1.56 | +1,314 | 754 |

**Look-ahead trap found and removed:** a first version that traded only days where *one* side of the first hour broke showed 64-66% wins and PF 3+. That rule needs the day's close to know the other side never broke, so it cannot be traded. Done correctly (enter on the first break), the breakout lost money over 200 sessions.

## Jev's judgement of the combination finalists

| Rule | Reliability | Overfit risk | Jev score | Final |
|---|---|---|---|---|
| EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 68 | fair | medium | 45.4 | 58.8 |
| EMA 105 + RSI>50 + ADX>20 + Daily>EMA50 · TOP exit RSI 70 | fair | medium | 41.6 | 57.1 |
| EMA 105 + RSI>50 + ADX>20 + Daily>EMA50 · TOP exit RSI 68 | fair | medium | 41.0 | 56.6 |
| EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 68 | fair | medium | 43.6 | 56.6 |
| EMA 105 + ADX>20 + Daily>EMA50 · TOP exit RSI 70 | fair | medium | 45.0 | 56.6 |
| EMA 105 + ADX>20 + Supertrend + EMA slope · TOP exit RSI 68 | fair | medium | 43.4 | 56.1 |

## Limits

- 8,056 combinations were tried; the best one is partly luck even with an unseen part. Expect live results to be weaker.
- About 3 years of 2-hour data; the unseen part holds only about 9-11 trades per setup.
- Index candles, not futures. Futures trade at a premium and gap differently at 09:15.
- Paper research. Not SEBI-registered advice. No orders are placed by this website.
