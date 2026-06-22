'use strict';

const cheerio = require('cheerio');

const CACHE = new Map();
const DAY = 24 * 60 * 60 * 1000;
const HOUR = 60 * 60 * 1000;

function nowIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

function cacheGet(key, ttlMs) {
  const hit = CACHE.get(key);
  if (!hit) return null;
  if (Date.now() - hit.time > ttlMs) return null;
  return hit.value;
}

function cacheSet(key, value) {
  CACHE.set(key, { time: Date.now(), value });
  return value;
}

async function fetchText(url, { timeoutMs = 15000, headers = {} } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36',
        accept: 'text/html,application/xhtml+xml,application/xml,text/plain,*/*',
        ...headers,
      },
    });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return await res.text();
  } finally {
    clearTimeout(timer);
  }
}

function parseCsvLine(line) {
  const out = [];
  let cur = '';
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else {
        quoted = !quoted;
      }
    } else if (ch === ',' && !quoted) {
      out.push(cur.trim());
      cur = '';
    } else {
      cur += ch;
    }
  }
  out.push(cur.trim());
  return out;
}

async function getNifty200Constituents() {
  const cached = cacheGet('nifty200', DAY);
  if (cached) return cached;
  const csv = await fetchText('https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv', {
    headers: { accept: '*/*' },
    timeoutMs: 20000,
  });
  const lines = csv.trim().split(/\r?\n/).filter(Boolean);
  const header = parseCsvLine(lines.shift());
  const rows = lines.map((line) => {
    const cols = parseCsvLine(line);
    const obj = {};
    header.forEach((h, i) => { obj[h] = cols[i]; });
    return {
      companyName: obj['Company Name'],
      industry: obj.Industry,
      symbol: obj.Symbol,
      series: obj.Series,
      isin: obj['ISIN Code'],
    };
  });
  return cacheSet('nifty200', rows);
}

async function findConstituent(symbol) {
  const normalized = String(symbol || '').trim().toUpperCase().replace(/\.NS$/, '');
  const rows = await getNifty200Constituents();
  return rows.find((r) => r.symbol.toUpperCase() === normalized) || null;
}

function mean(nums) {
  if (!nums.length) return null;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

function computeRsi(closes, period = 14) {
  if (!Array.isArray(closes) || closes.length < period + 1) return null;
  const slice = closes.slice(-(period + 1));
  let gains = 0;
  let losses = 0;
  for (let i = 1; i < slice.length; i++) {
    const diff = slice[i] - slice[i - 1];
    if (diff >= 0) gains += diff;
    else losses -= diff;
  }
  const avgGain = gains / period;
  const avgLoss = losses / period;
  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

async function getYahooQuote(symbol) {
  const normalized = String(symbol || '').trim().toUpperCase().replace(/\.NS$/, '');
  const key = `yahoo:${normalized}`;
  const cached = cacheGet(key, HOUR);
  if (cached) return cached;
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(normalized)}.NS?interval=1d&range=1y`;
  const text = await fetchText(url, { headers: { accept: 'application/json,text/plain,*/*' }, timeoutMs: 15000 });
  const json = JSON.parse(text);
  const result = json.chart && json.chart.result && json.chart.result[0];
  if (!result) throw new Error(`Yahoo chart returned no result for ${normalized}`);
  const meta = result.meta || {};
  const q = result.indicators && result.indicators.quote && result.indicators.quote[0];
  const highs = (q.high || []).filter(Number.isFinite);
  const lows = (q.low || []).filter(Number.isFinite);
  const closes = (q.close || []).filter(Number.isFinite);
  const value = {
    symbol: normalized,
    cmp: meta.regularMarketPrice ?? closes[closes.length - 1] ?? null,
    currency: meta.currency || 'INR',
    fiftyTwoWeekHigh: highs.length ? Math.max(...highs) : null,
    fiftyTwoWeekLow: lows.length ? Math.min(...lows) : null,
    dma50: closes.length >= 50 ? mean(closes.slice(-50)) : null,
    dma200: closes.length >= 200 ? mean(closes.slice(-200)) : null,
    rsi14: computeRsi(closes, 14),
    source: `Yahoo Finance chart API (${nowIsoDate()})`,
  };
  return cacheSet(key, value);
}

function parseNumber(text) {
  if (text == null) return null;
  const clean = String(text).replace(/,/g, '').replace(/[₹%x×]/g, '').trim();
  const match = clean.match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : null;
}

function metricsToValue(metrics, source, usedUrl) {
  return {
    source: `${source} (${usedUrl})`,
    raw: metrics,
    marketCapCr: metrics['Market Cap']?.value ?? null,
    currentPrice: metrics['Current Price']?.value ?? null,
    highLow: metrics['High / Low']?.raw ?? null,
    stockPE: metrics['Stock P/E']?.value ?? null,
    bookValue: metrics['Book Value']?.value ?? null,
    dividendYield: metrics['Dividend Yield']?.value ?? null,
    roce: metrics.ROCE?.value ?? null,
    roe: metrics.ROE?.value ?? null,
    faceValue: metrics['Face Value']?.value ?? null,
  };
}

function parseScreenerMarkdown(md) {
  const metrics = {};
  const keys = ['Market Cap', 'Current Price', 'High / Low', 'Stock P/E', 'Book Value', 'Dividend Yield', 'ROCE', 'ROE', 'Face Value'];
  for (const key of keys) {
    const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`${escaped}\\s+([^\\n]+)`, 'i');
    const match = md.match(re);
    if (match) {
      const raw = match[1].replace(/\\s+/g, ' ').trim();
      metrics[key] = { value: parseNumber(raw), raw };
    }
  }
  return metrics;
}


async function getScreenerMetrics(symbol) {
  const normalized = String(symbol || '').trim().toUpperCase().replace(/\.NS$/, '');
  const key = `screener:${normalized}`;
  const cached = cacheGet(key, 6 * HOUR);
  if (cached) return cached;
  const urls = [
    `https://www.screener.in/company/${encodeURIComponent(normalized)}/consolidated/`,
    `https://www.screener.in/company/${encodeURIComponent(normalized)}/`,
  ];
  let html = '';
  let usedUrl = '';
  let lastErr = null;
  for (const url of urls) {
    try {
      html = await fetchText(url, { timeoutMs: 20000 });
      usedUrl = url;
      break;
    } catch (err) {
      lastErr = err;
    }
  }
  if (html) {
    const $ = cheerio.load(html);
    const metrics = {};
    $('#top-ratios li').each((_, el) => {
      const name = $(el).find('.name').text().replace(/\s+/g, ' ').trim();
      const valueText = $(el).find('.value').text().replace(/\s+/g, ' ').trim();
      const num = parseNumber(valueText);
      if (name) metrics[name] = { value: num, raw: valueText };
    });
    if (Object.keys(metrics).length && (metrics['Stock P/E'] || metrics.ROE || metrics['Book Value'])) {
      return cacheSet(key, metricsToValue(metrics, 'Screener.in', usedUrl));
    }
  }

  for (const url of urls) {
    try {
      const readerUrl = `https://r.jina.ai/${url}`;
      const md = await fetchText(readerUrl, { timeoutMs: 25000 });
      const metrics = parseScreenerMarkdown(md);
      if (Object.keys(metrics).length) {
        return cacheSet(key, metricsToValue(metrics, 'Screener via Jina Reader fallback', readerUrl));
      }
    } catch (err) {
      lastErr = err;
    }
  }

  throw lastErr || new Error(`Screener unavailable for ${normalized}`);
}

