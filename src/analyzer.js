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

let preBakedReports = {};
try {
  preBakedReports = require(path.join(__dirname, '..', 'data', 'pre_baked_reports.json'));
} catch (_e) {}

// ── Budget 2022–2026 Theme Data ──────────────────────────────────────────────
// `nifty200` = Nifty 200 confirmed symbols only (analyzable in this app).
// `themeOnly` = reference names NOT in Nifty 200 — display only, never added as buttons.
const BUDGET_THEMES = {
  power_transmission: {
    label: '⚡ Power Grid & Electrification',
    tagline: 'Every government priority — railways, factories, data centres, EVs, renewables — needs more transmission capacity first.',
    budgetCatalyst: '2025–26: intra-state transmission, HVDC, grid-scale batteries, clean-tech manufacturing, energy security.',
    nifty200: ['POWERGRID', 'POWERINDIA', 'GVT&D', 'ENRIN', 'CGPOWER', 'BHEL', 'POLYCAB', 'KEI'],
    themeOnly: ['KEC International', 'Kalpataru Projects', 'Transformers & Rectifiers India'],
  },
  defence: {
    label: '🛡️ Defence & Strategic Self-Reliance',
    tagline: 'National security + import substitution + high-value manufacturing exports. Consistent 5-year priority across all Budgets.',
    budgetCatalyst: 'All 5 Budgets: indigenisation, PLI defence, export push, strategic shipbuilding.',
    nifty200: ['BEL', 'HAL', 'BDL', 'MAZDOCK', 'COCHINSHIP', 'SOLARINDS'],
    themeOnly: ['Garden Reach Shipbuilders (GRSE)', 'Data Patterns', 'Astra Microwave', 'MTAR Technologies'],
  },
  railways: {
    label: '🚆 Railways & Urban Transport',
    tagline: '7 high-speed corridors in 2026 Budget. Suppliers of propulsion/signalling/cables earn more durably than pure PSU contractors.',
    budgetCatalyst: '2026: 7 high-speed corridors, city economic regions, Tier-II/III urban infrastructure.',
    nifty200: ['LT', 'SIEMENS', 'ABB', 'CGPOWER', 'RVNL'],
    themeOnly: ['BEML', 'Titagarh Rail Systems', 'Jupiter Wagons', 'IRCON', 'RITES', 'RailTel', 'Texmaco Rail'],
  },
  capex_capital_goods: {
    label: '🏗️ Roads, Construction & Capital Goods',
    tagline: 'FY27 capex ₹11.2 lakh Cr. 2026 Budget: domestic machinery — tunnel-boring, lifts, firefighting systems.',
    budgetCatalyst: 'All 5 Budgets: Gati Shakti, roads, railways, water, housing. 2026: domestic machinery manufacturing push.',
    nifty200: ['LT', 'CUMMINSIND', 'BHEL', 'ABB', 'SIEMENS'],
    themeOnly: ['NCC', 'KEC International', 'Kalpataru Projects', 'HG Infra', 'PNC Infratech', 'Ashoka Buildcon', 'Thermax', 'AIA Engineering'],
  },
  electronics_semicon: {
    label: '🔬 Electronics & Semiconductor Supply Chain',
    tagline: 'India Semiconductor Mission 2.0 in 2026 Budget. ₹40,000 Cr components scheme. Deeper chain beats final-assembly plays.',
    budgetCatalyst: '2026: ISM 2.0, domestic IP, PCB, packaging, testing, design services, ₹40,000 Cr components scheme.',
    nifty200: ['DIXON', 'CGPOWER', 'TATAELXSI'],
    themeOnly: ['Kaynes Technology', 'Syrma SGS Technology', 'Cyient DLM', 'Avalon Technologies', 'Amber Enterprises'],
  },
  critical_minerals: {
    label: '⛏️ Critical Minerals & Rare Earths',
    tagline: 'Rare earth corridors in Odisha, Kerala, AP, TN. Domestic refining → magnets → motors, EVs, defence.',
    budgetCatalyst: '2025: critical-mineral recovery. 2026: rare-earth corridors in 4 states.',
    nifty200: ['NMDC', 'NATIONALUM', 'COALINDIA', 'HINDALCO', 'HINDZINC'],
    themeOnly: ['Hindustan Copper', 'MOIL', 'GMDC', 'Lloyds Metals & Energy', 'Gravita India'],
  },
  nuclear_energy: {
    label: '⚛️ Nuclear & Energy Security',
    tagline: '₹20,000 Cr SMR mission, 5 indigenous SMRs by 2033. 5–15 year theme — not an immediate earnings catalyst.',
    budgetCatalyst: '2025: ₹20,000 Cr Small Modular Reactor mission, 5 indigenous SMRs by 2033.',
    nifty200: ['BHEL', 'LT', 'NTPC'],
    themeOnly: ['Walchandnagar Industries', 'MTAR Technologies', 'Kirloskar Brothers', 'KSB Limited', 'Thermax', 'Power Mech Projects'],
  },
  shipbuilding_ports: {
    label: '🚢 Shipbuilding, Ports & Container Mfg',
    tagline: '₹25,000 Cr Maritime Fund (2025) + ₹10,000 Cr container-manufacturing programme (2026).',
    budgetCatalyst: '2025: ₹25,000 Cr Maritime Development Fund. 2026: ₹10,000 Cr container manufacturing.',
    nifty200: ['COCHINSHIP', 'MAZDOCK', 'ADANIPORTS'],
    themeOnly: ['Garden Reach Shipbuilders (GRSE)', 'Shipping Corporation of India', 'JSW Infrastructure', 'Great Eastern Shipping'],
  },
  biopharma: {
    label: '💊 Biopharma & Healthcare Manufacturing',
    tagline: 'Biopharma SHAKTI: ₹10,000 Cr over 5 years — biologics, biosimilars, 1,000+ clinical-trial sites.',
    budgetCatalyst: '2026: Biopharma SHAKTI — ₹10,000 Cr, biologics, biosimilars, 1,000+ clinical sites.',
    nifty200: ['BIOCON', 'DRREDDY', 'ZYDUSLIFE', 'LAURUSLABS', 'DIVISLAB'],
    themeOnly: ['Syngene International', 'Gland Pharma', 'Neuland Laboratories', 'Sai Life Sciences'],
  },
  water_infra: {
    label: '💧 Water, Pipes & Urban Infrastructure',
    tagline: 'Jal Jeevan extended to 2028. ₹1 lakh Cr Urban Challenge Fund for city water and sanitation.',
    budgetCatalyst: '2025: Jal Jeevan Mission extended to 2028 + ₹1 lakh Cr Urban Challenge Fund.',
    nifty200: ['LT', 'SUPREMEIND'],
    themeOnly: ['VA Tech Wabag', 'EMS Limited', 'Ion Exchange', 'Jash Engineering', 'Welspun Corp', 'Prince Pipes'],
  },
};

