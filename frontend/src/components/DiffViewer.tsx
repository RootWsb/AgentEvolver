import { DiffResponse } from '../types'
import { cn } from '../lib/utils'

interface Props {
  diff: DiffResponse
}

function highlightDiff(line: string): { content: string; className: string } {
  if (line.startsWith('+') && !line.startsWith('+++')) {
    return { content: line, className: 'bg-s-running/10 text-s-running' }
  }
  if (line.startsWith('-') && !line.startsWith('---')) {
    return { content: line, className: 'bg-s-error/10 text-s-error' }
  }
  if (line.startsWith('@@')) {
    return { content: line, className: 'text-a-link font-mono' }
  }
  return { content: line, className: 'text-t-secondary' }
}

export default function DiffViewer({ diff }: Props) {
  return (
    <div className="space-y-4">
      {diff.files.map((file) => (
        <div
          key={file.filename}
          className="bg-panel rounded-lg border border-b-color overflow-hidden"
        >
          <div className="bg-hover/50 px-3 py-2 flex items-center justify-between border-b border-b-divider">
            <span className="text-sm font-mono text-t-primary">{file.filename}</span>
            <div className="flex gap-3 text-[12px] font-mono">
              {file.added_lines > 0 && (
                <span className="text-s-running">+{file.added_lines}</span>
              )}
              {file.removed_lines > 0 && (
                <span className="text-s-error">-{file.removed_lines}</span>
              )}
            </div>
          </div>
          <div className="p-2 overflow-x-auto">
            <pre className="text-[12px] font-mono leading-relaxed">
              {file.diff.split('\n').map((line, i) => {
                const hl = highlightDiff(line)
                return (
                  <div key={i} className={cn(hl.className, 'px-1 rounded-sm')}>
                    {hl.content || ' '}
                  </div>
                )
              })}
            </pre>
          </div>
        </div>
      ))}

      {diff.new_files.map((file) => (
        <div
          key={file.filename}
          className="bg-panel rounded-lg border border-b-color overflow-hidden"
        >
          <div className="bg-hover/50 px-3 py-2 border-b border-b-divider">
            <span className="text-sm font-mono text-s-running">{file.filename} (新增)</span>
            <span className="text-[12px] text-t-tertiary ml-2">{file.line_count} 行</span>
          </div>
          <div className="p-2 overflow-x-auto">
            <pre className="text-[12px] font-mono text-t-secondary leading-relaxed">
              {file.content}
            </pre>
          </div>
        </div>
      ))}

      {diff.removed_files.map((file) => (
        <div
          key={file.filename}
          className="bg-panel rounded-lg border border-b-color overflow-hidden"
        >
          <div className="bg-hover/50 px-3 py-2 border-b border-b-divider">
            <span className="text-sm font-mono text-s-error">{file.filename} (已删除)</span>
          </div>
        </div>
      ))}

      {diff.files.length === 0 && diff.new_files.length === 0 && diff.removed_files.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="text-sm text-t-secondary">无差异</div>
          <div className="text-[12px] text-t-tertiary mt-1">
            候选版本与生产版本完全一致
          </div>
        </div>
      )}
    </div>
  )
}
