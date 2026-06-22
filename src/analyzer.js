'use strict';

const {
  findConstituent,
  getYahooQuote,
  getScreenerMetrics,
  getAttainixSummary,
} = require('./adapters');
const fs = require('fs');
const path = require('path');

let preAnalyzedDb = {};
try {
  preAnalyzedDb = require(path.join(__dirname, '..', 'data', 'pre_analyzed.json'));
} catch (_e) {}


function fmtMoney(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return 'n/a';
  return `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: digits, minimumFractionDigits: digits })}`;
}

function fmtNum(n, digits = 2, suffix = '') {
  if (n == null || Number.isNaN(n)) return 'n/a';
  return `${Number(n).toLocaleString('en-IN', { maximumFractionDigits: digits, minimumFractionDigits: digits })}${suffix}`;
}

function fmtPct(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return 'n/a';
  return `${Number(n).toLocaleString('en-IN', { maximumFractionDigits: digits, minimumFractionDigits: digits })}%`;
}

function pct(n, digits = 0) {
  if (n == null || Number.isNaN(n)) return 'n/a';
  return `${(n * 100).toLocaleString('en-IN', { maximumFractionDigits: digits, minimumFractionDigits: digits })}%`;
}

function table(headers, rows) {
  const line = `| ${headers.join(' | ')} |`;
  const sep = `| ${headers.map(() => '---').join(' | ')} |`;
  return [line, sep, ...rows.map((r) => `| ${r.join(' | ')} |`)].join('\n');
}

function isPsuBank(companyName, symbol) {
  return /bank/i.test(companyName || '') && [
    'BANKBARODA', 'BANKINDIA', 'CANBK', 'INDIANB', 'PNB', 'SBIN', 'UNIONBANK', 'CENTRALBK', 'MAHABANK',
  ].includes(String(symbol).toUpperCase());
}

function classifyFramework(constituent) {
  const name = constituent.companyName || '';
  const symbol = constituent.symbol || '';
  const industry = constituent.industry || '';
  if (/bank/i.test(name)) return 'bank';
  if (/Financial Services/i.test(industry) || /finance|financial|housing|muthoot|credit|rural electrification|power finance/i.test(name)) {
    return 'lender';
  }
  return 'industrial';
}

