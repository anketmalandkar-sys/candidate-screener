import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import RunDetailPage from './RunDetailPage'
import { api } from '../api'
import type { RunDetail } from './types'

vi.mock('../api', () => ({
  api: {
    getScreeningRun: vi.fn(),
    listRunAgentRuns: vi.fn().mockResolvedValue([]),
    listResultAgentRuns: vi.fn().mockResolvedValue([]),
  },
}))
const mockedApi = vi.mocked(api)

beforeEach(() => {
  mockedApi.listRunAgentRuns.mockResolvedValue([])
  mockedApi.listResultAgentRuns.mockResolvedValue([])
})

const run: RunDetail = {
  id: 7,
  role_id: 1,
  status: 'partial',
  provider: { detection: 'hf_inference', synthesis: 'openai' },
  models: {},
  counts: { total: 3, screened: 2, compromised: 1, errored: 1 },
  created_at: '2026-01-01T00:00:00Z',
  completed_at: '2026-01-01T00:01:00Z',
  results: [
    {
      candidate_id: '10',
      candidate_name: 'Clean Clara',
      status: 'screened',
      is_compromised: false,
      overall_disposition: 'clear',
      finding_count: 0,
    },
    {
      candidate_id: '11',
      candidate_name: 'Flagged Fred',
      status: 'screened',
      is_compromised: true,
      overall_disposition: 'high_concern',
      finding_count: 2,
    },
    {
      candidate_id: '12',
      candidate_name: 'Broken Bob',
      status: 'error',
      is_compromised: false,
      overall_disposition: null,
      finding_count: 0,
    },
  ],
}

function renderAt() {
  return render(
    <MemoryRouter initialEntries={['/screening/runs/7']}>
      <Routes>
        <Route path="/screening/runs/:runId" element={<RunDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

it('renders every candidate row including error and high-concern', async () => {
  mockedApi.getScreeningRun.mockResolvedValue(run)
  renderAt()

  expect(await screen.findByText('Clean Clara')).toBeInTheDocument()
  expect(screen.getByText('Flagged Fred')).toBeInTheDocument()
  expect(screen.getByText('Broken Bob')).toBeInTheDocument()

  const table = screen.getByRole('table')
  expect(within(table).getByText('High concern')).toBeInTheDocument()
  expect(within(table).getByText('Error')).toBeInTheDocument()
  expect(within(table).getByText('Clear')).toBeInTheDocument()
  // three data rows — nothing filtered away
  expect(within(table).getAllByRole('row')).toHaveLength(1 + 3)
})

it('shows progress from the counts', async () => {
  mockedApi.getScreeningRun.mockResolvedValue(run)
  renderAt()
  expect(
    await screen.findByText(/3 \/ 3 screened · 1 with findings · 1 errored/),
  ).toBeInTheDocument()
})

it('shows the agent activity feed', async () => {
  mockedApi.getScreeningRun.mockResolvedValue(run)
  mockedApi.listRunAgentRuns.mockResolvedValue([
    {
      id: 1,
      candidate_id: '11',
      candidate_name: 'Flagged Fred',
      agent_name: 'synthesizer',
      tier: 'openai',
      model: 'gpt-4.1',
      parsed_ok: true,
      repair_attempts: 0,
      degraded: false,
      notes: null,
      latency_ms: 4200,
      input_chars: 1800,
      created_at: '2026-01-01T00:00:30Z',
    },
  ])
  renderAt()
  expect(await screen.findByText(/Agent activity/)).toBeInTheDocument()
  expect(screen.getByText('synthesizer')).toBeInTheDocument()
  expect(screen.getByText('4200 ms')).toBeInTheDocument()
})

it('paginates the results table at 25 rows a page', async () => {
  const many = {
    ...run,
    counts: { total: 60, screened: 60, compromised: 0, errored: 0 },
    results: Array.from({ length: 60 }, (_, i) => ({
      candidate_id: String(i),
      candidate_name: `Cand ${String(i).padStart(2, '0')}`,
      status: 'screened' as const,
      is_compromised: false,
      overall_disposition: 'clear' as const,
      finding_count: 0,
    })),
  }
  mockedApi.getScreeningRun.mockResolvedValue(many)
  renderAt()

  const table = await screen.findByRole('table')
  expect(within(table).getAllByRole('row')).toHaveLength(1 + 25)
  expect(screen.getByText('1–25 of 60')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Next' }))
  expect(screen.getByText('26–50 of 60')).toBeInTheDocument()
})
