import { isApiError } from '../../api/problem';
import { Alert, Badge, Card, DataTable, Spinner } from '../../components/ui';
import { formatDate, formatLocalTime } from '../../lib/dates';
import { useDisruptions } from './api';

export default function DisruptionsPage() {
  const disruptions = useDisruptions();

  if (disruptions.isPending) return <Spinner label="Loading open disruptions" />;

  if (disruptions.isError) {
    return (
      <Alert tone="error">
        {isApiError(disruptions.error)
          ? disruptions.error.problem.detail
          : 'Disruptions could not be loaded.'}
      </Alert>
    );
  }

  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-medium">Open disruptions</h2>
        <p className="text-xs text-muted">
          Detected every 5 minutes. Affected passengers are offered alternatives automatically.
        </p>
      </div>

      <DataTable
        caption="Open flight disruptions"
        empty="Nothing disrupted. Cancellations and delays over two hours appear here."
        columns={['flight', 'type', 'delay', 'detected', 'reason']}
        rows={(disruptions.data ?? []).map((disruption) => [
          <span className="font-mono">{disruption.flight}</span>,
          <Badge tone={disruption.type === 'CANCELLATION' ? 'bad' : 'warn'}>
            {disruption.type.replace('_', ' ').toLowerCase()}
          </Badge>,
          disruption.delay_minutes ? `${disruption.delay_minutes} min` : '—',
          `${formatDate(disruption.detected_at)} ${formatLocalTime(disruption.detected_at)}`,
          <span className="text-muted">{disruption.reason}</span>,
        ])}
      />
    </Card>
  );
}
