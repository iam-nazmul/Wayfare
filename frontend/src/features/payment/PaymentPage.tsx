import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { isApiError } from '../../api/problem';
import type { Booking } from '../../api/types';
import { Alert, Button, Card, Field, Input } from '../../components/ui';
import { track } from '../../lib/analytics';
import { countdown } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { useBooking } from '../booking/api';
import { useBookingStatus, useConfirmIntent, useCreateIntent } from './api';

interface HandoffState {
  booking?: Booking;
  lastName?: string;
}

const TEST_CARDS = [
  { number: '4242424242424242', label: 'succeeds' },
  { number: '4000000000000002', label: 'is declined' },
  { number: '4000000000003220', label: 'needs 3-D Secure' },
];

export default function PaymentPage() {
  const { pnr = '' } = useParams();
  const navigate = useNavigate();
  const state = (useLocation().state ?? {}) as HandoffState;

  const [cardNumber, setCardNumber] = useState('');
  const [paying, setPaying] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const fetched = useBooking(state.booking ? '' : pnr, state.lastName);
  const booking = state.booking ?? fetched.data;
  const lastName = state.lastName ?? booking?.passengers[0]?.last_name;

  const createIntent = useCreateIntent(pnr, lastName);
  const confirmIntent = useConfirmIntent(pnr, lastName);
  const status = useBookingStatus(pnr, lastName, paying);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);

  // The booking is the source of truth, not the intent: the webhook decides, and it may land
  // after this page has already asked.
  useEffect(() => {
    if (status.data?.status === 'TICKETED') {
      track('booking_confirmed', {
        pnr,
        amount: status.data.total.amount,
        currency: status.data.total.currency,
      });
      navigate(`/booking/${pnr}`, { state: { booking: status.data, lastName } });
    }
  }, [status.data, pnr, lastName, navigate]);

  if (!booking) {
    if (fetched.isPending) {
      return <div className="h-48 animate-pulse rounded-card bg-brand-50" aria-busy="true" />;
    }
    return (
      <Alert tone="error">
        That booking could not be loaded.{' '}
        <Link className="underline" to="/">
          Start again
        </Link>
        .
      </Alert>
    );
  }

  const hold = booking.hold_expires_at ? countdown(booking.hold_expires_at, now) : null;
  const threeDs = confirmIntent.data?.status === 'REQUIRES_ACTION';
  const declined = status.data?.status === 'HELD' && confirmIntent.isSuccess && !threeDs;
  const error = createIntent.error ?? confirmIntent.error;

  async function pay(event: React.FormEvent) {
    event.preventDefault();
    track('payment_started', { pnr, amount: booking!.total.amount });

    const intent = await createIntent.mutateAsync().catch(() => null);
    if (!intent) return;

    setPaying(true);
    await confirmIntent
      .mutateAsync({ intentId: intent.intent_id, cardNumber })
      .catch(() => track('payment_failed', { pnr }));
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Pay for {booking.pnr}</h1>
        <p className="mt-1 text-sm text-muted">
          Your seats are held while you pay. Nothing is charged until you confirm.
        </p>
      </div>

      {hold && (
        <Alert tone={hold.expired ? 'error' : 'info'}>
          <span aria-live="polite">
            {hold.expired
              ? 'This hold has expired and the seats have been released.'
              : `Seats held for ${hold.minutes} more minute${hold.minutes === 1 ? '' : 's'}.`}
          </span>
        </Alert>
      )}

      {error && (
        <Alert tone="error">
          {isApiError(error) ? error.problem.detail : 'The payment could not be started.'}
        </Alert>
      )}

      {declined && (
        <Alert tone="error">
          That card was declined. Your seats are still held — try another card.
        </Alert>
      )}

      {threeDs && (
        <Alert>
          This card needs 3-D Secure. The provider’s authentication step is not wired up in the
          sandbox, so use a card that completes without it.
        </Alert>
      )}

      <Card>
        <div className="flex items-baseline justify-between">
          <span className="text-sm text-muted">Amount due</span>
          <span className="text-2xl font-semibold tabular-nums">
            {formatMoney(booking.balance_due)}
          </span>
        </div>
      </Card>

      <form onSubmit={pay} className="space-y-4">
        <Card>
          <fieldset disabled={paying && !declined}>
            <legend className="mb-3 text-sm font-medium">Card details</legend>

            <Field
              label="Card number"
              hint="Sandbox: card details go to the payment provider, never to Wayfare."
            >
              <Input
                required
                inputMode="numeric"
                autoComplete="cc-number"
                placeholder="4242 4242 4242 4242"
                value={cardNumber}
                onChange={(event) => setCardNumber(event.target.value.replace(/\s/g, ''))}
              />
            </Field>

            <ul className="mt-3 space-y-1 text-xs text-muted">
              {TEST_CARDS.map((card) => (
                <li key={card.number}>
                  <button
                    type="button"
                    className="font-mono underline"
                    onClick={() => setCardNumber(card.number)}
                  >
                    {card.number}
                  </button>{' '}
                  {card.label}
                </li>
              ))}
            </ul>
          </fieldset>
        </Card>

        <div className="flex items-center gap-4">
          <Button
            type="submit"
            disabled={hold?.expired || (paying && !declined && !threeDs)}
          >
            {paying && !declined && !threeDs
              ? 'Confirming payment…'
              : `Pay ${formatMoney(booking.balance_due)}`}
          </Button>
          <Link to={`/booking/${booking.pnr}`} className="text-sm text-brand-600 underline">
            Back to booking
          </Link>
        </div>

        {paying && !declined && !threeDs && (
          <p aria-live="polite" className="text-sm text-muted">
            Waiting for the provider to confirm. This page updates itself — do not refresh.
          </p>
        )}
      </form>
    </div>
  );
}
