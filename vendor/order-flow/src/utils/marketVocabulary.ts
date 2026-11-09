/**
 * marketVocabulary.ts — the one place the app's user-facing wording is decided.
 *
 * The rules (see docs/UI-TERMINOLOGY.md, which is the binding spec):
 *
 *   1. Sides read Call / Put. Never CE / PE. `optionSideLabel` in formatters.ts
 *      does that conversion and is re-exported here so callers need one import.
 *   2. Open Interest is spelled out. "OI" is an abbreviation reserved for
 *      genuinely tight surfaces — column heads, axis marks, legend chips — and
 *      every one of those must carry the spelled-out form in its hover title.
 *   3. Build-up signals read Long build-up / Short build-up / Short covering /
 *      Long unwinding. LB / SB / SC / LU are reserved for the same tight
 *      surfaces, on the same hover-title condition.
 *   4. Numbers never carry digit-grouping commas: 23900 Call, not 23,900 CE.
 *   Tone. Insight copy is descriptive, never advisory (design contract §5.4): it
 *      says what the data shows now. No forecasts, no probabilities the
 *      heuristics never computed, no instructions, no trades. See
 *      `findAdvisoryPhrase` at the foot of this file.
 *
 * Rules 1–4 are enforced by src/utils/marketVocabulary.test.ts, which fails the
 * build rather than trusting a convention comment — the CE/PE guard it grew out
 * of proved comments alone do not hold. The tone rule is enforced there over the
 * generators' source, and by src/utils/insightCopyTone.test.ts over what the
 * generators actually emit.
 */

import type { BuildUp } from '@/lib/buildUp';

export { optionSideLabel } from './formatters';

/** Spelled-out form. Default in prose, headings, tooltips and narrative copy. */
export const OPEN_INTEREST = 'Open Interest';

/**
 * The abbreviation. Importing this is the explicit, greppable admission that a
 * surface is too tight for the words; pair it with `openInterestTitle()`.
 */
export const OI_ABBR = 'OI';

/**
 * Hover text for any surface that shows `OI_ABBR`. Rule 2's other half: the
 * abbreviation is only allowed where the full term is one hover away.
 */
export function openInterestTitle(detail?: string): string {
  return detail ? `${OPEN_INTEREST} — ${detail}` : OPEN_INTEREST;
}

/* ── Gamma exposure ──────────────────────────────────────────────────────── */

/**
 * Spelled-out form. Default in prose, headings and tooltips.
 *
 * Fixed here on the day the GEX Levels workspace was written, before three
 * spellings could ship side by side the way "Long Build" / "Long Build-Up" /
 * "long buildup" once did. GEX is not banned the way bare "OI" is — PCR sets
 * the precedent for an abbreviation that names a whole workspace — but the
 * first mention in any block of prose should be the words.
 */
export const GAMMA_EXPOSURE = 'Gamma Exposure';

/**
 * The abbreviation. Reserved for tight surfaces — axis marks, stat-tile
 * eyebrows, the rail label — each of which must carry `gammaExposureTitle()`
 * on hover, exactly as `OI_ABBR` must.
 */
export const GEX_ABBR = 'GEX';

/** Hover text for any surface that shows `GEX_ABBR`. */
export function gammaExposureTitle(detail?: string): string {
  return detail ? `${GAMMA_EXPOSURE} — ${detail}` : GAMMA_EXPOSURE;
}

/* ── Implied volatility ──────────────────────────────────────────────────── */

/** Spelled-out form. Default in prose, headings and tooltips. */
export const IMPLIED_VOLATILITY = 'Implied Volatility';

/**
 * The abbreviation, and the one case where it outranks the spelled-out form on
 * a rail label's terms.
 *
 * "IV" is not banned the way bare "OI" is, and the reason is evidence rather
 * than taste: across a decade of Indian retail options forums the bare token is
 * what traders write, essentially always, while the spelled-out phrase appears
 * mainly in publisher copy. Spelling it out in a stat tile would be less
 * legible to the audience, not more.
 *
 * The hover obligation still stands — anywhere this is printed, `IMPLIED_VOLATILITY`
 * goes in the title — because a first-time reader deserves the words once.
 */
export const IV_ABBR = 'IV';

/**
 * At-the-money implied volatility.
 *
 * "At the money" is spelled out on first mention and in every hover; `ATM` is
 * the tight-surface form. The qualifier matters more than it looks: this app's
 * ATM is measured at the FORWARD, not at spot, and those are 2.6 strikes apart
 * on a 30-day NIFTY. A reader comparing our figure against a platform that
 * centres on spot needs the hover to say which.
 */
export const ATM_IMPLIED_VOLATILITY = 'At-the-money Implied Volatility';
export const ATM_IV_ABBR = 'ATM IV';

export function atmIvTitle(detail?: string): string {
  const base = `${ATM_IMPLIED_VOLATILITY} — measured at the forward, not at spot`;
  return detail ? `${base}. ${detail}` : base;
}

