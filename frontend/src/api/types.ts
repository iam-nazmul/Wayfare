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

export type PassengerType = 'ADT' | 'CHD' | 'INF';

export type BookingStatus =
  | 'DRAFT'
  | 'HELD'
  | 'PENDING_TICKETING'
  | 'TICKETED'
  | 'CONFIRMED'
  | 'CHANGE_PENDING'
  | 'DISRUPTED'
  | 'REBOOKED'
  | 'CANCELLED'
  | 'REFUND_PENDING'
  | 'REFUNDED'
  | 'EXPIRED';

export interface PassengerInput {
  type: PassengerType;
  first_name: string;
  last_name: string;
  dob: string;
  gender?: string;
  nationality?: string;
  doc_type?: string;
  doc_number?: string;
  doc_expiry?: string | null;
  frequent_flyer_number?: string;
}

export interface Passenger extends PassengerInput {
  id: number;
}

export interface BookingSegment {
  sequence: number;
  flight_public_id: string;
  designator: string;
  origin: string;
  destination: string;
  departure_utc: string;
  arrival_utc: string;
  departure_local: string;
  arrival_local: string;
  duration_minutes: number;
  cabin: Cabin;
  rbd: string;
  fare_basis: string;
  status: string;
  baggage_allowance: Record<string, unknown>;
}

export interface BookingRequest {
  offer_id: string;
  passengers: PassengerInput[];
  contact: { email: string; phone?: string };
}

export interface Booking {
  pnr: string;
  public_id: string;
  status: BookingStatus;
  trip_type: TripType;
  currency: string;
  base: Money;
  taxes: Money;
  fees: Money;
  discount: Money;
  total: Money;
  balance_due: Money;
  contact_email: string;
  contact_phone: string;
  hold_expires_at: string | null;
  booked_at: string | null;
  segments: BookingSegment[];
  passengers: Passenger[];
}

export type IntentStatus =
  | 'REQUIRES_PAYMENT'
  | 'REQUIRES_ACTION'
  | 'PROCESSING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'CANCELLED';

export interface PaymentIntent {
  intent_id: string;
  provider: string;
  provider_intent_id: string;
  amount: Money;
  status: IntentStatus;
  client_secret: string;
  three_ds_status: 'NOT_REQUIRED' | 'REQUIRED' | 'AUTHENTICATED' | 'FAILED';
  expires_at: string;
}

export interface Payment {
  payment_id: string;
  method: string;
  provider: string;
  amount: Money;
  status: 'AUTHORISED' | 'CAPTURED' | 'FAILED' | 'REFUNDED' | 'PARTIALLY_REFUNDED';
  card_brand: string;
  card_last4: string;
  captured_at: string | null;
  failure_code: string;
  failure_message: string;
}

export interface TicketCoupon {
  coupon_number: number;
  status: string;
  designator: string;
  origin: string;
  destination: string;
  departure_local: string;
  flown_at: string | null;
}

export interface Ticket {
  ticket_number: string;
  status: string;
  passenger_name: string;
  issued_at: string;
  fare: Money;
  taxes: Money;
  total: Money;
  fare_calculation: string;
  coupons: TicketCoupon[];
}
