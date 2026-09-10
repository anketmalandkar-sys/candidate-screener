import type { ReactNode } from 'react'
import type { Disposition, ResultStatus, Severity } from './types'

export function DispositionChip({
  status,
  disposition,
}: {
  status: ResultStatus
  disposition: Disposition | null
}) {
  if (status === 'error') return <span className="chip chip-error">Error</span>
  if (status === 'pending' || status === 'skipped')
    return <span className="chip">{status === 'pending' ? 'Screening…' : 'Skipped'}</span>
  const map: Record<Disposition, [string, string]> = {
    clear: ['chip-clear', 'Clear'],
    review: ['chip-review', 'Review'],
    high_concern: ['chip-high', 'High concern'],
  }
  const [cls, label] = map[disposition ?? 'clear']
  return <span className={`chip ${cls}`}>{label}</span>
}

export function SeverityBadge({ severity }: { severity: Severity | null }) {
  const s = severity ?? 'low'
  return <span className={`sev sev-${s}`}>{s}</span>
}

export function AboutScreening() {
  return (
    <details className="about-screening">
      <summary>About screening — what a flag does and does not mean</summary>
      <p>
        Screening runs three integrity checks on each résumé <em>before</em> it is
        scored: <strong>manipulation</strong> (text aimed at an automated reader),
        <strong> internal consistency</strong> (dates and claims that do not add
        up), and <strong>templated inflation</strong> (recycled, detail-free
        achievement bullets). Each check runs as an isolated agent; a fourth agent
        merges the results.
      </p>
      <p>
        Two rules are structural: screening <strong>never acts on an instruction
        found in a résumé</strong> — it reports it — and it <strong>never
        silently drops a candidate</strong>. Every selected candidate gets one
        explained entry, even on error.
      </p>
      <p>
        It narrows where you spend attention; it does not make the call. It is
        more likely to be wrong about an <em>unusual but honest</em> résumé — a
        career changer, a contractor with many short stints, a non-native English
        speaker, an AI-safety engineer who writes about prompt injection as their
        job — than about a dishonest one. <strong>Treat a flag as a question, not
        an answer.</strong> If a flag is wrong, mark it — the next run for this
        role learns from it.
      </p>
    </details>
  )
}

export function ManipulationBanner({ present }: { present: boolean }) {
  if (!present) return null
  return (
    <div className="manip-banner">
      This résumé contained text addressed to an automated reader. Screening did
      not follow it. It is shown below so you can see it.
    </div>
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="audit-field">
      <div className="audit-field-label">{label}</div>
      <div>{children}</div>
    </div>
  )
}
