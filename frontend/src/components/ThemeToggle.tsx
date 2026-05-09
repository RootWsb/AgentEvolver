import { useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'
import { cn } from '../lib/utils'

export default function ThemeToggle({ className }: { className?: string }) {
  const [isDark, setIsDark] = useState(() =>
    document.documentElement.classList.contains('dark'),
  )

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark)
  }, [isDark])

  return (
    <button
      onClick={() => setIsDark((d) => !d)}
      className={cn(
        'w-8 h-8 rounded-md flex items-center justify-center',
        'text-t-secondary hover:text-t-primary hover:bg-hover',
        'transition-colors',
        className,
      )}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {isDark ? <Sun size={16} strokeWidth={1.5} /> : <Moon size={16} strokeWidth={1.5} />}
    </button>
  )
}
