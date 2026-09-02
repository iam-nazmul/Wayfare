import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Booking, Ticket } from '../../api/types';

const get = vi.fn();

vi.mock('../../api/client', () => ({
  api: { get: (path: string) => get(path), post: vi.fn() },
  getAccessToken: () => null,
  setAccessToken: vi.fn(),
}));

const { default: TicketPage } = await import('./TicketPage');
const { useManageAccess } = await import('./store');

const booking = {
  pnr: 'AB12CD',
  status: 'TICKETED',
  currency: 'USD',
  base: { amount: '210.00', currency: 'USD' },
  taxes: { amount: '41.00', currency: 'USD' },
  fees: { amount: '9.50', currency: 'USD' },
  discount: { amount: '0.00', currency: 'USD' },
  total: { amount: '260.50', currency: 'USD' },
  balance_due: { amount: '0.00', currency: 'USD' },
  contact_email: 't@example.com',
  segments: [
    {
      sequence: 0,
      designator: 'WF101',
      origin: 'DAC',
      destination: 'DXB',
      departure_local: '2026-09-30T02:30:00Z',
      arrival_local: '2026-09-30T05:45:00Z',
      duration_minutes: 315,
      cabin: 'ECONOMY',
      rbd: 'L',
      fare_basis: 'LECOW',
      status: 'CONFIRMED',
    },
  ],
  passengers: [{ id: 1, type: 'ADT', first_name: 'Nazmul', last_name: 'Islam' }],
} as unknown as Booking;

const ticket = {
  ticket_number: '1760000000124',
  status: 'ISSUED',
  passenger_name: 'Islam/Nazmul',
  issued_at: '2026-09-02T10:00:00Z',
  fare: { amount: '210.00', currency: 'USD' },
  taxes: { amount: '50.50', currency: 'USD' },
  total: { amount: '260.50', currency: 'USD' },
  fare_calculation: 'DAC WF DXB',
  coupons: [
    {
      coupon_number: 1,
      status: 'OPEN',
      designator: 'WF101',
      origin: 'DAC',
      destination: 'DXB',
      departure_local: '2026-09-30T02:30:00Z',
      arrival_local: '2026-09-30T05:45:00Z',
      duration_minutes: 315,
      cabin: 'ECONOMY',
      rbd: 'L',
      fare_basis: 'LECOW',
      flown_at: null,
    },
  ],
} as unknown as Ticket;

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/manage/AB12CD/ticket']}>
        <Routes>
          <Route path="/manage/:pnr/ticket" element={<TicketPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('TicketPage', () => {
  beforeEach(() => {
    get.mockReset();
    useManageAccess.setState({ surnames: { AB12CD: 'Islam' } });
    get.mockImplementation((url: string) =>
      url.includes('/tickets') ? Promise.resolve([ticket]) : Promise.resolve(booking),
    );
  });

  it('shows what a desk agent asks for', async () => {
    renderPage();

    expect(await screen.findByText('1760000000124')).toBeInTheDocument();
    // Departure and arrival, not just one of them.
    expect(screen.getByText('02:30')).toBeInTheDocument();
    expect(screen.getByText('05:45')).toBeInTheDocument();
    expect(screen.getByText('LECOW')).toBeInTheDocument();
    expect(screen.getByText('Islam/Nazmul')).toBeInTheDocument();
    expect(screen.getByText('AB12CD')).toBeInTheDocument();
    expect(screen.getByText('DAC')).toBeInTheDocument();
    expect(screen.getByText('DXB')).toBeInTheDocument();
    expect(screen.getByText('WF101')).toBeInTheDocument();
  });

  it('does not pass itself off as a boarding pass', async () => {
    renderPage();

    expect(
      await screen.findByText(/e-ticket receipt, not a boarding pass/i),
    ).toBeInTheDocument();
  });

  it('downloads through the browser print dialog', async () => {
    const print = vi.fn();
    vi.stubGlobal('print', print);

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /download ticket/i }));
    expect(print).toHaveBeenCalled();

    vi.unstubAllGlobals();
  });

  it('says so when no ticket has been issued yet', async () => {
    get.mockImplementation((url: string) =>
      url.includes('/tickets') ? Promise.resolve([]) : Promise.resolve(booking),
    );

    renderPage();

    expect(await screen.findByText(/no e-ticket yet/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /download/i })).not.toBeInTheDocument();
  });

  it('carries the surname so a guest can open their own ticket', async () => {
    renderPage();
    await screen.findByText('1760000000124');

    expect(get).toHaveBeenCalledWith('/bookings/AB12CD?last_name=Islam');
    expect(get).toHaveBeenCalledWith('/bookings/AB12CD/tickets?last_name=Islam');
  });
});
