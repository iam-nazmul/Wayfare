import { NavLink, Navigate, Outlet, useLocation } from 'react-router-dom';

import { isStaff, useAuth } from '../auth/store';

const TABS = [
  { to: '/ops/reports', label: 'Reports' },
  { to: '/ops/refunds', label: 'Refunds' },
  { to: '/ops/disruptions', label: 'Disruptions' },
];

/**
 * Client-side gate for the ops console. It hides the console from travellers; it is not the
 * authorisation — every /ops endpoint checks the role server-side regardless.
 */
export default function OpsLayout() {
  const user = useAuth((state) => state.user);
  const location = useLocation();

  if (!isStaff(user)) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Ops console</h1>
        <p className="text-sm text-muted">
          Signed in as {user?.email}
          {user?.roles?.length ? ` · ${user.roles.join(', ').toLowerCase()}` : ''}
        </p>
      </div>

      <nav aria-label="Ops sections" className="flex gap-1 border-b border-line">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            className={({ isActive }) =>
              `-mb-px border-b-2 px-3 py-2 text-sm ${
                isActive
                  ? 'border-brand-600 font-medium text-ink'
                  : 'border-transparent text-muted hover:text-ink'
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </div>
  );
}
