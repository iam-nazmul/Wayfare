/**
 * Flight times render in airport-local time, never the viewer's timezone — a passenger boards on
 * the clock at the gate.
 *
 * The API sends *_local as a wall clock in a UTC container, so formatting MUST pin timeZone to
 * UTC. Without it the viewer's offset is applied and every departure time shifts.
 */
export function formatLocalTime(isoLocal: string, locale = 'en-US'): string {
  const date = new Date(isoLocal);
  if (Number.isNaN(date.getTime())) return isoLocal;
  return new Intl.DateTimeFormat(locale, {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'UTC',
  }).format(date);
}

export function formatDate(iso: string, locale = 'en-US'): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', year: 'numeric' })
    .format(date);
}

/** Durations come from the API as minutes; never recompute them from timestamps client-side. */
export function formatDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return hours > 0 ? `${hours}h ${mins.toString().padStart(2, '0')}m` : `${mins}m`;
}

/** Day offset badge for arrivals after midnight (+1). */
export function dayOffsetLabel(offset: number): string | null {
  return offset > 0 ? `+${offset}` : null;
}

export function countdown(toIso: string, now = Date.now()): { minutes: number; expired: boolean } {
  const target = new Date(toIso).getTime();
  const remaining = Math.max(0, target - now);
  return { minutes: Math.floor(remaining / 60_000), expired: remaining <= 0 };
}
