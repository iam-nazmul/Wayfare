import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

import { setAccessToken } from '../../api/client';
import type { User } from '../../api/types';

interface AuthState {
  user: User | null;
  signIn: (user: User, access: string) => void;
  signOut: () => void;
}

/**
 * Who is signed in, for rendering. The access token itself lives in the API client — this store
 * only mirrors the identity so the shell can show a name and gate the ops nav.
 */
export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      signIn: (user, access) => {
        setAccessToken(access);
        set({ user });
      },
      signOut: () => {
        setAccessToken(null);
        set({ user: null });
      },
    }),
    { name: 'wf_auth', storage: createJSONStorage(() => localStorage) },
  ),
);

//: Roles that may open the ops console. The server enforces this too — this only hides the nav.
const STAFF_ROLES = new Set(['OPS_AGENT', 'TICKETING', 'FINANCE', 'SUPERADMIN']);

export function isStaff(user: User | null): boolean {
  if (!user) return false;
  if (user.is_staff) return true;
  return (user.roles ?? []).some((role) => STAFF_ROLES.has(role));
}

export function hasRole(user: User | null, ...roles: string[]): boolean {
  if (!user) return false;
  if (user.is_staff) return true;
  return (user.roles ?? []).some((role) => roles.includes(role));
}
