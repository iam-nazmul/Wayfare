export function PageSkeleton() {
  return (
    <div className="animate-pulse space-y-4" aria-busy="true" aria-label="Loading">
      <div className="h-8 w-1/3 rounded bg-brand-100" />
      <div className="h-24 rounded-card bg-brand-50" />
      <div className="h-24 rounded-card bg-brand-50" />
    </div>
  );
}
