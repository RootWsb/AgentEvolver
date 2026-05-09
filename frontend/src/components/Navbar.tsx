import { Link, useLocation } from 'react-router-dom'
import { List, BarChart3 } from 'lucide-react'
import { cn } from '../lib/utils'

export default function Navbar() {
  const location = useLocation()
  const isActive = (path: string) => location.pathname === path

  const items = [
    { path: '/', label: '候选列表', icon: List },
    { path: '/metrics', label: '指标统计', icon: BarChart3 },
  ]

  return (
    <div className="flex flex-col gap-0.5 px-2">
      {items.map(({ path, label, icon: Icon }) => (
        <Link
          key={path}
          to={path}
          className={cn(
            'flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors',
            isActive(path)
              ? 'font-medium text-t-primary bg-hover'
              : 'text-t-secondary hover:text-t-primary hover:bg-hover',
          )}
        >
          <Icon size={16} strokeWidth={1.5} />
          {label}
        </Link>
      ))}
    </div>
  )
}
