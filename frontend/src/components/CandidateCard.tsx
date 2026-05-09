import { Link } from 'react-router-dom'
import { ArrowRight, GitBranch } from 'lucide-react'
import { Candidate } from '../types'
import StatusPill from './StatusPill'
import { cn } from '../lib/utils'

interface Props {
  candidate: Candidate
}

function evolutionBadge(type: string): { bg: string; text: string; label: string } {
  switch (type) {
    case 'fix':
      return { bg: 'bg-s-error/10', text: 'text-s-error', label: '修复' }
    case 'captured':
      return { bg: 'bg-a-link/10', text: 'text-a-link', label: '捕获' }
    case 'derived':
      return { bg: 'bg-s-waiting/10', text: 'text-s-waiting', label: '衍生' }
    default:
      return { bg: 'bg-t-tertiary/10', text: 'text-t-tertiary', label: type }
  }
}

export default function CandidateCard({ candidate }: Props) {
  const evo = evolutionBadge(candidate.evolution_type)
  const confidence = Math.round(candidate.confidence_score * 100)

  return (
    <Link
      to={`/candidate/${candidate.candidate_id}`}
      className={cn(
        'block bg-panel rounded-lg border border-b-color p-5',
        'hover:border-b-color/80 transition-colors',
        'anim-fade-in',
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-t-primary truncate">
            {candidate.skill_name}
          </h3>
          <div className="flex items-center gap-1.5 mt-1">
            <GitBranch size={12} strokeWidth={1.5} className="text-t-tertiary" />
            <span className="text-[12px] text-t-tertiary font-mono">
              v{candidate.version}
            </span>
          </div>
        </div>
        <StatusPill status={candidate.status} />
      </div>

      {/* Meta */}
      <div className="flex items-center gap-2 mb-3">
        <span className={cn('text-[11px] px-2 py-0.5 rounded-full font-medium', evo.bg, evo.text)}>
          {evo.label}
        </span>
        <span className="text-[11px] text-t-tertiary font-mono">
          {confidence}% 置信度
        </span>
      </div>

      {/* Confidence bar */}
      <div className="flex items-center gap-2 mb-3">
        <div className="flex-1 h-1.5 bg-input rounded-full overflow-hidden">
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

      {/* Footer */}
      <div className="flex items-center justify-between">
        {candidate.reason ? (
          <p className="text-[12px] text-t-secondary line-clamp-2 flex-1 mr-3">
            {candidate.reason}
          </p>
        ) : (
          <span className="text-[12px] text-t-tertiary flex-1">无描述</span>
        )}
        <ArrowRight size={14} strokeWidth={1.5} className="text-t-tertiary shrink-0" />
      </div>

      {/* Cross-session badge */}
      {candidate.cross_session_validation && candidate.cross_session_validation.similar_sessions_found > 0 && (
        <div className="mt-3 pt-3 border-t border-b-divider">
          <span className="text-[11px] text-a-link">
            跨会话验证: {candidate.cross_session_validation.similar_sessions_found} 个相似会话
          </span>
        </div>
      )}
    </Link>
  )
}
