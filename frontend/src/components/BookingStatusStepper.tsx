import type { BookingStatus } from '../api/types';
import { Badge } from './ui';

const STEPS = ['Held', 'Paid', 'Ticketed'] as const;

//: Where each status sits on the happy path. Anything off it renders as an exception instead.
const POSITION: Partial<Record<BookingStatus, number>> = {
  HELD: 0,
  PENDING_TICKETING: 1,
  TICKETED: 2,
  CONFIRMED: 2,
};

const TONE: Partial<Record<BookingStatus, 'good' | 'warn' | 'bad' | 'neutral'>> = {
  HELD: 'warn',
  PENDING_TICKETING: 'warn',
  CHANGE_PENDING: 'warn',
  REFUND_PENDING: 'warn',
  TICKETED: 'good',
  CONFIRMED: 'good',
  REBOOKED: 'good',
  DISRUPTED: 'bad',
  CANCELLED: 'bad',
  EXPIRED: 'bad',
  REFUNDED: 'neutral',
};

export function statusLabel(status: BookingStatus): string {
  return status.replace(/_/g, ' ').toLowerCase();
}

export function BookingStatusStepper({ status }: { status: BookingStatus }) {
  const current = POSITION[status];

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Badge tone={TONE[status] ?? 'neutral'}>{statusLabel(status)}</Badge>

      {current !== undefined && (
        <ol className="flex items-center gap-2 text-xs text-muted">
          {STEPS.map((step, index) => (
            <li key={step} className="flex items-center gap-2">
              {index > 0 && <span aria-hidden>→</span>}
              <span
                className={
                  index <= current ? 'font-medium text-ink' : 'text-muted'
                }
              >
                {/* The check is decorative; "done"/"to do" is carried by the text itself. */}
                {index <= current ? `${step} ✓` : step}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
