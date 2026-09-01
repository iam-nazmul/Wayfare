/**
 * The clickstream taxonomy (SPEC.md §9.4). Adding an event means extending this union,
 * so an ad-hoc name fails type-check instead of silently polluting ClickHouse.
 */
export const EVENT_NAMES = [
  'page_view',
  'search_submitted',
  'search_results_rendered',
  'filter_applied',
  'sort_changed',
  'offer_viewed',
  'offer_selected',
  'pax_details_started',
  'pax_details_completed',
  'ancillary_added',
  'ancillary_removed',
  'seat_selected',
  'payment_started',
  'payment_failed',
  'booking_confirmed',
  'checkin_started',
  'checkin_completed',
  'error_shown',
  'api_latency',
] as const;

export type EventName = (typeof EVENT_NAMES)[number];

export interface EventProps {
  origin?: string;
  destination?: string;
  cabin?: string;
  pax_count?: number;
  amount?: string;
  currency?: string;
  duration_ms?: number;
  offer_id?: string;
  pnr?: string;
  [key: string]: unknown;
}

export interface AnalyticsEvent {
  event_name: EventName;
  event_time: string;
  session_id: string;
  anon_id: string;
  page_path: string;
  referrer: string;
  props: EventProps;
}
