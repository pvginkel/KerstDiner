import { Minus, Plus } from 'lucide-react'

interface CounterProps {
  label: string
  value: number
  onDecrement?: () => void
  onIncrement?: () => void
}

const ROUND_BUTTON =
  'flex size-12 shrink-0 items-center justify-center rounded-full border-[3px] border-kerst-gold text-white shadow-md transition active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-kerst-gold-light'

/** A "Met wie?" counter: its label, and big − and + buttons around the number. */
export function Counter({ label, value, onDecrement, onIncrement }: CounterProps) {
  return (
    <div className="flex items-center justify-between gap-3 py-3">
      <span className="text-lg font-bold leading-tight">{label}</span>
      <span className="flex items-center gap-2">
        <button
          type="button"
          onClick={onDecrement}
          disabled={value <= 0}
          aria-label={`${label}: één minder`}
          className={`${ROUND_BUTTON} bg-kerst-green`}
        >
          <Minus className="size-6" strokeWidth={3} />
        </button>
        <output aria-label={label} className="w-10 text-center text-2xl font-extrabold tabular-nums">
          {value}
        </output>
        <button
          type="button"
          onClick={onIncrement}
          aria-label={`${label}: één meer`}
          className={`${ROUND_BUTTON} bg-kerst-red`}
        >
          <Plus className="size-6" strokeWidth={3} />
        </button>
      </span>
    </div>
  )
}
