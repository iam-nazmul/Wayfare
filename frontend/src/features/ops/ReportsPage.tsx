import { useState } from 'react';

import { getAccessToken } from '../../api/client';
import { isApiError } from '../../api/problem';
import { Alert, Button, Card, DataTable, Field, Input, Select, Spinner } from '../../components/ui';
import { type ReportParams, reportPath, useReport } from './api';

const REPORTS = [
  { slug: 'funnel', label: 'Funnel', blurb: 'Step-by-step conversion, by device.' },
  { slug: 'revenue', label: 'Revenue', blurb: 'By day, route, cabin and channel, in USD.' },
  { slug: 'load-factor', label: 'Load factor', blurb: 'Seats sold ÷ capacity, from live inventory.' },
  { slug: 'api-health', label: 'API health', blurb: 'Latency percentiles and error rate by route.' },
  { slug: 'search-conversion', label: 'Search conversion', blurb: 'Look-to-book by route.' },
  { slug: 'top-routes', label: 'Top routes', blurb: 'Demand against sales.' },
  { slug: 'abandonment', label: 'Abandonment', blurb: 'Reached payment, never confirmed.' },
  { slug: 'fare-trend', label: 'Fare trend', blurb: 'Price movement for a route and date.' },
];

function daysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return date.toISOString().slice(0, 10);
}

export default function ReportsPage() {
  const [slug, setSlug] = useState('funnel');
  const [params, setParams] = useState<ReportParams>({
    date_from: daysAgo(30),
    date_to: new Date().toISOString().slice(0, 10),
  });
  const [downloading, setDownloading] = useState(false);

  const report = useReport(slug, params);
  const current = REPORTS.find((entry) => entry.slug === slug);

  /**
   * The endpoint needs a bearer token, so a plain link cannot fetch it — pull the CSV with the
   * token attached and hand the browser a blob.
   */
  async function downloadCsv() {
    setDownloading(true);
    try {
      const base = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';
      const response = await fetch(`${base}${reportPath(slug, params)}`, {
        headers: { Accept: 'text/csv', Authorization: `Bearer ${getAccessToken() ?? ''}` },
        credentials: 'include',
      });
      if (!response.ok) return;

      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = `${slug}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Report">
          <Select value={slug} onChange={(event) => setSlug(event.target.value)}>
            {REPORTS.map((entry) => (
              <option key={entry.slug} value={entry.slug}>
                {entry.label}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="From">
          <Input
            type="date"
            value={params.date_from ?? ''}
            onChange={(event) => setParams({ ...params, date_from: event.target.value })}
          />
        </Field>

        <Field label="To">
          <Input
            type="date"
            value={params.date_to ?? ''}
            onChange={(event) => setParams({ ...params, date_to: event.target.value })}
          />
        </Field>

        {slug === 'fare-trend' ? (
          <div className="grid grid-cols-2 gap-2">
            <Field label="Origin">
              <Input
                maxLength={3}
                className="uppercase"
                value={params.origin ?? ''}
                onChange={(event) =>
                  setParams({ ...params, origin: event.target.value.toUpperCase() })
                }
              />
            </Field>
            <Field label="Destination">
              <Input
                maxLength={3}
                className="uppercase"
                value={params.destination ?? ''}
                onChange={(event) =>
                  setParams({ ...params, destination: event.target.value.toUpperCase() })
                }
              />
            </Field>
          </div>
        ) : (
          <div className="flex items-end">
            <Button variant="ghost" onClick={downloadCsv} disabled={downloading}>
              {downloading ? 'Preparing…' : 'Download CSV'}
            </Button>
          </div>
        )}
      </div>

      <p className="text-sm text-muted">{current?.blurb}</p>

      {report.isError && (
        <Alert tone="error">
          {isApiError(report.error)
            ? report.error.problem.detail
            : 'That report could not be loaded.'}
        </Alert>
      )}

      {report.isPending ? (
        <Spinner label={`Loading the ${current?.label ?? slug} report`} />
      ) : report.data ? (
        <Card>
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-medium">{current?.label}</h2>
            <p className="text-xs text-muted" aria-live="polite">
              {report.data.row_count} row{report.data.row_count === 1 ? '' : 's'} ·{' '}
              {report.data.date_from} to {report.data.date_to}
            </p>
          </div>

          <DataTable
            caption={`${current?.label} report`}
            columns={report.data.columns}
            rows={report.data.rows.map((row) => row.map((cell) => String(cell ?? '—')))}
            empty="No data in this window."
          />
        </Card>
      ) : null}
    </div>
  );
}