// Reverse map: Nifty 200 symbol → array of theme keys (built once at startup)
const SYMBOL_TO_THEMES = {};
for (const [key, theme] of Object.entries(BUDGET_THEMES)) {
  for (const sym of theme.nifty200) {
    if (!SYMBOL_TO_THEMES[sym]) SYMBOL_TO_THEMES[sym] = [];
    SYMBOL_TO_THEMES[sym].push(key);
  }
}

function classifyBudgetTheme(symbol) {
  return SYMBOL_TO_THEMES[String(symbol).toUpperCase()] || [];
}
// ─────────────────────────────────────────────────────────────────────────────

// ── Budget 2026 Highest-Quality Shortlist ────────────────────────────────────
// Source: 5-Budget Union Budget analysis (FY2022–FY2027).
// `policyScore` = policy-directness score (40–90); math bonus added from real pre-baked data.
// Non-Nifty-200 stocks have symbol:null — reference-only, not analyzable in this app.
const BUDGET_SHORTLIST = [
  {
    rank: 1, name: 'Larsen & Toubro', symbol: 'LT', nifty200: true,
    themes: ['capex_capital_goods', 'railways', 'nuclear_energy', 'water_infra'],
    rationale: 'Broadest capex proxy — defence, metros, railways, power, water, hydrocarbons, semiconductors and heavy engineering. May not rise fastest, but is the most diversified expression of India capex.',
    policyScore: 88,
  },
  {
    rank: 2, name: 'Bharat Electronics', symbol: 'BEL', nifty200: true,
    themes: ['defence'],
    rationale: 'Defence electronics diversified across army, navy and air force systems. Indigenisation moat with R&D capability. Consistent 5-Budget beneficiary.',
    policyScore: 85,
  },
  {
    rank: 3, name: 'Power Grid Corp', symbol: 'POWERGRID', nifty200: true,
    themes: ['power_transmission', 'nuclear_energy'],
    rationale: 'National transmission backbone — every government ambition (EVs, factories, data centres, railways, renewables) requires more transmission capacity first.',
    policyScore: 82,
  },
  {
    rank: 4, name: 'HAL', symbol: 'HAL', nifty200: true,
    themes: ['defence'],
    rationale: '₹1.89 lakh Cr order book (Mar 2025). Defence aircraft manufacturing and maintenance with a multi-decade indigenisation pipeline.',
    policyScore: 81,
  },
  {
    rank: 5, name: 'CG Power', symbol: 'CGPOWER', nifty200: true,
    themes: ['power_transmission', 'railways', 'electronics_semicon'],
    rationale: 'Rare multi-theme industrial: grid equipment, traction motors, railway electrification and semiconductor expansion — three themes converging in one business.',
    policyScore: 83,
  },
  {
    rank: 6, name: 'Polycab India', symbol: 'POLYCAB', nifty200: true,
    themes: ['power_transmission'],
    rationale: 'Electrification and cables — every building, EV, renewable project and data centre is a repeat customer. Structural demand, not episodic.',
    policyScore: 79,
  },
  {
    rank: 7, name: 'Siemens', symbol: 'SIEMENS', nifty200: true,
    themes: ['railways', 'capex_capital_goods', 'power_transmission'],
    rationale: 'Industrial automation, rail electrification and energy transition hardware across three capex themes simultaneously.',
    policyScore: 78,
  },
  {
    rank: 8, name: 'Cochin Shipyard', symbol: 'COCHINSHIP', nifty200: true,
    themes: ['shipbuilding_ports', 'defence'],
    rationale: 'Direct beneficiary of ₹25,000 Cr Maritime Fund + ₹10,000 Cr container programme. Naval + commercial shipbuilding with defence overlap.',
    policyScore: 76,
  },
  {
    rank: 9, name: 'Kaynes Technology', symbol: null, nifty200: false,
    themes: ['electronics_semicon'],
    rationale: 'Deeper electronics chain — PCBs, semiconductor packaging, IoT modules. ISM 2.0 most direct listed beneficiary. Not in Nifty 200 — not analyzable here.',
    policyScore: 72,
  },
  {
    rank: 10, name: 'VA Tech Wabag', symbol: null, nifty200: false,
    themes: ['water_infra'],
    rationale: 'Water treatment, sewage and industrial water reuse. Jal Jeevan Mission + ₹1 lakh Cr Urban Challenge Fund direct play. Not in Nifty 200 — not analyzable here.',
    policyScore: 68,
  },
];

