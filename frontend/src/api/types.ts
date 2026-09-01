import type { Money } from '../lib/money';

/**
 * Hand-written mirror of the API contract. Replaced by `src/api/schema.d.ts` (generated from
 * OpenAPI via `make schema`) as soon as the backend can be run to emit a schema.
 */

export type Cabin = 'ECONOMY' | 'PREMIUM_ECONOMY' | 'BUSINESS' | 'FIRST';
export type TripType = 'ONE_WAY' | 'ROUND_TRIP' | 'MULTI_CITY';

export interface Airport {
  iata_code: string;
  icao_code: string;
  name: string;
  city: string;
  country: string;
  country_code: string;
  timezone: string;
}

export interface Segment {
  flight_id: number;
  flight_public_id: string;
  designator: string;
  airline: string;
  origin: string;
  destination: string;
  departure_utc: string;
  arrival_utc: string;
  departure_local: string;
  arrival_local: string;
  duration_minutes: number;
  aircraft: string;
  cabin: Cabin;
  rbd: string;
}

export interface Itinerary {
  origin: string;
  destination: string;
  stops: number;
  duration_minutes: number;
  departure_utc: string;
  arrival_utc: string;
  segments: Segment[];
}

export interface TaxLine {
  code: string;
  name: string;
  amount: Money;
  refundable: boolean;
}

export interface FeeLine {
  code: string;
  name: string;
  amount: Money;
}

export interface PriceBreakdown {
  base: Money;
  taxes: Money;
  fees: Money;
  discount: Money;
  total: Money;
  tax_lines: TaxLine[];
  fee_lines: FeeLine[];
}

export interface Offer {
  offer_id: string;
  itinerary: Itinerary;
  price_breakdown: PriceBreakdown;
  total: Money;
  currency: string;
  seats_remaining: number;
  expires_at: string;
}

export interface SearchSliceResult {
  index: number;
  search_id: string;
  origin: string;
  destination: string;
  date: string;
  offers: Offer[];
}

export interface SearchResponse {
  trip_type: TripType;
  currency: string;
  partial: boolean;
  slices: SearchSliceResult[];
}

export interface SearchRequest {
  trip_type: TripType;
  slices: { origin: string; destination: string; date: string }[];
  passengers: { adults: number; children: number; infants: number };
  cabin: Cabin;
  currency: string;
  max_stops: number;
}
