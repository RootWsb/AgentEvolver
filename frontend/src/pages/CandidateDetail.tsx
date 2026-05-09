import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  GitBranch,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertCircle,
  Sparkles,
  FileText,
} from 'lucide-react'
import { api } from '../api'
import { Candidate, DiffResponse } from '../types'
import DiffViewer from '../components/DiffViewer'
import StatusPill from '../components/StatusPill'
import { cn } from '../lib/utils'

export default function CandidateDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [candidate, setCandidate] = useState<Candidate | null>(null)
  const [diff, setDiff] = useState<DiffResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [rejectReason, setRejectReason] = useState('')
  const [showRejectForm, setShowRejectForm] = useState(false)

  useEffect(() => {
    if (!id) return
    Promise.all([api.getCandidate(id), api.getDiff(id)])
      .then(([c, d]) => {
        setCandidate(c)
        setDiff(d)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [id])

  const handleApprove = async () => {
    if (!id || !candidate) return
    setActionLoading(true)
    try {
      await api.approve(id)
      const updated = await api.getCandidate(id)
      setCandidate(updated)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  const handleReject = async () => {
    if (!id || !candidate || !rejectReason.trim()) return
    setActionLoading(true)
    try {
      await api.reject(id, rejectReason)
      const updated = await api.getCandidate(id)
      setCandidate(updated)
      setShowRejectForm(false)
    } catch (err: any) {
      setError(err.message)
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-3">
        <Loader2 size={20} strokeWidth={1.5} className="text-t-tertiary animate-spin" />
        <span className="text-sm text-t-secondary">加载候选详情...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-panel rounded-lg border border-s-error p-4">
        <div className="flex items-center gap-2">
          <AlertCircle size={16} strokeWidth={1.5} className="text-s-error" />
          <span className="text-sm text-s-error font-medium">加载失败</span>
        </div>
        <div className="text-[12px] text-t-secondary mt-1">{error}</div>
      </div>
    )
  }

  if (!candidate || !diff) return null

  const isPending = candidate.status === 'pending' || candidate.status === 'auto_validated'
  const confidence = Math.round(candidate.confidence_score * 100)

  const evoLabel: Record<string, string> = {
    fix: '修复',
    captured: '捕获',
    derived: '衍生',
  }

  return (
    <div className="space-y-6 anim-fade-in max-w-4xl">
      {/* Back */}
      <button
        onClick={() => navigate(-1)}
        className="inline-flex items-center gap-1.5 text-[12px] text-t-secondary hover:text-t-primary transition-colors"
      >
        <ArrowLeft size={14} strokeWidth={1.5} />
        返回列表
      </button>

      {/* Header Card */}
      <div className="bg-panel rounded-lg border border-b-color overflow-hidden">
        <div className="px-5 py-4 border-b border-b-divider">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h1 className="text-lg font-semibold text-t-primary truncate">
                {candidate.skill_name}
              </h1>
              <div className="flex items-center gap-2 mt-1.5">
                <GitBranch size={12} strokeWidth={1.5} className="text-t-tertiary" />
                <span className="text-[12px] text-t-tertiary font-mono">
                  v{candidate.version}
                </span>
                <span className="text-[12px] text-t-tertiary">·</span>
                <span className="text-[12px] text-t-tertiary font-mono">
                  {candidate.candidate_id.slice(0, 12)}
                </span>
              </div>
            </div>
            <StatusPill status={candidate.status} />
          </div>
        </div>

        <div className="px-5 py-4 space-y-4">
          {/* Meta grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <MetaItem label="进化类型" value={evoLabel[candidate.evolution_type] || candidate.evolution_type} />
            <MetaItem label="置信度" value={`${confidence}%`} />
            <MetaItem label="创建时间" value={new Date(candidate.created_at).toLocaleString('zh-CN')} />
            <MetaItem label="文件数" value={`${diff.files.length + diff.new_files.length} 个`} />
          </div>

          {/* Confidence bar */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[11px] text-t-secondary">置信度评分</span>
              <span className="text-[11px] font-mono text-t-secondary">{confidence}%</span>
            </div>
            <div className="h-1.5 bg-input rounded-full overflow-hidden">
              <div
                className={cn(
                  'h-full rounded-full transition-all',
                  confidence >= 80 ? 'bg-s-running' :
                  confidence >= 50 ? 'bg-s-pending' : 'bg-s-error',
                )}
                style={{ width: `${confidence}%` }}
              />
            </div>
          </div>

          {/* Reason */}
          {candidate.reason && (
            <div>
              <div className="flex items-center gap-1.5 mb-1.5">
                <Sparkles size={12} strokeWidth={1.5} className="text-t-tertiary" />
                <span className="text-[11px] text-t-secondary font-medium">进化原因</span>
              </div>
              <p className="text-[13px] text-t-secondary bg-hover/50 rounded-md p-3 leading-relaxed">
                {candidate.reason}
              </p>
            </div>
          )}

          {/* Cross-session validation */}
          {candidate.cross_session_validation && candidate.cross_session_validation.similar_sessions_found > 0 && (
            <div className="bg-a-link/5 border border-a-link/10 rounded-md p-3">
              <div className="flex items-center gap-1.5 mb-1">
                <FileText size={12} strokeWidth={1.5} className="text-a-link" />
                <span className="text-[11px] font-medium text-a-link">跨会话验证</span>
              </div>
              <div className="text-[12px] text-t-secondary space-y-0.5">
                <div>
                  发现 {candidate.cross_session_validation.similar_sessions_found} 个相似会话
                </div>
                {candidate.cross_session_validation.statistical_confidence_boost > 0 && (
                  <div>
                    统计置信度提升:
                    {' '}
                    <span className="font-mono text-s-running">
                      +{Math.round(candidate.cross_session_validation.statistical_confidence_boost * 100)}%
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Actions */}
          {isPending && (
            <div className="flex gap-3 pt-2">
              <button
                onClick={handleApprove}
                disabled={actionLoading}
                className={cn(
                  'inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors',
                  'bg-s-running text-t-inverse hover:bg-s-running/90',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                {actionLoading ? (
                  <Loader2 size={14} strokeWidth={1.5} className="animate-spin" />
                ) : (
                  <CheckCircle2 size={14} strokeWidth={1.5} />
                )}
                {actionLoading ? '处理中...' : '通过并发布'}
              </button>
              <button
                onClick={() => setShowRejectForm(true)}
                disabled={actionLoading}
                className={cn(
                  'inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors',
                  'bg-s-error text-t-inverse hover:bg-s-error/90',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                )}
              >
                <XCircle size={14} strokeWidth={1.5} />
                拒绝
              </button>
            </div>
          )}

          {/* Reject form */}
          {showRejectForm && (
            <div className="bg-hover/50 border border-b-color rounded-md p-4 space-y-3">
              <label className="block text-[12px] font-medium text-t-secondary">
                拒绝原因
              </label>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                className={cn(
                  'w-full bg-panel border border-b-color rounded-md px-3 py-2 text-sm text-t-primary',
                  'placeholder:text-t-tertiary',
                  'focus:outline-none focus:border-t-secondary transition-colors resize-none',
                )}
                rows={3}
                placeholder="请输入拒绝此候选的原因..."
              />
              <div className="flex gap-2">
                <button
                  onClick={handleReject}
                  disabled={actionLoading || !rejectReason.trim()}
                  className={cn(
                    'inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors',
                    'bg-s-error text-t-inverse hover:bg-s-error/90',
                    'disabled:opacity-50 disabled:cursor-not-allowed',
                  )}
                >
                  {actionLoading && <Loader2 size={14} strokeWidth={1.5} className="animate-spin" />}
                  确认拒绝
                </button>
                <button
                  onClick={() => {
                    setShowRejectForm(false)
                    setRejectReason('')
                  }}
                  className={cn(
                    'inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors',
                    'bg-hover text-t-secondary hover:text-t-primary',
                  )}
                >
                  取消
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Diff Section */}
      <div>
        <div className="flex items-center gap-2 mb-4">
          <FileText size={16} strokeWidth={1.5} className="text-t-secondary" />
          <h2 className="text-base font-semibold text-t-primary">变更对比</h2>
        </div>
        <DiffViewer diff={diff} />
      </div>
    </div>
  )
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] text-t-tertiary uppercase tracking-wide mb-0.5">{label}</div>
      <div className="text-[13px] text-t-primary font-medium">{value}</div>
    </div>
  )
}
