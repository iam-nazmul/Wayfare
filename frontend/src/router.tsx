import { lazy, Suspense, type ComponentType } from 'react';
import { createBrowserRouter } from 'react-router-dom';

import { Layout } from './components/Layout';
import { PageSkeleton } from './components/PageSkeleton';

const Home = lazy(() => import('./features/search/HomePage'));
const SearchResults = lazy(() => import('./features/search/SearchResultsPage'));
const PassengerDetails = lazy(() => import('./features/booking/PassengerDetailsPage'));
const BookingConfirmation = lazy(() => import('./features/booking/BookingConfirmationPage'));
const Payment = lazy(() => import('./features/payment/PaymentPage'));
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
      { path: '*', element: lazyRoute(NotFound) },
    ],
  },
]);
