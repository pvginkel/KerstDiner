import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Holly } from './holly'

interface FestiveCardProps {
  title?: string
  children: ReactNode
  className?: string
}

/**
 * A cream card in a gold frame, with a sprig of holly on its corner and its
 * title in the festive font: the household page's questions, /admin's table.
 */
export function FestiveCard({ title, children, className }: FestiveCardProps) {
  return (
    <section
      className={cn('gold-frame relative rounded-3xl bg-kerst-cream px-5 pb-6 pt-5 text-kerst-ink sm:px-8 sm:pt-7', className)}
    >
      <Holly className="pointer-events-none absolute -right-3 -top-7 w-24 rotate-[18deg] sm:-right-6 sm:w-28" />
      {title && <h2 className="font-festive mb-4 pr-16 text-[2.6rem] text-kerst-red sm:text-5xl">{title}</h2>}
      {children}
    </section>
  )
}
