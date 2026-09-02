import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { isApiError } from '../../api/problem';
import { Alert, Button, Card, Field, Input } from '../../components/ui';
import { useLogin } from './api';
import { isStaff } from './store';

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const login = useLogin();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const from = (location.state as { from?: string } | null)?.from;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    login.mutate(
      { email, password },
      {
        onSuccess: (user) => {
          navigate(from ?? (isStaff(user) ? '/ops/reports' : '/'), { replace: true });
        },
      },
    );
  }

  return (
    <div className="mx-auto max-w-md space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="mt-1 text-sm text-muted">
          Staff sign in for the ops console. Travellers can{' '}
          <Link className="underline" to="/manage">
            find a booking
          </Link>{' '}
          with a reference and surname instead.
        </p>
      </div>

      {login.isError && (
        <Alert tone="error">
          {isApiError(login.error) && login.error.status === 401
            ? 'That email and password do not match.'
            : isApiError(login.error)
              ? login.error.problem.detail
              : 'Sign in failed. Please try again.'}
        </Alert>
      )}

      <Card>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Email">
            <Input
              required
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </Field>

          <Field label="Password">
            <Input
              required
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>

          <Button type="submit" disabled={login.isPending}>
            {login.isPending ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
      </Card>
    </div>
  );
}
