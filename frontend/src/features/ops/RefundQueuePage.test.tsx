import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { User } from '../../api/types';

const get = vi.fn();
const post = vi.fn();

vi.mock('../../api/client', () => ({
  api: {
    get: (path: string) => get(path),
    post: (path: string, body?: unknown) => post(path, body),
  },
  getAccessToken: () => 'token',
  setAccessToken: vi.fn(),
}));

const { default: RefundQueuePage } = await import('./RefundQueuePage');
const { default: OpsLayout } = await import('./OpsLayout');
const { useAuth } = await import('../auth/store');

const refund = {
  refund_id: 'r-1',
  pnr: 'AB12CD',
  amount: { amount: '544.00', currency: 'USD' },
  penalty: { amount: '40.00', currency: 'USD' },
  status: 'REQUESTED',
  reason: 'customer changed plans',
  provider_refund_id: '',
  processed_at: null,
  created_at: '2026-09-01T10:00:00Z',
};

function staff(roles: string[]): User {
  return {
    public_id: 'u1',
    email: 'finance@wayfare.local',
    first_name: 'Fin',
    last_name: 'Ance',
    phone: '',
    roles,
  };
}

function renderQueue() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RefundQueuePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('RefundQueuePage', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    get.mockResolvedValue([refund]);
    useAuth.setState({ user: staff(['FINANCE']) });
  });

  it('lists refunds awaiting a decision', async () => {
    renderQueue();

    expect(await screen.findByText('AB12CD')).toBeInTheDocument();
    expect(screen.getByText('$544.00')).toBeInTheDocument();
    expect(get).toHaveBeenCalledWith('/ops/refunds');
  });

  it('approves a refund with the note attached', async () => {
    post.mockResolvedValue({ ...refund, status: 'APPROVED' });
    const user = userEvent.setup();
    renderQueue();

    await user.type(
      await screen.findByLabelText(/note/i),
      'fare rule satisfied',
    );
    await user.click(screen.getByRole('button', { name: /approve/i }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/ops/refunds/r-1/approve', {
        reason: 'fare rule satisfied',
      }),
    );
  });

  it('rejects a refund', async () => {
    post.mockResolvedValue({ ...refund, status: 'REJECTED' });
    const user = userEvent.setup();
    renderQueue();

    await user.click(await screen.findByRole('button', { name: /reject/i }));

    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/ops/refunds/r-1/reject', { reason: '' }),
    );
  });

  it('hides the decision buttons from ops agents who are not finance', async () => {
    useAuth.setState({ user: staff(['OPS_AGENT']) });
    renderQueue();

    await screen.findByText('AB12CD');
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
    expect(screen.getByText(/needs the finance role/i)).toBeInTheDocument();
  });
});

function renderOps() {
  const client = new QueryClient();

  // Rendered through real routes: OpsLayout redirects, and a redirect only unmounts it if the
  // router has somewhere else to go.
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/ops/refunds']}>
        <Routes>
          <Route path="/ops/*" element={<OpsLayout />} />
          <Route path="/login" element={<p>Sign in</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('OpsLayout', () => {
  it('sends a traveller to sign in rather than rendering the console', () => {
    useAuth.setState({ user: null });
    renderOps();

    expect(screen.queryByText(/ops console/i)).not.toBeInTheDocument();
    expect(screen.getByText('Sign in')).toBeInTheDocument();
  });

  it('renders the console for staff', () => {
    useAuth.setState({ user: staff(['FINANCE']) });
    renderOps();

    expect(screen.getByText(/ops console/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Reports' })).toBeInTheDocument();
  });
});
