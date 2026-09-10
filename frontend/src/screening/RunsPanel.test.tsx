import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import RunsPanel from './RunsPanel'
import { api } from '../api'
import type { RunSummary } from './types'

vi.mock('../api', () => ({ api: { listScreeningRuns: vi.fn() } }))
const mockedApi = vi.mocked(api)

const runs: RunSummary[] = [
  {
    id: 3,
    role_id: 1,
    status: 'complete',
    provider: { detection: 'stub', synthesis: 'stub' },
    models: {},
    counts: { total: 4, screened: 4, compromised: 2, errored: 0 },
    created_at: '2026-01-02T10:00:00Z',
    completed_at: '2026-01-02T10:01:00Z',
  },
]

it('lists past runs with a link into each', async () => {
  mockedApi.listScreeningRuns.mockResolvedValue({
    items: runs,
    total: 1,
    limit: 15,
    offset: 0,
  })
  render(
    <MemoryRouter>
      <RunsPanel />
    </MemoryRouter>,
  )
  expect(await screen.findByText('#3')).toBeInTheDocument()
  expect(screen.getByText('4 / 4')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute(
    'href',
    '/screening/runs/3',
  )
})

it('says so when there are no runs', async () => {
  mockedApi.listScreeningRuns.mockResolvedValue({
    items: [],
    total: 0,
    limit: 15,
    offset: 0,
  })
  render(
    <MemoryRouter>
      <RunsPanel />
    </MemoryRouter>,
  )
  expect(await screen.findByText('No screening runs yet.')).toBeInTheDocument()
})
