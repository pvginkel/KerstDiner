import type { ReactNode } from 'react'
import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Snowflake } from './snowfall'

/** Who has a dish or servies item: nobody yet, this household, or another one. */
type ClaimState = 'free' | 'mine' | 'taken'

interface ClaimTileProps {
  /** The photo's URL. Without one, the tile shows a neutral placeholder. */
  photo?: string
  title: string
  /** A second line, such as "Voor 8 personen". A servies tile has none. */
  detail?: string
  state: ClaimState
  /** The state in words, such as "Nog vrij", "Dit maken jullie" or "Familie Jansen maakt dit". */
  status: string
  onClick?: () => void
  /** Shown but not clickable, as before the household has answered. */
  disabled?: boolean
}

const FRAME: Record<ClaimState, string> = {
  free: 'border-kerst-gold bg-kerst-cream shadow-[0_10px_22px_-10px_rgb(0_0_0/0.7)] hover:-translate-y-0.5 hover:shadow-[0_0_0_3px_var(--color-kerst-gold-light),0_14px_28px_-10px_rgb(0_0_0/0.7)]',
  mine: 'border-kerst-red bg-kerst-cream shadow-[0_0_0_4px_var(--color-kerst-gold-light),0_0_30px_6px_hsl(45_95%_60%/0.6)]',
  taken: 'border-stone-400 bg-stone-200',
}

const BAND: Record<ClaimState, string> = {
  free: 'bg-kerst-green text-white',
  mine: 'bg-kerst-red text-white',
  taken: 'bg-stone-400 text-stone-900',
}

/**
 * A dish or servies tile: its photo, its name, an optional second line and,
 * along the bottom, who brings it. Tapping it is the caller's to handle; a
 * tile another household has can't be tapped.
 */
export function ClaimTile({ photo, title, detail, state, status, onClick, disabled = false }: ClaimTileProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || state === 'taken'}
      aria-pressed={state === 'mine'}
      className={cn(
        'relative flex h-full w-full flex-col overflow-hidden rounded-2xl border-[3px] text-left text-kerst-ink transition duration-200',
        'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-kerst-gold-light disabled:cursor-not-allowed',
        FRAME[state],
        disabled && state !== 'taken' && 'opacity-75',
      )}
    >
      <span className="relative block aspect-[4/3] overflow-hidden bg-muted">
        {photo ? (
          <img
            src={photo}
            alt=""
            className={cn('h-full w-full object-cover', state === 'taken' && 'opacity-60 grayscale-[75%]')}
          />
        ) : (
          <span className="flex h-full w-full items-center justify-center text-kerst-gold">
            <Snowflake className="size-1/3" />
          </span>
        )}
        {state === 'mine' && (
          <span className="absolute right-2 top-2 flex size-10 items-center justify-center rounded-full bg-kerst-red text-white shadow-lg ring-[3px] ring-kerst-gold-light">
            <Check className="size-6" strokeWidth={3.5} />
          </span>
        )}
      </span>
      <span className="flex flex-1 flex-col gap-0.5 px-2.5 pb-3 pt-2.5 sm:px-3">
        <span className="hyphens-auto text-base font-extrabold leading-snug [overflow-wrap:anywhere] sm:text-lg">{title}</span>
        {detail && <span className="text-base font-semibold text-muted-foreground">{detail}</span>}
      </span>
      <span className={cn('px-2 py-2.5 text-center text-base font-extrabold leading-tight', BAND[state])}>
        {status}
      </span>
    </button>
  )
}

/** The tiles' grid: two across on a phone, up to four on a computer. */
export function ClaimTileGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-5 lg:grid-cols-4">{children}</div>
  )
}
