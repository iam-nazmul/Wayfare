/** Query-key factories. Never inline a key string — invalidation depends on these shapes. */
export const keys = {
  me: () => ['me'] as const,
  travellers: () => ['travellers'] as const,
  airports: (query: string) => ['airports', query] as const,
  search: (params: unknown) => ['search', params] as const,
  offers: (searchId: string) => ['offers', searchId] as const,
  booking: (pnr: string) => ['booking', pnr] as const,
  seatmap: (pnr: string, segmentId: string) => ['seatmap', pnr, segmentId] as const,
  checkin: (pnr: string) => ['checkin', pnr] as const,
} as const;
