import { useMutation, useQuery } from '@tanstack/react-query';

import { api } from '../../api/client';
import { keys } from '../../api/keys';
import type { Booking, BookingRequest } from '../../api/types';

export function useCreateBooking() {
  return useMutation({
    mutationFn: (request: BookingRequest) =>
      // The API requires an Idempotency-Key: a double-submitted form must not hold seats twice.
      api.post<Booking>('/bookings', request, { idempotent: true }),
    retry: false,
  });
}

export function useBooking(pnr: string, lastName?: string) {
  const query = lastName ? `?last_name=${encodeURIComponent(lastName)}` : '';

  return useQuery({
    queryKey: keys.booking(pnr),
    queryFn: () => api.get<Booking>(`/bookings/${pnr}${query}`),
    enabled: pnr.length > 0,
    retry: false,
  });
}
