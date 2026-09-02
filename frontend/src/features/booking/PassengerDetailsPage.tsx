import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { isApiError } from '../../api/problem';
import type { PassengerInput, PassengerType } from '../../api/types';
import { Alert, Button, Card, Field, Input, Select } from '../../components/ui';
import { track } from '../../lib/analytics';
import { countdown, formatDate, formatLocalTime } from '../../lib/dates';
import { formatMoney } from '../../lib/money';
import { useCreateBooking } from './api';
import { partyToTypes, useBookingWizard } from './store';

const TYPE_LABEL: Record<PassengerType, string> = {
  ADT: 'Adult',
  CHD: 'Child (2–11)',
  INF: 'Infant (under 2)',
};

function blank(type: PassengerType): PassengerInput {
  return { type, first_name: '', last_name: '', dob: '', gender: '', nationality: '' };
}

export default function PassengerDetailsPage() {
  const navigate = useNavigate();
  const { offer, party } = useBookingWizard();
  const createBooking = useCreateBooking();

  const types = useMemo(() => partyToTypes(party), [party]);
  const [passengers, setPassengers] = useState<PassengerInput[]>(() => types.map(blank));
  const [contact, setContact] = useState({ email: '', phone: '' });
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    track('pax_details_started', { offer_id: offer?.offer_id, pax_count: types.length });
  }, [offer?.offer_id, types.length]);

  // The offer expires in 15 minutes; the traveller needs to see that clock, not discover it
  // when the submit fails.
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);

  if (!offer) {
    return (
      <Alert tone="error">
        Your selected flight is no longer in this session.{' '}
        <Link className="underline" to="/">
          Start a new search
        </Link>
        .
      </Alert>
    );
  }

  const expiry = countdown(offer.expires_at, now);
  const first = offer.itinerary.segments[0];
  const last = offer.itinerary.segments[offer.itinerary.segments.length - 1];
  const fieldErrors = isApiError(createBooking.error) ? createBooking.error.fieldErrors() : {};

  function update(index: number, patch: Partial<PassengerInput>) {
    setPassengers((current) =>
      current.map((passenger, position) =>
        position === index ? { ...passenger, ...patch } : passenger,
      ),
    );
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!offer) return;

    createBooking.mutate(
      { offer_id: offer.offer_id, passengers, contact },
      {
        onSuccess: (booking) => {
          track('pax_details_completed', {
            offer_id: offer.offer_id,
            pnr: booking.pnr,
            pax_count: passengers.length,
          });
          navigate(`/booking/${booking.pnr}`, {
            state: { booking, lastName: passengers[0]?.last_name },
          });
        },
      },
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Who is travelling?</h1>
        <p className="mt-1 text-sm text-muted">
          Names must match the passport or ID each passenger travels on.
        </p>
      </div>

      <Card>
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <div className="font-medium">
              {offer.itinerary.origin} → {offer.itinerary.destination}
            </div>
            <div className="text-sm text-muted">
              {formatDate(first.departure_local)} · {formatLocalTime(first.departure_local)} –{' '}
              {formatLocalTime(last.arrival_local)} ·{' '}
              {offer.itinerary.segments.map((segment) => segment.designator).join(' + ')}
            </div>
          </div>
          <div className="text-right">
            <div className="text-xl font-semibold tabular-nums">{formatMoney(offer.total)}</div>
            <div className="text-xs text-muted">total for all passengers</div>
          </div>
        </div>

        <p aria-live="polite" className="mt-3 text-xs text-muted">
          {expiry.expired
            ? 'This price has expired — search again for a current fare.'
            : `This price is held for ${expiry.minutes} more minute${expiry.minutes === 1 ? '' : 's'}.`}
        </p>
      </Card>

      {createBooking.isError && (
        <Alert tone="error">
          {isApiError(createBooking.error)
            ? createBooking.error.problem.detail
            : 'We could not hold those seats. Please try again.'}
        </Alert>
      )}

      <form onSubmit={submit} className="space-y-4">
        {passengers.map((passenger, index) => (
          <Card key={index}>
            <fieldset>
              <legend className="mb-3 text-sm font-medium">
                Passenger {index + 1} · {TYPE_LABEL[passenger.type]}
              </legend>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="First name" error={fieldErrors[`passengers.${index}.first_name`]}>
                  <Input
                    required
                    autoComplete="given-name"
                    value={passenger.first_name}
                    onChange={(event) => update(index, { first_name: event.target.value })}
                  />
                </Field>

                <Field label="Last name" error={fieldErrors[`passengers.${index}.last_name`]}>
                  <Input
                    required
                    autoComplete="family-name"
                    value={passenger.last_name}
                    onChange={(event) => update(index, { last_name: event.target.value })}
                  />
                </Field>

                <Field
                  label="Date of birth"
                  hint="Determines the fare this passenger travels on."
                  error={
                    fieldErrors[`passengers.${index}.dob`] ?? fieldErrors[`passengers.${index}`]
                  }
                >
                  <Input
                    required
                    type="date"
                    max={new Date().toISOString().slice(0, 10)}
                    value={passenger.dob}
                    onChange={(event) => update(index, { dob: event.target.value })}
                  />
                </Field>

                <Field label="Gender">
                  <Select
                    value={passenger.gender}
                    onChange={(event) => update(index, { gender: event.target.value })}
                  >
                    <option value="">Prefer not to say</option>
                    <option value="M">Male</option>
                    <option value="F">Female</option>
                    <option value="X">Unspecified</option>
                  </Select>
                </Field>
              </div>
            </fieldset>
          </Card>
        ))}

        <Card>
          <fieldset>
            <legend className="mb-3 text-sm font-medium">Contact details</legend>
            <p className="mb-3 text-xs text-muted">
              The booking confirmation and any disruption notice go here.
            </p>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Email" error={fieldErrors['contact.email']}>
                <Input
                  required
                  type="email"
                  autoComplete="email"
                  value={contact.email}
                  onChange={(event) => setContact({ ...contact, email: event.target.value })}
                />
              </Field>

              <Field label="Phone" hint="Optional, for urgent flight changes.">
                <Input
                  type="tel"
                  autoComplete="tel"
                  value={contact.phone}
                  onChange={(event) => setContact({ ...contact, phone: event.target.value })}
                />
              </Field>
            </div>
          </fieldset>
        </Card>

        <div className="flex items-center gap-4">
          <Button type="submit" disabled={createBooking.isPending || expiry.expired}>
            {createBooking.isPending ? 'Holding your seats…' : 'Hold seats and get a PNR'}
          </Button>
          <Link to="/" className="text-sm text-brand-600 underline">
            Change flight
          </Link>
        </div>
      </form>
    </div>
  );
}
