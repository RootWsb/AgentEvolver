export interface CrossSessionValidation {
  similar_sessions_found: number
  recurring_patterns: Record<string, unknown>[]
  statistical_confidence_boost: number
}

export interface Candidate {
  candidate_id: string
  skill_name: string
  version: number
  status: string
  evolution_type: string
  confidence_score: number
  reason: string | null
  created_at: string
  skill_dir_path: string
  cross_session_validation?: CrossSessionValidation | null
}

export interface DiffFile {
  filename: string
  status: 'modified' | 'added' | 'removed'
  diff: string
  added_lines: number
  removed_lines: number
}

export interface DiffResponse {
  skill_name: string
  production_dir: string
  candidate_dir: string
  files: DiffFile[]
  new_files: { filename: string; content: string; line_count: number }[]
  removed_files: { filename: string }[]
}

export interface MetricSummary {
  period_hours: number
  total_sessions: number
  completed_sessions: number
  failed_sessions: number
  total_tokens: number
}

export interface StatsResponse {
  pending: number
  approved: number
  rejected: number
  published: number
  total: number
}
