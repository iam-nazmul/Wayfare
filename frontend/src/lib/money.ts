export interface Money {
  amount: string;
  currency: string;
}

/**
 * Format an API money object. Amounts arrive as decimal strings and stay strings —
 * parsing to Number for arithmetic reintroduces the float bug the API avoids.
 */
export function formatMoney(money: Money, locale = 'en-US'): string {
  const value = Number(money.amount);
  if (Number.isNaN(value)) return `${money.amount} ${money.currency}`;

  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: money.currency,
    minimumFractionDigits: 2,
  }).format(value);
}

/** Whole-currency display for prices in dense tables (fare grids, calendars). */
export function formatMoneyCompact(money: Money, locale = 'en-US'): string {
  const value = Number(money.amount);
  if (Number.isNaN(value)) return money.amount;

  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: money.currency,
    maximumFractionDigits: 0,
  }).format(value);
}

export function zeroMoney(currency: string): Money {
  return { amount: '0.00', currency };
}
