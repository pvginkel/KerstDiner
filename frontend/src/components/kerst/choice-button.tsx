import type { ReactNode } from 'react'
import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ChoiceButtonProps {
  children: ReactNode
  /** Yes turns green when chosen, no turns red. */
  tone: 'yes' | 'no'
  selected?: boolean
  onClick?: () => void
}

/** One of the big answer buttons, such as "Ja, we komen" and "Nee, helaas niet". */
export function ChoiceButton({ children, tone, selected = false, onClick }: ChoiceButtonProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={cn(
        'flex min-h-16 w-full items-center justify-center gap-2 rounded-2xl border-[3px] px-3 py-3 text-center text-lg font-extrabold leading-tight shadow-md transition active:scale-[0.98]',
        'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-kerst-gold-light',
        selected
          ? cn('border-kerst-gold text-white', tone === 'yes' ? 'bg-kerst-green' : 'bg-kerst-red')
          : 'border-kerst-gold/70 bg-white text-kerst-ink hover:bg-kerst-gold-light/30',
      )}
    >
      {selected && <Check className="size-6 shrink-0" strokeWidth={3.5} />}
      {children}
    </button>
  )
}
