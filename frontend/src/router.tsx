import { lazy, Suspense, type ComponentType } from 'react';
import { createBrowserRouter } from 'react-router-dom';

import { Layout } from './components/Layout';
import { PageSkeleton } from './components/PageSkeleton';

const Home = lazy(() => import('./features/search/HomePage'));
const SearchResults = lazy(() => import('./features/search/SearchResultsPage'));
const PassengerDetails = lazy(() => import('./features/booking/PassengerDetailsPage'));
const BookingConfirmation = lazy(() => import('./features/booking/BookingConfirmationPage'));
const Payment = lazy(() => import('./features/payment/PaymentPage'));
const FindBooking = lazy(() => import('./features/manage/FindBookingPage'));
const ManageBooking = lazy(() => import('./features/manage/ManageBookingPage'));
const Login = lazy(() => import('./features/auth/LoginPage'));
const Register = lazy(() => import('./features/auth/RegisterPage'));
const MyBookings = lazy(() => import('./features/account/MyBookingsPage'));
const TicketView = lazy(() => import('./features/manage/TicketPage'));
const OpsLayout = lazy(() => import('./features/ops/OpsLayout'));
const OpsReports = lazy(() => import('./features/ops/ReportsPage'));
const OpsRefunds = lazy(() => import('./features/ops/RefundQueuePage'));
const OpsDisruptions = lazy(() => import('./features/ops/DisruptionsPage'));
const NotFound = lazy(() => import('./features/shell/NotFoundPage'));

function lazyRoute(Component: ComponentType) {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Component />
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: lazyRoute(Home) },
      { path: 'search', element: lazyRoute(SearchResults) },
      { path: 'book', element: lazyRoute(PassengerDetails) },
      { path: 'booking/:pnr', element: lazyRoute(BookingConfirmation) },
      { path: 'booking/:pnr/pay', element: lazyRoute(Payment) },
      { path: 'manage', element: lazyRoute(FindBooking) },
      { path: 'manage/:pnr', element: lazyRoute(ManageBooking) },
      { path: 'manage/:pnr/ticket', element: lazyRoute(TicketView) },
      { path: 'login', element: lazyRoute(Login) },
      { path: 'register', element: lazyRoute(Register) },
      { path: 'account/bookings', element: lazyRoute(MyBookings) },
      {
        path: 'ops',
        element: lazyRoute(OpsLayout),
        children: [
          { index: true, element: lazyRoute(OpsReports) },
          { path: 'reports', element: lazyRoute(OpsReports) },
          { path: 'refunds', element: lazyRoute(OpsRefunds) },
          { path: 'disruptions', element: lazyRoute(OpsDisruptions) },
        ],
      },
      { path: '*', element: lazyRoute(NotFound) },
    ],
  },
]);
