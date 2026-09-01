import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <section className="py-16 text-center">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="mt-2 text-muted">That route does not exist.</p>
      <Link to="/" className="mt-6 inline-block text-brand-600 underline">
        Back to search
      </Link>
    </section>
  );
}