type BuildUpTerm = {
  /** Canonical full name. This is what prose, cells and legends print. */
  readonly name: string;
  /** Two-letter code. Tight surfaces only, always with `tip` on hover. */
  readonly code: string;
  /** The price and Open Interest legs, in words — the definition, not a read. */
  readonly legs: string;
  /** What the pattern conventionally implies. Descriptive, never advisory. */
  readonly meaning: string;
  /** Full hover detail: name, code, both legs and the conventional meaning. */
  readonly tip: string;
  /** Directional lean of the signal, for tone/colour. */
  readonly tone: 'up' | 'down' | 'flat';
  /** Whether the Open Interest leg rose or fell — drives bar texture. */
  readonly dir: 'add' | 'drop' | 'same';
};

function term(
  name: string,
  code: string,
  legs: string,
  meaning: string,
  tone: BuildUpTerm['tone'],
  dir: BuildUpTerm['dir'],
): BuildUpTerm {
  return { name, code, legs, meaning, tip: `${name} (${code}) — ${legs}. ${meaning}.`, tone, dir };
}

/**
 * The four build-up signals plus the neutral face, named once.
 *
 * Before this table the same four patterns shipped as "Long Build", "Long
 * Build-Up" and "long buildup" across three files. One spelling, one code, one
 * hover string — every renderer reads from here.
 */
export const BUILDUP_TERMS: Record<BuildUp, BuildUpTerm> = {
  LONG_BUILD: term(
    'Long build-up', 'LB',
    'price rose and Open Interest rose',
    'Fresh long positions are being opened, which is conventionally read as bullish conviction',
    'up', 'add',
  ),
  SHORT_BUILD: term(
    'Short build-up', 'SB',
    'price fell and Open Interest rose',
    'Fresh short positions are being opened, which is conventionally read as bearish conviction',
    'down', 'add',
  ),
  SHORT_COVER: term(
    'Short covering', 'SC',
    'price rose and Open Interest fell',
    'Existing short positions are being closed, which is conventionally read as bullish relief rather than fresh buying',
    'up', 'drop',
  ),
  LONG_UNWIND: term(
    'Long unwinding', 'LU',
    'price fell and Open Interest fell',
    'Existing long positions are being closed, which is conventionally read as bearish pressure rather than fresh selling',
    'down', 'drop',
  ),
  NEUTRAL: term(
    'No clear pattern', '—',
    'the move in price and Open Interest is inside this window’s noise floor',
    'Nothing is being claimed about positioning at this strike',
    'flat', 'same',
  ),
};

/** Canonical full name, e.g. 'Short covering'. The default in every surface. */
export function buildUpName(code: BuildUp | null | undefined): string {
  return BUILDUP_TERMS[code ?? 'NEUTRAL'].name;
}

/** Two-letter code. Tight surfaces only — render `buildUpTip` as its title. */
export function buildUpCode(code: BuildUp | null | undefined): string {
  return BUILDUP_TERMS[code ?? 'NEUTRAL'].code;
}

/** Full hover detail. Required wherever `buildUpCode` is rendered. */
export function buildUpTip(code: BuildUp | null | undefined): string {
  return BUILDUP_TERMS[code ?? 'NEUTRAL'].tip;
}

/**
 * Lowercase name for mid-sentence prose — "the leg is showing short covering".
 * Sentence-initial copy should use `buildUpName` instead.
 */
export function buildUpNameLower(code: BuildUp | null | undefined): string {
  return buildUpName(code).toLowerCase();
}

/**
 * A strike named the way the whole product names strikes: no grouping comma,
 * the side spelled out. `23900 Call`, never `23,900 CE`.
 */
export function strikeLabel(strike: number, side?: string | null): string {
  const digits = Number.isFinite(strike)
    ? String(Math.round(strike * 100) / 100)
    : '—';
  if (!side) return digits;
  const token = side.trim().toUpperCase();
  const word = token === 'CE' || token === 'CALL' || token === 'CALLS' ? 'Call' : 'Put';
  return `${digits} ${word}`;
}

/* ── Tone: descriptive, never advisory ───────────────────────────────────── */

/**
 * The tone rule — what insight copy may not say, as patterns a test can hold.
 *
 * docs/UI-TERMINOLOGY.md states it under Rule 3 ("Descriptive, never
 * advisory"); design contract §5.4 is the authority.
 *
 * Design contract §5.4: verdicts are states (bullish / bearish / neutral /
 * rangebound), levels are hedged, triggers are conditional. The copy kept
 * drifting anyway, one generator at a time: Open Interest Spurts shipped
 * "Strong upward momentum expected. High probability of continued bullish
 * movement." — a forecast, a probability no heuristic here computes, and the
 * verdict badge beside it said twice — and the Option Chain's scenarios read
 * "call writers will be forced to cover, accelerating upside momentum toward
 * 24082" and "Favors credit spreads and iron condors".
 *
 * Each pattern carries the reason it reads as a forecast or as advice, so a
 * failure explains itself. They are deliberately blunt: a word that is only
 * USUALLY advisory ("will", "should", "expect") is still out, because the
 * descriptive sentence is always available — "is priced for", "has moved",
 * "would put … in the money".
 */
