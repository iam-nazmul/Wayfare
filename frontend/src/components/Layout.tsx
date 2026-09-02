import { Link, Outlet, useNavigate } from 'react-router-dom';

import { useLogout } from '../features/auth/api';
import { isStaff, useAuth } from '../features/auth/store';

export function Layout() {
  const user = useAuth((state) => state.user);
  const logout = useLogout();
  const navigate = useNavigate();

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
          <Link to="/" className="text-lg font-semibold tracking-tight text-brand-700">
            Wayfare
          </Link>
          <nav aria-label="Main" className="flex items-center gap-6 text-sm text-muted">
            <Link to="/manage" className="hover:text-ink">
              Manage booking
            </Link>
            {user && (
              <Link to="/account/bookings" className="hover:text-ink">
                My bookings
              </Link>
            )}
            {isStaff(user) && (
              <Link to="/ops/reports" className="hover:text-ink">
                Ops
              </Link>
            )}
            {user ? (
              <button
                type="button"
                className="hover:text-ink"
                onClick={() =>
                  logout.mutate(undefined, { onSettled: () => navigate('/', { replace: true }) })
                }
              >
                Sign out
              </button>
            ) : (
              <>
                <Link to="/login" className="hover:text-ink">
                  Sign in
                </Link>
                <Link to="/register" className="hover:text-ink">
                  Sign up
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto max-w-6xl px-4 py-6 text-xs text-muted">
          Wayfare — flight booking and ticket management.
        </div>
      </footer>
    </div>
  );
}
