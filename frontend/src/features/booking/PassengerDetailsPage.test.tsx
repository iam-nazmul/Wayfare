import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Offer } from '../../api/types';

const navigate = vi.fn();
const post = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigate };
});

vi.mock('../../api/client', () => ({
  api: {
    post: (...args: unknown[]) => post(...args),
    get: vi.fn(),
  },
}));

const { default: PassengerDetailsPage } = await import('./PassengerDetailsPage');
const { useBookingWizard } = await import('./store');

const offer = {
  offer_id: 'offer-1',
  expires_at: new Date(Date.now() + 15 * 60_000).toISOString(),
  total: { amount: '260.50', currency: 'USD' },
  currency: 'USD',
  seats_remaining: 9,
  itinerary: {
    origin: 'DAC',
    destination: 'DXB',
    stops: 0,
    duration_minutes: 315,
    departure_utc: '2026-09-29T20:30:00Z',
    arrival_utc: '2026-09-30T01:45:00Z',
    segments: [
      {
        designator: 'WF101',
        origin: 'DAC',
        destination: 'DXB',
        departure_local: '2026-09-30T02:30:00Z',
        arrival_local: '2026-09-30T05:45:00Z',
        duration_minutes: 315,
      },
    ],
  },
} as unknown as Offer;

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PassengerDetailsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PassengerDetailsPage', () => {
  beforeEach(() => {
    navigate.mockReset();
    post.mockReset();
    useBookingWizard.setState({ offer, party: { adults: 1, children: 0, infants: 0 } });
  });

  it('sends the traveller back to search when no flight is selected', () => {
    useBookingWizard.setState({ offer: null, party: { adults: 1, children: 0, infants: 0 } });
    renderPage();

    expect(screen.getByRole('link', { name: /start a new search/i })).toBeInTheDocument();
  });

  it('renders one form per seated passenger', () => {
    useBookingWizard.setState({ offer, party: { adults: 2, children: 1, infants: 0 } });
    renderPage();

    expect(screen.getAllByLabelText('First name')).toHaveLength(3);
    expect(screen.getByText(/Passenger 3 · Child/)).toBeInTheDocument();
  });

  it('books the offer and goes to the confirmation', async () => {
    post.mockResolvedValue({ pnr: 'AB12CD' });
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText('First name'), 'Nazmul');
    await user.type(screen.getByLabelText('Last name'), 'Islam');
    // The hint sits inside the label, so it lands in the accessible name too.
    await user.type(screen.getByLabelText(/Date of birth/), '1990-05-14');
    await user.type(screen.getByLabelText('Email'), 'traveller@example.com');
    await user.click(screen.getByRole('button', { name: /continue to payment/i }));

    expect(post).toHaveBeenCalledWith(
      '/bookings',
      {
        offer_id: 'offer-1',
        passengers: [
          {
            type: 'ADT',
            first_name: 'Nazmul',
            last_name: 'Islam',
            dob: '1990-05-14',
            gender: '',
            nationality: '',
          },
        ],
        contact: { email: 'traveller@example.com', phone: '' },
      },
      // Without this the API would let a double-submitted form hold seats twice.
      { idempotent: true },
    );

    expect(navigate).toHaveBeenCalledWith('/booking/AB12CD/pay', expect.anything());
  });

  it('will not submit against an expired price', () => {
    useBookingWizard.setState({
      offer: { ...offer, expires_at: new Date(Date.now() - 1000).toISOString() },
      party: { adults: 1, children: 0, infants: 0 },
    });
    renderPage();

    expect(screen.getByRole('button', { name: /continue to payment/i })).toBeDisabled();
    expect(screen.getByText(/price has expired/i)).toBeInTheDocument();
  });
});