// Compute formula-based confidence for a shortlist entry.
// Returns confidence:null when real metric data is absent — never fabricates a score.
// policyScore is kept separate and must NOT be mixed into confidence.
function computeShortlistConfidence(entry) {
  // Non-Nifty-200: no metric data possible in this app.
  if (!entry.symbol) {
    return { confidence: null, status: 'theme-ref-only', signals: [], scoredSignals: 0 };
  }

  const preBaked = preAnalyzedDb[entry.symbol] || {};
  const m = preBaked.manual || {};

  // No pre-baked data: live analysis needed for a real score.
  if (Object.keys(m).length === 0) {
    return { confidence: null, status: 'pending', signals: ['Run analysis to compute score from live data'], scoredSignals: 0 };
  }

  // ── Signal scoring: each signal contributes 0-33 pts from real inputs only ──
  let totalPts = 0;
  let maxPts = 0;
  const signals = [];

  // Signal A: Earnings Yield vs India 10Y G-Sec proxy (7%). Needs: pe.
  if (m.pe && m.pe > 0) {
    maxPts += 33;
    const ey = +(100 / m.pe).toFixed(2);
    const spread = +(ey - 7.0).toFixed(2);
    let pts = 0;
    if (spread >= 5)       { pts = 33; signals.push(`EY ${ey}% — strong +${spread}% over G-Sec 7%`); }
    else if (spread >= 2)  { pts = 22; signals.push(`EY ${ey}% — positive +${spread}% over G-Sec 7%`); }
    else if (spread >= 0)  { pts = 11; signals.push(`EY ${ey}% — marginal +${spread}% over G-Sec 7%`); }
    else                   { pts =  0; signals.push(`EY ${ey}% — below G-Sec 7% (${spread}%); growth stock, not value`); }
    totalPts += pts;
  }

  // Signal B: ROCE vs WACC proxy (11%). Needs: roce.
  if (m.roce) {
    maxPts += 33;
    const spread = +(m.roce - 11).toFixed(2);
    let pts = 0;
    if (spread > 15)       { pts = 33; signals.push(`ROCE ${m.roce}% vs WACC ~11% (+${spread}% — strong value creator)`); }
    else if (spread > 8)   { pts = 22; signals.push(`ROCE ${m.roce}% vs WACC ~11% (+${spread}%)`); }
    else if (spread > 0)   { pts = 11; signals.push(`ROCE ${m.roce}% vs WACC ~11% (+${spread}% — marginal)`); }
    else                   { pts =  0; signals.push(`ROCE ${m.roce}% — at or below WACC proxy`); }
    totalPts += pts;
  }

  // Signal C: PEG ratio. Needs: pe + earningsGrowth (earningsGrowth must come from manual input).
  if (m.pe && m.pe > 0 && m.earningsGrowth && m.earningsGrowth > 0) {
    maxPts += 33;
    const peg = +(m.pe / m.earningsGrowth).toFixed(2);
    let pts = 0;
    if (peg < 1)           { pts = 33; signals.push(`PEG ${peg}× — strong value-growth signal`); }
    else if (peg < 1.5)    { pts = 22; signals.push(`PEG ${peg}× — reasonable`); }
    else if (peg < 2)      { pts = 11; signals.push(`PEG ${peg}× — fairly priced`); }
    else                   { pts =  0; signals.push(`PEG ${peg}× — priced for perfection`); }
    totalPts += pts;
  }

  if (maxPts === 0) {
    return { confidence: null, status: 'pending', signals: ['Pre-baked data lacks the metrics needed (pe/roce/earningsGrowth) — run live analysis'], scoredSignals: 0 };
  }

  const confidence = Math.round((totalPts / maxPts) * 100);
  return { confidence, status: 'scored', signals, scoredSignals: maxPts / 33 };
}