function classifyDiscount(constituent, metrics) {
  const symbol = constituent.symbol;
  const name = constituent.companyName;
  const industry = constituent.industry;
  const pe = metrics.pe;
  const pb = metrics.pb;
  const roe = metrics.roe;

  if (isPsuBank(name, symbol)) {
    return {
      label: 'Structural (PSU bank discount) — possibly mispriced if asset quality keeps improving',
      reason: 'Government ownership creates a persistent discount: directed lending risk, lower operating flexibility, priority-sector exposure, slower tech execution and political capital-allocation risk.',
      trap: 'GNPA/NNPA rises again, provision coverage weakens, NIM falls below cost-of-equity assumptions, or government-directed lending creates a new credit-cycle shock.',
    };
  }
  if (['BPCL', 'IOC', 'HINDPETRO'].includes(symbol)) {
    return {
      label: 'Regulated + cyclical OMC discount',
      reason: 'Oil-marketing earnings depend on crude, refining spreads and whether the government allows fuel-price pass-through. A low PE can be peak earnings, not permanent cheapness.',
      trap: 'Brent crude spikes while retail petrol/diesel prices are frozen; under-recoveries return and earnings collapse.',
    };
  }
  if (symbol === 'COALINDIA') {
    return {
      label: 'Cyclical + ESG/coal-transition discount',
      reason: 'Coal assets are penalised by ESG flows and long-term energy-transition risk, even when current ROE/ROCE and dividends are strong.',
      trap: 'E-auction premiums collapse, wage costs rise faster than volumes, or coal demand peaks earlier than expected.',
    };
  }
  if (['NMDC', 'SAIL', 'HINDALCO', 'HINDZINC', 'VEDL', 'NATIONALUM', 'TATASTEEL', 'JSWSTEEL', 'JINDALSTEL'].includes(symbol) || /Metals|Mining/i.test(industry)) {
    return {
      label: 'Commodity-cycle discount',
      reason: 'Metals/mining companies often look optically cheap near cycle-high earnings. The market discounts iron ore, steel, zinc/aluminium price volatility.',
      trap: 'Commodity realisations fall faster than volumes grow; the current PE expands mechanically because earnings drop.',
    };
  }
  if (symbol === 'MUTHOOTFIN') {
    return {
      label: 'Regulatory gold-loan NBFC discount',
      reason: 'The market discounts RBI scrutiny of gold loans, LTV caps, auction practices and concentration in one collateral class.',
      trap: 'Gold price falls sharply, RBI caps yields/LTV further, funding spreads widen, or Stage-III loans rise.',
    };
  }
  if (/Capital Goods/i.test(industry)) {
    return {
      label: pe && pe > 40 ? 'Growth/momentum valuation — not a low-PE value discount' : 'Capex-cycle discount',
      reason: 'Capital-goods stocks re-rate with order books and execution. Low valuation can mean market doubts margin conversion; high valuation means execution is already priced in.',
      trap: 'Order inflow slows or execution/margins disappoint.',
    };
  }
  if (pe != null && roe != null && pe < 15 && roe > 15) {
    return {
      label: 'Possible mispricing — low PE with high return ratios',
      reason: `PE ${fmtNum(pe, 2)}× with ROE ${fmtPct(roe)} suggests market is assigning a discount despite decent capital efficiency.`,
      trap: 'Earnings are one-off, cyclically elevated, or governance/capital-allocation risk is larger than headline metrics show.',
    };
  }
  if (pb != null && roe != null && pb < 1.2 && roe > 12) {
    return {
      label: 'Asset-value discount — low PB near/under book',
      reason: `PB ${fmtNum(pb, 2)}× while ROE is ${fmtPct(roe)} implies the market doubts sustainability of returns.`,
      trap: 'ROE falls below cost of equity or book value quality is impaired.',
    };
  }
  return {
    label: 'No obvious value discount from headline ratios',
    reason: 'The app did not detect a clear low-valuation/high-return mismatch from free-source metrics.',
    trap: 'Treat as watchlist-only until manual metrics or deeper research prove an actual mispricing.',
  };
}

function finitePositive(n) {
  return Number.isFinite(n) && n > 0;
}

function coerceNumber(value, key) {
  if (value == null || value === '') return null;
  const n = Number(String(value).replace(/[%₹,x×]/g, '').trim());
  if (!Number.isFinite(n)) return null;
  const percentFields = new Set(['roe', 'roce', 'dividendYield', 'gnpa', 'nnpa', 'pcr', 'car', 'nim', 'slippage', 'loanGrowth', 'earningsGrowth']);
  if (percentFields.has(key) && n > 1000) return null;
  if (['pe', 'pb', 'bookValue', 'marketCapCr', 'patCr'].includes(key) && n <= 0) return null;
  return n;
}

function extractManual(manual = {}) {
  if (!manual || typeof manual !== 'object') return {};
  const allowed = new Set(['pe', 'pb', 'bookValue', 'roe', 'roce', 'dividendYield', 'marketCapCr', 'gnpa', 'nnpa', 'pcr', 'car', 'nim', 'slippage', 'loanGrowth', 'patCr', 'earningsGrowth']);
  const normalized = {};
  for (const [k, v] of Object.entries(manual)) {
    const key = String(k).trim();
    if (!allowed.has(key)) continue;
    const n = coerceNumber(v, key);
    if (n != null) normalized[key] = n;
  }
  return normalized;
}

function makeMetrics(constituent, quote, screener, manual = {}) {
  const cmp = quote.cmp ?? screener.currentPrice ?? null;
  const pe = manual.pe ?? screener.stockPE ?? null;
  const bookValue = manual.bookValue ?? screener.bookValue ?? null;
  const pb = manual.pb ?? (bookValue && cmp ? cmp / bookValue : null);
  return {
    cmp,
    pe,
    pb,
    bookValue,
    roe: manual.roe ?? screener.roe ?? null,
    roce: manual.roce ?? screener.roce ?? null,
    dividendYield: manual.dividendYield ?? screener.dividendYield ?? null,
    marketCapCr: manual.marketCapCr ?? screener.marketCapCr ?? null,
    gnpa: manual.gnpa ?? null,
    nnpa: manual.nnpa ?? null,
    pcr: manual.pcr ?? null,
    car: manual.car ?? null,
    nim: manual.nim ?? null,
    slippage: manual.slippage ?? null,
    loanGrowth: manual.loanGrowth ?? null,
    patCr: manual.patCr ?? null,
    earningsGrowth: manual.earningsGrowth ?? null,
  };
}