export const ADVISORY_PATTERNS: ReadonlyArray<{ pattern: RegExp; why: string }> = [
  { pattern: /\bexpect(?:s|ed|ing|ation|ations)?\b/i, why: 'forecasts what price or the market does next' },
  { pattern: /\b(?:un)?likely\b/i, why: 'forecasts an outcome' },
  { pattern: /\bprobab(?:le|ly|ility|ilities)\b/i, why: 'states a probability no heuristic here computes' },
  { pattern: /\bwill\b/i, why: 'states a future outcome as fact' },
  { pattern: /\b(?:going to|poised to|bound to|set to (?:rise|fall|move|break))\b/i, why: 'states a future outcome as fact' },
  { pattern: /\bshould\b/i, why: 'tells the reader, or the market, what ought to happen' },
  { pattern: /\b(?:consider|recommend\w*|suggest(?:s|ed)?)\b/i, why: 'advises the reader' },
  { pattern: /\b(?:watch|wait|look) (?:for|out)\b/i, why: 'instructs the reader' },
  { pattern: /\bavoid\b/i, why: 'instructs the reader' },
  { pattern: /(?:^|[.!?;:—]\s*)(?:Buy|Sell|Hold|Enter|Exit|Avoid|Consider|Watch|Wait|Check|Compare|Book|Go)\b/, why: 'opens a sentence with an instruction' },
  { pattern: /\b(?:go|going) (?:long|short)\b|\bstrong (?:buy|sell)\b|\b(?:buy|sell)(?:ing)? (?:signal|setup|zone|opportunity)\b/i, why: 'is a trade call' },
  { pattern: /\b(?:entry|stop[- ]?loss|take[- ]profit)\b/i, why: 'is a trade instruction' },
  { pattern: /\b(?:iron condors?|credit spreads?|debit spreads?|bull call spreads?|bear put spreads?)\b/i, why: 'recommends a strategy' },
  { pattern: /\bfavou?r(?:s|ed)\b/i, why: 'recommends a side or a strategy' },
  { pattern: /\bgame ?plans?\b|\binvalidation\b/i, why: 'frames the read as a trading plan' },
  { pattern: /\btargets?\b/i, why: 'names a price the market is said to be heading for' },
  { pattern: /\bmomentum\b/i, why: 'frames positioning as a move already under way' },
  { pattern: /\bbreak(?:out|down)s?\b/i, why: 'names a move before it happens' },
  { pattern: /\bforecast(?:s|ed|ing)?\b|\bpredict(?:s|ed|ing|ion|ions|ive)?\b/i, why: 'forecasts' },
  { pattern: /\bpotential (?:for|upside|downside)\b|\b(?:upside|downside) potential\b/i, why: 'forecasts a move' },
  { pattern: /\bnext (?:move|direction(?:al)?)\b/i, why: 'forecasts the next move' },
  { pattern: /\bcontinued (?:bullish|bearish|upward|downward|upside|downside)\b/i, why: 'forecasts a continuation' },
  { pattern: /\b(?:pinning|magnet|gravitational)\b/i, why: 'says price is drawn to a level' },
  { pattern: /\boutlook\b/i, why: 'frames a state as a forecast' },
  { pattern: /\binstitution(?:al|s)?\b|\bsmart money\b/i, why: 'names who holds the positions, which open interest cannot show' },
];

/**
 * Phrases that contain a flagged word and are themselves descriptive, removed
 * before the patterns run.
 *
 * Two kinds only: a named pricing convention ("expected move" is the
 * straddle- or volatility-implied range, a term with a definition), and a
 * NEGATED disclaimer ("not a forecast", "not price targets", "no success
 * probability"), which is the descriptive device §5.4 asks for.
 */
const ADVISORY_EXEMPT: readonly RegExp[] = [
  /\bexpected[- ]moves?\b/gi,
  /\b(?:not|never|no|nor)\s+(?:a\s+|an\s+|any\s+)?(?:[\w-]+\s+)?(?:forecasts?|forecasted|predictions?|predicted|probability|probabilities|targets?)\b/gi,
  /\b(?:does|do|did|can)\s*not\s+(?:predict|forecast)\b/gi,
];

/**
 * The first advisory or predictive phrase in `copy`, with the reason, or null.
 * The tone rule's single check — the source scan and the generator-output test both
 * call it, so there is one definition of "advisory" to argue with.
 */
export function findAdvisoryPhrase(copy: string): { phrase: string; why: string } | null {
  const text = ADVISORY_EXEMPT.reduce((out, exempt) => out.replace(exempt, ' '), copy);
  for (const { pattern, why } of ADVISORY_PATTERNS) {
    const hit = text.match(pattern);
    if (hit) return { phrase: hit[0].replace(/^[.!?;:—\s]+/, ''), why };
  }
  return null;
}
