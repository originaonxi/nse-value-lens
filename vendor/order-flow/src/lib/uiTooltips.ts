/*
 * UI-STYLE TOOLTIPS for every control (owner, 26 Oct 2026: bring in what
 * the reference design does better). the reference design names every control in an inverted
 * pill as soon as the pointer rests on it, with its hotkey in key chips beside
 * the name ("Option Chain | Shift O"). The app named its ~200 controls with
 * the native `title`, which waits about a second, wears the OS style and
 * never shows a key.
 *
 * One listener set takes over every `title` in the document. On hover or
 * keyboard focus it moves the text to `data-ui-tip` (so the native box
 * never opens), and shows one shared pill under the control, above it when
 * there is no room. `aria-keyshortcuts` on the control becomes the chips. An
 * icon-only control whose only name was its title gets that text as its
 * aria-label first, so nothing loses its accessible name.
 *
 * Opt out with `data-no-ui-tip` on the control or any ancestor. A label
 * that may be truncated can carry `data-ui-tip` with
 * `data-ui-tip-when="cut"`: it is named in full only while cut.
 */

const SHOW_DELAY_MS = 350;
/** Moving between controls while a tip is (or just was) open shows the next at once. */
const WARM_MS = 600;
const GAP = 8;
const EDGE = 8;

const KEY_NAMES: Record<string, string> = {
  Control: 'Ctrl', Meta: '⌘', Alt: 'Alt', Shift: 'Shift', Escape: 'Esc', Enter: 'Enter', Space: 'Space',
  ArrowLeft: '←', ArrowRight: '→', ArrowUp: '↑', ArrowDown: '↓', Delete: 'Del', Backspace: '⌫',
};

const isMac = () => typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

/**
 * `aria-keyshortcuts` lists alternatives separated by spaces, each a
 * `+`-joined combo. Show one: the ⌘ form on a Mac when there is one,
 * otherwise the first.
 */
export function shortcutKeys(value: string | null): string[] {
  if (!value) return [];
  const combos = value.trim().split(/\s+/).filter(Boolean);
  if (!combos.length) return [];
  const pick = (isMac() && combos.find(c => c.includes('Meta'))) || combos.find(c => !c.includes('Meta')) || combos[0];
  // A bare "+" or "-" is a key of its own, not a separator.
  if (pick === '+' || pick === '-') return [pick];
  return pick.split('+').filter(Boolean).map(key => KEY_NAMES[key] ?? (key.length === 1 ? key.toUpperCase() : key));
}

function tipText(el: Element): string {
  const fromTitle = el.getAttribute('title');
  if (fromTitle !== null) {
    const text = fromTitle.trim();
    // An icon-only control whose name was its title keeps that name.
    if (text && !el.hasAttribute('aria-label') && !el.hasAttribute('aria-labelledby') && !(el.textContent || '').trim()) {
      el.setAttribute('aria-label', text);
    }
    el.setAttribute('data-ui-tip', text);
    el.removeAttribute('title');
    return text;
  }
  return (el.getAttribute('data-ui-tip') || '').trim();
}

