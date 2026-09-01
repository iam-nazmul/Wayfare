import { describe, expect, it } from 'vitest';

import { formatMoney, formatMoneyCompact, zeroMoney } from './money';

describe('formatMoney', () => {
  it('renders the currency symbol and two decimals', () => {
    expect(formatMoney({ amount: '412.50', currency: 'USD' })).toBe('$412.50');
  });

  it('keeps trailing zeros', () => {
    expect(formatMoney({ amount: '400.00', currency: 'USD' })).toBe('$400.00');
  });

  it('falls back to the raw string when the amount is not numeric', () => {
    expect(formatMoney({ amount: 'n/a', currency: 'USD' })).toBe('n/a USD');
  });

  it('drops decimals in compact mode', () => {
    expect(formatMoneyCompact({ amount: '412.50', currency: 'USD' })).toBe('$413');
  });

  it('builds a zero amount for a currency', () => {
    expect(zeroMoney('EUR')).toEqual({ amount: '0.00', currency: 'EUR' });
  });
});
