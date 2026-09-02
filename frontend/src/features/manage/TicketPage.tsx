import { Link, useParams } from 'react-router-dom';

import { isApiError } from '../../api/problem';
import type { Booking, Ticket, TicketCoupon } from '../../api/types';
import { Alert, Button, Spinner } from '../../components/ui';
import { formatDate, formatDuration, formatLocalTime } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { useManagedBooking, useTickets } from './api';
import { useManageAccess } from './store';

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-widest text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium">{value || '—'}</dd>
    </div>
  );
}

function Coupon({
  coupon,
  index,
  total,
}: {
  coupon: TicketCoupon;
  index: number;
  total: number;
}) {
  return (
    <div className="border-t border-dashed border-line pt-4 first:border-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-[10px] uppercase tracking-widest text-muted">
          Coupon {coupon.coupon_number}
        </span>
        <span className="text-[10px] uppercase tracking-widest text-muted">
          {coupon.status.replace(/_/g, ' ').toLowerCase()}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-start gap-x-6 gap-y-3">
        <div>
          <div className="text-3xl font-semibold leading-none tracking-tight">
            {coupon.origin}
          </div>
          <div className="mt-1 text-lg font-medium tabular-nums">
            {formatLocalTime(coupon.departure_local)}
          </div>
          <div className="text-xs text-muted">{formatDate(coupon.departure_local)}</div>
        </div>

        <div className="flex-1 pt-3" aria-hidden>
          <div className="relative h-px bg-line">
            <span className="absolute -top-2 left-1/2 -translate-x-1/2 bg-white px-2 text-xs text-muted">
              ✈
            </span>
          </div>
          <div className="mt-2 text-center text-xs text-muted">
            {formatDuration(coupon.duration_minutes)}
          </div>
        </div>

        <div className="text-right">
          <div className="text-3xl font-semibold leading-none tracking-tight">
            {coupon.destination}
          </div>
          <div className="mt-1 text-lg font-medium tabular-nums">
            {formatLocalTime(coupon.arrival_local)}
          </div>
          <div className="text-xs text-muted">{formatDate(coupon.arrival_local)}</div>
        </div>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Detail label="Flight" value={coupon.designator} />
        <Detail label="Class" value={`${coupon.cabin.replace('_', ' ').toLowerCase()} · ${coupon.rbd}`} />
        <Detail label="Fare basis" value={coupon.fare_basis} />
        <Detail label="Coupon" value={`${index + 1} of ${total}`} />
      </dl>
    </div>
  );
}

function TicketCard({ ticket, booking }: { ticket: Ticket; booking: Booking }) {
  return (
    <article className="ticket break-inside-avoid overflow-hidden rounded-card border border-line bg-white shadow-sm">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-brand-50 px-6 py-4">
        <div>
          <div className="text-lg font-semibold tracking-tight text-brand-700">Wayfare</div>
          <div className="text-[10px] uppercase tracking-widest text-muted">
            Electronic ticket
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-widest text-muted">Booking</div>
          <div className="font-mono text-xl font-semibold tracking-[0.2em]">{booking.pnr}</div>
        </div>
      </header>

      <div className="grid gap-6 px-6 py-5 sm:grid-cols-[2fr_1fr]">
        <div className="space-y-4">
          {ticket.coupons.map((coupon, index) => (
            <Coupon
              key={coupon.coupon_number}
              coupon={coupon}
              index={index}
              total={ticket.coupons.length}
            />
          ))}
        </div>

        {/* The stub: everything a desk agent asks for, kept together. */}
        <aside className="space-y-4 border-t border-dashed border-line pt-5 sm:border-l sm:border-t-0 sm:pl-6 sm:pt-0">
          <dl className="space-y-3">
            <Detail label="Passenger" value={ticket.passenger_name} />
            <Detail label="Ticket number" value={ticket.ticket_number} />
            <Detail label="Fare calculation" value={ticket.fare_calculation} />
            <Detail label="Issued" value={formatDate(ticket.issued_at)} />
            <Detail label="Status" value={ticket.status.toLowerCase()} />
          </dl>

          <div className="border-t border-line pt-3">
            <dl className="space-y-1 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted">Fare</dt>
                <dd className="tabular-nums">{formatMoney(ticket.fare)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted">Taxes and fees</dt>
                <dd className="tabular-nums">{formatMoney(ticket.taxes)}</dd>
              </div>
              <div className="flex justify-between font-medium">
                <dt>Total</dt>
                <dd className="tabular-nums">{formatMoney(ticket.total)}</dd>
              </div>
            </dl>
          </div>
        </aside>
      </div>

      <footer className="border-t border-line px-6 py-3 text-[11px] text-muted">
        {/* Times are each airport's own wall clock — what a traveller reads at the gate. */}
        All times are local to each airport. This is an e-ticket receipt, not a boarding pass —
        check in to get your boarding pass. Carry photo ID matching the passenger name.
      </footer>
    </article>
  );
}

export default function TicketPage() {
  const { pnr = '' } = useParams();
  const lastName = useManageAccess((state) => state.surnames[pnr.toUpperCase()]);

  const booking = useManagedBooking(pnr, lastName);
  const tickets = useTickets(pnr, lastName, booking.isSuccess);

  if (booking.isPending || tickets.isPending) return <Spinner label="Loading your ticket" />;

  if (booking.isError || !booking.data) {
    return (
      <Alert tone="error">
        {isApiError(booking.error) && booking.error.status === 404
          ? 'We could not find that booking. '
          : 'That booking could not be loaded. '}
        <Link className="underline" to="/manage">
          Try again
        </Link>
        .
      </Alert>
    );
  }

  const issued = tickets.data ?? [];

  if (issued.length === 0) {
    return (
      <Alert>
        No e-ticket yet — tickets are issued once payment clears.{' '}
        <Link className="underline" to={`/manage/${pnr}`}>
          Back to your booking
        </Link>
        .
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* The controls are the only thing the print stylesheet drops. */}
      <div className="no-print flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {issued.length === 1 ? 'Your e-ticket' : 'Your e-tickets'}
          </h1>
          <p className="mt-1 text-sm text-muted">
            One per passenger, with a coupon for every flight.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link to={`/manage/${pnr}`} className="text-sm text-brand-600 underline">
            Back to booking
          </Link>
          <Button onClick={() => window.print()}>Download ticket</Button>
        </div>
      </div>

      <div className="space-y-6">
        {issued.map((ticket) => (
          <TicketCard key={ticket.ticket_number} ticket={ticket} booking={booking.data} />
        ))}
      </div>

      <p className="no-print text-xs text-muted">
        Download opens your browser’s print dialog — choose “Save as PDF” to keep a copy.
      </p>
    </div>
  );
}