export function installUiTooltips(doc: Document = document): () => void {
  const win = doc.defaultView;
  if (!win) return () => {};
  const tip = doc.createElement('div');
  tip.className = 'ui-tip';
  tip.setAttribute('role', 'tooltip');
  tip.setAttribute('aria-hidden', 'true');
  doc.body.appendChild(tip);

  let owner: Element | null = null;
  let timer = 0;
  let hiddenAt = 0;

  const place = (el: Element) => {
    const r = el.getBoundingClientRect();
    const t = tip.getBoundingClientRect();
    const vw = doc.documentElement.clientWidth;
    const vh = doc.documentElement.clientHeight;
    let top = r.bottom + GAP;
    let side = 'below';
    if (top + t.height > vh - EDGE && r.top - GAP - t.height >= EDGE) {
      top = r.top - GAP - t.height;
      side = 'above';
    }
    const left = Math.min(Math.max(r.left + r.width / 2 - t.width / 2, EDGE), Math.max(EDGE, vw - EDGE - t.width));
    tip.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
    tip.dataset.side = side;
  };

  const show = (el: Element) => {
    const text = tipText(el);
    if (!text || !el.isConnected) return;
    owner = el;
    tip.replaceChildren();
    const keys = shortcutKeys(el.getAttribute('aria-keyshortcuts'));
    const label = doc.createElement('span');
    label.className = 'ui-tip__label';
    // "Maximise (M)": the chips say the key, so the bracket goes.
    label.textContent = keys.length ? text.replace(/\s*\([^()]{1,16}\)\s*$/, '') : text;
    tip.appendChild(label);
    if (keys.length) {
      const chips = doc.createElement('span');
      chips.className = 'ui-tip__keys';
      for (const key of keys) {
        const kbd = doc.createElement('kbd');
        kbd.textContent = key;
        chips.appendChild(kbd);
      }
      tip.appendChild(chips);
    }
    tip.classList.toggle('is-long', text.length > 48);
    tip.classList.add('is-measuring');
    place(el);
    tip.classList.remove('is-measuring');
    tip.classList.add('is-open');
  };

  const hide = () => {
    win.clearTimeout(timer);
    if (owner) hiddenAt = Date.now();
    owner = null;
    tip.classList.remove('is-open');
  };

  const candidate = (target: EventTarget | null): Element | null => {
    if (!(target instanceof Element)) return null;
    const el = target.closest('[title], [data-ui-tip]');
    if (!el || el === doc.documentElement || el === doc.body) return null;
    if (el.closest('[data-no-ui-tip]')) return null;
    // `data-ui-tip-when="cut"`: name a truncated label in full, and stay
    // quiet while the whole label already shows.
    if (el.getAttribute('data-ui-tip-when') === 'cut' && el.scrollWidth <= el.clientWidth + 1) return null;
    // SVG <title>-style attributes on chart marks are data, not controls.
    if (el instanceof SVGElement && !el.closest('button, a, [role="button"]')) return null;
    return el;
  };

  const arm = (el: Element) => {
    if (el === owner) return;
    win.clearTimeout(timer);
    // Take the title now, so the native box cannot open during the delay.
    tipText(el);
    const warm = owner !== null || Date.now() - hiddenAt < WARM_MS;
    if (owner) tip.classList.remove('is-open');
    owner = null;
    timer = win.setTimeout(() => show(el), warm ? 0 : SHOW_DELAY_MS);
  };

  const onOver = (event: PointerEvent) => {
    if (event.pointerType === 'touch') return;
    const el = candidate(event.target);
    if (el) arm(el);
  };
  const onOut = (event: PointerEvent) => {
    const from = candidate(event.target);
    if (!from) return;
    const to = event.relatedTarget instanceof Node ? event.relatedTarget : null;
    if (to && from.contains(to)) return;
    if (from === owner || !owner) hide();
  };
  const onFocus = (event: FocusEvent) => {
    const el = candidate(event.target);
    if (el && el === event.target && (el as HTMLElement).matches?.(':focus-visible')) arm(el);
  };
  const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') hide(); };

  doc.addEventListener('pointerover', onOver, true);
  doc.addEventListener('pointerout', onOut, true);
  doc.addEventListener('pointerdown', hide, true);
  doc.addEventListener('focusin', onFocus, true);
  doc.addEventListener('focusout', hide, true);
  doc.addEventListener('keydown', onKey, true);
  win.addEventListener('scroll', hide, true);
  win.addEventListener('blur', hide);

  return () => {
    hide();
    doc.removeEventListener('pointerover', onOver, true);
    doc.removeEventListener('pointerout', onOut, true);
    doc.removeEventListener('pointerdown', hide, true);
    doc.removeEventListener('focusin', onFocus, true);
    doc.removeEventListener('focusout', hide, true);
    doc.removeEventListener('keydown', onKey, true);
    win.removeEventListener('scroll', hide, true);
    win.removeEventListener('blur', hide);
    tip.remove();
  };
}