function targetPeFor(constituent, pe) {
  const symbol = constituent.symbol;
  const industry = constituent.industry || '';
  if (['BPCL', 'IOC', 'HINDPETRO'].includes(symbol)) return 9;
  if (symbol === 'COALINDIA') return 12;
  if (/Metals|Mining/i.test(industry)) return 15;
  if (/Oil Gas/i.test(industry)) return 10;
  if (/Fast Moving Consumer Goods|Consumer/i.test(industry)) return 35;
  if (/Capital Goods/i.test(industry)) return pe && pe > 40 ? Math.min(pe, 50) : 20;
  if (/Information Technology/i.test(industry)) return 22;
  if (/Healthcare/i.test(industry)) return 28;
  return 18;
}

function lenderValuation(metrics, framework) {
  const roe = metrics.roe;
  const pb = metrics.pb;
  if (!finitePositive(roe) || !finitePositive(pb)) return null;
  const coe = framework === 'bank' ? 12.5 : 13.0;
  const growth = framework === 'bank' ? 5.0 : 7.0;
  let fairPb = null;
  if (roe > growth && coe > growth) fairPb = (roe - growth) / (coe - growth);
  else fairPb = roe / coe;
  const cap = framework === 'bank' ? 1.8 : 4.0;
  fairPb = Math.max(0.3, Math.min(fairPb, cap));
  const upside = fairPb / pb - 1;
  return { fairPb, upside, coe, growth };
}

function industrialValuation(constituent, metrics) {
  if (!finitePositive(metrics.pe)) return null;
  const targetPe = targetPeFor(constituent, metrics.pe);
  const earningsGrowth = Number.isFinite(metrics.earningsGrowth) ? metrics.earningsGrowth : 0;
  const upside = (targetPe / metrics.pe) * (1 + earningsGrowth / 100) - 1;
  return { targetPe, earningsGrowth, upside };
}

function formatMetricRows(framework, metrics, quote, screener, attainix) {
  const rows = [
    ['CMP', fmtMoney(metrics.cmp), quote.source],
    ['52W Range', `${fmtMoney(quote.fiftyTwoWeekLow, 0)} – ${fmtMoney(quote.fiftyTwoWeekHigh, 0)}`, quote.source],
    ['50 DMA', fmtMoney(quote.dma50), 'Yahoo close series, computed'],
    ['200 DMA', fmtMoney(quote.dma200), 'Yahoo close series, computed'],
    ['RSI (14d)', fmtNum(quote.rsi14, 2), 'Yahoo close series, simple approximation'],
    ['PE', metrics.pe == null ? 'n/a' : `~${fmtNum(metrics.pe, 2)}×`, screener.source],
    ['PB', metrics.pb == null ? 'n/a' : `~${fmtNum(metrics.pb, 2)}×`, metrics.bookValue ? 'CMP / Screener book value' : 'Manual/source'],
    ['ROE', fmtPct(metrics.roe), screener.source],
  ];
  if (framework === 'industrial') {
    rows.push(['ROCE', fmtPct(metrics.roce), screener.source]);
    rows.push(['Dividend Yield', fmtPct(metrics.dividendYield), screener.source]);
  } else {
    rows.push(['GNPA Ratio', metrics.gnpa == null ? 'manual metric not supplied' : fmtPct(metrics.gnpa), 'Manual/filing input recommended']);
    rows.push(['NNPA Ratio', metrics.nnpa == null ? 'manual metric not supplied' : fmtPct(metrics.nnpa), 'Manual/filing input recommended']);
    rows.push(['Provision Coverage', metrics.pcr == null ? 'manual metric not supplied' : fmtPct(metrics.pcr), 'Manual/filing input recommended']);
    rows.push(['CAR / Tier-1', metrics.car == null ? 'manual metric not supplied' : fmtPct(metrics.car), 'Manual/filing input recommended']);
    rows.push(['NIM / Spread', metrics.nim == null ? 'manual metric not supplied' : fmtPct(metrics.nim), 'Manual/filing input recommended']);
    rows.push(['Loan Book Growth', metrics.loanGrowth == null ? 'manual metric not supplied' : fmtPct(metrics.loanGrowth), 'Manual/filing input recommended']);
  }
  if (attainix) {
    rows.push(['Attainix MV/IV', attainix.mvToIv == null ? 'n/a' : `${fmtNum(attainix.mvToIv, 2)} (${fmtMoney(attainix.intrinsicPriceOnValuationDate)} IV vs ${fmtMoney(attainix.latestMarketPrice)} latest)`, 'Attainix icTracker']);
    rows.push(['Attainix Outlook', attainix.outlook || 'n/a', 'Attainix icTracker']);
  }
  return rows;
}

