import { isApiError } from '../../api/problem';
import type { Booking } from '../../api/types';
import { Alert, Button, Card } from '../../components/ui';
import { formatDate, formatDuration, formatLocalTime } from '../../lib/dates';
import { useRebook, useRebookOptions } from './api';

/** Shown only when the airline has disrupted the flight. The alternatives cost nothing. */
export function RebookPanel({ booking, lastName }: { booking: Booking; lastName?: string }) {
  const options = useRebookOptions(booking.pnr, lastName);
  const rebook = useRebook(booking.pnr, lastName);

  const offered = options.data ?? [];
  if (offered.length === 0) return null;

  const first = offered[0];

  return (
    <Card>
      <h2 className="mb-1 text-sm font-medium">We need to move you</h2>
      <p className="mb-3 text-sm text-muted" aria-live="polite">
        {first.reason} Choose a replacement below — there is nothing more to pay.
      </p>

      {rebook.isError && (
        <div className="mb-3">
          <Alert tone="error">
            {isApiError(rebook.error)
              ? rebook.error.problem.detail
              : 'That flight could not be confirmed.'}
          </Alert>
        </div>
      )}

      <ul className="space-y-2">
        {offered.map((option) => (
          <li
            key={option.option_id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line px-3 py-2"
          >
            <div className="text-sm">
              <div className="font-medium">
                {option.designator} · {option.origin} → {option.destination}
              </div>
              <div className="text-muted tabular-nums">
                {formatDate(option.departure_local)} ·{' '}
                {formatLocalTime(option.departure_local)} –{' '}
                {formatLocalTime(option.arrival_local)} ·{' '}
                {formatDuration(option.duration_minutes)}
              </div>
            </div>

            <Button
              onClick={() => rebook.mutate(option.option_id)}
              disabled={rebook.isPending}
            >
              {rebook.isPending ? 'Confirming…' : 'Take this flight'}
            </Button>
          </li>
        ))}
      </ul>

      <p className="mt-3 text-xs text-muted">
        These alternatives hold no seats — they are re-checked when you choose one, so pick soon.
      </p>
    </Card>
  );
}
