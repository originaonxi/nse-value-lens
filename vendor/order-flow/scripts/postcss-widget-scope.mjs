/**
 * PostCSS plugin: lets a workspace's stylesheet apply inside a terminal widget.
 *
 * The analysis pages were written to be the ONE page in the app, so ~1,900
 * selectors are scoped to the app root's `data-active-tab`, for example
 *
 *   #root > .app.app[data-active-tab='pcr'] .ui-pcr-card { … }
 *
 * The terminal shows several workspaces at once under one root, so no single
 * `data-active-tab` can be right for all of them. Rather than fork every page's
 * CSS, each such selector gets a twin that points at the widget frame instead:
 *
 *   #root .tw-widget.tw-widget[data-widget-page='pcr'] .ui-pcr-card { … }
 *
 * The twin keeps the original's specificity (the `#root` id and the doubled
 * class stand in for `#root > .app.app`), so the cascade between sheets
 * resolves exactly as it does on the page's own route. An original with a
 * single `.app` gets a single `.tw-widget`: one class for one class, never one
 * more. The original selector is left untouched, so the stand-alone routes are
 * byte-for-byte what they were.
 *
 * Selectors with a bare `[data-active-tab]` (no value) describe the shell
 * itself, not a page, and are not twinned.
 */

/** The widget frame's class and attribute — the terminal's frame component writes both. */
export const WIDGET_CLASS = 'tw-widget';
export const WIDGET_ATTR = 'data-widget-page';

// The quote is a named group: the patterns below put a capture group of their own in front of it.
const VALUE = String.raw`\[data-active-tab=(?<quote>['"])([a-z0-9-]+)\k<quote>\]`;
// `#root > .app.app[...]` and `#root > .app[...]`, with any spacing round the `>`.
const ROOTED = new RegExp(String.raw`#root\s*>\s*\.app(\.app)?${VALUE}`, 'g');
// `.app.app[...]` / `.app[...]` with no `#root >` in front.
const APPED = new RegExp(String.raw`\.app(\.app)?${VALUE}`, 'g');
// A bare `[data-active-tab='x']`.
const BARE = new RegExp(VALUE, 'g');

const HAS_VALUE = new RegExp(VALUE);

// `#root > .app.app:is([data-active-tab='a'], [data-active-tab='b'])`: one rule written for several pages.
const LISTED = /(#root\s*>\s*)?\.app(\.app)?:(is|where)\(([^()]*data-active-tab[^()]*)\)/g;
const LISTED_VALUE = new RegExp(VALUE, 'g');

/** As many `.tw-widget` classes as the `.app` classes they stand in for: two when the original doubled `.app`, else one. */
const frame = doubled => (doubled ? `.${WIDGET_CLASS}.${WIDGET_CLASS}` : `.${WIDGET_CLASS}`);

/** Splits a selector list at its top-level commas, leaving `:is(a, b)` and `[x="a,b"]` whole. */
export function splitSelectorList(list) {
  const parts = [];
  let depth = 0;
  let quote = '';
  let start = 0;
  for (let i = 0; i < list.length; i += 1) {
    const ch = list[i];
    if (quote) {
      if (ch === '\\') i += 1;
      else if (ch === quote) quote = '';
    } else if (ch === '"' || ch === "'") quote = ch;
    else if (ch === '(' || ch === '[') depth += 1;
    else if (ch === ')' || ch === ']') depth -= 1;
    else if (ch === ',' && depth === 0) {
      parts.push(list.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(list.slice(start));
  return parts;
}

/** The widget twin of one selector, or null when it has no page scope. */
export function twinSelector(selector) {
  if (!HAS_VALUE.test(selector)) return null;
  const twin = selector
    .replace(LISTED, (_m, rooted, doubled, fn, inner) => {
      const pages = inner.replace(LISTED_VALUE, (_v, _q, page) => `[${WIDGET_ATTR}='${page}']`);
      return `${rooted ? '#root ' : ''}${frame(doubled)}:${fn}(${pages})`;
    })
    .replace(ROOTED, (_m, doubled, _q, page) => `#root ${frame(doubled)}[${WIDGET_ATTR}='${page}']`)
    .replace(APPED, (_m, doubled, _q, page) => `${frame(doubled)}[${WIDGET_ATTR}='${page}']`)
    .replace(BARE, (_m, _q, page) => `.${WIDGET_CLASS}[${WIDGET_ATTR}='${page}']`);
  return twin === selector ? null : twin;
}

/** The whole selector list plus the twin of every member that has one. */
export function withTwins(list) {
  const members = splitSelectorList(list);
  const twins = [];
  for (const member of members) {
    const twin = twinSelector(member);
    if (twin) twins.push(twin);
  }
  if (!twins.length) return null;
  const seen = new Set(members.map(m => m.trim()));
  const fresh = twins.filter(t => !seen.has(t.trim()));
  return fresh.length ? [...members.map(m => m.trim()), ...fresh.map(t => t.trim())].join(',\n') : null;
}

export default function widgetScope() {
  return {
    postcssPlugin: 'ui-widget-scope',
    Rule(rule) {
      // Keyframe steps and rules inside them have no page scope.
      if (rule.parent?.type === 'atrule' && /keyframes$/i.test(rule.parent.name)) return;
      if (!rule.selector.includes('data-active-tab')) return;
      const next = withTwins(rule.selector);
      if (next) rule.selector = next;
    },
  };
}
widgetScope.postcss = true;
