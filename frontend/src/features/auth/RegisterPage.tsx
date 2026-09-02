import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { api } from '../../api/client';
import { isApiError } from '../../api/problem';
import type { User } from '../../api/types';
import { Alert, Button, Card, Field, Input } from '../../components/ui';
import { useLogin } from './api';

export default function RegisterPage() {
  const navigate = useNavigate();
  const login = useLogin();

  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    password: '',
  });
  const [error, setError] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setFields({});

    try {
      await api.post<User>('/auth/register', form);
    } catch (caught) {
      if (isApiError(caught)) {
        setFields(caught.fieldErrors());
        setError(caught.problem.detail);
      } else {
        setError('We could not create that account.');
      }
      setBusy(false);
      return;
    }

    // Straight in rather than bouncing to a sign-in form they just filled the details for.
    login.mutate(
      { email: form.email, password: form.password },
      {
        onSuccess: () => navigate('/account/bookings', { replace: true }),
        onError: () => navigate('/login', { replace: true }),
        onSettled: () => setBusy(false),
      },
    );
  }

  return (
    <div className="mx-auto max-w-md space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Create an account</h1>
        <p className="mt-1 text-sm text-muted">
          Keep every booking in one place and get to your e-tickets without a reference number.
        </p>
      </div>

      {error && <Alert tone="error">{error}</Alert>}

      <Card>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="First name" error={fields.first_name}>
              <Input
                autoComplete="given-name"
                value={form.first_name}
                onChange={(event) => setForm({ ...form, first_name: event.target.value })}
              />
            </Field>

            <Field label="Last name" error={fields.last_name}>
              <Input
                autoComplete="family-name"
                value={form.last_name}
                onChange={(event) => setForm({ ...form, last_name: event.target.value })}
              />
            </Field>
          </div>

          <Field label="Email" error={fields.email}>
            <Input
              required
              type="email"
              autoComplete="email"
              value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
            />
          </Field>

          <Field
            label="Password"
            hint="At least 10 characters."
            error={fields.password}
          >
            <Input
              required
              type="password"
              minLength={10}
              autoComplete="new-password"
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
            />
          </Field>

          <Button type="submit" disabled={busy}>
            {busy ? 'Creating your account…' : 'Create account'}
          </Button>
        </form>
      </Card>

      <p className="text-sm text-muted">
        Already have an account?{' '}
        <Link className="underline" to="/login">
          Sign in
        </Link>
        . Booked as a guest?{' '}
        <Link className="underline" to="/manage">
          Find it with your reference
        </Link>
        .
      </p>
    </div>
  );
}
