import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { FlowBoard } from './FlowBoard';
import { FlowStatus } from './FlowStatus';
import type { FlowCheck, FlowSector, FlowStock, MarketFlow } from './marketFlowModel';

/* The board is drawn from a MarketFlow it is handed, so these tests build one by hand: none of them depends on how the model sorts. */

const OPEN = Date.parse('2026-10-09T09:15:00+05:30');
const MINUTE = 60_000;
const checks = (pass: Array<boolean | null>): FlowCheck[] => pass.map((p, i) => ({ id: (['fresh', 'spot', 'hour', 'options', 'sector'] as const)[i], label: `Check ${i + 1}`, pass: p, note: `note ${i + 1}` }));

function stock(symbol: string, side: 'bullish' | 'bearish', rank: number, over: Partial<FlowStock> = {}): FlowStock {
  const up = side === 'bullish';
  return {
    symbol, name: `${symbol} Industries Limited of India`, kind: 'stock', sector: 'fin', sectorLabel: 'Financial Services', lot: 100, expiry: '2026-10-27',
    spot: 1000, prevClose: 990, spotChangePct: up ? 1 : -1,
    fut: { from: null, to: OPEN + 30 * MINUTE, price: 1010, priceFrom: 1000, priceChange: up ? 10 : -10, priceChangePct: up ? 1 : -1, oi: 2_500_000, oiFrom: 2_000_000, oiChange: 500_000, oiChangePct: 25, buildUp: up ? 'LONG_BUILD' : 'SHORT_BUILD', contractDate: '2026-10-27', months: ['2026-10-27'] },
    futDay: null, futHour: null, futQuarter: null, futures: 'read', changePct: up ? 1.5 : -1.5, source: 'futures', oiChangePct: 12.5,
    buildUp: up ? 'LONG_BUILD' : 'SHORT_BUILD', side,
    options: { putOi: 1, callOi: 1, putOiAdded: 1, callOiAdded: 0, pcr: 1 },
    support: { strike: 980, oi: 500_000, oiChange: 1, distancePct: -2 }, support2: null,
    resistance: { strike: 1040, oi: 400_000, oiChange: 1, distancePct: 4 }, resistance2: null,
    zone: { low: 995, high: 1005, from: OPEN + 5 * MINUTE, to: OPEN + 20 * MINUTE, oiAdded: 120_000 }, zoneNote: null,
    profile: [{ strike: 980, put: 500_000, call: 10_000 }, { strike: 1000, put: 200_000, call: 200_000 }, { strike: 1040, put: 5_000, call: 400_000 }],
    checks: checks([true, true, false, null, true]), strength: 0.7, rank,
    candles: Array.from({ length: 30 }, (_, i) => ({ at: OPEN + i * MINUTE, close: 1000 + i * (up ? 0.4 : -0.4), oi: 2_000_000 + i * 1000 })),
    ...over,
  };
}

function build(bull: number, bear: number, over: Partial<MarketFlow> = {}): MarketFlow {
  const bullish = Array.from({ length: bull }, (_, i) => stock(i === 0 ? 'BAJAJ-AUTO' : `UP${i + 1}`, 'bullish', i + 1));
  const bearish = Array.from({ length: bear }, (_, i) => stock(`DOWN${i + 1}`, 'bearish', i + 1));
  const sectors: FlowSector[] = [{ id: 'fin', label: 'Financial Services', count: bull + bear + 1, bullish: bull, bearish: bear, rangebound: 1, unread: 0, lean: 'mixed', changePct: 0.4, symbols: [] }];
  return {
    asOf: OPEN + 60 * MINUTE, date: '2026-10-09', window: 'day', floorPct: 0.5,
    stocks: [...bullish, ...bearish], sectors, bullish, bearish, rangebound: [], unread: [],
    buckets: { LONG_BUILD: bullish, SHORT_BUILD: bearish, SHORT_COVER: [], LONG_UNWIND: [] },
    featured: { bullish: bullish.slice(0, 2), bearish: bearish.slice(0, 2) },
    futures: { read: bull + bear, unavailable: 0, failed: 0, pending: 0, total: bull + bear, latestAt: OPEN + 30 * MINUTE },
    provisional: false,
    ...over,
  };
}

