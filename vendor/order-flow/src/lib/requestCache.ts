/**
 * One request per URL, however many callers ask.
 *
 * The page asks for the same thing from several places at load: the archive
 * effect and the previous-close fallback both read today's day file, two hooks
 * ask for the same instrument and the same 1-minute candles, and a cache-busted
 * `?v=`/`?t=` URL defeats the browser's own sharing. `sharedFetch` keeps one
 * promise per URL (cache-buster params ignored) while it is in flight and, for
 * a short `ttlMs` after a SUCCESSFUL answer, hands out the same body to late
 * callers. Failures are never kept, so a retry always goes to the network.
 *
 * Every caller gets its own `Response` (built from the shared body), so each can
 * read the body and parse it without seeing another caller's mutations.
 *
 * `ttlMs: 0` is in-flight sharing only. Use that for anything polled, so a poll
 * can never be answered from a cache.
 */

interface Settled {
  status: number;
  statusText: string;
  headers: [string, string][];
  body: string;
}

interface Entry {
  promise: Promise<Settled>;
  /** Epoch ms the entry stops being served; 0 while the request is still in flight. */
  until: number;
}

export interface SharedFetchOptions {
  /** How long a successful answer is reused after it lands. Default 1500 ms. */
  ttlMs?: number;
  /** Query parameters that only bust caches and so do not make a request different. */
  ignoreParams?: readonly string[];
  /** Shared request's own abort window. Default 20 s. */
  timeoutMs?: number;
}

const DEFAULT_TTL_MS = 1_500;
const DEFAULT_IGNORED = ['t', 'v', '_'] as const;
const NULL_BODY_STATUS = new Set([101, 204, 205, 304]);
const entries = new Map<string, Entry>();
let sweepAt = 0;

function keyFor(url: string, ignore: readonly string[]): string {
  try {
    const parsed = new URL(url, typeof location !== 'undefined' ? location.href : 'http://localhost');
    for (const name of ignore) parsed.searchParams.delete(name);
    parsed.searchParams.sort();
    return parsed.toString();
  } catch {
    return url;
  }
}

function sweep(now: number): void {
  if (now < sweepAt) return;
  sweepAt = now + 10_000;
  for (const [key, entry] of entries) if (entry.until && entry.until <= now) entries.delete(key);
}

function toResponse(settled: Settled): Response {
  return new Response(NULL_BODY_STATUS.has(settled.status) ? null : settled.body, {
    status: settled.status,
    statusText: settled.statusText,
    headers: settled.headers,
  });
}

export async function sharedFetch(
  url: string,
  init: RequestInit = {},
  options: SharedFetchOptions = {},
): Promise<Response> {
  const { ttlMs = DEFAULT_TTL_MS, ignoreParams = DEFAULT_IGNORED, timeoutMs = 20_000 } = options;
  const method = (init.method || 'GET').toUpperCase();
  if (method !== 'GET' || typeof Response === 'undefined') return fetch(url, init);

  const now = Date.now();
  sweep(now);
  const key = keyFor(url, ignoreParams);
  const hit = entries.get(key);
  if (hit && (hit.until === 0 || hit.until > now)) return toResponse(await hit.promise);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const entry: Entry = {
    until: 0,
    promise: fetch(url, { ...init, signal: controller.signal }).then(async res => {
      const settled: Settled = {
        status: res.status,
        statusText: res.statusText ?? '',
        headers: res.headers && typeof res.headers.entries === 'function' ? [...res.headers.entries()] : [],
        body: await res.text(),
      };
      if (res.ok && ttlMs > 0) {
        entry.until = Date.now() + ttlMs;
        // Let go of the body as soon as the reuse window closes: day files run to megabytes.
        setTimeout(() => { if (entries.get(key) === entry) entries.delete(key); }, ttlMs + 50);
      } else if (entries.get(key) === entry) entries.delete(key);
      return settled;
    }),
  };
  entry.promise.catch(() => {
    if (entries.get(key) === entry) entries.delete(key);
  }).finally(() => clearTimeout(timer));
  entries.set(key, entry);
  return toResponse(await entry.promise);
}

/** Forgets every kept answer; requests already in flight finish as usual. For tests and a hard refresh. */
export function clearSharedFetch(): void {
  entries.clear();
}

/** How many URLs are in flight or still inside their reuse window. */
export function sharedFetchSize(): number {
  return entries.size;
}
