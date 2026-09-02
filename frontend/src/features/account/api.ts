import { useQuery } from '@tanstack/react-query';

import { api } from '../../api/client';
import { keys } from '../../api/keys';
import type { BookingSummary, Paginated } from '../../api/types';

/** The signed-in traveller's own bookings. Ownership is enforced server-side. */
export function useMyBookings(enabled = true) {
  return useQuery({
    queryKey: keys.myBookings(),
    queryFn: () => api.get<Paginated<BookingSummary>>('/me/bookings'),
    enabled,
    retry: false,
  });
}
