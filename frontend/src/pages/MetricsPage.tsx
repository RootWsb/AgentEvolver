import { useEffect, useState } from 'react'
import {
  Clock,
  Activity,
  CheckCircle2,
  XCircle,
  Loader2,
  Zap,
  GitBranch,
  TrendingUp,
  BarChart3,
  AlertCircle,
} from 'lucide-react'
import { api } from '../api'
import { MetricSummary, StatsResponse } from '../types'
import { cn } from '../lib/utils'

const HOUR_OPTIONS = [
  { value: 1, label: '最近 1 小时' },
  { value: 6, label: '最近 6 小时' },
  { value: 24, label: '最近 24 小时' },
  { value: 72, label: '最近 3 天' },
  { value: 168, label: '最近 7 天' },
]

export default function MetricsPage() {
  const [metrics, setMetrics] = useState<MetricSummary | null>(null)
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [hours, setHours] = useState(24)

  useEffect(() => {
    Promise.all([api.getMetrics(hours), api.getStats()])
      .then(([m, s]) => {
        setMetrics(m)
        setStats(s)
        setLoading(false)
      })
      .catch((err) => {
        setError(err.message)
        setLoading(false)
      })
  }, [hours])

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-32 gap-3">
        <Loader2 size={20} strokeWidth={1.5} className="text-t-tertiary animate-spin" />
        <span className="text-sm text-t-secondary">加载指标数据...</span>
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

  const successRate =
    metrics && metrics.total_sessions > 0
      ? Math.round((metrics.completed_sessions / metrics.total_sessions) * 100)
      : 0

  return (
    <div className="space-y-6 anim-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-t-primary">指标统计</h1>
          <p className="text-[12px] text-t-secondary mt-0.5">
            系统运行状态和进化效率概览
          </p>
        </div>
        <div className="relative">
          <Clock
            size={14}
            strokeWidth={1.5}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-t-tertiary pointer-events-none"
          />
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className={cn(
              'bg-panel border border-b-color rounded-md pl-9 pr-8 py-2 text-sm text-t-primary',
              'focus:outline-none focus:border-t-secondary transition-colors appearance-none',
            )}
          >
            {HOUR_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          icon={<Activity size={16} strokeWidth={1.5} />}
          title="总会话数"
          value={metrics?.total_sessions ?? 0}
          subtitle={`${metrics?.completed_sessions ?? 0} 完成 · ${metrics?.failed_sessions ?? 0} 失败`}
          accent="a-link"
        />
        <MetricCard
          icon={<TrendingUp size={16} strokeWidth={1.5} />}
          title="成功率"
          value={`${successRate}%`}
          subtitle={metrics && metrics.total_sessions > 0 ? '基于总会话计算' : '暂无数据'}
          accent="s-running"
        />
        <MetricCard
          icon={<Zap size={16} strokeWidth={1.5} />}
          title="总 Token 消耗"
          value={(metrics?.total_tokens ?? 0).toLocaleString()}
          subtitle="所有会话累计"
          accent="s-pending"
        />
        <MetricCard
          icon={<GitBranch size={16} strokeWidth={1.5} />}
          title="待审核候选"
          value={stats?.pending ?? 0}
          subtitle={`${stats?.total ?? 0} 个候选总计`}
          accent="s-waiting"
        />
      </div>

      {/* Status Breakdown */}
      <div className="bg-panel rounded-lg border border-b-color overflow-hidden">
        <div className="px-5 py-4 border-b border-b-divider">
          <div className="flex items-center gap-2">
            <BarChart3 size={16} strokeWidth={1.5} className="text-t-secondary" />
            <h2 className="text-base font-semibold text-t-primary">候选状态分布</h2>
          </div>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4">
            <StatusCount
              icon={<Clock size={16} strokeWidth={1.5} />}
              label="待审核"
              count={stats?.pending ?? 0}
              color="text-s-pending"
              bg="bg-s-pending/10"
            />
            <StatusCount
              icon={<CheckCircle2 size={16} strokeWidth={1.5} />}
              label="自动验证"
              count={stats?.approved ?? 0}
              color="text-a-link"
              bg="bg-a-link/10"
            />
            <StatusCount
              icon={<CheckCircle2 size={16} strokeWidth={1.5} />}
              label="已通过"
              count={stats?.approved ?? 0}
              color="text-s-running"
              bg="bg-s-running/10"
            />
            <StatusCount
              icon={<XCircle size={16} strokeWidth={1.5} />}
              label="已拒绝"
              count={stats?.rejected ?? 0}
              color="text-s-error"
              bg="bg-s-error/10"
            />
            <StatusCount
              icon={<GitBranch size={16} strokeWidth={1.5} />}
              label="已发布"
              count={stats?.published ?? 0}
              color="text-s-waiting"
              bg="bg-s-waiting/10"
            />
          </div>
        </div>
      </div>

      {/* Period Summary */}
      <div className="bg-panel rounded-lg border border-b-color overflow-hidden">
        <div className="px-5 py-4 border-b border-b-divider">
          <h2 className="text-base font-semibold text-t-primary">周期概览</h2>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-center">
            <div>
              <div className="text-2xl font-semibold text-t-primary">
                {metrics?.total_sessions ?? 0}
              </div>
              <div className="text-[12px] text-t-secondary mt-1">总会话</div>
            </div>
            <div>
              <div className="text-2xl font-semibold text-s-running">
                {metrics?.completed_sessions ?? 0}
              </div>
              <div className="text-[12px] text-t-secondary mt-1">成功会话</div>
            </div>
            <div>
              <div className="text-2xl font-semibold text-s-error">
                {metrics?.failed_sessions ?? 0}
              </div>
              <div className="text-[12px] text-t-secondary mt-1">失败会话</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function MetricCard({
  icon,
  title,
  value,
  subtitle,
  accent,
}: {
  icon: React.ReactNode
  title: string
  value: string | number
  subtitle: string
  accent: string
}) {
  return (
    <div className="bg-panel rounded-lg border border-b-color p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className={cn('text-t-tertiary', accent.replace('bg-', 'text-').replace('/10', ''))}>
          {icon}
        </span>
        <span className="text-[11px] text-t-tertiary uppercase tracking-wide">{title}</span>
      </div>
      <div className="text-2xl font-semibold text-t-primary">{value}</div>
      <div className="text-[12px] text-t-secondary mt-1">{subtitle}</div>
    </div>
  )
}

function StatusCount({
  icon,
  label,
  count,
  color,
  bg,
}: {
  icon: React.ReactNode
  label: string
  count: number
  color: string
  bg: string
}) {
  return (
    <div className={cn('rounded-md p-3 text-center', bg)}>
      <div className={cn('flex justify-center mb-1', color)}>{icon}</div>
      <div className={cn('text-xl font-semibold', color)}>{count}</div>
      <div className="text-[11px] text-t-secondary mt-0.5">{label}</div>
    </div>
  )
}