function getShortlist() {
  return BUDGET_SHORTLIST.map(entry => {
    const scored = computeShortlistConfidence(entry);
    return {
      ...entry,
      confidence: scored.confidence,          // null = no real data
      confidenceStatus: scored.status,        // 'scored' | 'pending' | 'theme-ref-only'
      mathSignals: scored.signals,            // what drove the score
      scoredSignals: scored.scoredSignals,    // how many formula signals contributed
      // policyScore kept as-is — displayed separately, never conflated with confidence
      themeLabels: entry.themes.map(k => BUDGET_THEMES[k]?.label || k),
    };
  });
}
// ─────────────────────────────────────────────────────────────────────────────


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
  if (['HAL', 'BEL', 'BDL', 'MAZDOCK', 'COCHINSHIP'].includes(symbol)) {
    return {
      label: 'Defence-PSU order-book + execution discount',
      reason: 'Market re-rates on order-book visibility and delivery cadence. PSU governance, lump-sum fixed-price contracts and long revenue-recognition cycles create an episodic discount vs private-sector peers.',
      trap: 'Order inflows slow, execution slips, margins compress on fixed-price contracts, or defence capex is deferred in a future Budget.',
    };
  }
  if (['POWERGRID'].includes(symbol)) {
    return {
      label: 'Regulated utility — high visibility, bounded upside',
      reason: 'POWERGRID earns a regulated ROE (~15%) on a tariff-based model. Earnings upside is bounded by regulation. Transmission capex optionality is real but takes years to earn through.',
      trap: 'Unfavourable tariff revision, capex approval delays for new transmission projects, or RoE regulation tightened further.',
    };
  }
  if (['POWERINDIA', 'GVT&D', 'ENRIN'].includes(symbol)) {
    return {
      label: 'Electrification equipment — growth premium, execution risk',
      reason: 'Transformer and T&D equipment makers re-rate on the transmission capex supercycle. The valuation prices in sustained order inflows; a slowdown or margin miss re-rates them sharply lower.',
      trap: 'Order additions slow, project execution delays expand working capital, or competitive pressure from imports compresses margins.',
    };
  }
  if (['RVNL'].includes(symbol)) {
    return {
      label: 'Railway infrastructure PSU — single-client + order-timing discount',
      reason: 'RVNL executes government railway projects with stable but thin margins. Market discounts concentration in one government client, lumpy order timing, and limited pricing power on fixed-cost contracts.',
      trap: 'Budget capex deferral to railways, project delays, or input-cost overruns on fixed-price bids.',
    };
  }
  if (['POLYCAB', 'KEI'].includes(symbol)) {
    return {
      label: 'Electrification growth premium — not a value discount',
      reason: 'Cables and wires companies re-rate on India electrification demand (buildings, infra, EVs, renewables). These trade at growth multiples; PE contraction is the primary risk if volume growth disappoints.',
      trap: 'Copper input cost spike without pricing power, slowdown in real estate/infra starts, or a major new entrant compresses spreads.',
    };
  }
  if (['NTPC', 'NHPC'].includes(symbol)) {
    return {
      label: 'Regulated power generator — earnings visibility, bounded PE',
      reason: 'Government-owned power generators earn regulated ROEs. Market caps valuation because earnings surprise is limited. NTPC renewable expansion adds optionality but also execution and capital-allocation risk.',
      trap: 'Fuel cost absorption with delayed tariff pass-through, renewable capex delays, or policy-directed below-cost power supply.',
    };
  }
  if (['BIOCON', 'LAURUSLABS', 'ZYDUSLIFE'].includes(symbol)) {
    return {
      label: 'Biopharma R&D + USFDA regulatory discount',
      reason: 'Biosimilar and generic pharma carry USFDA approval risk, clinical trial burn, and pricing pressure in developed markets. Budget SHAKTI (₹10,000 Cr) is long-dated; near-term earnings depend on regulatory execution.',
      trap: 'USFDA import alert or warning letter, clinical-trial failure, key-product pricing erosion in the US, or SHAKTI disbursement delays.',
    };
  }
  if (['DIXON', 'TATAELXSI'].includes(symbol)) {
    return {
      label: pe && pe > 40 ? 'Electronics/IT growth premium — valuation is the primary risk' : 'Electronics supply chain — capex cycle discount',
      reason: 'DIXON trades at a premium on PLI-linked assembly volume growth. TATAELXSI on design services and embedded software for EVs/broadcast. Both face valuation risk if growth misses expectations.',
      trap: 'PLI targets missed, customer concentration risk (DIXON: Samsung/Apple), or TATAELXSI project ramp slowdown in the auto segment.',
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

// ── Formula helpers — each gated strictly on real available inputs ────────────

// Earnings Yield = 1/PE × 100. Compare vs India 10Y G-Sec proxy (~7%).
// Only shown when PE is a real finite positive number.
function earningsYieldVsGsec(metrics) {
  if (!finitePositive(metrics.pe)) return null;
  const ey = +(100 / metrics.pe).toFixed(2);
  const gsec = 7.0;
  return { ey, gsec, spread: +(ey - gsec).toFixed(2) };
}

// Graham Number = √(22.5 × EPS × BV/share).
// EPS derived as CMP/PE (trailing). Only shown when CMP, PE and bookValue are all real.
function grahamNumber(metrics) {
  if (!finitePositive(metrics.cmp) || !finitePositive(metrics.pe) || !finitePositive(metrics.bookValue)) return null;
  const eps = metrics.cmp / metrics.pe;
  const gn = Math.sqrt(22.5 * eps * metrics.bookValue);
  return { value: +gn.toFixed(2), marginOfSafety: +((gn - metrics.cmp) / gn).toFixed(4) };
}

// PEG = PE / earningsGrowth. Only shown when earningsGrowth > 0 from manual input.
function pegRatio(metrics) {
  if (!finitePositive(metrics.pe) || !Number.isFinite(metrics.earningsGrowth) || metrics.earningsGrowth <= 0) return null;
  return +(metrics.pe / metrics.earningsGrowth).toFixed(2);
}

// ROCE vs WACC proxy — shown whenever ROCE is a real number.
// India WACC proxy: ~11% for most industrials.
function capitalQuality(metrics) {
  if (!Number.isFinite(metrics.roce) || metrics.roce == null) return null;
  const waccProxy = 11;
  const spread = +(metrics.roce - waccProxy).toFixed(2);
  const label = spread > 6 ? 'Strong value creator' : spread > 0 ? 'Adequate (above WACC)' : 'Potential value destroyer — ROCE below WACC proxy';
  return { spread, waccProxy, label };
}

// Dividend DDM: P = D₁ / (r – g). Cost of equity ~11%, terminal growth ~3%.
// Gated on: symbol in DDM_ELIGIBLE set, real dividendYield, real CMP.
// Only for PSU high-yield plays with stable policy-backed dividends.
const DDM_ELIGIBLE = new Set(['COALINDIA', 'NTPC', 'POWERGRID', 'RECLTD', 'PFC', 'ONGC', 'GAIL', 'IOC', 'HINDPETRO', 'BPCL', 'NHPC']);
function dividendDDM(symbol, metrics) {
  if (!DDM_ELIGIBLE.has(String(symbol).toUpperCase())) return null;
  if (!finitePositive(metrics.cmp) || !finitePositive(metrics.dividendYield)) return null;
  const d0 = metrics.cmp * (metrics.dividendYield / 100);
  const r = 11;
  const g = 3;
  if (r <= g) return null;
  const d1 = d0 * (1 + g / 100);
  const fairValue = d1 / ((r - g) / 100);
  return {
    d0: +d0.toFixed(2),
    d1: +d1.toFixed(2),
    fairValue: +fairValue.toFixed(2),
    impliedUpside: +((fairValue / metrics.cmp) - 1).toFixed(4),
  };
}
// ─────────────────────────────────────────────────────────────────────────────

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
  // Formula rows — each gated on real inputs, never displayed from missing/assumed data
  const ey = earningsYieldVsGsec(metrics);
  if (ey) {
    rows.push(['Earnings Yield', `${fmtNum(ey.ey, 2)}%`, `1/PE×100; India 10Y G-Sec proxy ~${ey.gsec}% → spread ${ey.spread >= 0 ? '+' : ''}${ey.spread}%`]);
  }
  if (framework === 'industrial') {
    const gn = grahamNumber(metrics);
    if (gn) {
      const mos = gn.marginOfSafety >= 0
        ? `${pct(gn.marginOfSafety, 0)} below GN (margin of safety exists)`
        : `${pct(-gn.marginOfSafety, 0)} above GN — CMP exceeds Graham value`;
      rows.push(['Graham Number', fmtMoney(gn.value, 0), `√(22.5 × CMP/PE × BV/share) — ${mos}`]);
    }
    const peg = pegRatio(metrics);
    if (peg != null) {
      rows.push(['PEG Ratio', `${fmtNum(peg, 2)}×`, 'PE ÷ earnings-growth % (manual). <1 = cheap growth; >2 = priced for perfection.']);
    }
    const cq = capitalQuality(metrics);
    if (cq) {
      rows.push(['ROCE vs WACC', `${cq.spread >= 0 ? '+' : ''}${cq.spread}%`, `ROCE ${fmtPct(metrics.roce)} − WACC proxy ~${cq.waccProxy}% — ${cq.label}`]);
    }
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

  // Budget theme section — only populated if this symbol is in SYMBOL_TO_THEMES
  const budgetThemeKeys = classifyBudgetTheme(constituent.symbol);
  let budgetThemeSection = '';
  if (budgetThemeKeys.length > 0) {
    const themeLines = budgetThemeKeys.map((k) => {
      const t = BUDGET_THEMES[k];
      return `**${t.label}**  \n${t.tagline}  \n_Budget catalyst: ${t.budgetCatalyst}_`;
    }).join('\n\n');
    budgetThemeSection = `\n\n## Budget 2022–2026 Theme Alignment\n${themeLines}`;
  }

  // DDM — only for PSU dividend plays, only when dividendYield + CMP are real
  const ddm = dividendDDM(constituent.symbol, metrics);
  let ddmSection = '';
  if (ddm) {
    ddmSection = `\n\n## Dividend Discount Model (DDM)\nD₀ = CMP × div yield = ${fmtMoney(ddm.d0)} | D₁ = ${fmtMoney(ddm.d1)} | cost of equity ~11% | terminal growth ~3%  \nFair value = D₁ ÷ (r − g) ≈ **${fmtMoney(ddm.fairValue)}**  \nImplied upside from DDM: **${pct(ddm.impliedUpside, 0)}**  \n_DDM suits PSU dividend plays with policy-backed payouts. Breaks down if payout ratio changes or ROE falls._`;
  }

  const markdown = `# ${constituent.symbol} · ${constituent.companyName}\n\n**Sector:** ${constituent.industry} · **Nifty 200:** ✅ verified via official NSE Indices CSV  \n**Discount type:** ${discount.label}  \n**Metrics framework:** ${framework === 'industrial' ? 'Industrial metrics apply — PE/PB/ROE/ROCE/FCF/net-debt.' : 'LENDER metrics apply — D/E and EV/EBITDA are not primary valuation tools.'}${budgetThemeSection}\n\n${table([metricTitle, 'Value', 'Source'], rows)}\n\n## Technical setup\n${technical}\n\n## Why it looks cheap / or does not\n${cheapnessText} ${attainixText}\n\n## Honest reason for the discount\n${discount.reason}\n\n## Why this may NOT be a pure value trap\n${valuationText}\n\n## Re-rating / double scenario\n${doubleScenario}${ddmSection}\n\n## Value-trap condition\n${discount.trap}\n\n## Thesis invalidation level\n${invalidationText}\n\n## Source caveats\n${sourceNotes.map((s) => `- ${s}`).join('\n')}\n\n> ⚠️ This is a speculative research report generated from free public sources. It is NOT financial advice, NOT a buy/sell recommendation, and not a substitute for a SEBI-registered investment advisor. Free-source scraping can fail or go stale; verify critical figures from exchange filings before investing.`;
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
  const sym = constituent.symbol.toUpperCase();
  const hasManual = manual && typeof manual === 'object' && Object.keys(manual).length > 0;
  if (preBakedReports[sym] && !hasManual) {
    const quote = { symbol: sym, cmp: null, source: 'Pre-baked' };
    const screener = { source: 'Pre-baked', raw: {} };
    const attainix = null;
    const preBakedData = preAnalyzedDb[sym] || {};
    const framework = classifyFramework(constituent);
    const metrics = makeMetrics(constituent, quote, screener, preBakedData.manual || {});
    const discount = classifyDiscount(constituent, metrics);
    if (preBakedData.wording) {
      discount.label = preBakedData.wording.discountLabel;
      discount.reason = preBakedData.wording.discountReason;
      discount.trap = preBakedData.wording.trap;
    }
    return buildReport({ constituent, quote, screener, attainix: null, manual: preBakedData.manual || {} });
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
  classifyBudgetTheme,
  BUDGET_THEMES,
  BUDGET_SHORTLIST,
  getShortlist,
  lenderValuation,
  industrialValuation,
  earningsYieldVsGsec,
  grahamNumber,
  pegRatio,
  capitalQuality,
  dividendDDM,
};
