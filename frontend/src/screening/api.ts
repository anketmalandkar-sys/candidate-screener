import { json, request } from '../client'
import type { Page } from '../types'
import type {
  AgentRun,
  AgentRunSummary,
  ComparisonDetail,
  RunDetail,
  RunSummary,
  UnifiedCandidateAudit,
} from './types'

/** Screening: start a run, watch it, read audits. */
export const screeningApi = {
  startScreening: (roleId: number, candidateIds: number[]) =>
    json<RunDetail>('/api/screening/runs', 'POST', {
      role_id: roleId,
      candidate_ids: candidateIds,
    }),

  listScreeningRuns: (opts: { limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams()
    if (opts.limit !== undefined) q.set('limit', String(opts.limit))
    if (opts.offset !== undefined) q.set('offset', String(opts.offset))
    const qs = q.toString()
    return request<Page<RunSummary>>(`/api/screening/runs${qs ? `?${qs}` : ''}`)
  },

  getScreeningRun: (runId: number) =>
    request<RunDetail>(`/api/screening/runs/${runId}`),

  getScreeningResult: (runId: number, candidateId: number | string) =>
    request<UnifiedCandidateAudit>(
      `/api/screening/runs/${runId}/results/${candidateId}`,
    ),

  /** Run-wide "what are the agents doing" feed (metadata only). */
  listRunAgentRuns: (runId: number) =>
    request<AgentRunSummary[]>(`/api/screening/runs/${runId}/agent-runs`),

  /** Per-candidate agent calls, with the verbatim request + response. */
  listResultAgentRuns: (runId: number, candidateId: number | string) =>
    request<AgentRun[]>(
      `/api/screening/runs/${runId}/results/${candidateId}/agent-runs`,
    ),

  rerunScreening: (runId: number, scope: 'all' | 'errored' | 'changed') =>
    json<RunDetail>(`/api/screening/runs/${runId}/rerun`, 'POST', { scope }),

  compareCandidates: (roleId: number, aId: number, bId: number) =>
    json<ComparisonDetail>('/api/screening/comparisons', 'POST', {
      role_id: roleId,
      candidate_a_id: aId,
      candidate_b_id: bId,
    }),
}
