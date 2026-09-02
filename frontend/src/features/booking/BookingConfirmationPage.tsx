import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';

import { isApiError } from '../../api/problem';
import type { Booking } from '../../api/types';
import { Alert, Card } from '../../components/ui';
import { track } from '../../lib/analytics';
import { countdown, formatDate, formatDuration, formatLocalTime } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { useBooking } from './api';
import { useBookingWizard } from './store';

interface HandoffState {
  booking?: Booking;
  lastName?: string;
}

export default function BookingConfirmationPage() {
  const { pnr = '' } = useParams();
  const state = (useLocation().state ?? {}) as HandoffState;
  const clearWizard = useBookingWizard((wizard) => wizard.clear);
  const [now, setNow] = useState(() => Date.now());

  // Straight off the create call we already have the booking; a bookmarked link does not, and
  // falls back to guest retrieval with the surname.
  const query = useBooking(state.booking ? '' : pnr, state.lastName);
  const booking = state.booking ?? query.data;

  useEffect(() => {
    if (booking) {
      track('booking_confirmed', {
        pnr: booking.pnr,
        amount: booking.total.amount,
        currency: booking.total.currency,
      });
      clearWizard();
    }
  }, [booking, clearWizard]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);

  if (!booking) {
    if (query.isPending) {
      return <div className="h-48 animate-pulse rounded-card bg-brand-50" aria-busy="true" />;
    }
    return (
      <Alert tone="error">
        {isApiError(query.error) && query.error.status === 404
          ? 'We could not find that booking. Open it from Manage booking with the PNR and the lead passenger’s surname.'
          : 'That booking could not be loaded.'}
      </Alert>
    );
  }

  const hold = booking.hold_expires_at ? countdown(booking.hold_expires_at, now) : null;

  return (
    <div className="space-y-6">
      <Card>
        <p className="text-sm text-muted">Your booking reference</p>
        <p className="mt-1 font-mono text-4xl font-semibold tracking-[0.2em]">{booking.pnr}</p>
        <p className="mt-3 text-sm">
          Seats are held for {booking.passengers.length} passenger
          {booking.passengers.length === 1 ? '' : 's'}. Keep this reference — with the lead
          passenger’s surname it is all you need to retrieve the booking.
        </p>

        {hold && (
          <p
            aria-live="polite"
            className={`mt-3 text-sm font-medium ${hold.expired ? 'text-red-700' : 'text-amber-700'}`}
          >
            {hold.expired
              ? 'This hold has expired and the seats have been released.'
              : `Hold expires in ${hold.minutes} minute${hold.minutes === 1 ? '' : 's'}.`}
          </p>
        )}
      </Card>

      <Card>
        <h2 className="mb-3 text-sm font-medium">Itinerary</h2>
        <ol className="space-y-4">
          {booking.segments.map((segment) => (
            <li key={segment.sequence} className="text-sm">
              <div className="font-medium">
                {segment.designator} · {segment.origin} → {segment.destination}
              </div>
              <div className="text-muted tabular-nums">
                {formatDate(segment.departure_local)} ·{' '}
                {formatLocalTime(segment.departure_local)} –{' '}
                {formatLocalTime(segment.arrival_local)} ·{' '}
                {formatDuration(segment.duration_minutes)}
              </div>
              <div className="text-xs text-muted">
                {segment.cabin.replace('_', ' ').toLowerCase()} · class {segment.rbd} ·{' '}
                fare {segment.fare_basis}
              </div>
            </li>
          ))}
        </ol>
      </Card>

      <div className="grid gap-6 sm:grid-cols-2">
        <Card>
          <h2 className="mb-3 text-sm font-medium">Passengers</h2>
          <ul className="space-y-2 text-sm">
            {booking.passengers.map((passenger) => (
              <li key={passenger.id}>
                <span className="font-medium">
                  {passenger.last_name}/{passenger.first_name}
                </span>{' '}
                <span className="text-muted">
                  {passenger.type === 'ADT'
                    ? 'Adult'
                    : passenger.type === 'CHD'
                      ? 'Child'
                      : 'Infant'}
                </span>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-medium">Price</h2>
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted">Base fare</dt>
              <dd className="tabular-nums">{formatMoney(booking.base)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">Taxes</dt>
              <dd className="tabular-nums">{formatMoney(booking.taxes)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">Fees</dt>
              <dd className="tabular-nums">{formatMoney(booking.fees)}</dd>
            </div>
            <div className="flex justify-between border-t border-line pt-1 font-medium">
              <dt>Total</dt>
              <dd className="tabular-nums">{formatMoney(booking.total)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">Balance due</dt>
              <dd className="tabular-nums">{formatMoney(booking.balance_due)}</dd>
            </div>
          </dl>
        </Card>
      </div>

      <p className="text-sm text-muted">
        Confirmation sent to {booking.contact_email}.{' '}
        <Link className="underline" to="/">
          Book another flight
        </Link>
      </p>
    </div>
  );
}