function buildPrompt({ constituent, quote, screener, attainix, framework, metrics, discount }) {
  return `You are an Indian equity research analyst. Produce a concise speculative research note for ${constituent.symbol} (${constituent.companyName}), a Nifty 200 stock.\n\nUse this framework: ${framework === 'industrial' ? 'industrial metrics (PE/PB/EV-EBITDA/ROE/ROCE/FCF/net-debt)' : 'lender metrics (P/B vs ROE, GNPA, NNPA, PCR, CAR, NIM, slippage, loan growth; do NOT use industrial D/E or EV/EBITDA)'}\n\nData:\n- CMP: ${fmtMoney(metrics.cmp)}\n- 52W range: ${fmtMoney(quote.fiftyTwoWeekLow)} - ${fmtMoney(quote.fiftyTwoWeekHigh)}\n- PE: ${metrics.pe}\n- PB: ${metrics.pb}\n- ROE: ${metrics.roe}%\n- ROCE: ${metrics.roce}%\n- Dividend yield: ${metrics.dividendYield}%\n- Attainix MV/IV: ${attainix?.mvToIv ?? 'n/a'}\n- Discount type: ${discount.label}\n\nRequired output sections:\n1. Metric table with values and sources\n2. Why it looks cheap\n3. Honest reason for the discount\n4. Why this may NOT be a value trap\n5. Re-rating math using Gordon PB model for lenders or PE expansion for industrials\n6. Value-trap condition\n7. Thesis invalidation level\n8. Not financial advice disclaimer`; 
}

