export type FindingCategory =
  | 'PROMPT_INJECTION'
  | 'SYSTEM_SPOOFING'
  | 'HIDDEN_PAYLOAD'
  | 'TIMELINE_OVERLAP'
  | 'CHRONOLOGICAL_ERROR'
  | 'SENIORITY_ANOMALY'
  | 'RECYCLED_METRIC'
  | 'UNSUBSTANTIATED_INFLATION'

export type AgentName =
  | 'manipulation_guard'
  | 'timeline_auditor'
  | 'inflation_auditor'

export type Severity = 'info' | 'low' | 'medium' | 'high'
export type Disposition = 'clear' | 'review' | 'high_concern'
export type RunStatus =
  | 'queued'
  | 'running'
  | 'partial'
  | 'complete'
  | 'failed'
export type ResultStatus = 'pending' | 'screened' | 'error' | 'skipped'

export interface IntegrityFlag {
  category: FindingCategory
  evidence: string
  reason: string
}

export interface IntegrityAuditResult {
  agent_name: AgentName
  candidate_id: string
  is_compromised: boolean
  flags: IntegrityFlag[]
}

export interface EnrichedFinding {
  id: number | null
  category: FindingCategory
  evidence: string
  reason: string
  source: AgentName
  severity: Severity | null
  benign_explanation: string | null
  confidence: number | null
  recommended_action: string | null
  pattern_key: string | null
  verified: boolean
}

export interface UnifiedCandidateAudit {
  run_id: number
  result_id: number | null
  candidate_id: string
  candidate_name: string
  status: ResultStatus
  resume_sha256: string
  is_compromised: boolean
  overall_disposition: Disposition | null
  summary: string
  agent_results: IntegrityAuditResult[]
  findings: EnrichedFinding[]
  degraded: string[]
  provider: Record<string, string>
  models: Record<string, string>
  error: string | null
  created_at: string | null
}

export interface RunResultSummary {
  candidate_id: string
  candidate_name: string
  status: ResultStatus
  is_compromised: boolean
  overall_disposition: Disposition | null
  finding_count: number
}

export interface RunSummary {
  id: number
  role_id: number
  status: RunStatus
  provider: Record<string, string>
  models: Record<string, string>
  counts: Record<'total' | 'screened' | 'compromised' | 'errored', number>
  created_at: string
  completed_at: string | null
}

export interface RunDetail extends RunSummary {
  results: RunResultSummary[]
}

export interface ComparisonDimension {
  dimension: 'TECHNICAL_DEPTH' | 'PROVEN_IMPACT' | 'ROLE_RELEVANCE' | 'RISK_PROFILE'
  candidate_a_evidence: string
  candidate_b_evidence: string
  tradeoff_analysis: string
}

export interface ComparativeAnalysisResult {
  higher_ranked_id: string
  lower_ranked_id: string
  decision_summary: string
  comparisons: ComparisonDimension[]
}

export interface ComparisonDetail extends ComparativeAnalysisResult {
  id: number
  role_id: number
  candidate_a_id: number
  candidate_b_id: number
  findings_surfaced: { category: string; evidence: string; severity: string }[]
  model: string
  prompt_text: string
  raw_response: string
  created_at: string | null
}

export interface ToolCall {
  name: string
  arguments: Record<string, unknown>
  result_summary: string
  latency_ms: number
}

export interface AgentRunSummary {
  id: number
  candidate_id: string
  candidate_name: string | null
  agent_name: string
  tier: 'hf' | 'openai' | 'stub'
  model: string
  parsed_ok: boolean
  repair_attempts: number
  degraded: boolean
  notes: string | null
  tool_call_count?: number
  latency_ms: number
  input_chars: number
  created_at: string
}

export interface AgentRun extends AgentRunSummary {
  prompt_text: string
  raw_response: string
  tool_calls?: ToolCall[]
}

export const AGENT_ROLE: Record<string, string> = {
  injection_classifier: 'Prompt-injection classifier · hf-inference (per candidate)',
  manipulation_guard: 'Agent 1 · manipulation & prompt injection',
  timeline_auditor: 'Agent 2 · internal consistency & timeline',
  inflation_auditor: 'Agent 3 · templated inflation',
  synthesizer: 'Agent 4 · aggregation & synthesis · OpenAI',
  comparative_reasoner: 'Agent 5 · comparative reasoner · OpenAI',
}

export const DISPOSITION_LABEL: Record<Disposition, string> = {
  clear: 'Clear',
  review: 'Review',
  high_concern: 'High concern',
}

export const AGENT_LABEL: Record<AgentName, string> = {
  manipulation_guard: 'Manipulation & prompt injection',
  timeline_auditor: 'Internal consistency & timeline',
  inflation_auditor: 'Templated inflation',
}

export const MANIPULATION_CATEGORIES: FindingCategory[] = [
  'PROMPT_INJECTION',
  'SYSTEM_SPOOFING',
  'HIDDEN_PAYLOAD',
]
