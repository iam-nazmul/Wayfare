import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const navigate = vi.fn();
const post = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigate };
});

vi.mock('../../api/client', () => ({
  api: { post: (path: string, body?: unknown) => post(path, body), get: vi.fn() },
  getAccessToken: () => null,
  setAccessToken: vi.fn(),
}));

const { default: SearchResultsPage } = await import('./SearchResultsPage');
const { useBookingWizard } = await import('../booking/store');

function offer(id: string, designator: string, amount: string, origin: string, dest: string) {
  return {
    offer_id: id,
    expires_at: new Date(Date.now() + 15 * 60_000).toISOString(),
    total: { amount, currency: 'USD' },
    currency: 'USD',
    seats_remaining: 9,
    price_breakdown: {
      base: { amount, currency: 'USD' },
      taxes: { amount: '0.00', currency: 'USD' },
      fees: { amount: '0.00', currency: 'USD' },
      discount: { amount: '0.00', currency: 'USD' },
      total: { amount, currency: 'USD' },
      tax_lines: [],
      fee_lines: [],
    },
    itinerary: {
      origin,
      destination: dest,
      stops: 0,
      duration_minutes: 315,
      departure_utc: '2026-10-10T20:30:00Z',
      arrival_utc: '2026-10-11T01:45:00Z',
      segments: [
        {
          flight_public_id: `f-${id}`,
          designator,
          origin,
          destination: dest,
          departure_local: '2026-10-10T02:30:00Z',
          arrival_local: '2026-10-10T05:45:00Z',
          duration_minutes: 315,
          aircraft: '32N',
          rbd: 'Y',
        },
      ],
    },
  };
}

function response(slices: number) {
  const out = {
    index: 0,
    search_id: 's0',
    origin: 'DAC',
    destination: 'DXB',
    date: '2026-10-10',
    offers: [offer('out-1', 'WF101', '260.50', 'DAC', 'DXB')],
  };
  const back = {
    index: 1,
    search_id: 's1',
    origin: 'DXB',
    destination: 'DAC',
    date: '2026-10-17',
    offers: [offer('back-1', 'WF102', '255.25', 'DXB', 'DAC')],
  };

  return {
    trip_type: slices === 2 ? 'ROUND_TRIP' : 'ONE_WAY',
    currency: 'USD',
    partial: false,
    slices: slices === 2 ? [out, back] : [out],
  };
}

function renderResults(query: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/search?${query}`]}>
        <Routes>
          <Route path="/search" element={<SearchResultsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const ROUND_TRIP =
  'trip=ROUND_TRIP&from=DAC&to=DXB&depart=2026-10-10&return=2026-10-17&adults=1&children=0&infants=0&cabin=ECONOMY';
const ONE_WAY = 'trip=ONE_WAY&from=DAC&to=DXB&depart=2026-10-10&adults=1&cabin=ECONOMY';

describe('SearchResultsPage — round trip selection', () => {
  beforeEach(() => {
    navigate.mockReset();
    post.mockReset();
    useBookingWizard.setState({ offers: [], party: { adults: 1, children: 0, infants: 0 } });
  });

  it('will not continue until both legs are chosen', async () => {
    post.mockResolvedValue(response(2));
    const user = userEvent.setup();
    renderResults(ROUND_TRIP);

    const continueButton = await screen.findByRole('button', { name: 'Continue' });
    expect(continueButton).toBeDisabled();
    expect(screen.getByText(/still to choose: DAC → DXB, DXB → DAC/i)).toBeInTheDocument();

    await user.click(screen.getAllByRole('button', { name: 'Select' })[0]);

    // One leg down: still not bookable, and it says which is missing.
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
    expect(screen.getByText(/still to choose: DXB → DAC/i)).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
  });

  it('continues once every leg has a flight', async () => {
    post.mockResolvedValue(response(2));
    const user = userEvent.setup();
    renderResults(ROUND_TRIP);

    await user.click((await screen.findAllByRole('button', { name: 'Select' }))[0]);
    await user.click(screen.getByRole('button', { name: 'Select' }));

    expect(screen.getByText(/both flights chosen/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Continue' }));

    expect(navigate).toHaveBeenCalledWith('/book');
    expect(useBookingWizard.getState().offers.map((o) => o?.offer_id)).toEqual([
      'out-1',
      'back-1',
    ]);
  });

  it('adds up both legs as they are chosen', async () => {
    post.mockResolvedValue(response(2));
    const user = userEvent.setup();
    renderResults(ROUND_TRIP);

    // Scoped to the summary bar: the same amount also appears on the flight card.
    const bar = () => within(screen.getByRole('region', { name: 'Your journey' }));

    await user.click((await screen.findAllByRole('button', { name: 'Select' }))[0]);
    expect(bar().getByText('$260.50')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Select' }));
    // 260.50 + 255.25
    expect(bar().getByText('$515.75')).toBeInTheDocument();
  });

  it('replaces a leg when a different flight is picked for it', async () => {
    const two = response(2);
    two.slices[0].offers.push(offer('out-2', 'WF103', '300.00', 'DAC', 'DXB'));
    post.mockResolvedValue(two);

    const user = userEvent.setup();
    renderResults(ROUND_TRIP);

    await user.click((await screen.findAllByRole('button', { name: 'Select' }))[0]);
    await user.click(screen.getAllByRole('button', { name: 'Select' })[0]);

    const chosen = useBookingWizard.getState().offers;
    expect(chosen).toHaveLength(2);
    expect(chosen[0]?.offer_id).toBe('out-2');
    expect(chosen[1]).toBeNull();
  });

  it('marks the chosen flight without relying on colour alone', async () => {
    post.mockResolvedValue(response(2));
    const user = userEvent.setup();
    renderResults(ROUND_TRIP);

    await user.click((await screen.findAllByRole('button', { name: 'Select' }))[0]);

    const selected = screen.getByRole('button', { name: /selected/i });
    expect(selected).toHaveAttribute('aria-pressed', 'true');
  });

  it('sends a one-way straight on without a summary bar', async () => {
    post.mockResolvedValue(response(1));
    const user = userEvent.setup();
    renderResults(ONE_WAY);

    await user.click(await screen.findByRole('button', { name: 'Select' }));

    expect(navigate).toHaveBeenCalledWith('/book');
    expect(screen.queryByRole('button', { name: 'Continue' })).not.toBeInTheDocument();
  });
});
