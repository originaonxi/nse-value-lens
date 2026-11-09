/**
 * PostCSS plugin: rewrites selectors that END in an `:is()` / `:where()` list
 * into plain selectors the browser can index, with the cascade unchanged.
 *
 * Chrome files every rule under the class, id, attribute or tag of the
 * selector's last compound, and only tries a rule on elements carrying that
 * key. A last compound that is `:is(.a, .b)` has no key, so the rule is tried
 * on EVERY element on every restyle. The app has ~360 of them, written to
 * keep long scoping prefixes readable:
 *
 *   :root[data-theme] body #root#root > .app.app :is(.ui-aisum, .ui-oi-card, …)
 *
 * On the OI Heatmap they were ~860 ms of a ~1.3 s restyle (one Tile colour
 * switch, measured headless on a production build, 10 Oct 2026). Rewritten,
 * each alternative is its own selector and is indexed by its own class:
 *
 *   P :is(A, B)  ->  P A, P B              (A, B compounds)
 *   P :is(A, B)  ->  A:is(P *), B:is(P *)  (an alternative with combinators,
 *                                           which `P A` would change: in the
 *                                           original A's ancestors may lie
 *                                           outside P)
 *
 * Specificity is kept exactly. `:is()` counts as its most specific
 * alternative, so each rewritten selector is padded up to that with
 * never-failing `:not()`s (`:not(#\#)` an id, `:not(.\#)` a class,
 * `:not(ui-pad)` a type), which add weight but no index key. `:where()`
 * counts nothing, so its alternatives are wrapped back in a one-item
 * `:where()`.
 *
 * Left alone, so the rule can never be dropped or reweighted:
 *   - an alternative a browser might not parse (`::`, vendor `:-x-`, `&`,
 *     a leading combinator). Inside `:is()` an unparsed alternative is
 *     skipped; in a plain selector list it would void the whole rule.
 *   - specificities that can't be padded equal. Padding only adds, so an
 *     alternative must not exceed the most specific one in any column.
 *   - a list that isn't the start of the last compound (`.x:is(.a, .b)` is
 *     already indexed by `.x`).
 */

const PAD = { a: ':not(#\\#)', b: ':not(.\\#)', c: ':not(ui-pad)' };
const LEGACY_PSEUDO_ELEMENT = /^:(before|after|first-line|first-letter)(?![-\w])/i;

/** Splits at top-level commas, leaving `:is(a, b)`, `[x="a,b"]` and escapes whole. */
export function splitList(list) {
  const parts = [];
  let depth = 0;
  let quote = '';
  let start = 0;
  for (let i = 0; i < list.length; i += 1) {
    const ch = list[i];
    if (ch === '\\') { i += 1; continue; }
    if (quote) { if (ch === quote) quote = ''; continue; }
    if (ch === '"' || ch === "'") quote = ch;
    else if (ch === '(' || ch === '[') depth += 1;
    else if (ch === ')' || ch === ']') depth -= 1;
    else if (ch === ',' && depth === 0) { parts.push(list.slice(start, i)); start = i + 1; }
  }
  parts.push(list.slice(start));
  return parts;
}

/** Index of the `)` (or `]`) closing the bracket opened at `open`, or -1. */
function closing(text, open) {
  let depth = 0;
  let quote = '';
  for (let i = open; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === '\\') { i += 1; continue; }
    if (quote) { if (ch === quote) quote = ''; continue; }
    if (ch === '"' || ch === "'") quote = ch;
    else if (ch === '(' || ch === '[') depth += 1;
    else if (ch === ')' || ch === ']') { depth -= 1; if (depth === 0) return i; }
  }
  return -1;
}

/** Top-level combinator runs (`' '`, `>`, `+`, `~` and the spaces round them). */
function combinators(selector) {
  const runs = [];
  let depth = 0;
  let quote = '';
  for (let i = 0; i < selector.length; i += 1) {
    const ch = selector[i];
    if (ch === '\\') { i += 1; continue; }
    if (quote) { if (ch === quote) quote = ''; continue; }
    if (ch === '"' || ch === "'") { quote = ch; continue; }
    if (ch === '(' || ch === '[') { depth += 1; continue; }
    if (ch === ')' || ch === ']') { depth -= 1; continue; }
    if (depth === 0 && /[\s>+~]/.test(ch)) {
      let j = i;
      while (j < selector.length && /[\s>+~]/.test(selector[j])) j += 1;
      runs.push({ start: i, end: j, text: selector.slice(i, j).trim() });
      i = j - 1;
    }
  }
  return runs;
}

function skipIdent(text, i) {
  while (i < text.length) {
    if (text[i] === '\\') { i += 2; continue; }
    if (/[-\w]/.test(text[i]) || text.charCodeAt(i) > 127) { i += 1; continue; }
    break;
  }
  return i;
}

const maxSpec = specs => specs.reduce((m, s) => (s.a > m.a || (s.a === m.a && (s.b > m.b || (s.b === m.b && s.c > m.c))) ? s : m), { a: 0, b: 0, c: 0 });

