import { candidatesApi } from './candidates/api'
import { screeningApi } from './screening/api'
import { json, request } from './client'
import type { Page, RequirementInput, RoleDetail, RoleSummary, User } from './types'

export { ApiError } from './client'

/** Auth and role/requirement management. */
const coreApi = {
  register: (email: string, name: string, password: string) =>
    json<User>('/api/auth/register', 'POST', { email, name, password }),

  login: (email: string, password: string) =>
    json<User>('/api/auth/login', 'POST', { email, password }),

  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),

  me: () => request<User>('/api/auth/me'),

  listRoles: (opts: { active?: boolean; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams()
    if (opts.active !== undefined) q.set('active', String(opts.active))
    if (opts.limit !== undefined) q.set('limit', String(opts.limit))
    if (opts.offset !== undefined) q.set('offset', String(opts.offset))
    const qs = q.toString()
    return request<Page<RoleSummary>>(`/api/roles${qs ? `?${qs}` : ''}`)
  },

  createRole: (title: string, description: string, requirements: RequirementInput[]) =>
    json<RoleDetail>('/api/roles', 'POST', { title, description, requirements }),

  getRole: (roleId: number) => request<RoleDetail>(`/api/roles/${roleId}`),

  updateRole: (
    roleId: number,
    patch: {
      title?: string
      description?: string
      is_active?: boolean
      requirements?: RequirementInput[]
    },
  ) => json<RoleDetail>(`/api/roles/${roleId}`, 'PATCH', patch),

  deleteRole: (roleId: number) =>
    request<void>(`/api/roles/${roleId}`, { method: 'DELETE' }),
}

/** The single API surface used across the app: core endpoints plus candidates. */
export const api = { ...coreApi, ...candidatesApi, ...screeningApi }
