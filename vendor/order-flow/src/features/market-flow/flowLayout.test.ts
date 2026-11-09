import { describe, expect, it } from 'vitest';
import { axisReach, labelCapacity, niceStep, quantile, stackLabels, CHANGE_STEPS } from './flowLayout';

const bounds = { height: 14, top: 10, bottom: 300 };
const gaps = (placed: Map<string, number>) => {
  const ys = [...placed.values()].sort((a, b) => a - b);
  return ys.slice(1).map((y, i) => y - ys[i]);
};

describe('stackLabels', () => {
  it('leaves a lone label where its line ends', () => {
    expect(stackLabels([{ id: 'A', y: 120 }], bounds).get('A')).toBe(120);
  });

  it('leaves labels that already clear one another where they are', () => {
    const placed = stackLabels([{ id: 'A', y: 40 }, { id: 'B', y: 100 }, { id: 'C', y: 200 }], bounds);
    expect([...placed.values()]).toEqual([40, 100, 200]);
  });

  it('lays a crowd down one label height apart, so none overprints another', () => {
    const anchors = ['A', 'B', 'C', 'D', 'E'].map((id, i) => ({ id, y: 150 + i * 2 }));
    const placed = stackLabels(anchors, bounds);
    for (const gap of gaps(placed)) expect(gap).toBeGreaterThanOrEqual(14 - 1e-9);
    // The crowd stays centred on where its members wanted to be.
    const mean = [...placed.values()].reduce((a, b) => a + b, 0) / placed.size;
    expect(mean).toBeGreaterThan(145);
    expect(mean).toBeLessThan(165);
  });

  it('keeps the order of the lines it was given', () => {
    const placed = stackLabels([{ id: 'low', y: 205 }, { id: 'high', y: 200 }, { id: 'mid', y: 202 }], bounds);
    expect(placed.get('high')!).toBeLessThan(placed.get('mid')!);
    expect(placed.get('mid')!).toBeLessThan(placed.get('low')!);
  });

  it('holds a crowd at the top edge inside the bounds, laid back down from the top', () => {
    const placed = stackLabels(['A', 'B', 'C'].map((id, i) => ({ id, y: 8 + i })), bounds);
    expect(placed.get('A')).toBe(10);
    expect(placed.get('B')).toBe(24);
    expect(placed.get('C')).toBe(38);
  });

  it('holds a crowd at the bottom edge inside the bounds', () => {
    const placed = stackLabels(['A', 'B', 'C'].map((id, i) => ({ id, y: 301 + i })), bounds);
    expect(Math.max(...placed.values())).toBeLessThanOrEqual(300);
    for (const gap of gaps(placed)) expect(gap).toBeGreaterThanOrEqual(14 - 1e-9);
  });

  it('keeps every pair apart however the lines are scattered (checked over many arrangements)', () => {
    let seed = 7;
    const rand = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
    for (let round = 0; round < 200; round += 1) {
      const n = 1 + Math.floor(rand() * 20);
      const anchors = Array.from({ length: n }, (_, i) => ({ id: `S${i}`, y: 10 + rand() * 290 }));
      const placed = stackLabels(anchors, bounds);
      expect(placed.size).toBe(n);
      for (const gap of gaps(placed)) expect(gap).toBeGreaterThanOrEqual(14 - 1e-6);
      for (const y of placed.values()) { expect(y).toBeGreaterThanOrEqual(10 - 1e-6); expect(y).toBeLessThanOrEqual(300 + 1e-6); }
    }
  });
});

describe('labelCapacity', () => {
  it('counts the labels that fit one height apart, both ends included', () => {
    expect(labelCapacity({ height: 14, top: 0, bottom: 28 })).toBe(3);
    expect(labelCapacity({ height: 14, top: 0, bottom: 27 })).toBe(2);
    expect(labelCapacity({ height: 14, top: 0, bottom: -5 })).toBe(0);
  });
});

describe('axes', () => {
  it('picks the first step that leaves the ticks their room', () => {
    expect(niceStep(8, 150, 30, CHANGE_STEPS)).toBe(2);
    expect(niceStep(0.5, 150, 30, CHANGE_STEPS)).toBe(0.1);
  });

  it('reaches the 99th percentile move, never under twice the floor, never short of the picks', () => {
    const changes = Array.from({ length: 100 }, (_, i) => (i - 50) / 25);
    expect(axisReach(changes, 0.5)).toBeGreaterThan(1.9);
    expect(axisReach([0.01, -0.02], 0.5)).toBe(1);
    expect(axisReach([0.5, -0.4], 0.1, 6)).toBeCloseTo(6.3, 5);
    expect(quantile([], 0.99)).toBe(0);
  });

});
