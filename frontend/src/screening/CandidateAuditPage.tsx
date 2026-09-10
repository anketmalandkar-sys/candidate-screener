import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import AgentRunTable, { AgentLegend } from './AgentRunTable'
import {
  AGENT_LABEL,
  MANIPULATION_CATEGORIES,
  type AgentName,
  type AgentRun,
  type EnrichedFinding,
  type UnifiedCandidateAudit,
} from './types'
import { Field, ManipulationBanner, SeverityBadge } from './ui'

const AGENTS: AgentName[] = [
  'manipulation_guard',
  'timeline_auditor',
  'inflation_auditor',
]

function highlight(resume: string, quote: string) {
  const q = quote.split('||')[0].trim().replace(/\s*\(repeated across[^)]*\)\s*$/, '')
  const at = resume.toLowerCase().indexOf(q.toLowerCase())
  if (at === -1 || q.length < 4) return <pre className="resume-view">{resume}</pre>
  return (
    <pre className="resume-view">
      {resume.slice(0, at)}
      <mark>{resume.slice(at, at + q.length)}</mark>
      {resume.slice(at + q.length)}
    </pre>
  )
}

function FindingCard({ finding }: { finding: EnrichedFinding }) {
  return (
    <div className={`finding sev-border-${finding.severity ?? 'low'}`}>
      <div className="finding-head">
        <SeverityBadge severity={finding.severity} />
        <strong>{finding.category.replace(/_/g, ' ')}</strong>
        {!finding.verified && <span className="chip">unverified quote</span>}
      </div>
      <Field label="What we found">
        <blockquote>{finding.evidence}</blockquote>
      </Field>
      <Field label="Why this matters">{finding.reason}</Field>
      {finding.benign_explanation && (
        <Field label="Most likely innocent explanation">
          {finding.benign_explanation}
        </Field>
      )}
      {finding.recommended_action && (
        <Field label="Recommended next step">{finding.recommended_action}</Field>
      )}
    </div>
  )
}

export default function CandidateAuditPage() {
  const { runId, candidateId } = useParams()
  const [audit, setAudit] = useState<UnifiedCandidateAudit | null>(null)
  const [resume, setResume] = useState('')
  const [calls, setCalls] = useState<AgentRun[]>([])
  const [showCalls, setShowCalls] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .getScreeningResult(Number(runId), candidateId!)
      .then((a) => {
        setAudit(a)
        return api.getCandidate(Number(a.candidate_id))
      })
      .then((c) => setResume(c.resume_text))
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : 'Failed to load the audit'),
      )
    api
      .listResultAgentRuns(Number(runId), candidateId!)
      .then(setCalls)
      .catch(() => setCalls([]))
  }, [runId, candidateId])

  const manipulationPresent = useMemo(
    () =>
      !!audit &&
      audit.findings.some((f) => MANIPULATION_CATEGORIES.includes(f.category)),
    [audit],
  )

  if (error) return <div className="banner banner-error">{error}</div>
  if (!audit) return <div className="empty">Loading…</div>

  const byAgent = (a: AgentName) => audit.findings.filter((f) => f.source === a)
  const primaryQuote = audit.findings[0]?.evidence ?? ''

  return (
    <div className="page">
      <p>
        <Link to={`/screening/runs/${audit.run_id}`}>← back to the run</Link>
      </p>
      <h1>{audit.candidate_name}</h1>
      <p className="muted">
        {audit.status === 'error' ? (
          <>Could not screen: {audit.error}</>
        ) : (
          <>
            {audit.summary} — screened with{' '}
            {Object.values(audit.models).join(' + ') || 'the stub pipeline'}
          </>
        )}
      </p>
      {audit.degraded.length > 0 && (
        <div className="banner">
          Assembled without the model for: {audit.degraded.join(', ')}. The
          deterministic pre-scan still ran.
        </div>
      )}

      <ManipulationBanner present={manipulationPresent} />

      {audit.status === 'screened' && (
        <div className="audit-layout">
          <div>
            {AGENTS.map((a) => {
              const items = byAgent(a)
              return (
                <section key={a} className="agent-section">
                  <h2>{AGENT_LABEL[a]}</h2>
                  {items.length === 0 ? (
                    <p className="no-concern">No concerns found</p>
                  ) : (
                    items.map((f, i) => (
                      <FindingCard key={f.id ?? i} finding={f} />
                    ))
                  )}
                </section>
              )
            })}
          </div>
          <aside className="resume-pane">
            <h3>Résumé</h3>
            {resume ? highlight(resume, primaryQuote) : <p>Loading…</p>}
          </aside>
        </div>
      )}

      {calls.length > 0 && (
        <section className="agent-section">
          <button className="link-btn" onClick={() => setShowCalls((v) => !v)}>
            {showCalls ? '▾' : '▸'} Model calls ({calls.length}) — the exact
            request sent to each agent and its reply
          </button>
          {showCalls && (
            <>
              <AgentLegend />
              <AgentRunTable rows={calls} showCandidate={false} />
            </>
          )}
        </section>
      )}
    </div>
  )
}
