# Nifty 50 research record

Generated 2026-11-08 10:29 IST from the live engines (`nifty_ema.py`, `nifty_combo.py`, `nifty_daynight.py`). Re-run `python scripts/nifty_research_md.py` to refresh. Paper research, not advice.

**Data:** NIFTY 50 index (^NSEI, Yahoo Finance). 2-hour candles 2024-03-19 → 2026-11-06 (2,586 candles). Daily candles 2016 → 2026-11-06. Hourly 2023 → today, 5-minute last ~60 sessions.

**Costs:** every trade pays 0.035% of price (≈ 9 Nifty points at 25,000).

**Honesty split:** rules are tested on 2024-03-19 → 2025-12-18 (the *tested part*) and judged on 2025-12-18 → 2026-11-06 (the *unseen part*, never used to pick). A rule is *robust* only if it makes money in both.

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
| **1** | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 68 | Best overall (the page's winner) | whole | 32 | 68.8% | 4.02 | +6,005 | 1,088 |
|  |  |  | tested | 23 | 69.6% | 3.40 | +4,242 | 1,088 |
|  |  |  | **unseen** | 9 | 66.7% | 9.06 | +1,764 | 174 |
| **2** | EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 70 | Best on the unseen part (70% win) | whole | 31 | 67.7% | 3.23 | +5,061 | 1,088 |
|  |  |  | tested | 21 | 66.7% | 3.00 | +3,394 | 1,088 |
|  |  |  | **unseen** | 10 | 70.0% | 3.89 | +1,667 | 245 |
| **3** | EMA 105 + ADX>20 + Daily>EMA50 · TOP exit RSI 70 | Fewest conditions, smallest drawdown | whole | 47 | 46.8% | 3.13 | +6,341 | 564 |
|  |  |  | tested | 33 | 45.5% | 3.25 | +4,586 | 564 |
|  |  |  | **unseen** | 14 | 50.0% | 2.86 | +1,755 | 331 |
| ref | EMA 105 alone · exit on close below | the starting point | whole | 56 | 25.0% | 1.71 | +3,269 | 1,786 |

**Worked maths for setup 1:** 32 trades, 22 winners → win rate 22 ÷ 32 = **68.8%**. Winners made 7,993.6 points, losers lost 1,988.3 → PF 7,993.6 ÷ 1,988.3 = **4.02**. Net 7,993.6 − 1,988.3 = **+6,005.2 points** ≈ ₹450,391 per lot of 75.

## How the win rate climbs toward 70% (one step at a time)

Each row adds one thing to the row above. Whole period, buy only, after costs.

| Step | Rule | Trades | Win % | PF | Net pts | Worst DD | Unseen win % | Unseen PF |
|---|---|---|---|---|---|---|---|---|
| 0 | EMA 105 · exit on close below | 56 | 25.0% | 1.71 | +3,269 | 1,786 | 18.2% | 1.20 |
| 1 | EMA 105 + ADX>20 · exit on close below | 48 | 25.0% | 1.70 | +3,123 | 1,558 | 23.5% | 1.28 |
| 2 | EMA 105 + ADX>20 + Daily>EMA50 · exit on close below | 34 | 23.5% | 1.49 | +1,932 | 1,566 | 18.2% | 0.89 |
| 3 | EMA 105 + ADX>20 + Daily>EMA50 + Supertrend · exit on close below | 26 | 26.9% | 1.37 | +1,479 | 1,458 | 12.5% | 1.00 |
| 4 | EMA 105 + ADX>20 + Daily>EMA50 + Supertrend · TOP exit RSI 70 | 31 | 67.7% | 3.55 | +5,664 | 1,088 | 77.8% | 5.34 |
| 5 | EMA 105 + ADX>20 + Daily>EMA50 + Supertrend · TOP exit RSI 68 | 32 | 68.8% | 4.02 | +6,005 | 1,088 | 66.7% | 9.06 |

What moves the number: **ADX > 20** removes trades in sideways markets (most of EMA 105's small losses). **Daily close above daily EMA 50** keeps only buys in a rising bigger trend. **Supertrend** removes late entries. The **RSI TOP exit** books the gain near the top instead of giving it back on the way down to EMA 105 - this step lifts the win rate the most.

**Best win rate by number of confirmations** (robust rules only, 20+ trades):

| Confirmations | Robust rules | Best win % | Rule |
|---|---|---|---|
| 0 | 37 | 42.9% | EMA 105 · target 2 ATR |
| 1 | 250 | 49.0% | EMA 105 + DI+>DI- · target 2 ATR |
| 2 | 877 | 60.5% | EMA 105 + Daily>EMA50 + DI+>DI- · TOP exit RSI 68 |
| 3 | 1,999 | 68.8% | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 68 |

## Where the win rate goes above 70%

- Rules with **70%+ over the whole period** and at least 10 trades: **0** of 8,056.
- Rules with **70%+ on the unseen part** (8+ trades) that also made money on the tested part: **3**:

| Rule | Tested part | Unseen part | Whole period |
|---|---|---|---|
| EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 70 | 22 tr · 63.6% · PF 3.15 · +3,921 | **9 tr · 77.8% · PF 5.34 · +1,742** | 31 tr · 67.7% · PF 3.55 · +5,664 |
| EMA 105 + ADX>20 + Supertrend + 2 closes · TOP exit RSI 70 | 27 tr · 48.1% · PF 2.48 · +3,755 | **10 tr · 70.0% · PF 4.24 · +2,086** | 37 tr · 54.1% · PF 2.83 · +5,841 |
| EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 70 | 21 tr · 66.7% · PF 3.00 · +3,394 | **10 tr · 70.0% · PF 3.89 · +1,667** | 31 tr · 67.7% · PF 3.23 · +5,061 |

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
| EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 68 | 22 tr · 72.7% · PF 3.26 · +3,714 | 10 tr · 60.0% · PF 5.29 · +1,689 |
| EMA 105 + RSI>50 + ADX>25 + Daily>EMA50 · target 2 ATR | 18 tr · 72.2% · PF 1.90 · +1,833 | 7 tr · 42.9% · PF 0.55 · -681 |
| EMA 105 + ADX>25 + Supertrend + Daily>EMA50 · target 2 ATR | 18 tr · 72.2% · PF 1.90 · +1,846 | 7 tr · 42.9% · PF 0.55 · -681 |
| EMA 105 + Daily>EMA50 + DI+>DI- · TOP exit 3 ATR | 24 tr · 70.8% · PF 3.24 · +1,898 | 14 tr · 50.0% · PF 0.63 · -499 |
| EMA 105 + Daily>EMA50 + EMA slope + DI+>DI- · TOP exit 3 ATR | 24 tr · 70.8% · PF 2.59 · +1,586 | 14 tr · 50.0% · PF 0.54 · -614 |
| EMA 105 + Daily>EMA50 + 2 closes + DI+>DI- · TOP exit 3 ATR | 24 tr · 70.8% · PF 2.65 · +1,601 | 14 tr · 50.0% · PF 0.59 · -572 |
| EMA 105 + ADX>25 + Daily>EMA50 + DI+>DI- · target 2 ATR | 17 tr · 70.6% · PF 1.32 · +770 | 7 tr · 42.9% · PF 0.55 · -681 |
| EMA 105 + ADX>25 + Daily>EMA50 + DI+>DI- · Bollinger top | 17 tr · 70.6% · PF 2.49 · +3,034 | 7 tr · 28.6% · PF 1.36 · +500 |

Of those 16, **0** stayed at 70%+ on unseen data and **14** lost money. So 70%+ is reachable on a stretch of data, and the setups above did hit 70-78% on the unseen part, but no rule held 70%+ over the whole period with enough trades. ~65-69% is the honest level.

## 30 combinations side by side

Same data, same costs. Tested part / unseen part / whole period. Long only unless marked.

| # | Rule | Tested: trades · win · PF · net | Unseen: trades · win · PF · net | Whole: trades | Win % | PF | Net pts | DD | Both parts profit |
|---|---|---|---|---|---|---|---|---|---|
| 1 | EMA 105 · exit on close below | 34 · 29.4% · 2.10 · +2,871 | 22 · 18.2% · 1.20 · +398 | 56 | 25.0% | 1.71 | +3,269 | 1,786 | ✓ |
| 2 | EMA 105 · exit on close below · buy+sell | 69 · 23.2% · 1.24 · +1,588 | 43 · 20.9% · 1.47 · +1,729 | 112 | 22.3% | 1.32 | +3,318 | 1,894 | ✓ |
| 3 | EMA 105 · TOP exit RSI 70 | 44 · 34.1% · 2.76 · +5,489 | 26 · 30.8% · 2.10 · +2,325 | 70 | 32.9% | 2.49 | +7,814 | 1,124 | ✓ |
| 4 | EMA 105 · target 2 ATR | 48 · 41.7% · 2.28 · +3,530 | 29 · 44.8% · 2.30 · +2,178 | 77 | 42.9% | 2.29 | +5,708 | 861 | ✓ |
| 5 | EMA 105 · TOP exit 4 ATR | 43 · 34.9% · 2.34 · +3,632 | 26 · 30.8% · 1.29 · +608 | 69 | 33.3% | 1.88 | +4,240 | 1,252 | ✓ |
| 6 | EMA 105 · trail 3 ATR | 44 · 31.8% · 2.36 · +4,356 | 27 · 33.3% · 1.56 · +1,173 | 71 | 32.4% | 2.04 | +5,529 | 1,428 | ✓ |
| 7 | EMA 105 + RSI>50 · exit on close below | 30 · 33.3% · 1.83 · +2,339 | 19 · 10.5% · 0.98 · -60 | 49 | 24.5% | 1.44 | +2,279 | 2,244 | ✗ |
| 8 | EMA 105 + MACD hist · exit on close below | 33 · 30.3% · 1.46 · +1,546 | 18 · 11.1% · 0.85 · -414 | 51 | 23.5% | 1.18 | +1,132 | 2,598 | ✗ |
| 9 | EMA 105 + ADX>20 · exit on close below | 31 · 25.8% · 2.01 · +2,598 | 17 · 23.5% · 1.28 · +525 | 48 | 25.0% | 1.70 | +3,123 | 1,558 | ✓ |
| 10 | EMA 105 + ADX>25 · exit on close below | 24 · 33.3% · 2.21 · +2,700 | 10 · 30.0% · 0.76 · -523 | 34 | 32.4% | 1.49 | +2,177 | 1,910 | ✗ |
| 11 | EMA 105 + Supertrend · exit on close below | 28 · 35.7% · 1.63 · +1,887 | 16 · 12.5% · 0.88 · -311 | 44 | 27.3% | 1.28 | +1,577 | 2,538 | ✗ |
| 12 | EMA 105 + Daily>EMA50 · exit on close below | 26 · 30.8% · 1.83 · +2,128 | 14 · 14.3% · 0.68 · -654 | 40 | 25.0% | 1.32 | +1,475 | 2,141 | ✗ |
| 13 | EMA 105 + Daily>EMA200 · exit on close below | 32 · 28.1% · 1.54 · +1,778 | 11 · 18.2% · 0.39 · -1,067 | 43 | 25.6% | 1.14 | +711 | 1,821 | ✗ |
| 14 | EMA 105 + EMA slope · exit on close below | 29 · 34.5% · 1.92 · +2,368 | 18 · 11.1% · 1.00 · +7 | 47 | 25.5% | 1.51 | +2,375 | 2,153 | ✗ |
| 15 | EMA 105 + 2 closes · exit on close below | 29 · 34.5% · 1.95 · +2,511 | 20 · 15.0% · 1.03 · +60 | 49 | 26.5% | 1.52 | +2,571 | 2,170 | ✓ |
| 16 | EMA 105 + DI+>DI- · exit on close below | 26 · 38.5% · 1.83 · +2,018 | 18 · 11.1% · 0.97 · -79 | 44 | 27.3% | 1.40 | +1,938 | 2,263 | ✗ |
| 17 | EMA 105 + ADX>20 · TOP exit RSI 70 | 41 · 34.1% · 2.73 · +4,805 | 20 · 40.0% · 2.71 · +2,460 | 61 | 36.1% | 2.72 | +7,264 | 1,032 | ✓ |
| 18 | EMA 105 + ADX>20 + Daily>EMA50 · exit on close below | 23 · 26.1% · 1.90 · +2,112 | 11 · 18.2% · 0.89 · -180 | 34 | 23.5% | 1.49 | +1,932 | 1,566 | ✗ |
| 19 | EMA 105 + ADX>20 + Daily>EMA50 · TOP exit RSI 70 | 33 · 45.5% · 3.25 · +4,586 | 14 · 50.0% · 2.86 · +1,755 | 47 | 46.8% | 3.13 | +6,341 | 564 | ✓ |
| 20 | EMA 105 + ADX>20 + Supertrend · TOP exit RSI 70 | 29 · 44.8% · 2.59 · +3,957 | 11 · 63.6% · 5.30 · +2,693 | 40 | 50.0% | 3.14 | +6,650 | 1,088 | ✓ |
| 21 | EMA 105 + RSI>50 + ADX>20 · TOP exit RSI 70 | 30 · 43.3% · 2.88 · +4,598 | 14 · 50.0% · 3.67 · +2,639 | 44 | 45.5% | 3.11 | +7,237 | 1,088 | ✓ |
| 22 | EMA 105 + Daily>EMA50 + DI+>DI- · TOP exit RSI 68 | 25 · 64.0% · 2.92 · +3,992 | 13 · 53.8% · 2.05 · +1,184 | 38 | 60.5% | 2.61 | +5,175 | 1,088 | ✓ |
| 23 | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · exit on close below | 18 · 33.3% · 1.56 · +1,486 | 8 · 12.5% · 1.00 · -7 | 26 | 26.9% | 1.37 | +1,479 | 1,458 | ✗ |
| 24 | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 68 | 23 · 69.6% · 3.40 · +4,242 | 9 · 66.7% · 9.06 · +1,764 | 32 | 68.8% | 4.02 | +6,005 | 1,088 | ✓ |
| 25 | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 70 | 22 · 63.6% · 3.15 · +3,921 | 9 · 77.8% · 5.34 · +1,742 | 31 | 67.7% | 3.55 | +5,664 | 1,088 | ✓ |
| 26 | EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 70 | 21 · 66.7% · 3.00 · +3,394 | 10 · 70.0% · 3.89 · +1,667 | 31 | 67.7% | 3.23 | +5,061 | 1,088 | ✓ |
| 27 | EMA 105 + RSI>50 + ADX>20 + Daily>EMA50 · TOP exit RSI 68 | 23 · 69.6% · 3.45 · +4,025 | 11 · 54.5% · 4.09 · +1,573 | 34 | 64.7% | 3.60 | +5,598 | 1,088 | ✓ |
| 28 | EMA 105 + ADX>20 + Supertrend + EMA slope · TOP exit RSI 68 | 27 · 63.0% · 3.14 · +4,473 | 10 · 50.0% · 5.72 · +1,870 | 37 | 59.5% | 3.55 | +6,344 | 1,088 | ✓ |
| 29 | EMA 105 + RSI>50 + ADX>25 + Daily>EMA50 · TOP exit 4 ATR | 16 · 75.0% · 6.08 · +2,560 | 8 · 50.0% · 0.40 · -452 | 24 | 66.7% | 2.68 | +2,108 | 1,008 | ✗ |
| 30 | EMA 105 + MACD hist + Daily>EMA200 + EMA slope · TOP exit 3 ATR · buy+sell | 36 · 58.3% · 2.71 · +3,314 | 19 · 57.9% · 1.88 · +974 | 55 | 58.2% | 2.41 | +4,288 | 711 | ✓ |

## Sensitivity: is the winner a lucky setting?

EMA 105 + ADX>a + Supertrend + Daily>EMA50, TOP exit at RSI r. Whole-period win % (PF).

| ADX > | RSI 65 | RSI 68 | RSI 70 | RSI 72 | RSI 75 | RSI 80 |
|---|---|---|---|---|---|---|
| 15 | 48.8% (1.65) | 57.5% (2.22) | 53.8% (2.16) | 48.6% (1.79) | 37.1% (1.32) | 33.3% (1.66) |
| 18 | 50.0% (2.23) | 59.5% (3.02) | 58.3% (2.87) | 51.4% (2.13) | 39.4% (1.52) | 35.5% (1.93) |
| 20 | 54.5% (2.78) | 68.8% (4.02) | 67.7% (3.55) | 56.7% (2.36) | 42.9% (1.63) | 38.5% (2.12) |
| 22 | 53.1% (2.51) | 67.7% (3.67) | 63.3% (3.30) | 58.6% (2.18) | 44.4% (1.51) | 40.0% (1.97) |
| 25 | 46.4% (1.57) | 55.6% (2.19) | 50.0% (2.18) | 56.0% (2.02) | 43.5% (1.50) | 42.9% (1.96) |
| 30 | 45.5% (1.48) | 45.5% (1.44) | 47.6% (1.44) | 50.0% (1.30) | 44.4% (1.12) | 50.0% (1.90) |

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
| Sell below EMA 105 + Supertrend + 0.5 ATR buffer + 2 closes | exit: rsi 70 | 25 · 44.0% · PF 1.16 · +411 | 14 · 42.9% · PF 1.55 · +776 | 39 · 43.6% · PF 1.30 · +1,187 |
| Sell below EMA 105 + Supertrend + 0.5 ATR buffer + 2 closes | exit: tp 3 | 22 · 50.0% · PF 1.85 · +2,074 | 14 · 42.9% · PF 1.56 · +782 | 36 · 47.2% · PF 1.74 · +2,856 |
| Sell below EMA 105 + MACD hist + 0.5 ATR buffer + 2 closes | exit: cross | 19 · 21.1% · PF 0.62 · -1,225 | 13 · 23.1% · PF 2.15 · +1,426 | 32 · 21.9% · PF 1.04 · +201 |
| Sell below EMA 105 + MACD hist + 0.5 ATR buffer + 2 closes | exit: rsi 70 | 23 · 39.1% · PF 0.96 · -103 | 14 · 42.9% · PF 1.93 · +1,071 | 37 · 40.5% · PF 1.26 · +968 |
| Sell below EMA 105 + MACD hist + 0.5 ATR buffer + 2 closes | exit: tp 3 | 21 · 52.4% · PF 1.70 · +1,790 | 14 · 50.0% · PF 2.41 · +1,538 | 35 · 51.4% · PF 1.91 · +3,327 |
| Sell below EMA 105 + Daily>EMA200 + Supertrend | exit: cross | 5 · 40.0% · PF 0.77 · -267 | 14 · 21.4% · PF 0.95 · -92 | 19 · 26.3% · PF 0.89 · -358 |
| Sell below EMA 105 + Daily>EMA200 + Supertrend | exit: rsi 70 | 5 · 60.0% · PF 1.47 · +409 | 16 · 37.5% · PF 0.66 · -725 | 21 · 42.9% · PF 0.90 · -316 |
| Sell below EMA 105 + Daily>EMA200 + Supertrend | exit: tp 3 | 5 · 80.0% · PF 8.81 · +2,020 | 17 · 35.3% · PF 1.27 · +604 | 22 · 45.5% · PF 2.06 · +2,624 |
| Sell below EMA 105 + ADX>20 + Daily>EMA50 + Supertrend | exit: cross | 13 · 30.8% · PF 0.48 · -1,716 | 13 · 23.1% · PF 0.74 · -677 | 26 · 26.9% · PF 0.59 · -2,392 |
| Sell below EMA 105 + ADX>20 + Daily>EMA50 + Supertrend | exit: rsi 70 | 15 · 40.0% · PF 0.75 · -556 | 14 · 21.4% · PF 0.34 · -1,528 | 29 · 31.0% · PF 0.54 · -2,084 |
| Sell below EMA 105 + ADX>20 + Daily>EMA50 + Supertrend | exit: tp 3 | 13 · 38.5% · PF 0.62 · -1,187 | 13 · 23.1% · PF 0.61 · -1,009 | 26 · 30.8% · PF 0.62 · -2,196 |

No sell rule was profitable and consistent in both parts, so the setups are buy only: a close below EMA 105 means stay out.

## Test 1: which single EMA? (every EMA 3-200 × 7 timeframes)

1,265 rules: close above EMA = up, close below = down, held to the opposite close. All timeframes ranked on the same 60 sessions (2026-08-12 → 2026-11-06); rules had to make money on BOTH up and down signals to score fully. Final = 60% numbers + 40% Jev.

| # | Candles | EMA | Signals | Up signals: hit · pts | Down signals: hit · pts | PF | Net pts | 140 sessions PF · net | Jev | Final |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2h | 105 | 10 | 20.0% · +1,791 | 40.0% · +996 | 6.54 | +2,787 | 1.62 · +1,412 | weak | 58.0 |
| 2 | 1h | 187 | 14 | 14.3% · +1,778 | 42.9% · +1,014 | 5.80 | +2,792 | 1.54 · +1,374 | weak | 57.6 |
| 3 | 15m | 77 | 51 | 23.1% · +1,688 | 40.0% · +874 | 2.27 | +2,562 | 2.27 · +2,562 | weak | 56.3 |
| 4 | 15m | 88 | 46 | 21.7% · +1,717 | 39.1% · +894 | 2.36 | +2,612 | 2.36 · +2,612 | weak | 56.1 |
| 5 | 15m | 76 | 51 | 26.9% · +1,722 | 40.0% · +909 | 2.35 | +2,631 | 2.35 · +2,631 | weak | 54.7 |
| 6 | 15m | 75 | 51 | 26.9% · +1,741 | 40.0% · +928 | 2.38 | +2,669 | 2.38 · +2,669 | weak | 54.5 |
| 7 | 30m | 83 | 25 | 30.8% · +1,984 | 25.0% · +354 | 3.58 | +2,338 | 3.58 · +2,338 | weak | 52.9 |
| 8 | 1D | 12 | 8 | 25.0% · +1,525 | 50.0% · +931 | 3.05 | +2,456 | 0.75 · -1,352 | weak | 47.8 |
| 9 | 5m | 181 | 116 | 15.5% · +1,283 | 22.4% · +482 | 1.56 | +1,765 | 1.56 · +1,765 | weak | 45.1 |
| 10 | 75m | 31 | 15 | 25.0% · +1,980 | 42.9% · +331 | 3.30 | +2,311 | 3.30 · +2,311 | weak | 43.9 |

Your EMAs 5, 6, 9, 10, 11 (same rule, same dates):

| Candles | EMA 5 | EMA 6 | EMA 9 | EMA 10 | EMA 11 |
|---|---|---|---|---|---|
| 5m | -6,331 | -5,773 | -4,701 | -4,277 | -4,082 |
| 15m | -2,014 | -2,090 | -2,130 | -1,438 | -1,224 |
| 30m | -611 | -834 | -1,323 | -1,233 | -1,376 |
| 75m | -540 | -33 | +1,164 | +1,765 | +1,765 |
| 1h | -2,321 | -1,540 | -1,256 | -496 | -555 |
| 2h | -7 | -353 | +1,303 | +1,869 | +2,204 |
| 1D | +1,579 | +1,753 | +2,220 | +1,455 | +2,433 |

## Test 3: day vs night (last 200 sessions, 2026-01-14 → 2026-11-06)

Night (close → next open) **-6** points, day (open → close) **-696**, close to close **-702**. Check: night + day = close to close on every session (max error 0.0).

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
| 2026 | -23 | -1,077 | +0.4% | -3.6% |

Where the EMA 105 trades made their points:

| Rule | Trades | Overnight pts | Daytime pts |
|---|---|---|---|
| EMA 105 (buy above, sell below) | 112 | +3,876 | +390 |
| EMA 105 buy only | 56 | +5,936 | -2,194 |
| EMA 105 + confirmations (the winner) | 32 | +4,809 | +1,468 |

All 49 session rules (sorted by points after costs; ✓ = profit in both 100-session halves):

| Idea | Rule | Side | Trades | Win % | PF | Net | 1st 100 | Last 100 | Holds |
|---|---|---|---|---|---|---|---|---|---|
| 5 Where it closed | Closed in top ¼ of the day's range → night buy | BUY | 68 | 47.1% | 1.64 | +2,051 | +2,397 | -346 |  |
| 3 Day of the week | Monday night sell | SELL | 40 | 50.0% | 1.69 | +1,567 | +2,036 | -469 |  |
| 3 Day of the week | Tuesday night buy (previous close → Tuesday open) | BUY | 38 | 42.1% | 1.93 | +1,268 | +1,376 | -108 |  |
| 5 Where it closed | Closed in bottom ¼ → night sell | SELL | 57 | 50.9% | 1.40 | +1,064 | +1,874 | -810 |  |
| 3 Day of the week | Tuesday day sell | SELL | 38 | 60.5% | 1.37 | +827 | +518 | +309 | ✓ |
| 8 Turn of the month | Last day + first 3 days: day buy | BUY | 44 | 54.5% | 1.24 | +714 | -302 | +1,015 |  |
| 3 Day of the week | Monday day buy (open → close) | BUY | 40 | 55.0% | 1.26 | +664 | +811 | -146 |  |
| 3 Day of the week | Wednesday night buy (previous close → Wednesday open) | BUY | 43 | 44.2% | 1.30 | +642 | +1,010 | -368 |  |
| 8 Turn of the month | Other days: day sell | SELL | 156 | 48.1% | 1.05 | +470 | +301 | +170 | ✓ |
| 3 Day of the week | Thursday day sell | SELL | 40 | 52.5% | 1.16 | +356 | +509 | -153 |  |
| 4 Gaps | Gap up > ¼ normal range → sell the open (fade) | SELL | 64 | 46.9% | 1.09 | +354 | +686 | -332 |  |
| 6 After an up / down day | Up day → next day sell | SELL | 99 | 51.5% | 1.04 | +229 | +1,235 | -1,006 |  |
| 9 After a wide / quiet day | Range > 1.5× normal → next day buy | BUY | 34 | 58.8% | 1.10 | +212 | -100 | +313 |  |
| 4 Gaps | Gap down > ¼ normal range → sell the open (follow) | SELL | 56 | 51.8% | 1.05 | +178 | -213 | +391 |  |
| 3 Day of the week | Friday night sell | SELL | 39 | 43.6% | 1.01 | +16 | +308 | -292 |  |
| 3 Day of the week | Thursday night sell | SELL | 40 | 42.5% | 1.01 | +15 | +689 | -675 |  |
| 7 Inside the day | 09:15→15:15 up → buy the last 15 minutes | BUY | 95 | 47.4% | 1.00 | -6 | -478 | +473 |  |
| 2 With the EMA 105 trend | Night buy only when 2h close > EMA 105 | BUY | 83 | 47.0% | 1.00 | -17 | -652 | +635 |  |
| 7 Inside the day | First hour up → buy 10:15, sell at close | BUY | 95 | 50.5% | 0.98 | -102 | -734 | +631 |  |
| 3 Day of the week | Wednesday day buy (open → close) | BUY | 43 | 55.8% | 0.94 | -142 | +525 | -667 |  |
| 3 Day of the week | Friday day sell | SELL | 39 | 38.5% | 0.91 | -253 | +1,248 | -1,501 |  |
| 8 Turn of the month | Last day + first 3 days: night buy | BUY | 44 | 47.7% | 0.93 | -267 | -810 | +543 |  |
| 2 With the EMA 105 trend | Night sell only when 2h close < EMA 105 | SELL | 116 | 48.3% | 0.96 | -351 | -138 | -214 |  |
| 2 With the EMA 105 trend | Day sell only when EMA 105 is down | SELL | 116 | 45.7% | 0.95 | -386 | -514 | +128 |  |
| 3 Day of the week | Friday day buy (open → close) | BUY | 39 | 53.8% | 0.86 | -404 | -1,589 | +1,185 |  |
| 6 After an up / down day | Down day → next day buy | BUY | 101 | 50.5% | 0.93 | -476 | +179 | -655 |  |
| 3 Day of the week | Wednesday day sell | SELL | 43 | 41.9% | 0.77 | -581 | -900 | +319 |  |
| 3 Day of the week | Friday night buy (previous close → Friday open) | BUY | 39 | 51.3% | 0.67 | -673 | -650 | -23 |  |
| 3 Day of the week | Thursday night buy (previous close → Thursday open) | BUY | 40 | 47.5% | 0.73 | -687 | -1,014 | +327 |  |
| 7 Inside the day | First hour down → sell 10:15, buy back at close | SELL | 104 | 47.1% | 0.88 | -720 | -1,023 | +303 |  |
| 9 After a wide / quiet day | Range > 1.5× normal → next day sell | SELL | 34 | 38.2% | 0.71 | -782 | -209 | -573 |  |
| 2 With the EMA 105 trend | Day buy only when EMA 105 is up | BUY | 83 | 44.6% | 0.84 | -843 | -1,372 | +529 |  |
| 1 Day vs night | Sell at open, buy back at close (day) | SELL | 200 | 46.5% | 0.93 | -984 | +211 | -1,195 |  |
| 3 Day of the week | Thursday day buy (open → close) | BUY | 40 | 37.5% | 0.65 | -1,028 | -833 | -196 |  |
| 4 Gaps | Gap down > ¼ normal range → buy the open (fade) | BUY | 56 | 44.6% | 0.75 | -1,110 | -322 | -787 |  |
| 6 After an up / down day | Down day → night buy | BUY | 101 | 43.6% | 0.82 | -1,304 | -1,212 | -93 |  |
| 3 Day of the week | Monday day sell | SELL | 40 | 40.0% | 0.63 | -1,334 | -1,164 | -169 |  |
| 9 After a wide / quiet day | Range < 0.7× normal → night buy | BUY | 30 | 33.3% | 0.42 | -1,363 | -1,324 | -39 |  |
| 3 Day of the week | Wednesday night sell | SELL | 43 | 46.5% | 0.56 | -1,365 | -1,384 | +20 |  |
| 4 Gaps | Gap up > ¼ normal range → buy the open (follow) | BUY | 64 | 48.4% | 0.70 | -1,430 | -1,213 | -218 |  |
| 3 Day of the week | Tuesday day buy (open → close) | BUY | 38 | 39.5% | 0.58 | -1,466 | -824 | -642 |  |
| 1 Day vs night | Sell at close, buy back next open (night) | SELL | 200 | 46.5% | 0.86 | -1,674 | -32 | -1,642 |  |
| 1 Day vs night | Buy at close, sell next open (night) | BUY | 200 | 46.0% | 0.86 | -1,686 | -1,668 | -18 |  |
| 3 Day of the week | Tuesday night sell | SELL | 38 | 50.0% | 0.35 | -1,907 | -1,682 | -225 |  |
| 10 Opening-range breakout | Break of the first-hour high (buy) or low (sell), hold to close | BOTH | 194 | 47.9% | 0.81 | -1,960 | -1,245 | -715 |  |
| 5 Where it closed | Closed in bottom ¼ → night buy (bounce) | BUY | 57 | 43.9% | 0.52 | -2,014 | -2,395 | +381 |  |
| 7 Inside the day | 09:15→15:15 down → sell the last 15 minutes | SELL | 104 | 27.9% | 0.21 | -2,030 | -994 | -1,037 |  |
| 3 Day of the week | Monday night buy (previous close → Monday open) | BUY | 40 | 45.0% | 0.46 | -2,237 | -2,391 | +154 |  |
| 1 Day vs night | Buy at open, sell at close (day) | BUY | 200 | 48.5% | 0.83 | -2,376 | -1,910 | -466 |  |

Opening-range breakout, checked twice:

| Version | Trades | Win % | PF | Net | DD |
|---|---|---|---|---|---|
| Hourly, first hour, 200 sessions | 194 | 47.9% | 0.81 | -1,960 | 3,839 |
| … first 100 | 97 | 47.4% | 0.79 | -1,245 | 1,737 |
| … last 100 | 97 | 48.5% | 0.84 | -715 | 2,134 |
| Hourly, same days as 5-min | 59 | 55.9% | 1.48 | +941 | 477 |
| 5-minute, first hour | 59 | 55.9% | 1.46 | +908 | 477 |
| 5-minute, first 15 min | 60 | 51.7% | 1.45 | +1,199 | 768 |
| 5-minute, first 30 min | 59 | 54.2% | 1.69 | +1,491 | 754 |

**Look-ahead trap found and removed:** a first version that traded only days where *one* side of the first hour broke showed 64-66% wins and PF 3+. That rule needs the day's close to know the other side never broke, so it cannot be traded. Done correctly (enter on the first break), the breakout lost money over 200 sessions.

## Jev's judgement of the combination finalists

| Rule | Reliability | Overfit risk | Jev score | Final |
|---|---|---|---|---|
| EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 68 | fair | medium | 48.2 | 59.9 |
| EMA 105 + RSI>50 + ADX>20 + Daily>EMA50 · TOP exit RSI 68 | fair | medium | 41.2 | 56.7 |
| EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 68 | fair | high | 43.2 | 56.5 |
| EMA 105 + RSI>50 + ADX>20 + Daily>EMA50 · TOP exit RSI 70 | fair | medium | 39.8 | 56.4 |
| EMA 105 + ADX>20 + Supertrend + EMA slope · TOP exit RSI 68 | fair | medium | 42.2 | 55.6 |
| EMA 105 + ADX>20 + Daily>EMA50 · TOP exit RSI 70 | fair | medium | 43.0 | 55.6 |

## Limits

- 8,056 combinations were tried; the best one is partly luck even with an unseen part. Expect live results to be weaker.
- About 3 years of 2-hour data; the unseen part holds only about 9-11 trades per setup.
- Index candles, not futures. Futures trade at a premium and gap differently at 09:15.
- Paper research. Not SEBI-registered advice. No orders are placed by this website.
