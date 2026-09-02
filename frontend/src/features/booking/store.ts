import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

import type { Offer, PassengerType } from '../../api/types';

export interface PartyCounts {
  adults: number;
  children: number;
  infants: number;
}

interface WizardState {
  offer: Offer | null;
  party: PartyCounts;
  select: (offer: Offer, party: PartyCounts) => void;
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
      offer: null,
      party: EMPTY_PARTY,
      select: (offer, party) => set({ offer, party }),
      clear: () => set({ offer: null, party: EMPTY_PARTY }),
    }),
    {
      name: 'wf_booking_wizard',
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);

/** One form row per seat sold, in the order the API expects them. */
export function partyToTypes(party: PartyCounts): PassengerType[] {
  return [
    ...Array<PassengerType>(party.adults).fill('ADT'),
    ...Array<PassengerType>(party.children).fill('CHD'),
    ...Array<PassengerType>(party.infants).fill('INF'),
  ];
}
