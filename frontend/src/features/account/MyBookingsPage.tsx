import { Link, Navigate } from 'react-router-dom';

import { isApiError } from '../../api/problem';
import { Alert, Badge, Card, Spinner } from '../../components/ui';
import { formatDate, formatLocalTime } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { useAuth } from '../auth/store';
import { useManageAccess } from '../manage/store';
import { useMyBookings } from './api';

const TONE: Record<string, 'good' | 'warn' | 'bad' | 'neutral'> = {
  TICKETED: 'good',
  CONFIRMED: 'good',
  REBOOKED: 'good',
  HELD: 'warn',
  PENDING_TICKETING: 'warn',
  CHANGE_PENDING: 'warn',
  REFUND_PENDING: 'warn',
  DISRUPTED: 'bad',
  CANCELLED: 'bad',
  EXPIRED: 'bad',
};

export default function MyBookingsPage() {
  const user = useAuth((state) => state.user);
  const remember = useManageAccess((state) => state.remember);
  const bookings = useMyBookings(Boolean(user));

  if (!user) return <Navigate to="/login" replace state={{ from: '/account/bookings' }} />;

  if (bookings.isPending) return <Spinner label="Loading your bookings" />;

  if (bookings.isError) {
    return (
      <Alert tone="error">
        {isApiError(bookings.error)
          ? bookings.error.problem.detail
          : 'Your bookings could not be loaded.'}
      </Alert>
    );
  }

  const rows = bookings.data?.results ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Your bookings</h1>
        <p className="mt-1 text-sm text-muted">
          Everything booked while signed in as {user.email}.
        </p>
      </div>

      {rows.length === 0 ? (
        <Card>
          <p className="text-sm text-muted">
            Nothing here yet.{' '}
            <Link className="underline" to="/">
              Search for a flight
            </Link>{' '}
            — or if you booked as a guest,{' '}
            <Link className="underline" to="/manage">
              find it with your reference
            </Link>
            .
          </p>
        </Card>
      ) : (
        <ul className="space-y-3">
          {rows.map((booking) => (
            <li key={booking.pnr}>
              <Card>
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-baseline gap-3">
                      <span className="text-lg font-semibold">
                        {booking.origin} → {booking.destination}
                      </span>
                      <Badge tone={TONE[booking.status] ?? 'neutral'}>
                        {booking.status.replace(/_/g, ' ').toLowerCase()}
                      </Badge>
                    </div>
                    <div className="mt-1 text-sm text-muted tabular-nums">
                      {booking.departure_local
                        ? `${formatDate(booking.departure_local)} · ${formatLocalTime(
                            booking.departure_local,
                          )}`
                        : 'Dates to be confirmed'}{' '}
                      · {booking.passenger_count} passenger
                      {booking.passenger_count === 1 ? '' : 's'} ·{' '}
                      <span className="font-mono">{booking.pnr}</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    <span className="text-lg font-semibold tabular-nums">
                      {formatMoney(booking.total)}
                    </span>

                    {/* Manage and ticket pages call the guest endpoints, which want a surname;
                        the account's own is the right one for a booking they made. */}
                    <Link
                      to={`/manage/${booking.pnr}`}
                      onClick={() => remember(booking.pnr, user.last_name)}
                      className="text-sm text-brand-600 underline"
                    >
                      Manage
                    </Link>

                    {(booking.status === 'TICKETED' || booking.status === 'CONFIRMED') && (
                      <Link
                        to={`/manage/${booking.pnr}/ticket`}
                        onClick={() => remember(booking.pnr, user.last_name)}
                        className="inline-flex items-center justify-center rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white hover:bg-brand-700"
                      >
                        Ticket
                      </Link>
                    )}
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
