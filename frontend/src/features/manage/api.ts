import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../../api/client';
import { keys } from '../../api/keys';
import type {
  Booking,
  CancelResponse,
  ChangeConfirmResponse,
  ChangeQuote,
  Payment,
  RebookOption,
  Refund,
  Ticket,
} from '../../api/types';

function guest(lastName?: string): string {
  return lastName ? `?last_name=${encodeURIComponent(lastName)}` : '';
}

/**
 * A booking in flight changes underneath the page: the webhook decides when it is ticketed, and
 * a disruption can arrive at any moment. Poll while it is still moving, stop when it settles.
 */
export function useManagedBooking(pnr: string, lastName?: string) {
  return useQuery({
    queryKey: keys.booking(pnr),
    queryFn: () => api.get<Booking>(`/bookings/${pnr}${guest(lastName)}`),
    enabled: pnr.length > 0,
    retry: false,
    staleTime: 0,
    refetchInterval: (query) =>
      query.state.data?.status === 'PENDING_TICKETING' ? 5000 : false,
  });
}

export function useTickets(pnr: string, lastName?: string, enabled = true) {
  return useQuery({
    queryKey: keys.tickets(pnr),
    queryFn: () => api.get<Ticket[]>(`/bookings/${pnr}/tickets${guest(lastName)}`),
    enabled: enabled && pnr.length > 0,
    retry: false,
  });
}

export function usePayments(pnr: string, lastName?: string, enabled = true) {
  return useQuery({
    queryKey: keys.payments(pnr),
    queryFn: () => api.get<Payment[]>(`/bookings/${pnr}/payments${guest(lastName)}`),
    enabled: enabled && pnr.length > 0,
    retry: false,
  });
}

export function useRefunds(pnr: string, lastName?: string, enabled = true) {
  return useQuery({
    queryKey: keys.refunds(pnr),
    queryFn: () => api.get<Refund[]>(`/bookings/${pnr}/refunds${guest(lastName)}`),
    enabled: enabled && pnr.length > 0,
    retry: false,
  });
}

export function useRebookOptions(pnr: string, lastName?: string, enabled = true) {
  return useQuery({
    queryKey: keys.rebookOptions(pnr),
    queryFn: () => api.get<RebookOption[]>(`/bookings/${pnr}/rebook-options${guest(lastName)}`),
    enabled: enabled && pnr.length > 0,
    retry: false,
  });
}

function useBookingMutation<TVariables, TData>(
  pnr: string,
  request: (variables: TVariables) => Promise<TData>,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: request,
    retry: false,
    // Anything that services a booking moves money, coupons or seats — refetch all of it.
    onSuccess: () => {
      for (const key of [
        keys.booking(pnr),
        keys.tickets(pnr),
        keys.payments(pnr),
        keys.refunds(pnr),
        keys.rebookOptions(pnr),
      ]) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });
}

export function useCancelBooking(pnr: string, lastName?: string) {
  return useBookingMutation(pnr, (body: { reason?: string; quote_only?: boolean }) =>
    api.post<CancelResponse>(
      `/bookings/${pnr}/cancel`,
      { last_name: lastName, ...body },
      { idempotent: true },
    ),
  );
}

/** Quoting is read-only, so it deliberately does not invalidate anything. */
export function useChangeQuote(pnr: string, lastName?: string) {
  return useMutation({
    mutationFn: (offerId: string) =>
      api.post<ChangeQuote>(`/bookings/${pnr}/change/quote`, {
        offer_id: offerId,
        last_name: lastName,
      }),
    retry: false,
  });
}

export function useConfirmChange(pnr: string, lastName?: string) {
  return useBookingMutation(pnr, (offerId: string) =>
    api.post<ChangeConfirmResponse>(
      `/bookings/${pnr}/change/confirm`,
      { offer_id: offerId, last_name: lastName },
      { idempotent: true },
    ),
  );
}

export function useRebook(pnr: string, lastName?: string) {
  return useBookingMutation(pnr, (optionId: string) =>
    api.post<Booking>(
      `/bookings/${pnr}/rebook`,
      { option_id: optionId, last_name: lastName },
      { idempotent: true },
    ),
  );
}
