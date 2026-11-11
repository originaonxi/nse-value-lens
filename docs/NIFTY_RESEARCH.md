# Nifty 50 research record

Generated 2026-11-11 23:32 IST from the live engines (`nifty_ema.py`, `nifty_combo.py`, `nifty_daynight.py`). Re-run `python scripts/nifty_research_md.py` to refresh. Paper research, not advice.

**Data:** NIFTY 50 index (^NSEI, Yahoo Finance). 2-hour candles 2024-03-19 → 2026-11-11 (2,594 candles). Daily candles 2016 → 2026-11-11. Hourly 2023 → today, 5-minute last ~60 sessions.

**Costs:** every trade pays 0.035% of price (≈ 9 Nifty points at 25,000).

**Honesty split:** rules are tested on 2024-03-19 → 2025-12-19 (the *tested part*) and judged on 2025-12-19 → 2026-11-11 (the *unseen part*, never used to pick). A rule is *robust* only if it makes money in both.

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
| **1** | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 68 | Best overall (the page's winner) | whole | 32 | 68.8% | 4.13 | +6,230 | 1,088 |
|  |  |  | tested | 23 | 69.6% | 3.40 | +4,242 | 1,088 |
|  |  |  | **unseen** | 9 | 66.7% | 10.09 | +1,988 | 174 |
| **2** | EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 70 | Best on the unseen part (70% win) | whole | 31 | 67.7% | 3.33 | +5,286 | 1,088 |
|  |  |  | tested | 21 | 66.7% | 3.00 | +3,394 | 1,088 |
|  |  |  | **unseen** | 10 | 70.0% | 4.28 | +1,892 | 245 |
| **3** | EMA 105 + ADX>20 + Daily>EMA50 · TOP exit RSI 70 | Fewest conditions, smallest drawdown | whole | 47 | 46.8% | 3.20 | +6,566 | 564 |
|  |  |  | tested | 33 | 45.5% | 3.25 | +4,586 | 564 |
|  |  |  | **unseen** | 14 | 50.0% | 3.10 | +1,980 | 331 |
| ref | EMA 105 alone · exit on close below | the starting point | whole | 56 | 25.0% | 1.76 | +3,494 | 1,785 |

**Worked maths for setup 1:** 32 trades, 22 winners → win rate 22 ÷ 32 = **68.8%**. Winners made 8,218.3 points, losers lost 1,988.3 → PF 8,218.3 ÷ 1,988.3 = **4.13**. Net 8,218.3 − 1,988.3 = **+6,229.9 points** ≈ ₹467,243 per lot of 75.

## How the win rate climbs toward 70% (one step at a time)

Each row adds one thing to the row above. Whole period, buy only, after costs.

| Step | Rule | Trades | Win % | PF | Net pts | Worst DD | Unseen win % | Unseen PF |
|---|---|---|---|---|---|---|---|---|
| 0 | EMA 105 · exit on close below | 56 | 25.0% | 1.76 | +3,494 | 1,785 | 19.0% | 1.32 |
| 1 | EMA 105 + ADX>20 · exit on close below | 48 | 25.0% | 1.76 | +3,348 | 1,558 | 23.5% | 1.40 |
| 2 | EMA 105 + ADX>20 + Daily>EMA50 · exit on close below | 34 | 23.5% | 1.55 | +2,156 | 1,566 | 18.2% | 1.03 |
| 3 | EMA 105 + ADX>20 + Daily>EMA50 + Supertrend · exit on close below | 26 | 26.9% | 1.42 | +1,704 | 1,458 | 12.5% | 1.16 |
| 4 | EMA 105 + ADX>20 + Daily>EMA50 + Supertrend · TOP exit RSI 70 | 31 | 67.7% | 3.65 | +5,888 | 1,088 | 77.8% | 5.90 |
| 5 | EMA 105 + ADX>20 + Daily>EMA50 + Supertrend · TOP exit RSI 68 | 32 | 68.8% | 4.13 | +6,230 | 1,088 | 66.7% | 10.09 |

What moves the number: **ADX > 20** removes trades in sideways markets (most of EMA 105's small losses). **Daily close above daily EMA 50** keeps only buys in a rising bigger trend. **Supertrend** removes late entries. The **RSI TOP exit** books the gain near the top instead of giving it back on the way down to EMA 105 - this step lifts the win rate the most.

**Best win rate by number of confirmations** (robust rules only, 20+ trades):

| Confirmations | Robust rules | Best win % | Rule |
|---|---|---|---|
| 0 | 37 | 42.9% | EMA 105 · target 2 ATR |
| 1 | 267 | 49.0% | EMA 105 + DI+>DI- · target 2 ATR |
| 2 | 972 | 60.5% | EMA 105 + Daily>EMA50 + DI+>DI- · TOP exit RSI 68 |
| 3 | 2,296 | 68.8% | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 68 |

## Where the win rate goes above 70%

- Rules with **70%+ over the whole period** and at least 10 trades: **0** of 8,056.
- Rules with **70%+ on the unseen part** (8+ trades) that also made money on the tested part: **3**:

| Rule | Tested part | Unseen part | Whole period |
|---|---|---|---|
| EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 70 | 22 tr · 63.6% · PF 3.15 · +3,921 | **9 tr · 77.8% · PF 5.90 · +1,967** | 31 tr · 67.7% · PF 3.65 · +5,888 |
| EMA 105 + ADX>20 + Supertrend + 2 closes · TOP exit RSI 70 | 27 tr · 48.1% · PF 2.48 · +3,755 | **10 tr · 70.0% · PF 4.60 · +2,311** | 37 tr · 54.1% · PF 2.91 · +6,066 |
| EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 70 | 21 tr · 66.7% · PF 3.00 · +3,394 | **10 tr · 70.0% · PF 4.28 · +1,892** | 31 tr · 67.7% · PF 3.33 · +5,286 |

- Rules that showed **70%+ on the tested part** (12+ trades): **17**. What they did next on the unseen part:

| Rule | Tested part | Unseen part |
|---|---|---|
| EMA 105 + RSI>50 + Daily>EMA50 + 0.5 ATR buffer · TOP exit 3 ATR | 26 tr · 76.9% · PF 4.27 · +2,808 | 15 tr · 40.0% · PF 0.35 · -1,169 |
| EMA 105 + RSI>50 + Daily>EMA50 + 2 closes · TOP exit 3 ATR | 26 tr · 76.9% · PF 4.16 · +2,588 | 15 tr · 40.0% · PF 0.36 · -1,071 |
| EMA 105 + RSI>50 + ADX>25 + Daily>EMA50 · TOP exit 4 ATR | 16 tr · 75.0% · PF 6.08 · +2,560 | 8 tr · 50.0% · PF 0.40 · -452 |
| EMA 105 + RSI>50 + Daily>EMA50 + DI+>DI- · TOP exit 3 ATR | 24 tr · 75.0% · PF 3.78 · +2,043 | 13 tr · 46.2% · PF 0.47 · -710 |
| EMA 105 + Daily>EMA50 + 0.5 ATR buffer + DI+>DI- · TOP exit 3 ATR | 24 tr · 75.0% · PF 3.20 · +2,024 | 13 tr · 46.2% · PF 0.45 · -784 |
| EMA 105 + MACD hist + Daily>EMA50 + DI+>DI- · TOP exit 3 ATR | 23 tr · 73.9% · PF 4.20 · +1,987 | 12 tr · 50.0% · PF 0.31 · -905 |
| EMA 105 + RSI>50 + Daily>EMA50 + EMA slope · TOP exit 3 ATR | 26 tr · 73.1% · PF 3.61 · +2,395 | 16 tr · 43.8% · PF 0.46 · -877 |
| EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 68 | 22 tr · 72.7% · PF 3.26 · +3,714 | 10 tr · 60.0% · PF 5.86 · +1,913 |
| EMA 105 + RSI>50 + ADX>25 + Daily>EMA50 · target 2 ATR | 18 tr · 72.2% · PF 1.90 · +1,833 | 7 tr · 42.9% · PF 0.55 · -681 |
| EMA 105 + ADX>25 + Supertrend + Daily>EMA50 · target 2 ATR | 18 tr · 72.2% · PF 1.90 · +1,846 | 7 tr · 42.9% · PF 0.55 · -681 |
| EMA 105 + Daily>EMA50 + DI+>DI- · TOP exit 3 ATR | 25 tr · 72.0% · PF 3.49 · +2,110 | 13 tr · 46.2% · PF 0.47 · -710 |
| EMA 105 + Daily>EMA50 + 2 closes + DI+>DI- · TOP exit 3 ATR | 25 tr · 72.0% · PF 2.90 · +1,837 | 13 tr · 46.2% · PF 0.43 · -808 |
| EMA 105 + RSI>50 + Daily>EMA50 · TOP exit 3 ATR | 28 tr · 71.4% · PF 5.04 · +2,952 | 15 tr · 40.0% · PF 0.39 · -973 |
| EMA 105 + MACD hist + Daily>EMA50 + DI+>DI- · TOP exit RSI 68 | 24 tr · 70.8% · PF 3.20 · +4,058 | 12 tr · 50.0% · PF 1.99 · +1,167 |
| EMA 105 + Daily>EMA50 + EMA slope + DI+>DI- · TOP exit 3 ATR | 24 tr · 70.8% · PF 2.59 · +1,586 | 14 tr · 50.0% · PF 0.54 · -614 |

Of those 17, **0** stayed at 70%+ on unseen data and **14** lost money. So 70%+ is reachable on a stretch of data, and the setups above did hit 70-78% on the unseen part, but no rule held 70%+ over the whole period with enough trades. ~65-69% is the honest level.

## 30 combinations side by side

Same data, same costs. Tested part / unseen part / whole period. Long only unless marked.

| # | Rule | Tested: trades · win · PF · net | Unseen: trades · win · PF · net | Whole: trades | Win % | PF | Net pts | DD | Both parts profit |
|---|---|---|---|---|---|---|---|---|---|
| 1 | EMA 105 · exit on close below | 35 · 28.6% · 2.09 · +2,861 | 21 · 19.0% · 1.32 · +633 | 56 | 25.0% | 1.76 | +3,494 | 1,785 | ✓ |
| 2 | EMA 105 · exit on close below · buy+sell | 70 · 22.9% · 1.24 · +1,579 | 42 · 21.4% · 1.53 · +1,964 | 112 | 22.3% | 1.34 | +3,543 | 1,894 | ✓ |
| 3 | EMA 105 · TOP exit RSI 70 | 45 · 33.3% · 2.75 · +5,480 | 25 · 32.0% · 2.22 · +2,559 | 70 | 32.9% | 2.54 | +8,039 | 1,124 | ✓ |
| 4 | EMA 105 · target 2 ATR | 49 · 42.9% · 2.34 · +3,690 | 28 · 42.9% · 2.21 · +2,017 | 77 | 42.9% | 2.29 | +5,708 | 861 | ✓ |
| 5 | EMA 105 · TOP exit 4 ATR | 44 · 34.1% · 2.33 · +3,623 | 25 · 32.0% · 1.30 · +618 | 69 | 33.3% | 1.88 | +4,240 | 1,252 | ✓ |
| 6 | EMA 105 · trail 3 ATR | 45 · 33.3% · 2.37 · +4,376 | 26 · 30.8% · 1.65 · +1,378 | 71 | 32.4% | 2.09 | +5,754 | 1,428 | ✓ |
| 7 | EMA 105 + RSI>50 · exit on close below | 31 · 32.3% · 1.82 · +2,330 | 18 · 11.1% · 1.07 · +174 | 49 | 24.5% | 1.48 | +2,504 | 2,244 | ✓ |
| 8 | EMA 105 + MACD hist · exit on close below | 34 · 29.4% · 1.45 · +1,537 | 17 · 11.8% · 0.93 · -179 | 51 | 23.5% | 1.22 | +1,357 | 2,597 | ✗ |
| 9 | EMA 105 + ADX>20 · exit on close below | 31 · 25.8% · 2.01 · +2,598 | 17 · 23.5% · 1.40 · +750 | 48 | 25.0% | 1.76 | +3,348 | 1,558 | ✓ |
| 10 | EMA 105 + ADX>25 · exit on close below | 24 · 33.3% · 2.21 · +2,700 | 10 · 30.0% · 0.86 · -298 | 34 | 32.4% | 1.54 | +2,401 | 1,910 | ✗ |
| 11 | EMA 105 + Supertrend · exit on close below | 28 · 35.7% · 1.63 · +1,887 | 16 · 12.5% · 0.98 · -56 | 44 | 27.3% | 1.33 | +1,831 | 2,509 | ✗ |
| 12 | EMA 105 + Daily>EMA50 · exit on close below | 27 · 29.6% · 1.82 · +2,119 | 13 · 15.4% · 0.80 · -419 | 40 | 25.0% | 1.37 | +1,699 | 2,141 | ✗ |
| 13 | EMA 105 + Daily>EMA200 · exit on close below | 33 · 27.3% · 1.53 · +1,769 | 10 · 20.0% · 0.52 · -833 | 43 | 25.6% | 1.19 | +936 | 1,821 | ✗ |
| 14 | EMA 105 + EMA slope · exit on close below | 29 · 34.5% · 1.92 · +2,368 | 18 · 11.1% · 1.11 · +231 | 47 | 25.5% | 1.56 | +2,598 | 2,153 | ✓ |
| 15 | EMA 105 + 2 closes · exit on close below | 30 · 36.7% · 1.95 · +2,526 | 19 · 10.5% · 1.12 · +270 | 49 | 26.5% | 1.57 | +2,796 | 2,170 | ✓ |
| 16 | EMA 105 + DI+>DI- · exit on close below | 27 · 37.0% · 1.82 · +2,008 | 17 · 11.8% · 1.06 · +155 | 44 | 27.3% | 1.45 | +2,163 | 2,263 | ✓ |
| 17 | EMA 105 + ADX>20 · TOP exit RSI 70 | 41 · 34.1% · 2.73 · +4,805 | 20 · 40.0% · 2.87 · +2,684 | 61 | 36.1% | 2.77 | +7,489 | 1,032 | ✓ |
| 18 | EMA 105 + ADX>20 + Daily>EMA50 · exit on close below | 23 · 26.1% · 1.90 · +2,112 | 11 · 18.2% · 1.03 · +45 | 34 | 23.5% | 1.55 | +2,156 | 1,566 | ✓ |
| 19 | EMA 105 + ADX>20 + Daily>EMA50 · TOP exit RSI 70 | 33 · 45.5% · 3.25 · +4,586 | 14 · 50.0% · 3.10 · +1,980 | 47 | 46.8% | 3.20 | +6,566 | 564 | ✓ |
| 20 | EMA 105 + ADX>20 + Supertrend · TOP exit RSI 70 | 29 · 44.8% · 2.59 · +3,957 | 11 · 63.6% · 5.66 · +2,918 | 40 | 50.0% | 3.21 | +6,875 | 1,088 | ✓ |
| 21 | EMA 105 + RSI>50 + ADX>20 · TOP exit RSI 70 | 30 · 43.3% · 2.88 · +4,598 | 14 · 50.0% · 3.89 · +2,864 | 44 | 45.5% | 3.18 | +7,462 | 1,088 | ✓ |
| 22 | EMA 105 + Daily>EMA50 + DI+>DI- · TOP exit RSI 68 | 26 · 65.4% · 3.01 · +4,183 | 12 · 50.0% · 2.08 · +1,217 | 38 | 60.5% | 2.68 | +5,400 | 1,088 | ✓ |
| 23 | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · exit on close below | 18 · 33.3% · 1.56 · +1,486 | 8 · 12.5% · 1.16 · +218 | 26 | 26.9% | 1.42 | +1,704 | 1,458 | ✓ |
| 24 | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 68 | 23 · 69.6% · 3.40 · +4,242 | 9 · 66.7% · 10.09 · +1,988 | 32 | 68.8% | 4.13 | +6,230 | 1,088 | ✓ |
| 25 | EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 70 | 22 · 63.6% · 3.15 · +3,921 | 9 · 77.8% · 5.90 · +1,967 | 31 | 67.7% | 3.65 | +5,888 | 1,088 | ✓ |
| 26 | EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 70 | 21 · 66.7% · 3.00 · +3,394 | 10 · 70.0% · 4.28 · +1,892 | 31 | 67.7% | 3.33 | +5,286 | 1,088 | ✓ |
| 27 | EMA 105 + RSI>50 + ADX>20 + Daily>EMA50 · TOP exit RSI 68 | 23 · 69.6% · 3.45 · +4,025 | 11 · 54.5% · 4.53 · +1,797 | 34 | 64.7% | 3.70 | +5,822 | 1,088 | ✓ |
| 28 | EMA 105 + ADX>20 + Supertrend + EMA slope · TOP exit RSI 68 | 27 · 63.0% · 3.14 · +4,473 | 10 · 50.0% · 6.29 · +2,096 | 37 | 59.5% | 3.65 | +6,569 | 1,088 | ✓ |
| 29 | EMA 105 + RSI>50 + ADX>25 + Daily>EMA50 · TOP exit 4 ATR | 16 · 75.0% · 6.08 · +2,560 | 8 · 50.0% · 0.40 · -452 | 24 | 66.7% | 2.68 | +2,108 | 1,008 | ✗ |
| 30 | EMA 105 + MACD hist + Daily>EMA200 + EMA slope · TOP exit 3 ATR · buy+sell | 36 · 58.3% · 2.71 · +3,314 | 19 · 57.9% · 1.88 · +975 | 55 | 58.2% | 2.41 | +4,289 | 711 | ✓ |

## Sensitivity: is the winner a lucky setting?

EMA 105 + ADX>a + Supertrend + Daily>EMA50, TOP exit at RSI r. Whole-period win % (PF).

| ADX > | RSI 65 | RSI 68 | RSI 70 | RSI 72 | RSI 75 | RSI 80 |
|---|---|---|---|---|---|---|
| 15 | 48.8% (1.71) | 57.5% (2.28) | 53.8% (2.22) | 48.6% (1.84) | 37.1% (1.36) | 33.3% (1.68) |
| 18 | 50.0% (2.31) | 59.5% (3.10) | 58.3% (2.94) | 51.4% (2.19) | 39.4% (1.57) | 35.5% (1.96) |
| 20 | 54.5% (2.89) | 68.8% (4.13) | 67.7% (3.65) | 56.7% (2.43) | 42.9% (1.69) | 38.5% (2.14) |
| 22 | 53.1% (2.61) | 67.7% (3.77) | 63.3% (3.40) | 58.6% (2.25) | 44.4% (1.57) | 40.0% (1.99) |
| 25 | 46.4% (1.64) | 55.6% (2.27) | 50.0% (2.26) | 56.0% (2.09) | 43.5% (1.56) | 42.9% (1.99) |
| 30 | 45.5% (1.56) | 45.5% (1.51) | 47.6% (1.51) | 50.0% (1.37) | 44.4% (1.18) | 50.0% (1.93) |

The best area is ADX 18-22 with an RSI top at 68-70; results fade smoothly away from it rather than jumping, so the setting is not a single lucky point.

## Independent check: daily candles 2017-11-22 → 2023-11-22 (years the 2-hour test never saw)

| Rule | Trades | Win % | PF | Net pts | Worst DD |
|---|---|---|---|---|---|
| Daily EMA 26 alone (≈ 2-hour EMA 105) | 80 | 25.0% | 2.06 | +8,146 | 1,648 |
| + ADX>20 + Supertrend + trend gate, RSI-70 TOP exit | 42 | 45.2% | 1.83 | +3,626 | 1,298 |
| + ADX>20 + Supertrend + trend gate, exit on close below | 27 | 48.1% | 2.34 | +3,653 | 532 |

The same confirmations roughly double the win rate and cut the drawdown in a completely different period, but they do not reach 70% there.

## After a TOP: does Nifty go back toward EMA 105?

21 TOP signals. Within the next 10 two-hour candles: fell at least 1 ATR **66.7%**, reached EMA 105 **38.1%**, median move back **58.0%** of the gap.

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

1,269 rules: close above EMA = up, close below = down, held to the opposite close. All timeframes ranked on the same 62 sessions (2026-08-12 → 2026-11-11); rules had to make money on BOTH up and down signals to score fully. Final = 60% numbers + 40% Jev.

| # | Candles | EMA | Signals | Up signals: hit · pts | Down signals: hit · pts | PF | Net pts | 140 sessions PF · net | Jev | Final |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 30m | 83 | 25 | 30.8% · +2,209 | 25.0% · +355 | 3.83 | +2,564 | 3.83 · +2,564 | weak | 60.9 |
| 2 | 30m | 81 | 21 | 18.2% · +2,272 | 30.0% · +417 | 4.20 | +2,689 | 4.20 · +2,689 | weak | 59.8 |
| 3 | 15m | 75 | 51 | 26.9% · +1,967 | 40.0% · +929 | 2.50 | +2,896 | 2.50 · +2,896 | weak | 56.5 |
| 4 | 1h | 187 | 14 | 14.3% · +2,003 | 42.9% · +1,015 | 6.20 | +3,018 | 1.63 · +1,601 | weak | 56.5 |
| 5 | 15m | 76 | 51 | 26.9% · +1,948 | 40.0% · +910 | 2.47 | +2,858 | 2.47 · +2,858 | weak | 56.1 |
| 6 | 15m | 77 | 51 | 23.1% · +1,913 | 40.0% · +876 | 2.38 | +2,789 | 2.38 · +2,789 | weak | 55.2 |
| 7 | 2h | 21 | 19 | 20.0% · +1,950 | 33.3% · +950 | 3.46 | +2,901 | 1.15 · +844 | weak | 53.4 |
| 8 | 75m | 31 | 15 | 25.0% · +2,205 | 42.9% · +331 | 3.53 | +2,536 | 3.53 · +2,536 | weak | 52.4 |
| 9 | 1D | 12 | 8 | 25.0% · +1,750 | 50.0% · +931 | 3.23 | +2,681 | 0.79 · -1,127 | weak | 46.6 |
| 10 | 5m | 181 | 116 | 15.5% · +1,510 | 22.4% · +484 | 1.63 | +1,994 | 1.63 · +1,994 | weak | 45.8 |

Your EMAs 5, 6, 9, 10, 11 (same rule, same dates):

| Candles | EMA 5 | EMA 6 | EMA 9 | EMA 10 | EMA 11 |
|---|---|---|---|---|---|
| 5m | -6,548 | -6,046 | -4,814 | -4,301 | -3,964 |
| 15m | -1,733 | -1,752 | -2,083 | -1,490 | -1,215 |
| 30m | -573 | -868 | -1,307 | -1,020 | -1,201 |
| 75m | -316 | +190 | +1,388 | +1,990 | +1,990 |
| 1h | -2,163 | -1,593 | -1,314 | -552 | -610 |
| 2h | -62 | -129 | +1,528 | +2,094 | +2,429 |
| 1D | +1,804 | +1,978 | +2,445 | +1,679 | +2,658 |

## Test 3: day vs night (last 200 sessions, 2026-01-19 → 2026-11-11)

Night (close → next open) **+386** points, day (open → close) **-826**, close to close **-439**. Check: night + day = close to close on every session (max error 0.0).

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
| 2026 | +317 | -1,191 | +1.8% | -4.1% |

Where the EMA 105 trades made their points:

| Rule | Trades | Overnight pts | Daytime pts |
|---|---|---|---|
| EMA 105 (buy above, sell below) | 112 | +4,253 | +237 |
| EMA 105 buy only | 56 | +6,265 | -2,298 |
| EMA 105 + confirmations (the winner) | 32 | +5,146 | +1,357 |

All 49 session rules (sorted by points after costs; ✓ = profit in both 100-session halves):

| Idea | Rule | Side | Trades | Win % | PF | Net | 1st 100 | Last 100 | Holds |
|---|---|---|---|---|---|---|---|---|---|
| 5 Where it closed | Closed in top ¼ of the day's range → night buy | BUY | 70 | 48.6% | 1.74 | +2,373 | +2,444 | -71 |  |
| 3 Day of the week | Monday night sell | SELL | 41 | 48.8% | 1.65 | +1,512 | +2,036 | -524 |  |
| 3 Day of the week | Tuesday night buy (previous close → Tuesday open) | BUY | 38 | 42.1% | 1.93 | +1,268 | +1,438 | -170 |  |
| 5 Where it closed | Closed in bottom ¼ → night sell | SELL | 57 | 50.9% | 1.40 | +1,064 | +1,796 | -732 |  |
| 3 Day of the week | Wednesday night buy (previous close → Wednesday open) | BUY | 43 | 46.5% | 1.50 | +1,020 | +1,150 | -131 |  |
| 3 Day of the week | Tuesday day sell | SELL | 38 | 60.5% | 1.37 | +827 | +444 | +382 | ✓ |
| 3 Day of the week | Monday day buy (open → close) | BUY | 41 | 53.7% | 1.24 | +624 | +811 | -187 |  |
| 4 Gaps | Gap up > ¼ normal range → sell the open (fade) | SELL | 65 | 47.7% | 1.11 | +428 | +612 | -184 |  |
| 3 Day of the week | Thursday day sell | SELL | 40 | 52.5% | 1.16 | +356 | +509 | -153 |  |
| 6 After an up / down day | Up day → next day sell | SELL | 101 | 52.5% | 1.05 | +326 | +1,112 | -786 |  |
| 2 With the EMA 105 trend | Night buy only when 2h close > EMA 105 | BUY | 85 | 48.2% | 1.08 | +304 | -543 | +848 |  |
| 4 Gaps | Gap down > ¼ normal range → sell the open (follow) | SELL | 55 | 52.7% | 1.05 | +204 | -187 | +391 |  |
| 9 After a wide / quiet day | Range > 1.5× normal → next day buy | BUY | 34 | 55.9% | 1.07 | +164 | -108 | +272 |  |
| 3 Day of the week | Friday night sell | SELL | 38 | 44.7% | 1.03 | +55 | +348 | -292 |  |
| 3 Day of the week | Thursday night sell | SELL | 40 | 42.5% | 1.01 | +15 | +689 | -675 |  |
| 7 Inside the day | First hour up → buy 10:15, sell at close | BUY | 95 | 51.6% | 1.00 | -7 | -579 | +572 |  |
| 7 Inside the day | 09:15→15:15 up → buy the last 15 minutes | BUY | 94 | 46.8% | 0.99 | -12 | -496 | +484 |  |
| 8 Turn of the month | Last day + first 3 days: night buy | BUY | 44 | 47.7% | 0.99 | -19 | -853 | +834 |  |
| 8 Turn of the month | Last day + first 3 days: day buy | BUY | 44 | 52.3% | 0.94 | -208 | -648 | +440 |  |
| 3 Day of the week | Wednesday day buy (open → close) | BUY | 43 | 53.5% | 0.90 | -242 | +550 | -792 |  |
| 3 Day of the week | Friday day sell | SELL | 38 | 39.5% | 0.91 | -246 | +1,255 | -1,501 |  |
| 8 Turn of the month | Other days: day sell | SELL | 156 | 48.1% | 0.97 | -321 | -136 | -185 |  |
| 2 With the EMA 105 trend | Night sell only when 2h close < EMA 105 | SELL | 114 | 48.2% | 0.96 | -344 | -130 | -214 |  |
| 3 Day of the week | Friday day buy (open → close) | BUY | 38 | 55.3% | 0.86 | -393 | -1,578 | +1,185 |  |
| 2 With the EMA 105 trend | Day sell only when EMA 105 is down | SELL | 114 | 45.6% | 0.95 | -437 | -565 | +128 |  |
| 6 After an up / down day | Down day → next day buy | BUY | 99 | 50.5% | 0.93 | -473 | +181 | -655 |  |
| 3 Day of the week | Wednesday day sell | SELL | 43 | 44.2% | 0.81 | -481 | -923 | +442 |  |
| 3 Day of the week | Thursday night buy (previous close → Thursday open) | BUY | 40 | 47.5% | 0.73 | -687 | -1,014 | +327 |  |
| 3 Day of the week | Friday night buy (previous close → Friday open) | BUY | 38 | 50.0% | 0.66 | -694 | -671 | -23 |  |
| 9 After a wide / quiet day | Range > 1.5× normal → next day sell | SELL | 34 | 41.2% | 0.73 | -733 | -183 | -550 |  |
| 7 Inside the day | First hour down → sell 10:15, buy back at close | SELL | 104 | 47.1% | 0.87 | -781 | -1,115 | +334 |  |
| 1 Day vs night | Sell at open, buy back at close (day) | SELL | 200 | 47.5% | 0.94 | -854 | +121 | -975 |  |
| 2 With the EMA 105 trend | Day buy only when EMA 105 is up | BUY | 85 | 43.5% | 0.82 | -975 | -1,282 | +307 |  |
| 3 Day of the week | Thursday day buy (open → close) | BUY | 40 | 37.5% | 0.65 | -1,028 | -833 | -196 |  |
| 4 Gaps | Gap down > ¼ normal range → buy the open (fade) | BUY | 55 | 43.6% | 0.75 | -1,118 | -330 | -787 |  |
| 6 After an up / down day | Down day → night buy | BUY | 99 | 43.4% | 0.82 | -1,233 | -1,140 | -93 |  |
| 1 Day vs night | Buy at close, sell next open (night) | BUY | 200 | 46.5% | 0.89 | -1,293 | -1,488 | +195 |  |
| 3 Day of the week | Monday day sell | SELL | 41 | 41.5% | 0.63 | -1,311 | -1,164 | -146 |  |
| 9 After a wide / quiet day | Range < 0.7× normal → night buy | BUY | 30 | 33.3% | 0.42 | -1,363 | -1,277 | -86 |  |
| 3 Day of the week | Tuesday day buy (open → close) | BUY | 38 | 39.5% | 0.58 | -1,466 | -768 | -698 |  |
| 4 Gaps | Gap up > ¼ normal range → buy the open (follow) | BUY | 65 | 47.7% | 0.69 | -1,522 | -1,156 | -366 |  |
| 3 Day of the week | Wednesday night sell | SELL | 43 | 44.2% | 0.49 | -1,741 | -1,523 | -219 |  |
| 3 Day of the week | Tuesday night sell | SELL | 38 | 50.0% | 0.35 | -1,907 | -1,760 | -146 |  |
| 10 Opening-range breakout | Break of the first-hour high (buy) or low (sell), hold to close | BOTH | 194 | 48.5% | 0.81 | -1,934 | -1,172 | -762 |  |
| 5 Where it closed | Closed in bottom ¼ → night buy (bounce) | BUY | 57 | 43.9% | 0.52 | -2,014 | -2,333 | +319 |  |
| 1 Day vs night | Sell at close, buy back next open (night) | SELL | 200 | 46.0% | 0.84 | -2,066 | -210 | -1,856 |  |
| 7 Inside the day | 09:15→15:15 down → sell the last 15 minutes | SELL | 105 | 27.6% | 0.20 | -2,193 | -968 | -1,225 |  |
| 3 Day of the week | Monday night buy (previous close → Monday open) | BUY | 41 | 46.3% | 0.47 | -2,200 | -2,391 | +191 |  |
| 1 Day vs night | Buy at open, sell at close (day) | BUY | 200 | 48.0% | 0.82 | -2,506 | -1,818 | -687 |  |

Opening-range breakout, checked twice:

| Version | Trades | Win % | PF | Net | DD |
|---|---|---|---|---|---|
| Hourly, first hour, 200 sessions | 194 | 48.5% | 0.81 | -1,934 | 3,838 |
| … first 100 | 97 | 48.5% | 0.80 | -1,172 | 1,833 |
| … last 100 | 97 | 48.5% | 0.83 | -762 | 2,133 |
| Hourly, same days as 5-min | 61 | 55.7% | 1.36 | +766 | 477 |
| 5-minute, first hour | 61 | 55.7% | 1.34 | +732 | 477 |
| 5-minute, first 15 min | 62 | 50.0% | 1.30 | +892 | 768 |
| 5-minute, first 30 min | 61 | 52.5% | 1.45 | +1,143 | 754 |

**Look-ahead trap found and removed:** a first version that traded only days where *one* side of the first hour broke showed 64-66% wins and PF 3+. That rule needs the day's close to know the other side never broke, so it cannot be traded. Done correctly (enter on the first break), the breakout lost money over 200 sessions.

## Jev's judgement of the combination finalists

| Rule | Reliability | Overfit risk | Jev score | Final |
|---|---|---|---|---|
| EMA 105 + ADX>20 + Daily>EMA50 · TOP exit RSI 70 | good | medium | 49.6 | 61.0 |
| EMA 105 + ADX>20 + Supertrend + Daily>EMA50 · TOP exit RSI 68 | fair | medium | 48.8 | 60.1 |
| EMA 105 + RSI>50 + ADX>20 + Daily>EMA50 · TOP exit RSI 70 | fair | medium | 43.8 | 58.0 |
| EMA 105 + ADX>20 + Daily>EMA50 · TOP exit RSI 68 | fair | medium | 46.2 | 57.8 |
| EMA 105 + RSI>50 + ADX>20 + Daily>EMA50 · TOP exit RSI 68 | fair | medium | 40.4 | 56.4 |
| EMA 105 + ADX>20 + Daily>EMA50 + DI+>DI- · TOP exit RSI 68 | fair | high | 42.0 | 56.0 |

## Limits

- 8,056 combinations were tried; the best one is partly luck even with an unseen part. Expect live results to be weaker.
- About 3 years of 2-hour data; the unseen part holds only about 9-11 trades per setup.
- Index candles, not futures. Futures trade at a premium and gap differently at 09:15.
- Paper research. Not SEBI-registered advice. No orders are placed by this website.
