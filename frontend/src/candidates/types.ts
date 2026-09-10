/** One row of the candidate pool. */
export interface CandidatePoolItem {
  id: number
  name: string
  email: string | null
  source: string
  original_filename: string | null
  created_at: string
}

export interface CandidatePoolDetail {
  id: number
  name: string
  email: string | null
  source: string
  original_filename: string | null
  created_at: string
  resume_text: string
}
