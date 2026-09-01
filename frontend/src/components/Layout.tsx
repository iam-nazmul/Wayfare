import { Link, Outlet } from 'react-router-dom';

export function Layout() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
          <Link to="/" className="text-lg font-semibold tracking-tight text-brand-700">
            Wayfare
          </Link>
          <nav aria-label="Main" className="flex gap-6 text-sm text-muted">
            <Link to="/manage" className="hover:text-ink">
              Manage booking
            </Link>
            <Link to="/checkin" className="hover:text-ink">
              Check in
            </Link>
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
