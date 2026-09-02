import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { isApiError } from '../../api/problem';
import type { Booking, ChangeQuote, Offer } from '../../api/types';
import { Alert, Button, Card, Field, Input, Spinner } from '../../components/ui';
import { formatDuration, formatLocalTime } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { useFlightSearch } from '../search/api';
import { useChangeQuote, useConfirmChange } from './api';

/**
 * Search → quote → confirm. The search reuses the storefront's own endpoint, so an exchange is
 * priced against exactly the fares a new customer would see.
 */
export function ChangePanel({ booking, lastName }: { booking: Booking; lastName?: string }) {
  const navigate = useNavigate();
  const first = booking.segments[0];

  const [date, setDate] = useState('');
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<Offer | null>(null);
  const [quote, setQuote] = useState<ChangeQuote | null>(null);

  const quoteChange = useChangeQuote(booking.pnr, lastName);
  const confirmChange = useConfirmChange(booking.pnr, lastName);

  const search = useFlightSearch(
    searching && date
      ? {
          trip_type: 'ONE_WAY',
          slices: [{ origin: first.origin, destination: first.destination, date }],
          passengers: { adults: booking.passengers.length, children: 0, infants: 0 },
          cabin: first.cabin,
          currency: booking.currency,
          max_stops: 1,
        }
      : null,
  );

  const offers = search.data?.slices[0]?.offers ?? [];

  function choose(offer: Offer) {
    setSelected(offer);
    quoteChange.mutate(offer.offer_id, { onSuccess: setQuote });
  }

  function confirm() {
    if (!selected) return;
    confirmChange.mutate(selected.offer_id, {
      onSuccess: (response) => {
        // Anything owed is collected through the ordinary payment flow, which triggers the
        // reissue; a zero-delta change is already ticketed by the time this returns.
        if (Number(response.quote.amount_due.amount) > 0) {
          navigate(`/booking/${booking.pnr}/pay`, {
            state: { booking: response.booking, lastName },
          });
        }
      },
    });
  }

  const error = quoteChange.error ?? confirmChange.error;

  return (
    <Card>
      <h2 className="mb-1 text-sm font-medium">Change your flight</h2>
      <p className="mb-3 text-xs text-muted">
        {first.origin} → {first.destination}. You pay the fare difference plus the change fee.
      </p>

      {error && (
        <div className="mb-3">
          <Alert tone="error">
            {isApiError(error) ? error.problem.detail : 'That change could not be priced.'}
          </Alert>
        </div>
      )}

      <div className="flex flex-wrap items-end gap-3">
        <div className="w-48">
          <Field label="New departure date">
            <Input
              type="date"
              min={new Date().toISOString().slice(0, 10)}
              value={date}
              onChange={(event) => {
                setDate(event.target.value);
                setSearching(false);
                setSelected(null);
                setQuote(null);
              }}
            />
          </Field>
        </div>
        <Button variant="ghost" onClick={() => setSearching(true)} disabled={!date}>
          Find flights
        </Button>
      </div>

      {searching && search.isPending && (
        <div className="mt-4">
          <Spinner label="Searching for alternatives" />
        </div>
      )}

      {searching && !search.isPending && offers.length === 0 && (
        <p className="mt-4 text-sm text-muted">No flights on that date. Try another.</p>
      )}

      {offers.length > 0 && (
        <ul className="mt-4 space-y-2">
          {offers.map((offer) => {
            const segment = offer.itinerary.segments[0];
            const last = offer.itinerary.segments[offer.itinerary.segments.length - 1];
            const chosen = selected?.offer_id === offer.offer_id;

            return (
              <li key={offer.offer_id}>
                <button
                  type="button"
                  onClick={() => choose(offer)}
                  aria-pressed={chosen}
                  className={`flex w-full items-baseline justify-between gap-4 rounded-lg border px-3 py-2 text-left text-sm ${
                    chosen ? 'border-brand-600 bg-brand-50' : 'border-line hover:bg-brand-50'
                  }`}
                >
                  <span className="tabular-nums">
                    {formatLocalTime(segment.departure_local)} –{' '}
                    {formatLocalTime(last.arrival_local)}
                  </span>
                  <span className="text-muted">
                    {offer.itinerary.segments.map((s) => s.designator).join(' + ')} ·{' '}
                    {formatDuration(offer.itinerary.duration_minutes)}
                  </span>
                  <span className="font-medium tabular-nums">{formatMoney(offer.total)}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {quote && (
        <div className="mt-4 space-y-3 border-t border-line pt-4" aria-live="polite">
          <dl className="space-y-1 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted">Fare difference</dt>
              <dd className="tabular-nums">{formatMoney(quote.fare_difference)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">Change fee</dt>
              <dd className="tabular-nums">{formatMoney(quote.change_fee)}</dd>
            </div>
            <div className="flex justify-between border-t border-line pt-1 font-medium">
              <dt>To pay now</dt>
              <dd className="tabular-nums">{formatMoney(quote.amount_due)}</dd>
            </div>
            {Number(quote.residual.amount) > 0 && (
              <div className="flex justify-between text-green-700">
                <dt>Credit left over</dt>
                <dd className="tabular-nums">{formatMoney(quote.residual)}</dd>
              </div>
            )}
          </dl>

          <p className="text-xs text-muted">{quote.reason}</p>

          {quote.changeable ? (
            <Button onClick={confirm} disabled={confirmChange.isPending}>
              {confirmChange.isPending
                ? 'Confirming…'
                : Number(quote.amount_due.amount) > 0
                  ? `Confirm and pay ${formatMoney(quote.amount_due)}`
                  : 'Confirm the change'}
            </Button>
          ) : (
            <Alert tone="error">{quote.reason}</Alert>
          )}
        </div>
      )}
    </Card>
  );
}
