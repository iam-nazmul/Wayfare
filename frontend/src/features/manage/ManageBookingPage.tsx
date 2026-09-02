import { Link, useParams } from 'react-router-dom';

import { isApiError } from '../../api/problem';
import { BookingStatusStepper } from '../../components/BookingStatusStepper';
import { Alert, Badge, Card, DataTable, Spinner } from '../../components/ui';
import { formatDate, formatDuration, formatLocalTime } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { CancelPanel } from './CancelPanel';
import { ChangePanel } from './ChangePanel';
import { RebookPanel } from './RebookPanel';
import { useManagedBooking, usePayments, useRefunds, useTickets } from './api';
import { useManageAccess } from './store';

//: What a traveller may still act on. Everything else is read-only history.
const CANCELLABLE = new Set(['HELD', 'PENDING_TICKETING', 'TICKETED', 'CONFIRMED']);
const CHANGEABLE = new Set(['TICKETED', 'CONFIRMED']);

export default function ManageBookingPage() {
  const { pnr = '' } = useParams();
  const lastName = useManageAccess((state) => state.surnames[pnr.toUpperCase()]);

  const booking = useManagedBooking(pnr, lastName);
  const tickets = useTickets(pnr, lastName, booking.isSuccess);
  const payments = usePayments(pnr, lastName, booking.isSuccess);
  const refunds = useRefunds(pnr, lastName, booking.isSuccess);

  if (booking.isPending) return <Spinner label="Loading your booking" />;

  if (booking.isError || !booking.data) {
    return (
      <Alert tone="error">
        {isApiError(booking.error) && booking.error.status === 404
          ? 'We could not find that booking. Check the reference and surname and '
          : 'That booking could not be loaded. '}
        <Link className="underline" to="/manage">
          try again
        </Link>
        .
      </Alert>
    );
  }

  const data = booking.data;
  const balance = Number(data.balance_due.amount);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm text-muted">Booking reference</p>
          <p className="font-mono text-3xl font-semibold tracking-[0.2em]">{data.pnr}</p>
        </div>
        <BookingStatusStepper status={data.status} />
      </div>

      {data.status === 'PENDING_TICKETING' && (
        <Alert>
          <span aria-live="polite">
            Payment received — we are issuing your tickets now. This page updates itself.
          </span>
        </Alert>
      )}

      {balance > 0 && data.status === 'HELD' && (
        <Alert>
          {formatMoney(data.balance_due)} is still to pay.{' '}
          <Link className="underline" to={`/booking/${data.pnr}/pay`} state={{ booking: data, lastName }}>
            Pay now
          </Link>{' '}
          to secure these seats.
        </Alert>
      )}

      {data.status === 'DISRUPTED' && <RebookPanel booking={data} lastName={lastName} />}

      <Card>
        <h2 className="mb-3 text-sm font-medium">Itinerary</h2>
        <ol className="space-y-4">
          {data.segments.map((segment) => (
            <li key={segment.sequence} className="text-sm">
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="font-medium">
                  {segment.designator} · {segment.origin} → {segment.destination}
                </span>
                {segment.status === 'CANCELLED' && <Badge tone="bad">cancelled</Badge>}
              </div>
              <div className="text-muted tabular-nums">
                {formatDate(segment.departure_local)} ·{' '}
                {formatLocalTime(segment.departure_local)} –{' '}
                {formatLocalTime(segment.arrival_local)} ·{' '}
                {formatDuration(segment.duration_minutes)}
              </div>
              <div className="text-xs text-muted">
                {segment.cabin.replace('_', ' ').toLowerCase()} · class {segment.rbd}
                {segment.fare_basis ? ` · fare ${segment.fare_basis}` : ''}
              </div>
            </li>
          ))}
        </ol>
      </Card>

      <div className="grid gap-6 sm:grid-cols-2">
        <Card>
          <h2 className="mb-3 text-sm font-medium">Passengers</h2>
          <ul className="space-y-2 text-sm">
            {data.passengers.map((passenger) => (
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
              <dd className="tabular-nums">{formatMoney(data.base)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">Taxes</dt>
              <dd className="tabular-nums">{formatMoney(data.taxes)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">Fees</dt>
              <dd className="tabular-nums">{formatMoney(data.fees)}</dd>
            </div>
            <div className="flex justify-between border-t border-line pt-1 font-medium">
              <dt>Total</dt>
              <dd className="tabular-nums">{formatMoney(data.total)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">Balance due</dt>
              <dd className="tabular-nums">{formatMoney(data.balance_due)}</dd>
            </div>
          </dl>
        </Card>
      </div>

      {(tickets.data?.length ?? 0) > 0 && (
        <Card>
          <h2 className="mb-3 text-sm font-medium">E-tickets</h2>
          <DataTable
            caption="E-tickets and coupon status"
            columns={['ticket', 'passenger', 'status', 'total', 'coupons']}
            rows={(tickets.data ?? []).map((ticket) => [
              <span className="font-mono">{ticket.ticket_number}</span>,
              ticket.passenger_name,
              <Badge tone={ticket.status === 'ISSUED' ? 'good' : 'neutral'}>
                {ticket.status.toLowerCase()}
              </Badge>,
              formatMoney(ticket.total),
              ticket.coupons
                .map((coupon) => `${coupon.designator} ${coupon.status.toLowerCase()}`)
                .join(' · '),
            ])}
          />
        </Card>
      )}

      {(payments.data?.length ?? 0) > 0 && (
        <Card>
          <h2 className="mb-3 text-sm font-medium">Payments</h2>
          <DataTable
            caption="Payment history"
            columns={['status', 'card', 'amount', 'taken']}
            rows={(payments.data ?? []).map((payment) => [
              <Badge tone={payment.status === 'CAPTURED' ? 'good' : 'bad'}>
                {payment.status.toLowerCase()}
              </Badge>,
              payment.card_last4 ? `${payment.card_brand} ····${payment.card_last4}` : payment.method,
              formatMoney(payment.amount),
              payment.captured_at ? formatDate(payment.captured_at) : '—',
            ])}
          />
        </Card>
      )}

      {(refunds.data?.length ?? 0) > 0 && (
        <Card>
          <h2 className="mb-3 text-sm font-medium">Refunds</h2>
          <DataTable
            caption="Refund history"
            columns={['status', 'amount', 'penalty', 'reason']}
            rows={(refunds.data ?? []).map((refund) => [
              <Badge
                tone={
                  refund.status === 'PROCESSED'
                    ? 'good'
                    : refund.status === 'REJECTED'
                      ? 'bad'
                      : 'warn'
                }
              >
                {refund.status.toLowerCase()}
              </Badge>,
              formatMoney(refund.amount),
              formatMoney(refund.penalty),
              refund.reason,
            ])}
          />
          <p className="mt-3 text-xs text-muted">
            Refunds above our approval limit are reviewed by our team before the money moves.
          </p>
        </Card>
      )}

      {CHANGEABLE.has(data.status) && <ChangePanel booking={data} lastName={lastName} />}
      {CANCELLABLE.has(data.status) && <CancelPanel booking={data} lastName={lastName} />}
    </div>
  );
}
