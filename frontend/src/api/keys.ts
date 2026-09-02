/** Query-key factories. Never inline a key string — invalidation depends on these shapes. */
export const keys = {
  me: () => ['me'] as const,
  travellers: () => ['travellers'] as const,
  airports: (query: string) => ['airports', query] as const,
  search: (params: unknown) => ['search', params] as const,
  offers: (searchId: string) => ['offers', searchId] as const,
  booking: (pnr: string) => ['booking', pnr] as const,
  tickets: (pnr: string) => ['tickets', pnr] as const,
  payments: (pnr: string) => ['payments', pnr] as const,
  refunds: (pnr: string) => ['refunds', pnr] as const,
  rebookOptions: (pnr: string) => ['rebook-options', pnr] as const,
  refundQueue: (status: string) => ['ops', 'refunds', status] as const,
  disruptions: () => ['ops', 'disruptions'] as const,
  report: (slug: string, params: unknown) => ['ops', 'report', slug, params] as const,
  paymentIntent: (pnr: string, intentId: string) => ['payment-intent', pnr, intentId] as const,
  seatmap: (pnr: string, segmentId: string) => ['seatmap', pnr, segmentId] as const,
  checkin: (pnr: string) => ['checkin', pnr] as const,
} as const;
