import { Candidate, DiffResponse, MetricSummary, StatsResponse } from './types'

const API_BASE = '/api'

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw new Error(err.detail || `HTTP ${resp.status}`)
  }
  return resp.json()
}

export const api = {
  health: () => fetchJSON<{ status: string }>('/health'),

  listCandidates: (params?: { skill_name?: string; status?: string; limit?: number; offset?: number }) => {
    const search = new URLSearchParams()
    if (params?.skill_name) search.set('skill_name', params.skill_name)
    if (params?.status) search.set('status', params.status)
    if (params?.limit) search.set('limit', String(params.limit))
    if (params?.offset !== undefined) search.set('offset', String(params.offset))
    return fetchJSON<Candidate[]>(`/candidates?${search}`)
  },

  getCandidate: (id: string) => fetchJSON<Candidate>(`/candidates/${id}`),

  getDiff: (id: string) => fetchJSON<DiffResponse>(`/candidates/${id}/diff`),

  approve: (id: string, approverId = 'dashboard') =>
    fetchJSON<{ success: boolean; candidate_id: string }>(`/candidates/${id}/approve`, {
      method: 'POST',
      body: JSON.stringify({ approver_id: approverId }),
    }),

  reject: (id: string, reason: string, approverId = 'dashboard') =>
    fetchJSON<{ success: boolean; candidate_id: string }>(`/candidates/${id}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason, approver_id: approverId }),
    }),

  getMetrics: (hours = 24) => fetchJSON<MetricSummary>(`/metrics?hours=${hours}`),

  getStats: () => fetchJSON<StatsResponse>('/stats'),

  getVersions: (skill_name: string) => fetchJSON<Candidate[]>(`/skills/${skill_name}/versions`),
}
