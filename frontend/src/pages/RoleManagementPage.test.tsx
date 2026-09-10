import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import RoleManagementPage from './RoleManagementPage'
import { api } from '../api'
import type { RoleDetail, RoleSummary } from '../types'

vi.mock('../api', () => ({
  api: {
    listRoles: vi.fn(),
    getRole: vi.fn(),
    createRole: vi.fn(),
    updateRole: vi.fn(),
    deleteRole: vi.fn(),
  },
}))

const mockedApi = vi.mocked(api)

const activeRole: RoleSummary = {
  id: 1,
  title: 'Still Hiring',
  description: 'Owns billing.',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  requirement_count: 2,
}

const inactiveRole: RoleSummary = {
  id: 2,
  title: 'Filled',
  description: '',
  is_active: false,
  created_at: '2026-01-02T00:00:00Z',
  requirement_count: 0,
}

const detailFor = (r: RoleSummary): RoleDetail => ({
  id: r.id,
  title: r.title,
  description: r.description,
  is_active: r.is_active,
  created_at: r.created_at,
  requirements: [],
})

beforeEach(() => {
  vi.clearAllMocks()
  mockedApi.listRoles.mockResolvedValue({
    items: [activeRole, inactiveRole],
    total: 2,
    limit: 20,
    offset: 0,
  })
  mockedApi.getRole.mockImplementation((id: number) =>
    Promise.resolve(detailFor(id === 1 ? activeRole : inactiveRole)),
  )
  mockedApi.createRole.mockResolvedValue(detailFor(activeRole))
  mockedApi.updateRole.mockResolvedValue(detailFor(activeRole))
  mockedApi.deleteRole.mockResolvedValue(undefined)
})

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/roles/manage']}>
      <RoleManagementPage />
    </MemoryRouter>,
  )
}

const rowFor = (title: string) => screen.getByText(title).closest('li') as HTMLElement

test('lists every role with its active/inactive status', async () => {
  renderPage()
  await screen.findByText('Still Hiring')

  expect(within(rowFor('Still Hiring')).getByText('Active')).toBeInTheDocument()
  expect(within(rowFor('Filled')).getByText('Inactive')).toBeInTheDocument()
})

test('creating a role sends title, description and requirements', async () => {
  const user = userEvent.setup()
  renderPage()
  await screen.findByText('Still Hiring')

  await user.click(screen.getByRole('button', { name: 'New role' }))
  await user.type(screen.getByLabelText('Title'), 'Platform Engineer')
  await user.type(screen.getByLabelText('Job description'), 'Runs the clusters.')
  await user.click(screen.getByRole('button', { name: 'Add requirement' }))
  await user.type(screen.getByRole('textbox', { name: 'Requirement 1' }), 'Kubernetes')
  await user.selectOptions(screen.getByRole('combobox', { name: 'Weight 1' }), 'important')

  await user.click(screen.getByRole('button', { name: 'Create role' }))

  expect(mockedApi.createRole).toHaveBeenCalledWith('Platform Engineer', 'Runs the clusters.', [
    { label: 'Kubernetes', weight: 'important', aliases: [] },
  ])
})

test('a title that already exists is not blocked before sending', async () => {
  const user = userEvent.setup()
  renderPage()
  await screen.findByText('Still Hiring')

  await user.click(screen.getByRole('button', { name: 'New role' }))
  await user.type(screen.getByLabelText('Title'), 'Still Hiring')
  await user.click(screen.getByRole('button', { name: 'Create role' }))

  expect(mockedApi.createRole).toHaveBeenCalledWith('Still Hiring', '', [])
})

test('editing a role prefills the form and PATCHes title, description and requirements', async () => {
  const user = userEvent.setup()
  renderPage()
  await screen.findByText('Still Hiring')

  await user.click(within(rowFor('Still Hiring')).getByRole('button', { name: 'Edit' }))

  const title = await screen.findByLabelText('Title')
  expect(title).toHaveValue('Still Hiring')

  await user.clear(title)
  await user.type(title, 'Staff Backend Engineer')
  await user.click(screen.getByRole('button', { name: 'Save role' }))

  expect(mockedApi.updateRole).toHaveBeenCalledWith(1, {
    title: 'Staff Backend Engineer',
    description: 'Owns billing.',
    requirements: [],
  })
})

test('deactivating an active role PATCHes is_active false and reloads the list', async () => {
  const user = userEvent.setup()
  renderPage()
  await screen.findByText('Still Hiring')

  await user.click(within(rowFor('Still Hiring')).getByRole('button', { name: 'Deactivate' }))

  expect(mockedApi.updateRole).toHaveBeenCalledWith(1, { is_active: false })
  expect(mockedApi.listRoles).toHaveBeenCalledTimes(2)
})

test('activating an inactive role PATCHes is_active true', async () => {
  const user = userEvent.setup()
  renderPage()
  await screen.findByText('Filled')

  await user.click(within(rowFor('Filled')).getByRole('button', { name: 'Activate' }))

  expect(mockedApi.updateRole).toHaveBeenCalledWith(2, { is_active: true })
})

test('paginates: Next asks for the following page', async () => {
  const user = userEvent.setup()
  const many = Array.from({ length: 20 }, (_, i) => ({
    ...activeRole,
    id: i + 1,
    title: `Role ${i + 1}`,
  }))
  mockedApi.listRoles.mockResolvedValue({
    items: many,
    total: 25,
    limit: 20,
    offset: 0,
  })
  renderPage()
  await screen.findByText('Role 1')

  await user.click(screen.getByRole('button', { name: 'Next' }))

  expect(mockedApi.listRoles).toHaveBeenLastCalledWith({ offset: 20, limit: 20 })
})

test('no pager when everything fits on one page', async () => {
  renderPage()
  await screen.findByText('Still Hiring')
  expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
})

test('deleting a role confirms, calls the API and reloads', async () => {
  const user = userEvent.setup()
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
  renderPage()
  await screen.findByText('Still Hiring')

  await user.click(within(rowFor('Still Hiring')).getByRole('button', { name: 'Delete' }))

  expect(confirm).toHaveBeenCalled()
  expect(mockedApi.deleteRole).toHaveBeenCalledWith(1)
  expect(mockedApi.listRoles).toHaveBeenCalledTimes(2)
  confirm.mockRestore()
})
