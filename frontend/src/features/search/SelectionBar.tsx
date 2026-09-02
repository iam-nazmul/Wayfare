import type { Offer } from '../../api/types';
import { Button } from '../../components/ui';
import { formatDate, formatLocalTime } from '../../lib/dates';
import { type Money, formatMoney } from '../../lib/money';

interface Slice {
  index: number;
  origin: string;
  destination: string;
}

/**
 * A round trip is one journey, so it is booked as one PNR: the traveller picks a flight for
 * every leg here, and only then continues. Sticky, because the return list can be long enough
 * to push the outbound choice off screen.
 */
export function SelectionBar({
  slices,
  chosen,
  currency,
  onContinue,
}: {
  slices: Slice[];
  chosen: (Offer | null)[];
  currency: string;
  onContinue: () => void;
}) {
  if (slices.length < 2) return null;

  const complete = chosen.length === slices.length && chosen.every(Boolean);
  const total: Money = {
    amount: chosen
      .reduce((sum, offer) => sum + Number(offer?.total.amount ?? 0), 0)
      .toFixed(2),
    currency,
  };
  const remaining = slices.filter((slice) => !chosen[slice.index]);

  return (
    <section
      aria-label="Your journey"
      className="sticky bottom-0 z-10 -mx-4 border-t border-line bg-white/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-card sm:border"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <ol className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          {slices.map((slice) => {
            const offer = chosen[slice.index];
            const segment = offer?.itinerary.segments[0];

            return (
              <li key={slice.index}>
                <span className="text-xs uppercase tracking-wide text-muted">
                  {slice.index === 0 ? 'Outbound' : 'Return'}
                </span>
                <div className={offer ? 'font-medium' : 'text-muted'}>
                  {offer && segment ? (
                    <>
                      {segment.designator} · {formatDate(segment.departure_local)}{' '}
                      <span className="tabular-nums">
                        {formatLocalTime(segment.departure_local)}
                      </span>
                    </>
                  ) : (
                    `Choose a ${slice.origin} → ${slice.destination} flight`
                  )}
                </div>
              </li>
            );
          })}
        </ol>

        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-xl font-semibold tabular-nums">{formatMoney(total)}</div>
            <div className="text-xs text-muted">
              {complete ? 'total for all passengers' : 'so far'}
            </div>
          </div>

          <Button onClick={onContinue} disabled={!complete}>
            Continue
          </Button>
        </div>
      </div>

      {/* Says which leg is still missing rather than leaving a disabled button unexplained. */}
      <p aria-live="polite" className="mt-2 text-xs text-muted">
        {complete
          ? 'Both flights chosen — continue to passenger details.'
          : `Still to choose: ${remaining
              .map((slice) => `${slice.origin} → ${slice.destination}`)
              .join(', ')}.`}
      </p>
    </section>
  );
}
