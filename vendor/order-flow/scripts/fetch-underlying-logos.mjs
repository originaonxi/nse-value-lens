/**
 * Underlying logos, from Wikidata → Wikimedia Commons.
 *
 * WHY THIS SOURCE. A company logo is a trademark, and most of them are hosted
 * on Wikipedia under a non-free "fair use" tag that we may not redistribute.
 * Wikimedia COMMONS is the opposite: it only accepts files that are freely
 * licensed or below the threshold of originality (`PD-textlogo`), which is
 * what most Indian wordmarks are. Wikidata's P154 ("logo image") points only
 * at Commons files, so following that claim keeps us on the redistributable
 * side by construction. Every file's source page and licence are recorded in
 * the manifest so the provenance survives the download.
 *
 * Trademark still belongs to the issuer. These marks identify the instrument
 * being quoted — nominative use — and must never be drawn as an endorsement.
 *
 * Usage:
 *   node scripts/fetch-underlying-logos.mjs            # every underlying
 *   node scripts/fetch-underlying-logos.mjs NIFTY TCS  # just these
 *   node scripts/fetch-underlying-logos.mjs --limit 5  # first five
 *
 * Writes public/brand/underlyings/<SYMBOL>.<ext> plus manifest.json, and
 * prints every symbol it could not resolve so the gap is visible rather than
 * silently falling back to a monogram.
 */
import { readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT_DIR = join(ROOT, 'public/brand/underlyings');
/* Wikimedia asks automated clients to identify themselves and give a contact
   page. The product's own site is that contact; no personal address is sent. */
const UA = 'OrderFlowLogoFetch/1.0 (+https://github.com/MrChartist/order-flow) node-fetch';
const PAUSE_MS = 180;

/* An index is a brand of the exchange that publishes it, so its mark is the
   exchange's. Anything not listed here is searched by its company name. */
const INDEX_OWNER = {
  NIFTY: 'National Stock Exchange of India',
  BANKNIFTY: 'National Stock Exchange of India',
  FINNIFTY: 'National Stock Exchange of India',
  MIDCPNIFTY: 'National Stock Exchange of India',
  NIFTYNXT50: 'National Stock Exchange of India',
  SENSEX: 'Bombay Stock Exchange',
  SENSEX50: 'Bombay Stock Exchange',
  BANKEX: 'Bombay Stock Exchange',
  FOCIT: 'Bombay Stock Exchange',
};

/** Names whose Wikidata search lands on the wrong item without a nudge. */
const SEARCH_HINT = {
  ABB: 'ABB India Limited',
  AMBER: 'Amber Enterprises',
  BEL: 'Bharat Electronics',
  CAMS: 'Computer Age Management Services',
  CDSL: 'Central Depository Services',
  HAL: 'Hindustan Aeronautics',
  IEX: 'Indian Energy Exchange',
  IRFC: 'Indian Railway Finance Corporation',
  LTF: 'L&T Finance',
  MCX: 'Multi Commodity Exchange',
  PFC: 'Power Finance Corporation',
  RVNL: 'Rail Vikas Nigam Limited',
  SBIN: 'State Bank of India',
  TCS: 'Tata Consultancy Services',
  /* Each of these resolved to a real company that was simply the wrong one:
     REC to an engineering college in Chennai, Blue Star to a Greek ferry
     line, Phoenix to one of its own shopping centres, Tech Mahindra to the
     parent group's brand. */
  RECLTD: 'REC Limited',
  BLUESTARCO: 'Blue Star (company)',
  PHOENIXLTD: 'The Phoenix Mills',
  TECHM: 'Tech Mahindra',
};

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

async function api(url) {
  const response = await fetch(url, { headers: { 'User-Agent': UA, Accept: 'application/json' } });
  if (!response.ok) throw new Error(`${response.status} ${url.slice(0, 90)}`);
  return response.json();
}

/** Candidate Wikidata items for a name, best first. */
async function searchEntities(term) {
  const url = `https://www.wikidata.org/w/api.php?action=wbsearchentities&search=${encodeURIComponent(term)}&language=en&uselang=en&type=item&limit=6&format=json&origin=*`;
  const data = await api(url);
  return (data.search ?? []).map(item => ({ id: item.id, label: item.label, description: item.description ?? '' }));
}

/** The claims we care about: the logo file, the country, and what it is. */
async function entityFacts(ids) {
  const url = `https://www.wikidata.org/w/api.php?action=wbgetentities&ids=${ids.join('|')}&props=claims&format=json&origin=*`;
  const data = await api(url);
  const out = {};
  for (const [id, entity] of Object.entries(data.entities ?? {})) {
    const claims = entity.claims ?? {};
    const value = (property, path = 'value') => claims[property]?.[0]?.mainsnak?.datavalue?.[path];
    out[id] = {
      logo: value('P154'),
      website: value('P856'),
      country: claims.P17?.[0]?.mainsnak?.datavalue?.value?.id ?? null,
      instanceOf: (claims.P31 ?? []).map(claim => claim.mainsnak?.datavalue?.value?.id).filter(Boolean),
    };
  }
  return out;
}

const INDIA = 'Q668';
/** business, enterprise, public company, bank, stock exchange, conglomerate … */
const ORG_CLASSES = new Set(['Q4830453', 'Q6881511', 'Q891723', 'Q783794', 'Q22687', 'Q11691', 'Q43229', 'Q161726', 'Q4830453', 'Q1589009', 'Q18388277']);

const normalise = text => (text || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
const SUFFIXES = ['', 'LIMITED', 'LTD', 'INDIA', 'INDIALIMITED', 'INDIALTD', 'CORPORATION', 'CORPORATIONLIMITED', 'GROUP', 'COMPANY'];

/**
 * Does this item actually name the company we asked for?
 *
 * The gate exists because a bare search is happy to answer "ITC" with
 * "itch.io" — same three opening letters, a real logo on Commons, and
 * nothing else in common. Prefix matching would have let that through, so
 * the label must equal the name, or the name plus one ordinary suffix.
 */
function labelMatchesName(label, name) {
  const target = normalise(name);
  const candidate = normalise(label);
  if (!target || !candidate) return false;
  return SUFFIXES.some(suffix => candidate === target + suffix || target === candidate + suffix);
}

const IGNORED_WORDS = new Set(['LIMITED', 'LTD', 'INDIA', 'INDIAN', 'THE', 'AND', 'CORPORATION', 'COMPANY', 'GROUP', 'BANK', 'FINANCE', 'FINANCIAL', 'SERVICES', 'INDUSTRIES', 'ENTERPRISES', 'PHARMA', 'PHARMACEUTICALS', 'MOTORS', 'STEEL', 'CEMENT', 'POWER', 'ENERGY', 'LABORATORIES', 'LABS', 'TECHNOLOGIES', 'CHEMICALS']);

/**
 * Do the two names share a distinguishing word?
 *
 * The India check alone is far too loose: "Zydus Lifesciences" matched
 * CADILA PHARMACEUTICALS — a different company that happens to be Indian —
 * and shipped its stopwatch favicon. Generic industry words are ignored, so
 * the overlap has to be the part of the name that identifies the firm.
 */
function sharesDistinguishingWord(label, name) {
  const words = text => new Set((String(text).toUpperCase().match(/[A-Z]{4,}/g) ?? []).filter(word => !IGNORED_WORDS.has(word)));
  const left = words(label);
  for (const word of words(name)) if (left.has(word)) return true;
  return false;
}

/** Pick the candidate that is an Indian organisation and carries a logo. */
function pickEntity(candidates, facts, { requireIndia, name, needsAsset = true }) {
  const scored = candidates.map(candidate => {
    const fact = facts[candidate.id];
    // The article path only needs the item itself; a logo claim or a website
    // is required only when the file is coming from Wikidata directly.
    if (needsAsset && !fact?.logo && !fact?.website) return null;
    if (!fact) return null;
    // Hard gate: an Indian entity, or an item whose own label is the company.
    const named = labelMatchesName(candidate.label, name);
    const related = named || sharesDistinguishingWord(candidate.label, name);
    if (requireIndia && !related) return null;
    let score = 0;
    if (named) score += 3;
    if (fact.logo) score += 4;
    if (fact.country === INDIA) score += 3;
    if (fact.instanceOf.some(id => ORG_CLASSES.has(id))) score += 2;
    if (/company|manufacturer|bank|corporation|enterprise|conglomerate|business|exchange/i.test(candidate.description)) score += 1;
    if (requireIndia && fact.country && fact.country !== INDIA) score -= 2;
    return { ...candidate, logo: fact.logo, website: fact.website, score };
  }).filter(Boolean);
  scored.sort((a, b) => b.score - a.score);
  return scored[0] ?? null;
}

/** Download the Commons file, preferring the original SVG. */
async function downloadLogo(fileName, symbol) {
  const isSvg = /\.svg$/i.test(fileName);
  const base = `https://commons.wikimedia.org/wiki/Special:FilePath/${encodeURIComponent(fileName)}`;
  const url = isSvg ? base : `${base}?width=256`;
  const response = await fetch(url, { headers: { 'User-Agent': UA }, redirect: 'follow' });
  if (!response.ok) throw new Error(`file ${response.status}`);
  const type = response.headers.get('content-type') ?? '';
  const ext = isSvg ? 'svg' : type.includes('png') ? 'png' : type.includes('jpeg') ? 'jpg' : null;
  if (!ext) throw new Error(`unsupported type ${type}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  if (bytes.length < 200) throw new Error('file too small');
  await writeFile(join(OUT_DIR, `${symbol}.${ext}`), bytes);
  return { file: `${symbol}.${ext}`, bytes: bytes.length, aspect: aspectOf(bytes, ext) };
}

/**
 * Fallback: the company's own site icon, from the official website Wikidata
 * records. Lower fidelity than a vector logo, but it is the issuer's own
 * artwork rather than a guess.
 */
async function downloadSiteIcon(website, symbol) {
  const host = new URL(website).hostname.replace(/^www\./, '');
  /* Highest resolution first. A 16px .ico rendered into a 22px tile at 2x is
     visibly soft, so the 128px PNG is tried before the favicon service. */
  const sources = [
    { url: `https://www.google.com/s2/favicons?sz=128&domain=${host}`, min: 700 },
    { url: `https://icons.duckduckgo.com/ip3/${host}.ico`, min: 200 },
  ];
  let lastError = 'no source';
  for (const source of sources) {
    try {
      const response = await fetch(source.url, { headers: { 'User-Agent': UA }, redirect: 'follow' });
      if (!response.ok) { lastError = `icon ${response.status}`; continue; }
      const bytes = Buffer.from(await response.arrayBuffer());
      // A 16px placeholder weighs a few hundred bytes; a real 128px mark does not.
      if (bytes.length < source.min) { lastError = `icon too small (${bytes.length}B)`; continue; }
      const type = response.headers.get('content-type') ?? '';
      const ext = type.includes('png') ? 'png' : type.includes('svg') ? 'svg' : 'ico';
      await writeFile(join(OUT_DIR, `${symbol}.${ext}`), bytes);
      return { file: `${symbol}.${ext}`, bytes: bytes.length, host };
    } catch (error) {
      lastError = error.message;
    }
  }
  throw new Error(lastError);
}

/**
 * Width ÷ height, from the bytes themselves — no image library.
 *
 * It decides whether a mark can survive a 22px square. Roughly half of the
 * logos on Commons are WORDMARKS: a company name set in type, four or five
 * times wider than it is tall. Contained in a small square that becomes an
 * illegible hairline, so anything wider than 1.8:1 is swapped for the
 * issuer's site emblem, which is drawn square by design.
 */
function aspectOf(bytes, ext) {
  if (ext === 'svg') {
    const text = bytes.toString('utf8').slice(0, 4000);
    const box = text.match(/viewBox\s*=\s*["']\s*[-\d.]+[ ,]+[-\d.]+[ ,]+([\d.]+)[ ,]+([\d.]+)/i);
    if (box) return Number(box[1]) / Number(box[2]);
    const width = text.match(/\swidth\s*=\s*["']([\d.]+)/i);
    const height = text.match(/\sheight\s*=\s*["']([\d.]+)/i);
    if (width && height && Number(height[1]) > 0) return Number(width[1]) / Number(height[1]);
    return null;
  }
  if (ext === 'png' && bytes.length > 24 && bytes.readUInt32BE(0) === 0x89504e47) {
    const width = bytes.readUInt32BE(16);
    const height = bytes.readUInt32BE(20);
    return height > 0 ? width / height : null;
  }
  return null;
}

const MAX_ASPECT = 1.8;

async function resolve(entry) {
  const terms = [];
  if (INDEX_OWNER[entry.symbol]) terms.push(INDEX_OWNER[entry.symbol]);
  else {
    if (SEARCH_HINT[entry.symbol]) terms.push(SEARCH_HINT[entry.symbol]);
    terms.push(entry.name, `${entry.name} Limited`, `${entry.name} India`);
  }
  for (const term of terms) {
    if (!term) continue;
    const candidates = await searchEntities(term);
    if (!candidates.length) { await sleep(PAUSE_MS); continue; }
    const facts = await entityFacts(candidates.map(candidate => candidate.id));
    const hit = pickEntity(candidates, facts, { requireIndia: !INDEX_OWNER[entry.symbol], name: entry.name });
    await sleep(PAUSE_MS);
    if (hit) return { ...hit, term };
  }
  return null;
}

/**
 * Pixel size of a raster mark, so a blurry one never ships.
 *
 * A 16px favicon rendered into a 22px tile at 2x is visibly soft, and a soft
 * logo looks worse than the crisp monogram it replaced. SVG is exempt: it is
 * resolution-free by definition.
 */
function rasterTooSmall(bytes, ext) {
  if (ext === 'svg') return false;
  if (ext === 'png' && bytes.length > 24 && bytes.readUInt32BE(0) === 0x89504e47) {
    return Math.min(bytes.readUInt32BE(16), bytes.readUInt32BE(20)) < MIN_PIXELS;
  }
  // .ico and .jpg carry no dimensions we can read cheaply; weight stands in.
  return bytes.length < MIN_BYTES;
}

const MIN_PIXELS = 48;
const MIN_BYTES = 8000;

/** Drop marks that are too small to render cleanly, and say which. */
async function prune() {
  const manifest = JSON.parse(await readFile(join(OUT_DIR, 'manifest.json'), 'utf8'));
  const dropped = [];
  for (const [symbol, entry] of Object.entries(manifest)) {
    const path = join(OUT_DIR, entry.file);
    let bytes;
    try { bytes = await readFile(path); } catch { delete manifest[symbol]; dropped.push(`${symbol} (file missing)`); continue; }
    const ext = entry.file.split('.').pop().toLowerCase();
    if (rasterTooSmall(bytes, ext)) {
      await rm(path, { force: true });
      delete manifest[symbol];
      dropped.push(`${symbol} ${entry.file} (${Math.round(bytes.length / 100) / 10}kB)`);
    }
  }
  await writeFile(join(OUT_DIR, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`pruned ${dropped.length} low-resolution marks; ${Object.keys(manifest).length} remain`);
  if (dropped.length) console.log(`  ${dropped.join('\n  ')}`);
}

/*
 * Index marks, taken by name from en.wikipedia.
 *
 * NSE publishes no freely-licensed emblem: Commons holds a 512x31 wordmark
 * and nothing else, and the marks below are tagged FAIR USE on Wikipedia,
 * which is a claim for encyclopedic use and not a redistribution licence.
 * They are fetched on the product owner's explicit instruction; the licence
 * is recorded on every entry so the decision stays visible, and the exchange
 * should be asked for a press-kit asset before this ships publicly.
 */
const WIKI_INDEX_FILES = {
  NIFTY: 'File:Nifty 50 Logo.svg',
  BANKNIFTY: 'File:NSE Indices logo.svg',
  FINNIFTY: 'File:NSE Indices logo.svg',
  MIDCPNIFTY: 'File:NSE Indices logo.svg',
  NIFTYNXT50: 'File:NSE Indices logo.svg',
};

async function wikiIndexLogos() {
  const manifest = JSON.parse(await readFile(join(OUT_DIR, 'manifest.json'), 'utf8'));
  const raw = JSON.parse(await readFile(join(ROOT, 'public/underlyings.json'), 'utf8'));
  const names = Object.fromEntries((raw.underlyings ?? []).map(entry => [entry.symbol, entry.name]));
  for (const [symbol, title] of Object.entries(WIKI_INDEX_FILES)) {
    try {
      // `iiurlwidth` asks the wiki itself for a rendered thumbnail; building
      // the /thumb/ path by hand is rejected for some files.
      const url = `https://en.wikipedia.org/w/api.php?action=query&prop=imageinfo&iiprop=url|size|extmetadata&iiurlwidth=256&titles=${encodeURIComponent(title)}&format=json`;
      const page = Object.values((await api(url)).query.pages)[0];
      const info = page?.imageinfo?.[0];
      if (!info?.url) throw new Error('no file');
      let source = info.url;
      let ext = (new URL(info.url).pathname.split('.').pop() || 'svg').toLowerCase();
      /* Some of these SVGs are 384kB of paths for a 22px mark. Above 60kB the
         wiki's own 256px render is both smaller and sharper at this size. */
      if (ext === 'svg' && (info.size ?? 0) > 60_000 && info.thumburl) {
        source = info.thumburl;
        ext = (new URL(info.thumburl).pathname.split('.').pop() || 'png').toLowerCase();
      }
      const response = await fetch(source, { headers: { 'User-Agent': UA }, redirect: 'follow' });
      if (!response.ok) throw new Error(`file ${response.status}`);
      const bytes = Buffer.from(await response.arrayBuffer());
      /* Four NSE index series share one 384kB file; storing it per symbol
         would ship the same bytes four times. The file is named for its
         SOURCE and every symbol that uses it points at that one copy. */
      const shared = `${title.replace(/^File:/, '').replace(/\.[a-z]+$/i, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}.${ext}`;
      await writeFile(join(OUT_DIR, shared), bytes);
      manifest[symbol] = {
        file: shared,
        name: names[symbol] ?? symbol,
        kind: 'index',
        source: `https://en.wikipedia.org/wiki/${encodeURIComponent(title.replace(/ /g, '_'))}`,
        via: 'wikipedia',
        licence: (info.extmetadata?.LicenseShortName?.value ?? 'unknown'),
      };
      console.log(`ok   ${symbol.padEnd(12)} ${shared.padEnd(26)} ${info.width}x${info.height} · ${manifest[symbol].licence}`);
      await sleep(PAUSE_MS);
    } catch (error) {
      console.log(`miss ${symbol.padEnd(12)} ${error.message}`);
    }
  }
  await writeFile(join(OUT_DIR, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`manifest holds ${Object.keys(manifest).length}`);
}

/* Wiki furniture that appears on almost every article. */
const CHROME = /^File:(Edit-clear|Flag of|Increase|Decrease|Steady|OOjs|Semi-protection|Commons-logo|Wikidata|Wiktionary|Question_book|Ambox|Symbol|Folder|Padlock|Red_pencil|Office-book|Crystal|Nuvola|P_|Portal|Text_document|Wikisource|Wikiquote|Blue_pencil|Emblem-|Star_|Yes_check|X_mark)/i;
const LOGOISH = /(logo|wordmark|emblem|brand|identity)/i;

/**
 * The logo file on a company's English Wikipedia article.
 *
 * Name matching does the work: Reliance's mark is `File:Reliance
 * Industries.svg`, with no "logo" in the title at all, while every article
 * also carries a dozen pieces of wiki furniture (Edit-clear, Flag of India,
 * Increase2). Files are scored on how much of the company's name they share,
 * with a bonus for saying "logo" and for being a vector.
 */
function pickArticleLogo(files, name) {
  const words = normalise(name).match(/[A-Z0-9]+/g) ?? [normalise(name)];
  const tokens = (name.toUpperCase().match(/[A-Z0-9]{3,}/g) ?? []).filter(word => !['LIMITED', 'LTD', 'INDIA', 'THE', 'AND', 'CORPORATION', 'COMPANY'].includes(word));
  const scored = files.filter(title => !CHROME.test(title)).map(title => {
    const bare = title.replace(/^File:/, '');
    const upper = bare.toUpperCase();
    let score = 0;
    let named = false;
    for (const token of tokens) if (upper.includes(token)) { score += 3; named = true; }
    /* The file has to name the company. Without this, "looks like a logo and
       is a vector" was enough, and NMDC's article handed back an Indian
       Railways emblem. */
    if (!named) return { title, score: 0 };
    if (LOGOISH.test(bare)) score += 2;
    if (/\.svg$/i.test(bare)) score += 2;
    else if (/\.png$/i.test(bare)) score += 1;
    else score -= 1; // a .jpg on a company article is usually a photograph
    if (normalise(bare).startsWith(words.join(''))) score += 2;
    return { title, score };
  }).filter(entry => entry.score >= 3);
  scored.sort((a, b) => b.score - a.score);
  return scored[0]?.title ?? null;
}

/** Download a wiki file by title, preferring a 256px render for heavy SVGs. */
async function downloadWikiFile(title, symbol, wiki = 'en.wikipedia.org') {
  const url = `https://${wiki}/w/api.php?action=query&prop=imageinfo&iiprop=url|size|extmetadata&iiurlwidth=256&titles=${encodeURIComponent(title)}&format=json`;
  const info = Object.values((await api(url)).query.pages)[0]?.imageinfo?.[0];
  if (!info?.url) throw new Error('no file');
  let source = info.url;
  let ext = (new URL(info.url).pathname.split('.').pop() || 'svg').toLowerCase();
  if (ext === 'svg' && (info.size ?? 0) > 60_000 && info.thumburl) {
    source = info.thumburl;
    ext = (new URL(info.thumburl).pathname.split('.').pop() || 'png').toLowerCase();
  }
  const response = await fetch(source, { headers: { 'User-Agent': UA }, redirect: 'follow' });
  if (!response.ok) throw new Error(`file ${response.status}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  if (bytes.length < 400) throw new Error('file too small');
  await writeFile(join(OUT_DIR, `${symbol}.${ext}`), bytes);
  return {
    file: `${symbol}.${ext}`,
    licence: info.extmetadata?.LicenseShortName?.value ?? 'unknown',
    source: `https://${wiki}/wiki/${encodeURIComponent(title.replace(/ /g, '_'))}`,
    size: `${info.width}x${info.height}`,
  };
}

/** Fill the gaps from English Wikipedia's own article logos. */
async function wikiFill() {
  const manifest = JSON.parse(await readFile(join(OUT_DIR, 'manifest.json'), 'utf8'));
  const raw = JSON.parse(await readFile(join(ROOT, 'public/underlyings.json'), 'utf8'));
  const missing = (raw.underlyings ?? []).filter(entry => !manifest[entry.symbol]);
  console.log(`${missing.length} symbols without a mark`);
  let done = 0;
  const failed = [];
  for (const entry of missing) {
    try {
      // Wikidata knows which article belongs to this company; a bare title
      // guess lands on disambiguation pages and other countries' namesakes.
      const candidates = await searchEntities(SEARCH_HINT[entry.symbol] ?? entry.name);
      const facts = await entityFacts(candidates.map(candidate => candidate.id));
      const hit = pickEntity(candidates, facts, { requireIndia: true, name: entry.name, needsAsset: false });
      let article = null;
      if (hit) {
        const linkUrl = `https://www.wikidata.org/w/api.php?action=wbgetentities&ids=${hit.id}&props=sitelinks&sitefilter=enwiki&format=json`;
        article = (await api(linkUrl)).entities?.[hit.id]?.sitelinks?.enwiki?.title ?? null;
      }
      if (!article) throw new Error('no English article');
      const pageUrl = `https://en.wikipedia.org/w/api.php?action=query&prop=images&titles=${encodeURIComponent(article)}&imlimit=60&redirects=1&format=json`;
      const page = Object.values((await api(pageUrl)).query.pages)[0];
      const file = pickArticleLogo((page?.images ?? []).map(image => image.title), entry.name);
      if (!file) throw new Error('no logo file on the article');
      const saved = await downloadWikiFile(file, entry.symbol);
      manifest[entry.symbol] = {
        file: saved.file,
        name: entry.name,
        kind: entry.kind,
        wikidata: hit.id,
        source: saved.source,
        via: 'wikipedia',
        licence: saved.licence,
      };
      done += 1;
      console.log(`ok   ${entry.symbol.padEnd(12)} ${saved.file.padEnd(20)} ${saved.size.padEnd(10)} ${saved.licence.padEnd(12)} ← ${file.replace('File:', '')}`);
    } catch (error) {
      failed.push(`${entry.symbol} (${entry.name}) — ${error.message}`);
    }
    await sleep(PAUSE_MS);
  }
  await writeFile(join(OUT_DIR, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`\n${done} filled · ${failed.length} still without a mark · manifest holds ${Object.keys(manifest).length}`);
  if (failed.length) console.log(failed.map(line => `  ${line}`).join('\n'));
}

async function main() {
  if (process.argv.includes('--wiki-fill')) { await wikiFill(); return; }
  if (process.argv.includes('--prune')) { await prune(); return; }
  if (process.argv.includes('--index-logos')) { await wikiIndexLogos(); return; }
  const args = process.argv.slice(2);
  const limitIndex = args.indexOf('--limit');
  const limit = limitIndex >= 0 ? Number(args[limitIndex + 1]) : null;
  const only = args.filter(arg => /^[A-Z0-9&-]+$/.test(arg));

  const raw = JSON.parse(await readFile(join(ROOT, 'public/underlyings.json'), 'utf8'));
  let list = raw.underlyings ?? [];
  if (only.length) list = list.filter(entry => only.includes(entry.symbol));
  if (limit) list = list.slice(0, limit);

  await mkdir(OUT_DIR, { recursive: true });
  let manifest = {};
  try { manifest = JSON.parse(await readFile(join(OUT_DIR, 'manifest.json'), 'utf8')); } catch { /* first run */ }

  const missing = [];
  let done = 0;
  for (const entry of list) {
    try {
      const hit = await resolve(entry);
      if (!hit) { missing.push(`${entry.symbol} (${entry.name}) — no Commons logo`); continue; }
      let saved;
      let provenance;
      if (hit.logo) {
        saved = await downloadLogo(hit.logo, entry.symbol);
        provenance = { commons: hit.logo, source: `https://commons.wikimedia.org/wiki/File:${encodeURIComponent(hit.logo.replace(/ /g, '_'))}`, via: 'commons' };
        // A wordmark cannot read at 22px; take the square emblem instead.
        if (saved.aspect != null && saved.aspect > MAX_ASPECT && hit.website) {
          try {
            const square = await downloadSiteIcon(hit.website, entry.symbol);
            if (square.file !== saved.file) await rm(join(OUT_DIR, saved.file), { force: true });
            saved = square;
            provenance = { source: hit.website, via: 'site-icon', wordmarkSkipped: hit.logo };
          } catch { /* keep the wordmark rather than nothing */ }
        }
      } else {
        saved = await downloadSiteIcon(hit.website, entry.symbol);
        provenance = { source: hit.website, via: 'site-icon' };
      }
      manifest[entry.symbol] = { file: saved.file, name: entry.name, kind: entry.kind, wikidata: hit.id, ...provenance };
      done += 1;
      console.log(`ok   ${entry.symbol.padEnd(12)} ${hit.id.padEnd(10)} ${saved.file.padEnd(18)} ${provenance.via.padEnd(10)} ← ${hit.label}`);
    } catch (error) {
      missing.push(`${entry.symbol} (${entry.name}) — ${error.message}`);
      console.log(`miss ${entry.symbol.padEnd(12)} ${error.message}`);
    }
    await sleep(PAUSE_MS);
  }

  await writeFile(join(OUT_DIR, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
  console.log(`\n${done} logos saved · ${missing.length} unresolved · manifest holds ${Object.keys(manifest).length}`);
  if (missing.length) console.log(`unresolved:\n  ${missing.join('\n  ')}`);
}

main().catch(error => { console.error(error); process.exit(1); });
