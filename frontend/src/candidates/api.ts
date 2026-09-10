import { json, request } from '../client'
import type { Page } from '../types'
import type { CandidatePoolDetail, CandidatePoolItem } from './types'

/** The candidate pool: résumé intake and retrieval. */
export const candidatesApi = {
  /** One page of the pool, newest first. */
  listCandidates: (opts: { limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams()
    if (opts.limit !== undefined) q.set('limit', String(opts.limit))
    if (opts.offset !== undefined) q.set('offset', String(opts.offset))
    const qs = q.toString()
    return request<Page<CandidatePoolItem>>(`/api/candidates${qs ? `?${qs}` : ''}`)
  },

  getCandidate: (candidateId: number) =>
    request<CandidatePoolDetail>(`/api/candidates/${candidateId}`),

  createCandidate: (name: string, resumeText: string, email?: string) =>
    json<CandidatePoolItem>('/api/candidates', 'POST', {
      name,
      resume_text: resumeText,
      ...(email ? { email } : {}),
    }),

  uploadCandidate: (name: string, file: File) => {
    const form = new FormData()
    form.append('name', name)
    form.append('file', file)
    // No Content-Type header: the browser must set the multipart boundary.
    return request<CandidatePoolItem>('/api/candidates/upload', {
      method: 'POST',
      body: form,
    })
  },

  deleteCandidate: (candidateId: number) =>
    request<void>(`/api/candidates/${candidateId}`, { method: 'DELETE' }),
}