function buildReport({ constituent, quote, screener, attainix, manual = {} }) {
  const framework = classifyFramework(constituent);
  const metrics = makeMetrics(constituent, quote, screener, manual);
  const discount = classifyDiscount(constituent, metrics);
  const rows = formatMetricRows(framework, metrics, quote, screener, attainix);
  const metricTitle = framework === 'industrial' ? 'Industrial Metric' : (framework === 'bank' ? 'Bank/Lender Metric' : 'NBFC/Lender Metric');

  let valuationText = '';
  let doubleScenario = '';
  if (framework === 'industrial') {
    const val = industrialValuation(constituent, metrics);
    if (val) {
      const targetPrice = finitePositive(metrics.cmp) ? metrics.cmp * (1 + val.upside) : null;
      valuationText = `Rough PE sensitivity: target PE ${fmtNum(val.targetPe, 1)}× / current PE ${fmtNum(metrics.pe, 2)}× × earnings growth factor ${(1 + val.earningsGrowth / 100).toFixed(2)} = implied upside ${pct(val.upside, 0)}. This is conditional on earnings being sustainable; for cyclicals, low PE can be peak-cycle earnings.`;
      doubleScenario = targetPrice
        ? `If earnings hold and the market assigns ${fmtNum(val.targetPe, 1)}× PE, implied price is roughly ${fmtMoney(targetPrice)}. A true 100% scenario needs either a higher target multiple, earnings growth, or both.`
        : `CMP is unavailable, so the app cannot translate PE sensitivity into a price target.`;
    } else {
      valuationText = 'PE was not available from free sources, so the app cannot compute a reliable PE re-rating case without manual input.';
      doubleScenario = 'Paste PE/EPS or EV/EBITDA data to compute a quantified double scenario.';
    }
  } else {
    const val = lenderValuation(metrics, framework);
    if (val) {
      const targetPrice = finitePositive(metrics.cmp) ? metrics.cmp * (1 + val.upside) : null;
      valuationText = `Rough Gordon-style PB sensitivity: fair PB ≈ (ROE ${fmtPct(metrics.roe)} - growth ${fmtPct(val.growth)}) / (cost of equity ${fmtPct(val.coe)} - growth ${fmtPct(val.growth)}) = ${fmtNum(val.fairPb, 2)}×. Current PB is ${fmtNum(metrics.pb, 2)}×, implying ${pct(val.upside, 0)} potential if ROE, credit quality, and funding costs are sustainable.`;
      doubleScenario = targetPrice
        ? `If ROE persists and PB re-rates to ${fmtNum(val.fairPb, 2)}×, implied price is roughly ${fmtMoney(targetPrice)}. A 100% case requires ROE improvement, book-value growth, or a higher PB justified by cleaner asset quality.`
        : `CMP is unavailable, so the app cannot translate PB sensitivity into a price target.`;
    } else {
      valuationText = 'ROE/PB was not available from free sources, so the app cannot compute Gordon PB sensitivity without manual input.';
      doubleScenario = 'Paste PB and ROE to compute a lender-specific double scenario.';
    }
  }

  const technical = quote.cmp && quote.dma200
    ? `Technically, CMP is ${pct(quote.cmp / quote.dma200 - 1, 0)} versus the 200 DMA and ${pct(quote.cmp / quote.fiftyTwoWeekHigh - 1, 0)} from the 52-week high. Simple RSI(14) approximation is ${fmtNum(quote.rsi14, 1)}.`
    : 'Technical positioning could not be fully computed from Yahoo data.';

  const sourceNotes = [
    'Yahoo Finance chart API for price/52W/DMAs/RSI',
    'Screener.in for headline ratios where available',
    'Official NSE Indices CSV for Nifty 200 membership',
    attainix ? 'Attainix icTracker for MV/IV secondary valuation' : 'Attainix unavailable or unmatched for this ticker',
    framework !== 'industrial' ? 'For lender-specific GNPA/NNPA/CAR/NIM, paste latest filing values if free scrape misses them' : 'For industrial balance-sheet quality, verify debt/cash/FCF from latest annual report',
  ];

  let cheapnessText = '';
  if (metrics.pe != null && metrics.roe != null && metrics.pe < 15 && metrics.roe > 15) {
    cheapnessText = `Headline valuation shows PE ${fmtNum(metrics.pe, 2)}× against ROE ${fmtPct(metrics.roe)}. That is a genuine low-PE/high-ROE value signal if earnings are sustainable.`;
  } else if (metrics.pb != null && metrics.roe != null && metrics.pb < 1.2 && metrics.roe > 12) {
    cheapnessText = `PB ${fmtNum(metrics.pb, 2)}× against ROE ${fmtPct(metrics.roe)} suggests an asset-value discount if book value quality is sound.`;
  } else if (metrics.pe != null && metrics.pe > 40) {
    cheapnessText = `This does NOT look statistically cheap on PE: ${fmtNum(metrics.pe, 2)}×. The report treats it as a growth/momentum case, not a value case.`;
  } else if (metrics.pe != null && metrics.roe != null) {
    cheapnessText = `Headline valuation shows PE ${fmtNum(metrics.pe, 2)}× against ROE ${fmtPct(metrics.roe)}. This is not automatically cheap; sustainability and sector context decide whether it is value or a trap.`;
  } else {
    cheapnessText = 'Headline PE/ROE data is incomplete from free sources; use manual input or verify filings before drawing a value conclusion.';
  }

  let attainixText = '';
  if (attainix?.mvToIv != null) {
    if (attainix.mvToIv < 0.85) attainixText = `Attainix MV/IV is ${fmtNum(attainix.mvToIv, 2)}, so its model sees market value below intrinsic value.`;
    else if (attainix.mvToIv > 1.15) attainixText = `Attainix MV/IV is ${fmtNum(attainix.mvToIv, 2)}, so its model sees market value ABOVE intrinsic value — not a value signal.`;
    else attainixText = `Attainix MV/IV is ${fmtNum(attainix.mvToIv, 2)}, roughly around its modelled intrinsic value.`;
  }

  const sym = String(constituent.symbol).trim().toUpperCase();
  const preBaked = preAnalyzedDb[sym];
  if (preBaked && preBaked.wording) {
    discount.label = preBaked.wording.discountLabel;
    discount.reason = preBaked.wording.discountReason;
    discount.trap = preBaked.wording.trap;
    valuationText = preBaked.wording.whyNotTrap;
    doubleScenario = preBaked.wording.doubleScenario;
    cheapnessText = preBaked.wording.whyCheap;
    attainixText = '';
  }

  const invalidationText = preBaked && preBaked.wording && preBaked.wording.invalidation
    ? preBaked.wording.invalidation
    : `Price invalidation: watch for a weekly close below the 200 DMA (${fmtMoney(quote.dma200)}), unless the stock is a deep cyclic where commodity/fundamental triggers matter more. Fundamental invalidation: the value-trap condition above materialises.`;

  const markdown = `# ${constituent.symbol} · ${constituent.companyName}\n\n**Sector:** ${constituent.industry} · **Nifty 200:** ✅ verified via official NSE Indices CSV  \n**Discount type:** ${discount.label}  \n**Metrics framework:** ${framework === 'industrial' ? 'Industrial metrics apply — PE/PB/ROE/ROCE/FCF/net-debt.' : 'LENDER metrics apply — D/E and EV/EBITDA are not primary valuation tools.'}\n\n${table([metricTitle, 'Value', 'Source'], rows)}\n\n## Technical setup\n${technical}\n\n## Why it looks cheap / or does not\n${cheapnessText} ${attainixText}\n\n## Honest reason for the discount\n${discount.reason}\n\n## Why this may NOT be a pure value trap\n${valuationText}\n\n## Re-rating / double scenario\n${doubleScenario}\n\n## Value-trap condition\n${discount.trap}\n\n## Thesis invalidation level\n${invalidationText}\n\n## Source caveats\n${sourceNotes.map((s) => `- ${s}`).join('\n')}\n\n> ⚠️ This is a speculative research report generated from free public sources. It is NOT financial advice, NOT a buy/sell recommendation, and not a substitute for a SEBI-registered investment advisor. Free-source scraping can fail or go stale; verify critical figures from exchange filings before investing.`;
  return {
    markdown,
    data: { constituent, quote, screener, attainix, framework, metrics, discount },
    prompt: buildPrompt({ constituent, quote, screener, attainix, framework, metrics, discount }),
  };
}

