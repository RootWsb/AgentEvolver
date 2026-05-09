import { cn } from '../lib/utils'

interface Props {
  status: string
  className?: string
}

const statusMap: Record<string, { bg: string; text: string; label: string }> = {
  pending:        { bg: 'bg-s-pending/15',    text: 'text-s-pending',    label: '待处理' },
  auto_validated: { bg: 'bg-s-waiting/15',    text: 'text-s-waiting',    label: '已验证' },
  approved:       { bg: 'bg-s-running/15',    text: 'text-s-running',    label: '已批准' },
  rejected:       { bg: 'bg-s-error/15',      text: 'text-s-error',      label: '已拒绝' },
  published:      { bg: 'bg-a-link/15',       text: 'text-a-link',       label: '已发布' },
  running:        { bg: 'bg-s-running/15',    text: 'text-s-running',    label: '运行中' },
  stopped:        { bg: 'bg-s-stopped/15',    text: 'text-s-stopped',    label: '已停止' },
  error:          { bg: 'bg-s-error/15',      text: 'text-s-error',      label: '错误' },
  waiting:        { bg: 'bg-s-waiting/15',    text: 'text-s-waiting',    label: '等待中' },
}

export default function StatusPill({ status, className }: Props) {
  const mapped = statusMap[status.toLowerCase()] || {
    bg: 'bg-t-tertiary/10',
    text: 'text-t-tertiary',
    label: status,
  }

  return (
    <span
      className={cn(
        'inline-flex items-center justify-center rounded-full px-2.5 py-0.5 text-[12px] font-medium min-w-[64px]',
        mapped.bg,
        mapped.text,
        className,
      )}
    >
      {mapped.label}
    </span>
  )
}
