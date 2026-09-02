import { useState } from 'react';

import { isApiError } from '../../api/problem';
import type { Booking, RefundQuote } from '../../api/types';
import { Alert, Button, Card, Field, Input } from '../../components/ui';
import { formatMoney } from '../../lib/money';
import { useCancelBooking } from './api';

/** Cancelling is irreversible, so the penalty is shown and confirmed before anything happens. */
export function CancelPanel({
  booking,
  lastName,
}: {
  booking: Booking;
  lastName?: string;
}) {
  const cancel = useCancelBooking(booking.pnr, lastName);
  const [quote, setQuote] = useState<RefundQuote | null>(null);
  const [voided, setVoided] = useState(false);
  const [reason, setReason] = useState('');
  const [done, setDone] = useState(false);

  function preview() {
    cancel.mutate(
      { quote_only: true },
      {
        onSuccess: (response) => {
          setQuote(response.quote);
          setVoided(response.voided);
        },
      },
    );
  }

  function confirm() {
    cancel.mutate({ reason }, { onSuccess: () => setDone(true) });
  }

  if (done) {
    return (
      <Card>
        <h2 className="mb-2 text-sm font-medium">Cancelled</h2>
        <Alert>
          This booking is cancelled. Any refund due is shown under Refunds below and is paid back
          to the original card.
        </Alert>
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="mb-1 text-sm font-medium">Cancel this booking</h2>
      <p className="mb-3 text-xs text-muted">
        See what a cancellation returns before you commit to it.
      </p>

      {cancel.isError && (
        <div className="mb-3">
          <Alert tone="error">
            {isApiError(cancel.error)
              ? cancel.error.problem.detail
              : 'That could not be cancelled.'}
          </Alert>
        </div>
      )}

      {quote === null ? (
        <Button variant="ghost" onClick={preview} disabled={cancel.isPending}>
          {cancel.isPending ? 'Checking…' : 'Show me the refund'}
        </Button>
      ) : (
        <div className="space-y-4">
          <dl className="space-y-1 text-sm" aria-live="polite">
            <div className="flex justify-between">
              <dt className="text-muted">Paid</dt>
              <dd className="tabular-nums">{formatMoney(quote.paid)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">Cancellation penalty</dt>
              <dd className="tabular-nums">−{formatMoney(quote.penalty)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">Non-refundable taxes and fees</dt>
              <dd className="tabular-nums">−{formatMoney(quote.non_refundable_tax)}</dd>
            </div>
            <div className="flex justify-between border-t border-line pt-1 font-medium">
              <dt>You get back</dt>
              <dd className="tabular-nums">{formatMoney(quote.refundable)}</dd>
            </div>
          </dl>

          <p className="text-xs text-muted">{quote.reason}</p>

          {voided && (
            <Alert>
              This is still the day of issue, so the ticket is voided in full — no penalty applies.
            </Alert>
          )}

          <Field label="Reason" hint="Optional, shown to our team.">
            <Input value={reason} onChange={(event) => setReason(event.target.value)} />
          </Field>

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={confirm} disabled={cancel.isPending}>
              {cancel.isPending
                ? 'Cancelling…'
                : `Cancel and refund ${formatMoney(quote.refundable)}`}
            </Button>
            <Button variant="ghost" onClick={() => setQuote(null)}>
              Keep my booking
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
