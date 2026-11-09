import { useCallback, useState, type SetStateAction } from 'react';
import { useScopedKey } from '@/lib/widgetScope';

/**
 * A choice the reader made, remembered in this browser.
 *
 * Owner, 2026-09-26: every page's customisation is kept in the reader's own
 * browser, so a page reopens the way they left it. There is no account behind
 * it: the choice lives in this browser's localStorage, one copy per browser
 * and device, and survives a reload, a new tab and a restart. Clearing the
 * browser's cache keeps it; clearing the site's data forgets it.
 *
 * What goes through here is a way of LOOKING: a view, a time window, a time
 * step. A MOMENT is never remembered (an as-of time, a rewind, a replay, a
 * picked strike): reopening tomorrow on yesterday's 11:05 would chart a stale
 * instant that looks live.
 *
 * Every read is checked against what the page offers today (`parse`), so an
 * entry from an older release, another tab or a hand edit falls back to the
 * default instead of breaking the page. Storage that is blocked or full costs
 * only the memory: the choice still applies for this visit.
 *
 * The pages' Customise lenses keep their own `<page>Customise:v1` objects;
 * this is for the single choices that sit beside them.
 */

/** Every key read or written here, so tests can forget exactly these. */
const served = new Set<string>();

export function readRemembered<T>(key: string, parse: (raw: unknown) => T | undefined, fallback: T): T {
  served.add(key);
  try {
    const raw = window.localStorage.getItem(key);
    if (raw == null) return fallback;
    const value = parse(JSON.parse(raw));
    return value === undefined ? fallback : value;
  } catch {
    return fallback;
  }
}

export function remember(key: string, value: unknown): void {
  served.add(key);
  try { window.localStorage.setItem(key, JSON.stringify(value)); } catch { /* blocked or full: the choice lasts this visit */ }
}

/** A `parse` that accepts only the values a control offers. */
export function oneOf<T>(allowed: readonly T[]): (raw: unknown) => T | undefined {
  return raw => ((allowed as readonly unknown[]).includes(raw) ? raw as T : undefined);
}

/**
 * `useState` that opens on the remembered value and remembers every change.
 * The key is fixed for the component's life; inside a terminal widget it is scoped to that widget.
 */
export function useRemembered<T>(
  routeKey: string,
  parse: (raw: unknown) => T | undefined,
  fallback: T,
): [T, (next: SetStateAction<T>) => void] {
  /* Inside a terminal widget the key is that widget's own (lib/widgetScope); on a route it is routeKey. */
  const key = useScopedKey(routeKey);
  const [value, setValue] = useState<T>(() => readRemembered(key, parse, fallback));
  const update = useCallback((next: SetStateAction<T>) => {
    setValue(previous => {
      const resolved = typeof next === 'function' ? (next as (previous: T) => T)(previous) : next;
      remember(key, resolved);
      return resolved;
    });
  }, [key]);
  return [value, update];
}

/** One of a control's fixed values: a view capsule, a window, a time step. */
export function useRememberedChoice<T extends string | number>(
  key: string,
  allowed: readonly T[],
  fallback: T,
): [T, (next: SetStateAction<T>) => void] {
  return useRemembered(key, oneOf(allowed), fallback);
}

/** Test support: forget every key served here, so one test's choice never opens the next test's page. */
export function forgetRemembered(): void {
  served.forEach(key => {
    try { window.localStorage.removeItem(key); } catch { /* nothing to forget */ }
  });
}
