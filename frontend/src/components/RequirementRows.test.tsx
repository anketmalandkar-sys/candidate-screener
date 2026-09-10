import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import RequirementRows from './RequirementRows'
import type { RequirementInput } from '../types'

/** A tiny controlled host so we can observe what RequirementRows emits. */
function Host({ initial = [] as RequirementInput[] }) {
  const [value, setValue] = useState<RequirementInput[]>(initial)
  return (
    <>
      <RequirementRows value={value} onChange={setValue} />
      <pre data-testid="state">{JSON.stringify(value)}</pre>
    </>
  )
}

const state = () => JSON.parse(screen.getByTestId('state').textContent || '[]')

test('Add requirement appends a blank must-have row', async () => {
  const user = userEvent.setup()
  render(<Host />)

  await user.click(screen.getByRole('button', { name: 'Add requirement' }))

  expect(state()).toEqual([{ label: '', weight: 'must', aliases: [] }])
})

test('typing a label, picking a weight and listing aliases is reflected in the value', async () => {
  const user = userEvent.setup()
  render(<Host initial={[{ label: '', weight: 'must', aliases: [] }]} />)

  await user.type(screen.getByRole('textbox', { name: 'Requirement 1' }), 'Kubernetes')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Weight 1' }), 'important')
  // Aliases are a comma-separated list; paste fires one change, the way a
  // recruiter actually fills this field.
  await user.click(screen.getByRole('textbox', { name: 'Also counts as 1' }))
  await user.paste('k8s, container orchestration')

  expect(state()).toEqual([
    { label: 'Kubernetes', weight: 'important', aliases: ['k8s', 'container orchestration'] },
  ])
})

test('removing a row drops it and reindexes the rest', async () => {
  const user = userEvent.setup()
  render(
    <Host
      initial={[
        { label: 'React', weight: 'must', aliases: [] },
        { label: 'Node', weight: 'nice', aliases: [] },
      ]}
    />,
  )

  await user.click(screen.getByRole('button', { name: 'Remove requirement 1' }))

  expect(state()).toEqual([{ label: 'Node', weight: 'nice', aliases: [] }])
  expect(screen.getByRole('textbox', { name: 'Requirement 1' })).toHaveValue('Node')
})
