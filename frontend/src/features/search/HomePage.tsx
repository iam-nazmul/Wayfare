export default function HomePage() {
  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Find your flight</h1>
        <p className="mt-2 text-muted">
          Search fares, book, and manage your ticket end to end.
        </p>
      </div>

      <div className="rounded-card border border-line bg-white p-6 shadow-sm">
        <p className="text-sm text-muted">
          Flight search arrives with milestone M2. The API contract it will call is published at{' '}
          <a className="text-brand-600 underline" href="/api/docs/">
            /api/docs
          </a>
          .
        </p>
      </div>
    </section>
  );
}
