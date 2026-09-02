import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { User } from '../../api/types';

const get = vi.fn();

vi.mock('../../api/client', () => ({
  api: { get: (path: string) => get(path), post: vi.fn() },
  getAccessToken: () => 'token',
  setAccessToken: vi.fn(),
}));

const { default: MyBookingsPage } = await import('./MyBookingsPage');
const { useAuth } = await import('../auth/store');

const user: User = {
  public_id: 'u1',
  email: 'traveller@example.com',
  first_name: 'Nazmul',
  last_name: 'Islam',
  phone: '',
  roles: ['TRAVELLER'],
};

const row = {
  pnr: 'AB12CD',
  status: 'TICKETED',
  trip_type: 'ONE_WAY',
  origin: 'DAC',
  destination: 'DXB',
  departure_local: '2026-09-30T02:30:00Z',
  passenger_count: 2,
  total: { amount: '521.00', currency: 'USD' },
  booked_at: '2026-09-02T10:00:00Z',
  hold_expires_at: null,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/account/bookings']}>
        <Routes>
          <Route path="/account/bookings" element={<MyBookingsPage />} />
          <Route path="/login" element={<p>Sign in</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('MyBookingsPage', () => {
  beforeEach(() => {
    get.mockReset();
    useAuth.setState({ user });
    get.mockResolvedValue({ results: [row], next: null, previous: null });
  });

  it('lists the traveller’s own bookings', async () => {
    renderPage();

    expect(await screen.findByText('DAC → DXB')).toBeInTheDocument();
    expect(screen.getByText('$521.00')).toBeInTheDocument();
    expect(screen.getByText(/2 passengers/)).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/me/bookings');
  });

  it('offers the ticket once it is issued', async () => {
    renderPage();

    const ticket = await screen.findByRole('link', { name: 'Ticket' });
    expect(ticket).toHaveAttribute('href', '/manage/AB12CD/ticket');
  });

  it('offers no ticket while the booking is only held', async () => {
    get.mockResolvedValue({
      results: [{ ...row, status: 'HELD' }],
      next: null,
      previous: null,
    });

    renderPage();

    await screen.findByText('DAC → DXB');
    expect(screen.queryByRole('link', { name: 'Ticket' })).not.toBeInTheDocument();
  });

  it('points a traveller with nothing booked at search and guest retrieval', async () => {
    get.mockResolvedValue({ results: [], next: null, previous: null });

    renderPage();

    expect(await screen.findByText(/nothing here yet/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /find it with your reference/i })).toBeInTheDocument();
  });

  it('sends a signed-out visitor to sign in', () => {
    useAuth.setState({ user: null });
    renderPage();

    expect(screen.getByText('Sign in')).toBeInTheDocument();
    expect(get).not.toHaveBeenCalled();
  });
});
