import { useMutation, useQuery } from '@tanstack/react-query';

import { api } from '../../api/client';
import { keys } from '../../api/keys';
import type { Booking, PaymentIntent, Ticket } from '../../api/types';

function guest(lastName?: string): string {
  return lastName ? `?last_name=${encodeURIComponent(lastName)}` : '';
}

export function useCreateIntent(pnr: string, lastName?: string) {
  return useMutation({
    mutationFn: () =>
      api.post<PaymentIntent>(`/bookings/${pnr}/payment-intents${guest(lastName)}`, undefined, {
        idempotent: true,
      }),
    retry: false,
  });
}

/**
 * Stands in for the provider's browser SDK. With a real provider the card would go straight to
 * them and never touch this origin; the sandbox endpoint mirrors that shape so the code either
 * side of it is the same.
 */
export function useConfirmIntent(pnr: string, lastName?: string) {
  return useMutation({
    mutationFn: ({ intentId, cardNumber }: { intentId: string; cardNumber: string }) =>
      api.post<PaymentIntent>(`/bookings/${pnr}/payment-intents/${intentId}/confirm`, {
        card_number: cardNumber,
        last_name: lastName,
      }),
    retry: false,
  });
}

/** Confirmation must not depend on the webhook round-trip being visible to the browser. */
export function useBookingStatus(pnr: string, lastName: string | undefined, active: boolean) {
  return useQuery({
    queryKey: keys.booking(pnr),
    queryFn: () => api.get<Booking>(`/bookings/${pnr}${guest(lastName)}`),
    enabled: active && pnr.length > 0,
    refetchInterval: (query) =>
      query.state.data?.status === 'TICKETED' || query.state.data?.status === 'CONFIRMED'
        ? false
        : 2000,
    retry: false,
  });
}

export function useTickets(pnr: string, lastName: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: keys.tickets(pnr),
    queryFn: () => api.get<Ticket[]>(`/bookings/${pnr}/tickets${guest(lastName)}`),
    enabled: enabled && pnr.length > 0,
    retry: false,
  });
}
