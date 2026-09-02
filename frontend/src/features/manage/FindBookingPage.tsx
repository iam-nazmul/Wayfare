import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Button, Card, Field, Input } from '../../components/ui';
import { useManageAccess } from './store';

export default function FindBookingPage() {
  const navigate = useNavigate();
  const remember = useManageAccess((state) => state.remember);

  const [pnr, setPnr] = useState('');
  const [lastName, setLastName] = useState('');

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const reference = pnr.trim().toUpperCase();
    // The surname is needed on every subsequent call, so it is kept for the session rather
    // than asked for again on each action.
    remember(reference, lastName.trim());
    navigate(`/manage/${reference}`);
  }

  return (
    <div className="mx-auto max-w-md space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Find your booking</h1>
        <p className="mt-1 text-sm text-muted">
          Your six-character reference and the lead passenger’s surname.
        </p>
      </div>

      <Card>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Booking reference" hint="Six characters, for example 4818JD.">
            <Input
              required
              minLength={6}
              maxLength={6}
              autoCapitalize="characters"
              spellCheck={false}
              className="font-mono uppercase tracking-[0.2em]"
              value={pnr}
              onChange={(event) => setPnr(event.target.value.toUpperCase())}
            />
          </Field>

          <Field label="Lead passenger surname">
            <Input
              required
              autoComplete="family-name"
              value={lastName}
              onChange={(event) => setLastName(event.target.value)}
            />
          </Field>

          <Button type="submit">Find booking</Button>
        </form>
      </Card>
    </div>
  );
}
