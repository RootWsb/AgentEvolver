import { useEffect, useState } from 'react'
import { Search, Filter, Inbox, Loader2 } from 'lucide-react'
import { api } from '../api'
import { Candidate } from '../types'
import CandidateCard from '../components/CandidateCard'
import { cn } from '../lib/utils'

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'pending', label: '待审核' },
  { value: 'auto_validated', label: '自动验证' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已拒绝' },
  { value: 'published', label: '已发布' },
]

export default function CandidateList() {
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  useEffect(() => {
    api
      .listCandidates({ status: statusFilter || undefined, limit: 200 })
      .then((data) => {
        setCandidates(data)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [statusFilter])

  const filtered = candidates.filter(
    (c) =>
      c.skill_name.toLowerCase().includes(filter.toLowerCase()) ||
      c.candidate_id.toLowerCase().includes(filter.toLowerCase()),
  )

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-3">
        <Loader2 size={20} strokeWidth={1.5} className="text-t-tertiary animate-spin" />
        <span className="text-sm text-t-secondary">加载候选列表...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-panel rounded-lg border border-s-error p-4">
        <div className="text-sm text-s-error font-medium">加载失败</div>
        <div className="text-[12px] text-t-secondary mt-1">{error}</div>
      </div>
    )
  }

  return (
    <div className="anim-fade-in">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-t-primary">候选列表</h1>
        <p className="text-[12px] text-t-secondary mt-0.5">
          查看和管理所有进化产生的候选技能
        </p>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-col sm:flex-row gap-3">
        <div className="flex-1 relative">
          <Search
            size={14}
            strokeWidth={1.5}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-t-tertiary pointer-events-none"
          />
          <input
            type="text"
            placeholder="搜索技能名称或 ID..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className={cn(
              'w-full bg-input border border-b-color rounded-md pl-9 pr-3 py-2 text-sm text-t-primary',
              'placeholder:text-t-tertiary',
              'focus:outline-none focus:border-t-secondary transition-colors',
            )}
          />
        </div>
        <div className="relative">
          <Filter
            size={14}
            strokeWidth={1.5}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-t-tertiary pointer-events-none"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className={cn(
              'bg-input border border-b-color rounded-md pl-9 pr-8 py-2 text-sm text-t-primary',
              'focus:outline-none focus:border-t-secondary transition-colors appearance-none',
            )}
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Count */}
      <div className="mb-4 text-[12px] text-t-tertiary">
        共 {filtered.length} 个候选
        {filtered.length !== candidates.length && (
          <span>（筛选自 {candidates.length} 个）</span>
        )}
      </div>

      {/* Grid */}
      {filtered.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((candidate) => (
            <CandidateCard key={candidate.candidate_id} candidate={candidate} />
          ))}
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <Inbox size={32} strokeWidth={1.5} className="text-t-tertiary mb-3" />
          <div className="text-sm text-t-secondary">未找到候选</div>
          <div className="text-[12px] text-t-tertiary mt-1">
            {filter || statusFilter
              ? '尝试调整搜索条件或筛选器'
              : '暂无候选技能，等待进化引擎产生'}
          </div>
        </div>
      )}
    </div>
  )
}
