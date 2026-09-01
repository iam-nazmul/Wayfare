import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Alert, Button, Field, Select } from '../../components/ui';
import type { Cabin, TripType } from '../../api/types';
import { track } from '../../lib/analytics';
import { AirportInput } from './AirportInput';

const CABINS: { value: Cabin; label: string }[] = [
  { value: 'ECONOMY', label: 'Economy' },
  { value: 'PREMIUM_ECONOMY', label: 'Premium economy' },
  { value: 'BUSINESS', label: 'Business' },
  { value: 'FIRST', label: 'First' },
];

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function SearchForm() {
  const navigate = useNavigate();

  const [tripType, setTripType] = useState<TripType>('ROUND_TRIP');
  const [origin, setOrigin] = useState('');
  const [destination, setDestination] = useState('');
  const [departDate, setDepartDate] = useState(today());
  const [returnDate, setReturnDate] = useState('');
  const [adults, setAdults] = useState(1);
  const [children, setChildren] = useState(0);
  const [infants, setInfants] = useState(0);
  const [cabin, setCabin] = useState<Cabin>('ECONOMY');
  const [error, setError] = useState('');

  function submit(event: React.FormEvent) {
    event.preventDefault();
    setError('');

    if (!origin || !destination) return setError('Choose where you are flying from and to.');
    if (origin === destination) return setError('Origin and destination must be different.');
    if (infants > adults) return setError('Each infant must travel with an adult.');
    if (tripType === 'ROUND_TRIP' && !returnDate) return setError('Choose a return date.');
    if (tripType === 'ROUND_TRIP' && returnDate < departDate)
      return setError('The return date cannot be before the outbound date.');

    track('search_submitted', {
      origin,
      destination,
      cabin,
      pax_count: adults + children + infants,
    });

    const params = new URLSearchParams({
      trip: tripType,
      from: origin,
      to: destination,
      depart: departDate,
      adults: String(adults),
      children: String(children),
      infants: String(infants),
      cabin,
    });
    if (tripType === 'ROUND_TRIP') params.set('return', returnDate);

    navigate(`/search?${params.toString()}`);
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <fieldset className="flex gap-4">
        <legend className="sr-only">Trip type</legend>
        {(['ROUND_TRIP', 'ONE_WAY'] as TripType[]).map((value) => (
          <label key={value} className="flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="trip_type"
              value={value}
              checked={tripType === value}
              onChange={() => setTripType(value)}
            />
            {value === 'ROUND_TRIP' ? 'Return' : 'One way'}
          </label>
        ))}
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2">
        <AirportInput label="From" value={origin} onChange={setOrigin} placeholder="City or airport" />
        <AirportInput label="To" value={destination} onChange={setDestination} placeholder="City or airport" />
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Departing">
          <input
            type="date"
            value={departDate}
            min={today()}
            onChange={(event) => setDepartDate(event.target.value)}
            className="w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm"
          />
        </Field>
        <Field label="Returning">
          <input
            type="date"
            value={returnDate}
            min={departDate}
            disabled={tripType !== 'ROUND_TRIP'}
            onChange={(event) => setReturnDate(event.target.value)}
            className="w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm disabled:bg-brand-50 disabled:text-muted"
          />
        </Field>
      </div>

      <div className="grid gap-4 sm:grid-cols-4">
        <Field label="Adults">
          <Select value={adults} onChange={(e) => setAdults(Number(e.target.value))}>
            {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </Select>
        </Field>
        <Field label="Children" hint="2–11 years">
          <Select value={children} onChange={(e) => setChildren(Number(e.target.value))}>
            {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </Select>
        </Field>
        <Field label="Infants" hint="Under 2, on lap">
          <Select value={infants} onChange={(e) => setInfants(Number(e.target.value))}>
            {[0, 1, 2, 3, 4].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </Select>
        </Field>
        <Field label="Cabin">
          <Select value={cabin} onChange={(e) => setCabin(e.target.value as Cabin)}>
            {CABINS.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </Select>
        </Field>
      </div>

      {error && <Alert tone="error">{error}</Alert>}

      <Button type="submit" className="w-full sm:w-auto">
        Search flights
      </Button>
    </form>
  );
}