/** Selectors Level 4 specificity of one complex selector, as {a, b, c}. */
export function specificity(selector) {
  let a = 0; let b = 0; let c = 0;
  let atCompoundStart = true;
  for (let i = 0; i < selector.length;) {
    const ch = selector[i];
    if (/[\s>+~]/.test(ch)) { atCompoundStart = true; i += 1; continue; }
    if (ch === '*') { atCompoundStart = false; i += 1; continue; }
    if (ch === '#') { a += 1; i = skipIdent(selector, i + 1); atCompoundStart = false; continue; }
    if (ch === '.') { b += 1; i = skipIdent(selector, i + 1); atCompoundStart = false; continue; }
    if (ch === '[') { b += 1; i = closing(selector, i) + 1; atCompoundStart = false; continue; }
    if (ch === ':') {
      atCompoundStart = false;
      if (selector[i + 1] === ':') { c += 1; const end = skipIdent(selector, i + 2); i = selector[end] === '(' ? closing(selector, end) + 1 : end; continue; }
      if (LEGACY_PSEUDO_ELEMENT.test(selector.slice(i))) { c += 1; i = skipIdent(selector, i + 1); continue; }
      const end = skipIdent(selector, i + 1);
      const name = selector.slice(i + 1, end).toLowerCase();
      if (selector[end] !== '(') { b += 1; i = end; continue; }
      const close = closing(selector, end);
      const inner = selector.slice(end + 1, close);
      if (name === 'where') { /* counts nothing */ } else if (['is', 'not', 'has', 'matches', '-webkit-any'].includes(name)) {
        const m = maxSpec(splitList(inner).map(s => specificity(s.trim())));
        a += m.a; b += m.b; c += m.c;
      } else if (name === 'nth-child' || name === 'nth-last-child') {
        b += 1;
        const of = inner.match(/\sof\s([\s\S]*)$/i);
        if (of) { const m = maxSpec(splitList(of[1]).map(s => specificity(s.trim()))); a += m.a; b += m.b; c += m.c; }
      } else b += 1;
      i = close + 1;
      continue;
    }
    if (atCompoundStart && (/[a-zA-Z_-]/.test(ch) || ch === '\\' || selector.charCodeAt(i) > 127)) {
      c += 1; i = skipIdent(selector, i); atCompoundStart = false; continue;
    }
    i += 1;
  }
  return { a, b, c };
}

const UNSAFE_ARG = /::|(^|[^\\]):-|&|^\s*[>+~]|\/\*/;

/** A rewritten list for one complex selector, or null to leave it alone. */
export function bucketSelector(raw) {
  const selector = raw.trim();
  if (selector.includes('/*')) return null;
  const runs = combinators(selector);
  const last = runs[runs.length - 1];
  const compoundStart = last ? last.end : 0;
  const compound = selector.slice(compoundStart);
  const fn = compound.match(/^:(is|where)\(/i);
  if (!fn) return null;
  const open = fn[0].length - 1;
  const close = closing(compound, open);
  if (close < 0) return null;
  const args = splitList(compound.slice(open + 1, close)).map(s => s.trim());
  if (args.some(arg => !arg || UNSAFE_ARG.test(arg) || LEGACY_PSEUDO_ELEMENT.test(arg))) return null;
  let rest = compound.slice(close + 1);
  // A pseudo-element in the rest stays last.
  let tail = '';
  const pe = rest.search(/::|:(before|after|first-line|first-letter)(?![-\w])/i);
  if (pe >= 0) { tail = rest.slice(pe); rest = rest.slice(0, pe); }
  if (/^[\w\\-]/.test(rest)) return null;
  const prefix = last ? selector.slice(0, last.start) : '';
  const comb = last ? (last.text ? ` ${last.text} ` : ' ') : '';
  const isWhere = fn[1].toLowerCase() === 'where';
  const specs = args.map(specificity);
  const top = maxSpec(specs);
  const out = [];
  for (let k = 0; k < args.length; k += 1) {
    const arg = args[k];
    let pad = '';
    if (!isWhere) {
      const d = { a: top.a - specs[k].a, b: top.b - specs[k].b, c: top.c - specs[k].c };
      if (d.a < 0 || d.b < 0 || d.c < 0) return null;
      pad = PAD.a.repeat(d.a) + PAD.b.repeat(d.b) + PAD.c.repeat(d.c);
    }
    const body = isWhere ? `:where(${arg})` : arg;
    const complex = combinators(arg).length > 0;
    if (!prefix) out.push(`${body}${pad}${rest}${tail}`);
    else if (!complex) out.push(`${prefix}${comb}${body}${pad}${rest}${tail}`);
    else out.push(`${body}${pad}${rest}:is(${prefix}${comb}*)${tail}`);
  }
  return out;
}

/** The whole rewritten selector list, or null when nothing changed. */
export function bucketList(list) {
  let changed = false;
  const out = [];
  for (const member of splitList(list)) {
    const next = bucketSelector(member);
    if (next) { changed = true; out.push(...next); } else out.push(member.trim());
  }
  return changed ? [...new Set(out)].join(',\n') : null;
}

export default function bucketSelectors() {
  return {
    postcssPlugin: 'ui-bucket-selectors',
    // After every other plugin has written its selectors (the widget twins).
    OnceExit(root) {
      root.walkRules(rule => {
        if (rule.parent?.type === 'atrule' && /keyframes$/i.test(rule.parent.name)) return;
        if (!/:(is|where)\(/i.test(rule.selector)) return;
        const next = bucketList(rule.selector);
        if (next) rule.selector = next;
      });
    },
  };
}
bucketSelectors.postcss = true;
