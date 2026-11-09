import '@testing-library/jest-dom';
import { afterEach } from 'vitest';
import { forgetRemembered } from '@/lib/remembered';
import { clearSharedFetch } from '@/lib/requestCache';

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
  .IS_REACT_ACT_ENVIRONMENT = true;

// jsdom ships no matchMedia, so any component that asks the viewport a
// question (useNarrowViewport) throws on mount. Report "not narrow" and keep
// the listener API real so components can subscribe and unsubscribe cleanly.
if (typeof window !== 'undefined' && typeof window.matchMedia !== 'function') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
}

// Use jsdom's own Storage for every test. Newer Node versions put an
// experimental localStorage on the global object that shadows it (and warns
// that it needs --localstorage-file); jsdom's is the spec-shaped one that
// StorageEvent, Object.keys(localStorage) and `length` all expect.
{
  const jsdomWindow = (globalThis as typeof globalThis & { jsdom?: { window: Window } }).jsdom?.window;
  if (jsdomWindow) {
    for (const target of [globalThis, window]) {
      Object.defineProperty(target, 'localStorage', { value: jsdomWindow.localStorage, writable: true, configurable: true });
    }
  }
}

// Remembered choices (src/lib/remembered.ts) live in localStorage, which a
// test file shares across its tests: forget them after each one, so a view
// picked in one test never opens the next test's page.
afterEach(() => { forgetRemembered(); });

// The shared request layer reuses an answer for a moment; no test may see another's.
afterEach(() => clearSharedFetch());