const SETTINGS = { named: null, lines: 'all' as const };
const board = (flow: MarketFlow | null, layout: 'diagram' | 'desktop' | 'tablet' | 'phone') => (
  <MemoryRouter><FlowBoard flow={flow} settings={SETTINGS} layout={layout} status={<p role="status">status</p>} /></MemoryRouter>
);
const tile = (symbol: string) => document.querySelector<HTMLButtonElement>(`.mf-tile[data-sym="${symbol}"]`)!;

beforeAll(() => {
  // jsdom lays nothing out: give the chart cell a size so the chart draws.
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 1400, height: 800, top: 0, left: 0, right: 1400, bottom: 800, x: 0, y: 0, toJSON: () => ({}) } as DOMRect);
});
afterEach(cleanup);

describe('the desktop board', () => {
  it('draws the chart, the Bullish half over the Bearish half and the sectors, as one surface', () => {
    const { container } = render(board(build(4, 3), 'desktop'));
    expect(container.querySelector('.mf-board[data-layout="desktop"]')).not.toBeNull();
    expect(screen.getByRole('region', { name: /^Bullish 4$/ })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /^Bearish 3$/ })).toBeInTheDocument();
    expect(screen.getByText('Through the day')).toBeInTheDocument();
    expect(container.querySelector('.mf-chart__svg')).not.toBeNull();
    expect(screen.getByRole('button', { name: /^Financial Services: median \+0\.40%/ })).toBeInTheDocument();
    // The sectors come after both halves in the reading order.
    const side = container.querySelector('.mf-side')!;
    const rail = container.querySelector('.mf-rail')!;
    expect(side.compareDocumentPosition(rail) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('shows every underlying of a side as a tile, ranked, then one or two large cards', () => {
    render(board(build(70, 2), 'desktop'));
    const bullish = screen.getByRole('region', { name: /^Bullish 70$/ });
    expect(bullish.querySelectorAll('.mf-tile')).toHaveLength(70);
    expect(within(bullish).getAllByRole('article')).toHaveLength(2);
    expect(tile('BAJAJ-AUTO').textContent).toContain('BAJAJ-AUTO');
    expect(tile('BAJAJ-AUTO').querySelector('.mf-tile__rk')!.textContent).toBe('1');
  });

  it('uses the true minus, no advice words, and no native tooltips', () => {
    const { container } = render(board(build(3, 2), 'desktop'));
    expect(container.querySelector('.mf-half.is-bearish .mf-num.is-down')!.textContent).toBe('−1.50%');
    expect(container.textContent).not.toMatch(/\bpick|R:R|\brisk\b|\btrade\b/i);
    expect(container.querySelector('[title]')).toBeNull();
  });

  it('fills the large cards with demo cards on the real leaders while the futures load', () => {
    const flow = build(4, 3, { featured: { bullish: [], bearish: [] }, futures: { read: 2, unavailable: 0, failed: 0, pending: 5, total: 7, latestAt: null }, provisional: true });
    const { container } = render(board(flow, 'desktop'));
    const demos = [...container.querySelectorAll('.mf-card.is-demo')];
    expect(demos).toHaveLength(4);
    expect(demos.map(card => card.getAttribute('data-sym'))).toEqual([...flow.bullish.slice(0, 2), ...flow.bearish.slice(0, 2)].map(stock => stock.symbol));
    expect(screen.getAllByText('Demo')).toHaveLength(4);
    expect(container.querySelector('.mf-card.is-holding')).toBeNull();
  });

  it('says so plainly when a side is empty', () => {
    render(board(build(0, 3), 'desktop'));
    expect(screen.getByText('None up more than 0.5%')).toBeInTheDocument();
  });

  it('gives conviction as five dots with an accessible label', () => {
    const { container } = render(board(build(2, 1), 'desktop'));
    const meter = container.querySelector('.mf-card .mf-dots')!;
    expect(meter).toHaveAttribute('role', 'img');
    expect(meter.getAttribute('aria-label')).toBe('Conviction: 3 of 4');
    expect(meter.querySelectorAll('i')).toHaveLength(5);
  });
});

describe('hover and pin', () => {
  it('lights the tile, its card and its line on hover without re-rendering, and opens the detail over the other half', async () => {
    vi.useFakeTimers();
    const { container } = render(board(build(4, 3), 'desktop'));
    const target = tile('BAJAJ-AUTO');
    fireEvent.pointerOver(target, { pointerType: 'mouse' });
    expect(target).toHaveClass('is-lit');
    expect(container.querySelector('.mf-board')).toHaveClass('has-focus');
    expect(container.querySelector('.mf-card[data-sym="BAJAJ-AUTO"]')).toHaveClass('is-lit');
    expect(container.querySelector('.mf-chart__lit .is-up')!.getAttribute('d')).toMatch(/^M/);
    act(() => { vi.advanceTimersByTime(100); });
    const detail = screen.getByRole('tooltip', { name: 'BAJAJ-AUTO in detail' });
    expect(detail).toHaveClass('is-bottom');
    expect(within(detail).getByText('#1')).toBeInTheDocument();
    expect(within(detail).getByText('Long build-up')).toBeInTheDocument();
    fireEvent.pointerOut(target, { pointerType: 'mouse', relatedTarget: document.body });
    act(() => { vi.advanceTimersByTime(200); });
    expect(target).not.toHaveClass('is-lit');
    expect(screen.queryByRole('tooltip')).toBeNull();
    vi.useRealTimers();
  });

  it('pins the detail on a click, with no links off the page, and lets go on Escape', () => {
    render(board(build(4, 3), 'desktop'));
    fireEvent.click(tile('DOWN1'));
    const detail = screen.getByRole('dialog', { name: 'DOWN1 in detail' });
    // Pinned, the detail takes the whole column (owner, 26 Oct 2026).
    expect(detail).toHaveClass('is-full');
    expect(within(detail).queryByRole('link')).toBeNull();
    // → steps to the next stock on the same side, ← back.
    fireEvent.keyDown(document, { key: 'ArrowRight' });
    expect(screen.getByRole('dialog', { name: 'DOWN2 in detail' })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'ArrowLeft' });
    expect(screen.getByRole('dialog', { name: 'DOWN1 in detail' })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('lights a sector’s tiles and dims the rest, and keeps it on a click', () => {
    const { container } = render(board(build(3, 2), 'desktop'));
    const sector = screen.getByRole('button', { name: /^Financial Services: / });
    fireEvent.pointerEnter(sector, { pointerType: 'mouse' });
    expect(container.querySelector('.mf-board')).toHaveAttribute('data-focus-kind', 'sector');
    expect(tile('UP2')).toHaveClass('is-lit');
    fireEvent.click(sector);
    fireEvent.pointerLeave(sector, { pointerType: 'mouse' });
    expect(tile('UP2')).toHaveClass('is-lit');
  });

  it('moves between tiles with the arrow keys', () => {
    render(board(build(4, 1), 'desktop'));
    const first = tile('BAJAJ-AUTO');
    expect(first.tabIndex).toBe(0);
    expect(tile('UP2').tabIndex).toBe(-1);
    first.focus();
    fireEvent.keyDown(first, { key: 'ArrowRight' });
    expect(document.activeElement).toBe(tile('UP2'));
    expect(tile('UP2').tabIndex).toBe(0);
  });
});

describe('tablet and phone', () => {
  it('stacks the chart over the two halves on a tablet', () => {
    render(board(build(4, 3), 'tablet'));
    expect(screen.getByRole('region', { name: 'Through the day' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /^Bullish 4$/ })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /^Bearish 3$/ })).toBeInTheDocument();
  });

  it('shows one panel at a time under a segmented control on a phone, and opens the detail as a sheet on a tap', () => {
    render(board(build(4, 3), 'phone'));
    expect(screen.getByRole('radio', { name: 'Chart' })).toBeChecked();
    expect(screen.queryByRole('region', { name: /^Bullish/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: /^Bullish 4$/ }));
    expect(screen.getByRole('region', { name: /^Bullish 4$/ })).toBeInTheDocument();
    fireEvent.click(tile('UP2'));
    expect(screen.getByRole('dialog', { name: 'UP2 in detail' })).toHaveClass('is-sheet');
  });
});

describe('before anything is read', () => {
  it('draws the same frame with quiet blocks, never an empty box', () => {
    const { container } = render(board(null, 'desktop'));
    expect(screen.getByRole('region', { name: 'Bullish' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Bearish' })).toBeInTheDocument();
    expect(container.querySelectorAll('.mf-tile.is-skeleton').length).toBeGreaterThan(10);
    expect(container.querySelector('.mf-skel.is-chart')).not.toBeNull();
  });
});

describe('the status line', () => {
  const base = { loading: false, futuresRead: 124, futuresTotal: 124, onRescan: () => undefined };
  const flow = build(53, 71);

  it('says how the market split and of how many, and the time the board stands for', () => {
    render(<FlowStatus {...base} flow={flow} at={OPEN + 60 * MINUTE} now={OPEN + 3 * 60 * MINUTE} />);
    const status = screen.getByRole('status');
    expect(status.textContent).toContain('53 up · 0 flat · 71 down of 124');
    expect(status.textContent).toContain('As of 9 Oct, 10:15 · futures to 09:45');
    expect(status.textContent).not.toContain('earlier session');
  });

  it('marks the counts as updating while futures load, and says how many failed once done', () => {
    const { rerender } = render(<FlowStatus {...base} flow={{ ...flow, provisional: true }} at={OPEN} futuresRead={84} futuresTotal={124} now={OPEN} />);
    expect(screen.getByRole('status')).toHaveClass('is-updating');
    expect(screen.getByText(/Updating · futures 84 of 124/)).toBeInTheDocument();
    rerender(<FlowStatus {...base} flow={{ ...flow, futures: { ...flow.futures, failed: 3 } }} at={OPEN} now={OPEN} />);
    expect(screen.getByText('3 could not load')).toBeInTheDocument();
  });

  it('says when the file is from an earlier session', () => {
    render(<FlowStatus {...base} flow={flow} at={OPEN + 60 * MINUTE} now={Date.parse('2026-10-13T10:00:00+05:30')} />);
    expect(screen.getByText('an earlier session')).toHaveClass('mf-status__aged');
  });

  it('says it is loading, passes on the server\'s error, and offers to try again', () => {
    const { rerender } = render(<FlowStatus {...base} flow={null} at={null} loading />);
    expect(screen.getByText('Loading the market…')).toBeInTheDocument();
    rerender(<FlowStatus {...base} flow={null} at={null} loading error="Provider failed to start: Set UPSTOX_ACCESS_TOKEN." />);
    expect(screen.getByText(/Set UPSTOX_ACCESS_TOKEN/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
  });

  it('names the source, and marks the demo market as live', () => {
    const { rerender } = render(<FlowStatus {...base} flow={flow} at={OPEN} now={OPEN} provider={{ id: 'demo', label: 'Demo market', alwaysLive: true }} />);
    expect(screen.getByText('Demo market · live')).toHaveClass('is-demo');
    rerender(<FlowStatus {...base} flow={flow} at={OPEN} now={OPEN} provider={{ id: 'upstox', label: 'Upstox', alwaysLive: false }} />);
    expect(screen.getByText('Upstox')).not.toHaveClass('is-demo');
    rerender(<FlowStatus {...base} flow={flow} at={OPEN} now={Date.parse('2026-11-04T10:00:00+05:30')} provider={{ id: 'recorded', label: 'Recorded 30 Oct 2026', alwaysLive: true }} />);
    expect(screen.getByText('Recorded 30 Oct 2026 · replay')).toBeInTheDocument();
    // A recorded day is old on purpose: no "earlier session" warning.
    expect(screen.queryByText(/an earlier session/)).toBeNull();
  });
});

describe('the wide desktop diagram', () => {
  it('carries each line on to its tile: halves, small tiles, tall tiles and cards, the sector pills and the strip', () => {
    const { container } = render(board(build(6, 5), 'diagram'));
    expect(container.querySelector('.mf-board[data-layout="diagram"]')).not.toBeNull();
    expect(screen.getByRole('region', { name: 'Bullish 6' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Bearish 5' })).toBeInTheDocument();
    // Two featured each side as a tall tile and a card; the other names as small tiles.
    expect(container.querySelectorAll('.is-bullish .mf-tall')).toHaveLength(2);
    expect(container.querySelectorAll('.is-bullish .mf-dgcard')).toHaveLength(2);
    expect(container.querySelectorAll('.is-bullish .mf-tile.is-dg')).toHaveLength(4);
    // A curve per shown tile, drawn under them.
    expect(container.querySelector('.mf-dg__conn.is-up')!.getAttribute('d')).toMatch(/C/);
    expect(screen.getByRole('button', { name: /^Financial Services: median/ })).toHaveClass('mf-pill');
    // The count sits in its own span (it pops when it changes), so match the whole label.
    expect(screen.getByText((_, el) => el?.tagName === 'B' && el.textContent === '▲ Bullish 6')).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/\bpick|R:R|\brisk\b|\btrade\b|unlock/i);
  });

  it('lights one path end to end on hover: line, gate run and curve, and the tile', () => {
    const { container } = render(board(build(6, 5), 'diagram'));
    const target = container.querySelector<HTMLButtonElement>('.mf-tile.is-dg[data-sym="UP4"]')!;
    fireEvent.pointerOver(target, { pointerType: 'mouse' });
    expect(target).toHaveClass('is-lit');
    const lit = container.querySelector('.mf-dg__lit .is-line')!.getAttribute('d')!;
    expect(lit.startsWith('M')).toBe(true);
    expect(lit.match(/C/g)!.length).toBeGreaterThanOrEqual(2);
    expect(container.querySelector('.mf-dg__lit')).toHaveClass('is-up');
  });

  it('shows as many tiles as fit and no "more" tile or list for the rest', () => {
    const { container } = render(board(build(90, 2), 'diagram'));
    const tiles = container.querySelectorAll('.is-bullish .mf-tile.is-dg');
    expect(tiles.length).toBeGreaterThan(0);
    expect(tiles.length).toBeLessThan(90);
    expect(container.querySelector('.mf-tile.is-more')).toBeNull();
    expect(container.textContent).not.toMatch(/\+\d+\s*more/);
  });

  it('runs a comet along each lead path, pulses its last reading and haloes the origin', () => {
    const { container } = render(board(build(6, 5), 'diagram'));
    const comets = Array.from(container.querySelectorAll('.mf-dg__comet'));
    expect(comets.length).toBeGreaterThan(0);
    // Every comet's track is a lead path that exists in the document.
    for (const comet of comets) {
      const href = comet.querySelector('mpath')?.getAttribute('href') ?? '';
      expect(href).toMatch(/^#mf-lead-/);
      expect(container.querySelector(href)?.classList.contains('mf-dg__bold')).toBe(true);
    }
    expect(container.querySelectorAll('.mf-dg__live')).toHaveLength(comets.length);
    expect(container.querySelector('.mf-dg__origin .is-halo')).not.toBeNull();
  });

  it('pins the detail with candles from a card', () => {
    const { container } = render(board(build(6, 5), 'diagram'));
    fireEvent.click(container.querySelector<HTMLButtonElement>('.mf-dgcard[data-sym="DOWN1"] .mf-dgcard__main')!);
    const detail = screen.getByRole('dialog', { name: 'DOWN1 in detail' });
    expect(detail).toHaveClass('is-full');
    expect(container.querySelector('.mf-dgcard[data-sym="DOWN1"] .mf-candles rect')).not.toBeNull();
  });
});
