import { useState } from 'react';

import { Button, Card } from '../../components/ui';
import type { Offer } from '../../api/types';
import { formatDuration, formatLocalTime } from '../../lib/dates';
import { formatMoney } from '../../lib/money';

function stopsLabel(stops: number): string {
  if (stops === 0) return 'Non-stop';
  return stops === 1 ? '1 stop' : `${stops} stops`;
}

export function FlightCard({
  offer,
  selected = false,
  onSelect,
}: {
  offer: Offer;
  selected?: boolean;
  onSelect: (offer: Offer) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const { itinerary, price_breakdown: price } = offer;
  const first = itinerary.segments[0];
  const last = itinerary.segments[itinerary.segments.length - 1];

  return (
    <Card className={selected ? 'border-brand-600 ring-1 ring-brand-600' : ''}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-3">
            <span className="text-xl font-semibold tabular-nums">
              {formatLocalTime(first.departure_local)}
            </span>
            <span aria-hidden className="text-muted">→</span>
            <span className="text-xl font-semibold tabular-nums">
              {formatLocalTime(last.arrival_local)}
            </span>
            <span className="text-sm text-muted">
              {itinerary.origin} – {itinerary.destination}
            </span>
          </div>

          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted">
            <span>{formatDuration(itinerary.duration_minutes)}</span>
            <span aria-hidden>·</span>
            <span>{stopsLabel(itinerary.stops)}</span>
            <span aria-hidden>·</span>
            <span>{itinerary.segments.map((s) => s.designator).join(' + ')}</span>
          </div>

          {offer.seats_remaining > 0 && offer.seats_remaining <= 4 && (
            <p className="mt-2 text-xs font-medium text-amber-700">
              Only {offer.seats_remaining} left at this price
            </p>
          )}
        </div>

        <div className="flex items-center gap-4 sm:flex-col sm:items-end">
          <div className="text-right">
            <div className="text-2xl font-semibold tabular-nums">{formatMoney(offer.total)}</div>
            <div className="text-xs text-muted">total for all passengers</div>
          </div>
          {/* Selection is not colour-only: the label changes too. */}
          <Button
            variant={selected ? 'ghost' : 'primary'}
            aria-pressed={selected}
            onClick={() => onSelect(offer)}
          >
            {selected ? 'Selected ✓' : 'Select'}
          </Button>
        </div>
      </div>

      <button
        type="button"
        onClick={() => setExpanded((open) => !open)}
        aria-expanded={expanded}
        className="mt-3 text-sm text-brand-600 underline"
      >
        {expanded ? 'Hide details' : 'Flight and price details'}
      </button>

      {expanded && (
        <div className="mt-4 grid gap-6 border-t border-line pt-4 sm:grid-cols-2">
          <div>
            <h3 className="mb-2 text-sm font-medium">Itinerary</h3>
            <ol className="space-y-3">
              {itinerary.segments.map((segment) => (
                <li key={segment.flight_public_id} className="text-sm">
                  <div className="font-medium">
                    {segment.designator} · {segment.origin} → {segment.destination}
                  </div>
                  <div className="text-muted tabular-nums">
                    {formatLocalTime(segment.departure_local)} –{' '}
                    {formatLocalTime(segment.arrival_local)} ·{' '}
                    {formatDuration(segment.duration_minutes)} · {segment.aircraft} ·{' '}
                    class {segment.rbd}
                  </div>
                </li>
              ))}
            </ol>
          </div>

          <div>
            <h3 className="mb-2 text-sm font-medium">Price</h3>
            <dl className="space-y-1 text-sm">
              <div className="flex justify-between">
                <dt className="text-muted">Base fare</dt>
                <dd className="tabular-nums">{formatMoney(price.base)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted">Taxes</dt>
                <dd className="tabular-nums">{formatMoney(price.taxes)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-muted">Fees</dt>
                <dd className="tabular-nums">{formatMoney(price.fees)}</dd>
              </div>
              {Number(price.discount.amount) > 0 && (
                <div className="flex justify-between text-green-700">
                  <dt>Discount</dt>
                  <dd className="tabular-nums">−{formatMoney(price.discount)}</dd>
                </div>
              )}
              <div className="flex justify-between border-t border-line pt-1 font-medium">
                <dt>Total</dt>
                <dd className="tabular-nums">{formatMoney(price.total)}</dd>
              </div>
            </dl>
          </div>
        </div>
      )}
    </Card>
  );
}
