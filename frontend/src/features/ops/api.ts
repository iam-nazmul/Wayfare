import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../../api/client';
import { keys } from '../../api/keys';
import type { Disruption, Refund, ReportResponse } from '../../api/types';

export function useRefundQueue(status: string) {
  return useQuery({
    queryKey: keys.refundQueue(status),
    queryFn: () =>
      api.get<Refund[]>(`/ops/refunds${status ? `?status=${encodeURIComponent(status)}` : ''}`),
    retry: false,
  });
}

export function useRefundDecision(status: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      refundId,
      decision,
      reason,
    }: {
      refundId: string;
      decision: 'approve' | 'reject';
      reason?: string;
    }) => api.post<Refund>(`/ops/refunds/${refundId}/${decision}`, { reason }),
    retry: false,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.refundQueue(status) }),
  });
}

export function useDisruptions() {
  return useQuery({
    queryKey: keys.disruptions(),
    queryFn: () => api.get<Disruption[]>('/ops/disruptions'),
    retry: false,
    // Ops watches this while a disruption is unfolding; five minutes is the detector's cadence.
    refetchInterval: 60_000,
  });
}

export interface ReportParams {
  date_from?: string;
  date_to?: string;
  origin?: string;
  destination?: string;
}

export function reportPath(slug: string, params: ReportParams): string {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => Boolean(value)) as [string, string][],
  );
  return `/ops/reports/${slug}${query.size ? `?${query}` : ''}`;
}

export function useReport(slug: string, params: ReportParams) {
  return useQuery({
    queryKey: keys.report(slug, params),
    queryFn: () => api.get<ReportResponse>(reportPath(slug, params)),
    retry: false,
    // Matches the server's five-minute cache; refetching sooner re-reads the same answer.
    staleTime: 5 * 60 * 1000,
  });
}
