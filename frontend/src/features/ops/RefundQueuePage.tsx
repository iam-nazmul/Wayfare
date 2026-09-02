import { useState } from 'react';

import { isApiError } from '../../api/problem';
import { Alert, Badge, Button, Card, DataTable, Input, Select, Spinner } from '../../components/ui';
import { formatDate } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { hasRole, useAuth } from '../auth/store';
import { useRefundDecision, useRefundQueue } from './api';

const STATUSES = ['REQUESTED', 'APPROVED', 'PROCESSED', 'REJECTED', 'FAILED'];

export default function RefundQueuePage() {
  const user = useAuth((state) => state.user);
  const [status, setStatus] = useState('');
  const [reason, setReason] = useState('');
  const [acting, setActing] = useState<string | null>(null);

  const queue = useRefundQueue(status);
  const decide = useRefundDecision(status);

  //: Only finance approves money out. The server enforces it; this keeps the buttons honest.
  const canDecide = hasRole(user, 'FINANCE', 'SUPERADMIN');

  function act(refundId: string, decision: 'approve' | 'reject') {
    setActing(refundId);
    decide.mutate(
      { refundId, decision, reason },
      { onSettled: () => setActing(null) },
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="w-56">
          <label className="mb-1 block text-xs font-medium text-muted" htmlFor="refund-status">
            Status
          </label>
          <Select
            id="refund-status"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">Awaiting a decision</option>
            {STATUSES.map((option) => (
              <option key={option} value={option}>
                {option.toLowerCase()}
              </option>
            ))}
          </Select>
        </div>

        {canDecide && (
          <div className="w-72">
            <label className="mb-1 block text-xs font-medium text-muted" htmlFor="refund-note">
              Note (recorded on the decision)
            </label>
            <Input
              id="refund-note"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </div>
        )}
      </div>

      {!canDecide && (
        <Alert>
          You can review this queue, but approving or rejecting a refund needs the finance role.
        </Alert>
      )}

      {decide.isError && (
        <Alert tone="error">
          {isApiError(decide.error)
            ? decide.error.problem.detail
            : 'That decision could not be recorded.'}
        </Alert>
      )}

      {queue.isPending ? (
        <Spinner label="Loading the refund queue" />
      ) : queue.isError ? (
        <Alert tone="error">
          {isApiError(queue.error) ? queue.error.problem.detail : 'The queue could not be loaded.'}
        </Alert>
      ) : (
        <Card>
          <DataTable
            caption="Refunds awaiting a decision"
            empty="Nothing waiting. Refunds under the auto-approval limit never reach this queue."
            columns={['pnr', 'amount', 'penalty', 'status', 'raised', 'reason', '']}
            rows={(queue.data ?? []).map((refund) => [
              <span className="font-mono">{refund.pnr}</span>,
              formatMoney(refund.amount),
              formatMoney(refund.penalty),
              <Badge
                tone={
                  refund.status === 'PROCESSED'
                    ? 'good'
                    : refund.status === 'REJECTED' || refund.status === 'FAILED'
                      ? 'bad'
                      : 'warn'
                }
              >
                {refund.status.toLowerCase()}
              </Badge>,
              formatDate(refund.created_at),
              <span className="text-muted">{refund.reason}</span>,
              canDecide && refund.status === 'REQUESTED' ? (
                <span className="flex gap-2">
                  <Button
                    className="px-3 py-1"
                    disabled={acting === refund.refund_id}
                    onClick={() => act(refund.refund_id, 'approve')}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="ghost"
                    className="px-3 py-1"
                    disabled={acting === refund.refund_id}
                    onClick={() => act(refund.refund_id, 'reject')}
                  >
                    Reject
                  </Button>
                </span>
              ) : (
                <span className="text-muted">—</span>
              ),
            ])}
          />
        </Card>
      )}
    </div>
  );
}
