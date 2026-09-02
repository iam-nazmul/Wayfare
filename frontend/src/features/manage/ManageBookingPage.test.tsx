import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Booking } from '../../api/types';

const get = vi.fn();
const post = vi.fn();

vi.mock('../../api/client', () => ({
  api: {
    get: (path: string) => get(path),
    post: (path: string, body?: unknown, options?: unknown) => post(path, body, options),
  },
  getAccessToken: () => null,
  setAccessToken: vi.fn(),
}));

const { default: ManageBookingPage } = await import('./ManageBookingPage');
const { useManageAccess } = await import('./store');

const booking = {
  pnr: 'AB12CD',
  public_id: 'p1',
  status: 'TICKETED',
  trip_type: 'ONE_WAY',
  currency: 'USD',
  base: { amount: '210.00', currency: 'USD' },
  taxes: { amount: '41.00', currency: 'USD' },
  fees: { amount: '9.50', currency: 'USD' },
  discount: { amount: '0.00', currency: 'USD' },
  total: { amount: '260.50', currency: 'USD' },
  balance_due: { amount: '0.00', currency: 'USD' },
  contact_email: 'traveller@example.com',
  contact_phone: '',
  hold_expires_at: null,
  booked_at: '2026-09-01T10:00:00Z',
  segments: [
    {
      sequence: 0,
      flight_public_id: 'f1',
      designator: 'WF101',
      origin: 'DAC',
      destination: 'DXB',
      departure_utc: '2026-09-29T20:30:00Z',
      arrival_utc: '2026-09-30T01:45:00Z',
      departure_local: '2026-09-30T02:30:00Z',
      arrival_local: '2026-09-30T05:45:00Z',
      duration_minutes: 315,
      cabin: 'ECONOMY',
      rbd: 'L',
      fare_basis: 'LECOW',
      status: 'CONFIRMED',
      baggage_allowance: {},
    },
  ],
  passengers: [
    {
      id: 1,
      type: 'ADT',
      first_name: 'Nazmul',
      last_name: 'Islam',
      dob: '1990-05-14',
    },
  ],
} as unknown as Booking;

function route(path: string) {
  return (url: string) => url.startsWith(path);
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/manage/AB12CD']}>
        <Routes>
          <Route path="/manage/:pnr" element={<ManageBookingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ManageBookingPage', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    useManageAccess.setState({ surnames: { AB12CD: 'Islam' } });

    get.mockImplementation((url: string) => {
      if (route('/bookings/AB12CD/tickets')(url)) return Promise.resolve([]);
      if (route('/bookings/AB12CD/payments')(url)) return Promise.resolve([]);
      if (route('/bookings/AB12CD/refunds')(url)) return Promise.resolve([]);
      if (route('/bookings/AB12CD/rebook-options')(url)) return Promise.resolve([]);
      return Promise.resolve(booking);
    });
  });

  it('carries the surname on every guest call', async () => {
    renderPage();
    await screen.findByText('AB12CD');

    expect(get).toHaveBeenCalledWith('/bookings/AB12CD?last_name=Islam');
  });

  it('shows the itinerary, passengers and price', async () => {
    renderPage();

    expect(await screen.findByText(/WF101 · DAC → DXB/)).toBeInTheDocument();
    expect(screen.getByText('Islam/Nazmul')).toBeInTheDocument();
    expect(screen.getByText('$260.50')).toBeInTheDocument();
  });

  it('quotes a cancellation before cancelling anything', async () => {
    post.mockResolvedValue({
      booking,
      quote: {
        paid: { amount: '260.50', currency: 'USD' },
        penalty: { amount: '40.00', currency: 'USD' },
        non_refundable_tax: { amount: '40.00', currency: 'USD' },
        refundable: { amount: '180.50', currency: 'USD' },
        refundable_fare: true,
        reason: 'Economy Flex: 0% fare penalty plus the refund fee.',
      },
      voided: false,
      refund_id: null,
      refund_status: null,
    });

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /show me the refund/i }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /cancel and refund \$180\.50/i })).toBeInTheDocument(),
    );
    expect(post).toHaveBeenCalledWith(
      '/bookings/AB12CD/cancel',
      { last_name: 'Islam', quote_only: true },
      { idempotent: true },
    );
  });

  it('offers a rebooking when the flight is disrupted', async () => {
    get.mockImplementation((url: string) => {
      if (route('/bookings/AB12CD/rebook-options')(url)) {
        return Promise.resolve([
          {
            option_id: 'opt-1',
            rank: 0,
            status: 'OFFERED',
            designator: 'WF310',
            origin: 'DAC',
            destination: 'DXB',
            departure_local: '2026-10-01T02:30:00Z',
            arrival_local: '2026-10-01T05:45:00Z',
            duration_minutes: 315,
            cabin: 'ECONOMY',
            fare_delta: { amount: '0.00', currency: 'USD' },
            expires_at: '2026-10-05T00:00:00Z',
            disrupted_flight: 'WF101',
            disruption_type: 'CANCELLATION',
            reason: 'The airline cancelled this flight.',
          },
        ]);
      }
      if (url.includes('/tickets') || url.includes('/payments') || url.includes('/refunds')) {
        return Promise.resolve([]);
      }
      return Promise.resolve({ ...booking, status: 'DISRUPTED' });
    });

    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText(/we need to move you/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /take this flight/i }));

    expect(post).toHaveBeenCalledWith(
      '/bookings/AB12CD/rebook',
      { option_id: 'opt-1', last_name: 'Islam' },
      { idempotent: true },
    );
  });

  it('does not offer to cancel a booking that is already refunded', async () => {
    get.mockImplementation((url: string) => {
      if (url.includes('/tickets') || url.includes('/payments') || url.includes('/refunds')) {
        return Promise.resolve([]);
      }
      if (url.includes('rebook-options')) return Promise.resolve([]);
      return Promise.resolve({ ...booking, status: 'REFUNDED' });
    });

    renderPage();
    await screen.findByText('AB12CD');

    expect(screen.queryByRole('button', { name: /show me the refund/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/change your flight/i)).not.toBeInTheDocument();
  });

  it('reports a booking it cannot find', async () => {
    const { ApiError } = await import('../../api/problem');
    get.mockRejectedValue(
      new ApiError({
        type: 'about:blank',
        title: 'Not found',
        status: 404,
        detail: 'No booking matches those details.',
        code: 'not_found',
      }),
    );

    renderPage();

    expect(await screen.findByText(/could not find that booking/i)).toBeInTheDocument();
  });
});
