export type Weight = 'nice' | 'important' | 'must'

export interface User {
  id: number
  email: string
  name: string
}

export interface Requirement {
  id: number
  label: string
  weight: Weight
  aliases: string[]
  position: number
}

export interface RequirementInput {
  label: string
  weight: Weight
  aliases: string[]
}

export interface RoleSummary {
  id: number
  title: string
  description: string
  is_active: boolean
  created_at: string
  requirement_count: number
}

export interface RoleDetail {
  id: number
  title: string
  description: string
  is_active: boolean
  created_at: string
  requirements: Requirement[]
}

/** One page of a listing plus the total number of rows available. */
export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

// Candidate-facing view models live in ./candidates/types.

export const WEIGHT_ORDER: Weight[] = ['must', 'important', 'nice']

export const WEIGHT_LABEL: Record<Weight, string> = {
  must: 'Must have',
  important: 'Important',
  nice: 'Nice to have',
}
