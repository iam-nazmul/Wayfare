import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { isApiError } from '../../api/problem';
import type { Cabin, SearchRequest, TripType } from '../../api/types';
import { Alert, Card, Select } from '../../components/ui';
import { track } from '../../lib/analytics';
import { FlightCard } from './FlightCard';
import { useFlightSearch } from './api';

type Sort = 'price' | 'duration' | 'departure';

function buildRequest(params: URLSearchParams): SearchRequest | null {
  const from = params.get('from');
  const to = params.get('to');
  const depart = params.get('depart');
  if (!from || !to || !depart) return null;

  const tripType = (params.get('trip') as TripType) ?? 'ONE_WAY';
  const returnDate = params.get('return');

  const slices = [{ origin: from, destination: to, date: depart }];
  if (tripType === 'ROUND_TRIP' && returnDate) {
    slices.push({ origin: to, destination: from, date: returnDate });
  }

  return {
    trip_type: tripType,
    slices,
    passengers: {
      adults: Number(params.get('adults') ?? 1),
      children: Number(params.get('children') ?? 0),
      infants: Number(params.get('infants') ?? 0),
    },
    cabin: (params.get('cabin') as Cabin) ?? 'ECONOMY',
    currency: 'USD',
    max_stops: 1,
  };
}

export default function SearchResultsPage() {
  const [params] = useSearchParams();
  const request = useMemo(() => buildRequest(params), [params]);
  const [sort, setSort] = useState<Sort>('price');

  const { data, isPending, isError, error } = useFlightSearch(request);

  useEffect(() => {
    if (data) {
      track('search_results_rendered', {
        origin: request?.slices[0]?.origin,
        destination: request?.slices[0]?.destination,
        pax_count: data.slices[0]?.offers.length ?? 0,
      });
    }
  }, [data, request]);

  if (!request) {
    return (
      <Alert tone="error">
        That search link is incomplete. <Link className="underline" to="/">Start a new search</Link>.
      </Alert>
    );
  }

  if (isPending) {
    return (
      <div className="space-y-3" aria-busy="true" aria-label="Searching for flights">
        {[0, 1, 2, 3].map((n) => (
          <div key={n} className="h-32 animate-pulse rounded-card bg-brand-50" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <Alert tone="error">
        {isApiError(error) ? error.problem.detail : 'Search failed. Please try again.'}
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {data.partial && (
        <Alert>
          Showing partial results — the search took longer than expected. Refresh for the full list.
        </Alert>
      )}

      <div className="flex items-center justify-between gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">
          {request.slices[0].origin} → {request.slices[0].destination}
        </h1>
        <div className="w-44">
          <Select
            aria-label="Sort results"
            value={sort}
            onChange={(event) => {
              setSort(event.target.value as Sort);
              track('sort_changed', { sort: event.target.value });
            }}
          >
            <option value="price">Cheapest first</option>
            <option value="duration">Fastest first</option>
            <option value="departure">Earliest departure</option>
          </Select>
        </div>
      </div>

      {data.slices.map((slice) => {
        const offers = [...slice.offers].sort((a, b) => {
          if (sort === 'duration') return a.itinerary.duration_minutes - b.itinerary.duration_minutes;
          if (sort === 'departure')
            return a.itinerary.departure_utc.localeCompare(b.itinerary.departure_utc);
          return Number(a.total.amount) - Number(b.total.amount);
        });

        return (
          <section key={slice.search_id} className="space-y-3">
            {data.slices.length > 1 && (
              <h2 className="text-sm font-medium text-muted">
                {slice.index === 0 ? 'Outbound' : 'Return'} · {slice.origin} → {slice.destination} ·{' '}
                {slice.date}
              </h2>
            )}

            {offers.length === 0 ? (
              <Card>
                <p className="text-sm text-muted">
                  No flights found for this date. Try a nearby date or allow more stops.
                </p>
              </Card>
            ) : (
              offers.map((offer) => <FlightCard key={offer.offer_id} offer={offer} />)
            )}
          </section>
        );
      })}
    </div>
  );
}
