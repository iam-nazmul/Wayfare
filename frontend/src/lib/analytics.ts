import type { AnalyticsEvent, EventName, EventProps } from './events';

const ENDPOINT = `${import.meta.env.VITE_API_BASE_URL ?? '/api/v1'}/collect`;
const FLUSH_AT = 10;
const IDLE_MS = 5_000;
const MAX_BATCH = 100;

let queue: AnalyticsEvent[] = [];
let idleTimer: ReturnType<typeof setTimeout> | undefined;

function consented(): boolean {
  if (import.meta.env.VITE_ANALYTICS_ENABLED === '0') return false;
  if (typeof navigator !== 'undefined' && navigator.doNotTrack === '1') return false;
  try {
    return localStorage.getItem('wf_analytics_consent') !== 'denied';
  } catch {
    return false; // storage blocked — treat as no consent rather than guessing
  }
}

function id(key: string, store: Storage): string {
  try {
    const existing = store.getItem(key);
    if (existing) return existing;
    const created = crypto.randomUUID();
    store.setItem(key, created);
    return created;
  } catch {
    return 'anonymous';
  }
}

function sessionId(): string {
  return typeof sessionStorage === 'undefined' ? 'anonymous' : id('wf_session', sessionStorage);
}

function anonId(): string {
  return typeof localStorage === 'undefined' ? 'anonymous' : id('wf_anon', localStorage);
}

export function track(name: EventName, props: EventProps = {}): void {
  if (!consented()) return;

  queue.push({
    event_name: name,
    event_time: new Date().toISOString(),
    session_id: sessionId(),
    anon_id: anonId(),
    page_path: typeof location === 'undefined' ? '' : location.pathname,
    referrer: typeof document === 'undefined' ? '' : document.referrer,
    props,
  });

  if (queue.length >= FLUSH_AT) {
    flush();
    return;
  }

  clearTimeout(idleTimer);
  idleTimer = setTimeout(flush, IDLE_MS);
}

export function flush(): void {
  if (queue.length === 0) return;

  const events = queue.slice(0, MAX_BATCH);
  queue = queue.slice(MAX_BATCH);
  clearTimeout(idleTimer);

  const body = JSON.stringify({ events });

  // sendBeacon survives the page unload that ends most abandoned funnels.
  if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
    navigator.sendBeacon(ENDPOINT, new Blob([body], { type: 'application/json' }));
    return;
  }

  void fetch(ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
  }).catch(() => undefined);
}

export function installAnalytics(): void {
  if (typeof document === 'undefined') return;
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flush();
  });
}
