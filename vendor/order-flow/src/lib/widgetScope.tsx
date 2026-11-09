/**
 * Which terminal widget a component is rendered inside, if any.
 *
 * A workspace page keeps its choices (view, window, columns, overlays) under
 * fixed localStorage keys and owns a few fixed element ids. That is right for a
 * route, where one copy exists. The terminal can show several widgets that are
 * built from the same page — Open Interest as a profile, as a change view and
 * as a strike PCR — and each must remember its own choices and keep its own ids.
 *
 * The terminal wraps every widget in `WidgetScopeContext` with the widget's
 * type as the scope. Outside it (the routes) the scope is null and every key
 * and id is exactly what it always was, so a route is byte-for-byte unchanged.
 */

import { createContext, useContext, useRef } from 'react';

export const WidgetScopeContext = createContext<string | null>(null);

/** The scope of the widget this component sits in, or null on a route. */
export function useWidgetScope(): string | null {
  return useContext(WidgetScopeContext);
}

/** Marks a storage key as one widget's own. A route's key (no scope) is returned unchanged. */
export function scopedKey(key: string, scope: string | null): string {
  return scope ? `${key}@tw:${scope}` : key;
}

/** `scopedKey` for the widget this component sits in. */
export function useScopedKey(key: string): string {
  return scopedKey(key, useWidgetScope());
}

/** A DOM id that stays unique when several widgets of one page share the screen. */
export function useWidgetDomId(base: string): string {
  const scope = useWidgetScope();
  return scope ? `${base}-${scope}` : base;
}

/** Removes every choice the given widgets remembered (their keys all carry the `@tw:<scope>` mark), in one pass over storage. */
export function forgetWidgetScopes(scopes: readonly string[]): void {
  if (scopes.length === 0) return;
  try {
    const marks = scopes.map(scope => `@tw:${scope}`);
    const doomed: string[] = [];
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const key = window.localStorage.key(i);
      if (key && marks.some(mark => key.endsWith(mark))) doomed.push(key);
    }
    doomed.forEach(key => window.localStorage.removeItem(key));
  } catch { /* storage blocked: nothing was kept */ }
}

/** Removes every choice one widget remembered. The terminal calls it (through `forgetWidgetScopes`) once a widget type has left every saved layout. */
export function forgetWidgetScope(scope: string): void {
  forgetWidgetScopes([scope]);
}

/**
 * Whether the widget this component sits in is doing work. False while the card
 * is far from the visible stage or the tab is hidden; a route (no widget) is
 * always active. A heavy widget reads it to skip its own timers and rebuilds.
 */
export const WidgetActivityContext = createContext(true);

export function useWidgetActive(): boolean {
  return useContext(WidgetActivityContext);
}

/** `value`, held at its last active reading while the widget is inactive, so a memo keyed on it does not rebuild for nobody. */
export function useHeldWhileInactive<T>(value: T): T {
  const active = useWidgetActive();
  const held = useRef(value);
  if (active) held.current = value;
  return held.current;
}
