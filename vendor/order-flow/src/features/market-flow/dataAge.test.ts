import { describe, expect, it } from 'vitest';
import { describeDataAge } from './dataAge';

const ist = (iso: string) => Date.parse(`${iso}+05:30`);

describe('describeDataAge', () => {
  it('is fresh when the reading is from the latest trading session, even after the close', () => {
    const age = describeDataAge(ist('2026-10-15T15:40:00'), ist('2026-10-15T18:00:00'));
    expect(age).toEqual({ aged: false, date: '2026-10-15' });
  });

  it('is aged when the reading is from an earlier session than the latest', () => {
    expect(describeDataAge(ist('2026-10-14T15:40:00'), ist('2026-10-15T11:00:00')).aged).toBe(true);
  });

  it('treats a weekend as part of Friday: a Friday reading read on Sunday is fresh', () => {
    expect(describeDataAge(ist('2026-10-16T15:40:00'), ist('2026-10-18T12:00:00')).aged).toBe(false);
  });
});