async function analyzeSymbol(symbol, manual = {}) {
  const constituent = await findConstituent(symbol);
  if (!constituent) {
    throw new Error(`${symbol} was not found in the official Nifty 200 CSV. Try the exact NSE symbol, e.g. BANKBARODA, POLYCAB, MUTHOOTFIN.`);
  }
  const [quote, screener] = await Promise.all([
    getYahooQuote(constituent.symbol).catch((err) => ({
      symbol: constituent.symbol,
      cmp: null,
      fiftyTwoWeekHigh: null,
      fiftyTwoWeekLow: null,
      dma50: null,
      dma200: null,
      rsi14: null,
      source: `Yahoo failed: ${err.message}`,
    })),
    getScreenerMetrics(constituent.symbol).catch((err) => ({ source: `Screener failed: ${err.message}`, raw: {} })),
  ]);
  const attainix = await getAttainixSummary(constituent.companyName, constituent.symbol).catch(() => null);
  const sym = constituent.symbol.toUpperCase();
  const preBaked = preAnalyzedDb[sym];
  const mergedManual = preBaked && preBaked.manual
    ? { ...preBaked.manual, ...extractManual(manual) }
    : extractManual(manual);
  return buildReport({ constituent, quote, screener, attainix, manual: mergedManual });
}

module.exports = {
  analyzeSymbol,
  classifyFramework,
  classifyDiscount,
  lenderValuation,
  industrialValuation,
};
