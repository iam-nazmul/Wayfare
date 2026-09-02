import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, setAccessToken } from '../../api/client';
import { keys } from '../../api/keys';
import type { TokenPair, User } from '../../api/types';
import { useAuth } from './store';

export function useLogin() {
  const signIn = useAuth((state) => state.signIn);

  return useMutation({
    mutationFn: async (credentials: { email: string; password: string }) => {
      const tokens = await api.post<TokenPair>('/auth/login', credentials);
      // The token has to be in place before /me is called, or it answers 401.
      setAccessToken(tokens.access);
      const user = await api.get<User>('/me');
      signIn(user, tokens.access);
      return user;
    },
    retry: false,
  });
}

export function useLogout() {
  const signOut = useAuth((state) => state.signOut);
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.post<void>('/auth/logout', {}).catch(() => undefined),
    onSettled: () => {
      signOut();
      queryClient.clear();
    },
  });
}

/** Revalidates the persisted identity; a revoked account should not keep a stale nav. */
export function useMe(enabled: boolean) {
  return useQuery({
    queryKey: keys.me(),
    queryFn: () => api.get<User>('/me'),
    enabled,
    retry: false,
    staleTime: 5 * 60 * 1000,
  });
}
