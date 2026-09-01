import { useQuery } from '@tanstack/react-query';

import { api } from '../../api/client';
import { keys } from '../../api/keys';
import type { Airport, SearchRequest, SearchResponse } from '../../api/types';

export function useAirports(query: string) {
  return useQuery({
    queryKey: keys.airports(query),
    queryFn: () => api.get<Airport[]>(`/airports?q=${encodeURIComponent(query)}`),
    // Airport data effectively never changes within a session.
    staleTime: 24 * 60 * 60 * 1000,
    enabled: query.trim().length >= 2,
  });
}

export function useFlightSearch(request: SearchRequest | null) {
  return useQuery({
    queryKey: keys.search(request),
    queryFn: () => api.post<SearchResponse>('/search/flights', request),
    // Matches the server-side 60s search cache; refetching sooner just re-reads the same prices.
    staleTime: 60_000,
    enabled: request !== null,
    retry: false,
  });
}
