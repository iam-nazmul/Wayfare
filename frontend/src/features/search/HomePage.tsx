import { useEffect } from 'react';

import { Card } from '../../components/ui';
import { installAnalytics, track } from '../../lib/analytics';
import { SearchForm } from './SearchForm';

export default function HomePage() {
  useEffect(() => {
    installAnalytics();
    track('page_view', {});
  }, []);

  return (
    <section className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Find your flight</h1>
        <p className="mt-2 text-muted">
          Search fares across our network, book, and manage your ticket end to end.
        </p>
      </div>

      <Card>
        <SearchForm />
      </Card>
    </section>
  );
}
