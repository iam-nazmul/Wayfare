import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface ManageState {
  /** Surname per PNR: guest retrieval needs it on every call, including after a reload. */
  surnames: Record<string, string>;
  remember: (pnr: string, lastName: string) => void;
  surnameFor: (pnr: string) => string | undefined;
  forget: (pnr: string) => void;
}

export const useManageAccess = create<ManageState>()(
  persist(
    (set, get) => ({
      surnames: {},
      remember: (pnr, lastName) =>
        set((state) => ({ surnames: { ...state.surnames, [pnr.toUpperCase()]: lastName } })),
      surnameFor: (pnr) => get().surnames[pnr.toUpperCase()],
      forget: (pnr) =>
        set((state) => {
          const next = { ...state.surnames };
          delete next[pnr.toUpperCase()];
          return { surnames: next };
        }),
    }),
    { name: 'wf_manage', storage: createJSONStorage(() => sessionStorage) },
  ),
);
