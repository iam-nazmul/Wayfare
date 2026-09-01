import { describe, expect, it } from 'vitest';

import { countdown, dayOffsetLabel, formatDuration } from './dates';

describe('formatDuration', () => {
  it('renders hours and padded minutes', () => {
    expect(formatDuration(185)).toBe('3h 05m');
  });

  it('renders minutes alone under an hour', () => {
    expect(formatDuration(45)).toBe('45m');
  });
});

describe('dayOffsetLabel', () => {
  it('marks arrivals after midnight', () => {
    expect(dayOffsetLabel(1)).toBe('+1');
  });

  it('stays silent for same-day arrivals', () => {
    expect(dayOffsetLabel(0)).toBeNull();
  });
});

describe('countdown', () => {
  it('reports remaining whole minutes', () => {
    const now = Date.UTC(2026, 8, 1, 12, 0, 0);
    expect(countdown('2026-09-01T12:20:00Z', now)).toEqual({ minutes: 20, expired: false });
  });

  it('clamps a passed deadline to expired', () => {
    const now = Date.UTC(2026, 8, 1, 12, 0, 0);
    expect(countdown('2026-09-01T11:59:00Z', now)).toEqual({ minutes: 0, expired: true });
  });
});