async function getAttainixSummary(companyName, symbol) {
  const cached = cacheGet('attainix:nifty200', 12 * HOUR);
  let rows = cached;
  if (!rows) {
    const html = await fetchText('https://www.attainix.com/ICTrackerSummary.aspx?indexcode=CNX200.IN', { timeoutMs: 25000 });
    const $ = cheerio.load(html);
    rows = [];
    $('tr').each((_, tr) => {
      const tds = $(tr).find('td').map((__, td) => $(td).text().replace(/\s+/g, ' ').trim()).get();
      if (tds.length >= 12 && /^\d+$/.test(tds[0])) {
        rows.push({
          no: tds[0],
          stockName: tds[1],
          industry: tds[2],
          valuationDate: tds[3],
          marketPriceOnValuationDate: parseNumber(tds[4]),
          intrinsicPriceOnValuationDate: parseNumber(tds[5]),
          latestMarketPrice: parseNumber(tds[6]),
          latestFullMarketCapCr: parseNumber(tds[7]),
          latestFreeFloatMarketCapCr: parseNumber(tds[8]),
          mvToIv: parseNumber(tds[9]),
          kb: parseNumber(tds[10]),
          evaToNw: parseNumber(tds[11]),
          outlook: tds[12] || null,
        });
      }
    });
    cacheSet('attainix:nifty200', rows);
  }
  const wanted = String(companyName || symbol || '').toLowerCase();
  const sym = String(symbol || '').toLowerCase();
  const normalize = (s) => String(s || '').toLowerCase().replace(/limited|ltd\.?|corp(?:oration)?|company|india|bank|of|the|\.|\(|\)/g, '').replace(/\s+/g, ' ').trim();
  const target = normalize(wanted);
  let best = rows.find((r) => normalize(r.stockName) === target);
  if (!best) best = rows.find((r) => normalize(r.stockName).includes(target) || target.includes(normalize(r.stockName)));
  if (!best) best = rows.find((r) => normalize(r.stockName).replace(/\s/g, '').includes(sym));
  return best || null;
}

module.exports = {
  getNifty200Constituents,
  findConstituent,
  getYahooQuote,
  getScreenerMetrics,
  getAttainixSummary,
  parseNumber,
};
