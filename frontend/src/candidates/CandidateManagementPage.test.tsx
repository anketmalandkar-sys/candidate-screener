import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import CandidateManagementPage from './CandidateManagementPage'
import { api } from '../api'
import type { CandidatePoolItem } from './types'

vi.mock('../api', () => ({
  api: {
    listCandidates: vi.fn(),
    getCandidate: vi.fn(),
    createCandidate: vi.fn(),
    uploadCandidate: vi.fn(),
    deleteCandidate: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

function candidate(id: number, name: string, email: string | null): CandidatePoolItem {
  return {
    id,
    name,
    email,
    source: 'paste',
    original_filename: null,
    created_at: '2026-02-01T00:00:00Z',
  }
}

const priya = candidate(10, 'Priya Nair', null)
const sam = candidate(11, 'Sam Okafor', 'sam@example.com')

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.listCandidates.mockResolvedValue({
    items: [sam, priya],
    total: 2,
    limit: 20,
    offset: 0,
  })
  mockedApi.deleteCandidate.mockResolvedValue(undefined)
  mockedApi.createCandidate.mockResolvedValue(candidate(99, 'New Person', null))
  mockedApi.getCandidate.mockResolvedValue({
    ...priya,
    resume_text: 'Six years of Python and Postgres.',
  })
})

const rowFor = (name: string) => screen.getByText(name).closest('li') as HTMLElement

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/candidates']}>
      <CandidateManagementPage />
    </MemoryRouter>,
  )
}

test('lists candidate names and emails as text', async () => {
  renderPage()
  await screen.findByText('Priya Nair')

  expect(within(rowFor('Sam Okafor')).getByText(/sam@example.com/)).toBeInTheDocument()
  expect(within(rowFor('Priya Nair')).getByText(/no email/)).toBeInTheDocument()
})

test('"View résumé" opens a modal with the résumé text', async () => {
  const user = userEvent.setup()
  renderPage()
  await screen.findByText('Priya Nair')

  await user.click(within(rowFor('Priya Nair')).getByRole('button', { name: /View résumé/ }))

  const dialog = await screen.findByRole('dialog')
  expect(mockedApi.getCandidate).toHaveBeenCalledWith(10)
  expect(within(dialog).getByText('Six years of Python and Postgres.')).toBeInTheDocument()
  expect(within(dialog).getByRole('heading', { name: 'Priya Nair' })).toBeInTheDocument()

  await user.click(within(dialog).getByRole('button', { name: 'Close' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('the résumé cannot be edited (no textarea in the modal)', async () => {
  const user = userEvent.setup()
  renderPage()
  await screen.findByText('Priya Nair')

  await user.click(within(rowFor('Priya Nair')).getByRole('button', { name: /View résumé/ }))
  const dialog = await screen.findByRole('dialog')

  expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument()
})

test('deleting a candidate confirms, calls the API and reloads', async () => {
  const user = userEvent.setup()
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
  renderPage()
  await screen.findByText('Priya Nair')

  await user.click(within(rowFor('Priya Nair')).getByRole('button', { name: 'Delete' }))

  expect(confirm).toHaveBeenCalled()
  expect(mockedApi.deleteCandidate).toHaveBeenCalledWith(10)
  expect(mockedApi.listCandidates).toHaveBeenCalledTimes(2)
  confirm.mockRestore()
})

test('paginates: Next asks for the following page', async () => {
  const user = userEvent.setup()
  const many = Array.from({ length: 20 }, (_, i) => candidate(i + 1, `Person ${i + 1}`, null))
  mockedApi.listCandidates.mockResolvedValue({
    items: many,
    total: 42,
    limit: 20,
    offset: 0,
  })
  renderPage()
  await screen.findByText('Person 1')

  await user.click(screen.getByRole('button', { name: 'Next' }))

  expect(mockedApi.listCandidates).toHaveBeenLastCalledWith({ offset: 20, limit: 20 })
})

test('the name search filters the visible rows', async () => {
  const user = userEvent.setup()
  renderPage()
  await screen.findByText('Priya Nair')

  await user.type(screen.getByLabelText('Search by name'), 'sam')

  expect(screen.getByText('Sam Okafor')).toBeInTheDocument()
  expect(screen.queryByText('Priya Nair')).not.toBeInTheDocument()
})

test('the add form creates a pool candidate and reloads', async () => {
  const user = userEvent.setup()
  renderPage()
  await screen.findByText('Priya Nair')

  await user.click(screen.getByRole('button', { name: 'New candidate' }))
  await user.type(screen.getByLabelText('Candidate name'), 'New Person')
  await user.type(screen.getByLabelText('Resume text'), 'React and TypeScript')
  await user.click(screen.getByRole('button', { name: 'Add to pool' }))

  expect(mockedApi.createCandidate).toHaveBeenCalledWith('New Person', 'React and TypeScript')
  expect(mockedApi.listCandidates).toHaveBeenCalledTimes(2)
})

test('the add form is hidden until "New candidate" is clicked, and closes after adding', async () => {
  const user = userEvent.setup()
  renderPage()
  await screen.findByText('Priya Nair')

  expect(screen.queryByLabelText('Candidate name')).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'New candidate' }))
  expect(screen.getByLabelText('Candidate name')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'New candidate' })).not.toBeInTheDocument()

  await user.type(screen.getByLabelText('Candidate name'), 'New Person')
  await user.type(screen.getByLabelText('Resume text'), 'React and TypeScript')
  await user.click(screen.getByRole('button', { name: 'Add to pool' }))

  await screen.findByRole('button', { name: 'New candidate' })
  expect(screen.queryByLabelText('Candidate name')).not.toBeInTheDocument()
})

test('"Cancel" closes the add form without adding', async () => {
  const user = userEvent.setup()
  renderPage()
  await screen.findByText('Priya Nair')

  await user.click(screen.getByRole('button', { name: 'New candidate' }))
  await user.click(screen.getByRole('button', { name: 'Cancel' }))

  expect(screen.queryByLabelText('Candidate name')).not.toBeInTheDocument()
  expect(mockedApi.createCandidate).not.toHaveBeenCalled()
})
