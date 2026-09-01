import { lazy, Suspense, type ComponentType } from 'react';
import { createBrowserRouter } from 'react-router-dom';

import { Layout } from './components/Layout';
import { PageSkeleton } from './components/PageSkeleton';

const Home = lazy(() => import('./features/search/HomePage'));
const SearchResults = lazy(() => import('./features/search/SearchResultsPage'));
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
      { path: '*', element: lazyRoute(NotFound) },
    ],
  },
]);
