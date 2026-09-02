import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

import type { Offer, PassengerType } from '../../api/types';

export interface PartyCounts {
  adults: number;
  children: number;
  infants: number;
}

interface WizardState {
  /** One chosen offer per journey slice, indexed by slice. A round trip needs both filled. */
  offers: (Offer | null)[];
  party: PartyCounts;
  choose: (sliceIndex: number, offer: Offer, party: PartyCounts, sliceCount: number) => void;
  clear: () => void;
}

const EMPTY_PARTY: PartyCounts = { adults: 1, children: 0, infants: 0 };

/**
 * The booking wizard's client state, in sessionStorage so a reload on the passenger form does
 * not throw the traveller back to search results. Server state stays in TanStack Query.
 */
export const useBookingWizard = create<WizardState>()(
  persist(
    (set) => ({
      offers: [],
      party: EMPTY_PARTY,
      choose: (sliceIndex, offer, party, sliceCount) =>
        set((state) => {
          // Re-selecting a leg replaces it; the other legs keep what they had.
          const next = Array.from(
            { length: sliceCount },
            (_, index) => state.offers[index] ?? null,
          );
          next[sliceIndex] = offer;
          return { offers: next, party };
        }),
      clear: () => set({ offers: [], party: EMPTY_PARTY }),
    }),
    {
      name: 'wf_booking_wizard',
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);

/** Every slice has a flight, so the journey can be booked. */
export function isComplete(offers: (Offer | null)[]): offers is Offer[] {
  return offers.length > 0 && offers.every(Boolean);
}

/** One form row per seat sold, in the order the API expects them. */
export function partyToTypes(party: PartyCounts): PassengerType[] {
  return [
    ...Array<PassengerType>(party.adults).fill('ADT'),
    ...Array<PassengerType>(party.children).fill('CHD'),
    ...Array<PassengerType>(party.infants).fill('INF'),
  ];
}
