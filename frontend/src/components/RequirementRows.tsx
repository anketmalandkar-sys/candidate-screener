import type { RequirementInput, Weight } from '../types'
import { WEIGHT_LABEL, WEIGHT_ORDER } from '../types'

interface Props {
  value: RequirementInput[]
  onChange: (next: RequirementInput[]) => void
}

function blank(): RequirementInput {
  return { label: '', weight: 'must', aliases: [] }
}

/**
 * The must-have requirements grid: one row per requirement with a label, a
 * weight dropdown and a comma-separated "also counts as" list, plus add/remove.
 * Fully controlled — the parent owns the array and decides when to persist it.
 */
export default function RequirementRows({ value, onChange }: Props) {
  function update(index: number, patch: Partial<RequirementInput>) {
    onChange(value.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  }

  return (
    <div>
      <div className="req-row req-row-head">
        <div>Requirement</div>
        <div>Weight</div>
        <div>Also counts as</div>
        <div />
      </div>

      {value.map((item, index) => (
        <div className="req-row" key={index}>
          <input
            type="text"
            aria-label={`Requirement ${index + 1}`}
            value={item.label}
            placeholder="Python"
            onChange={(e) => update(index, { label: e.target.value })}
          />
          <select
            aria-label={`Weight ${index + 1}`}
            value={item.weight}
            onChange={(e) => update(index, { weight: e.target.value as Weight })}
          >
            {WEIGHT_ORDER.map((weight) => (
              <option key={weight} value={weight}>
                {WEIGHT_LABEL[weight]}
              </option>
            ))}
          </select>
          <input
            type="text"
            aria-label={`Also counts as ${index + 1}`}
            value={item.aliases.join(', ')}
            placeholder="k8s, container orchestration"
            onChange={(e) =>
              update(index, {
                aliases: e.target.value
                  .split(',')
                  .map((alias) => alias.trim())
                  .filter(Boolean),
              })
            }
          />
          <button
            className="danger"
            type="button"
            aria-label={`Remove requirement ${index + 1}`}
            title="Remove"
            onClick={() => onChange(value.filter((_, i) => i !== index))}
          >
            ×
          </button>
        </div>
      ))}

      <div className="hint" style={{ marginBottom: 12 }}>
        “Also counts as” is how you teach the matcher your vocabulary. Common
        synonyms like k8s → Kubernetes are already built in.
      </div>

      <button type="button" onClick={() => onChange([...value, blank()])}>
        Add requirement
      </button>
    </div>
  )
}
