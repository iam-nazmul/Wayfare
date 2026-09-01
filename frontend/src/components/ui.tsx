import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react';

const focusRing = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600';

export function Button({
  variant = 'primary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' }) {
  const styles =
    variant === 'primary'
      ? 'bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-100 disabled:text-muted'
      : 'border border-line bg-white text-ink hover:bg-brand-50';

  return (
    <button
      className={`inline-flex items-center justify-center rounded-lg px-4 py-2.5 text-sm font-medium transition-colors disabled:cursor-not-allowed ${styles} ${focusRing} ${className}`}
      {...props}
    />
  );
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-muted">{label}</span>
      {children}
      {error ? (
        <span role="alert" className="mt-1 block text-xs text-red-600">
          {error}
        </span>
      ) : hint ? (
        <span className="mt-1 block text-xs text-muted">{hint}</span>
      ) : null}
    </label>
  );
}

export function Input({ className = '', ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-ink placeholder:text-muted ${focusRing} ${className}`}
      {...props}
    />
  );
}

export function Select({ className = '', ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={`w-full rounded-lg border border-line bg-white px-3 py-2.5 text-sm text-ink ${focusRing} ${className}`}
      {...props}
    />
  );
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-card border border-line bg-white p-5 shadow-sm ${className}`}>
      {children}
    </div>
  );
}

export function Alert({ tone = 'info', children }: { tone?: 'info' | 'error'; children: ReactNode }) {
  const styles =
    tone === 'error'
      ? 'border-red-200 bg-red-50 text-red-800'
      : 'border-brand-100 bg-brand-50 text-ink';
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={`rounded-lg border px-4 py-3 text-sm ${styles}`}>
      {children}
    </div>
  );
}
