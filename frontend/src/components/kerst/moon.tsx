import { useId, type SVGProps } from 'react'

/**
 * A crescent moon, pale gold, with a soft glow and a few faint craters. The
 * dark side is cut away by a mask, so the night sky shows through it. Its
 * gradients and mask have ids of their own, so two moons on a page (one shown
 * on a phone, one on a computer) never borrow each other's.
 */
export function Moon(props: SVGProps<SVGSVGElement>) {
  const id = useId()
  const glow = `${id}-glow`
  const face = `${id}-face`
  const crescent = `${id}-crescent`
  return (
    <svg viewBox="0 0 100 100" aria-hidden {...props}>
      <defs>
        <radialGradient id={glow}>
          <stop offset="0.45" stopColor="hsl(48 100% 85%)" stopOpacity={0.35} />
          <stop offset="1" stopColor="hsl(48 100% 85%)" stopOpacity={0} />
        </radialGradient>
        <linearGradient id={face} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="hsl(50 100% 94%)" />
          <stop offset="1" stopColor="hsl(44 85% 72%)" />
        </linearGradient>
        <mask id={crescent}>
          <circle cx={50} cy={50} r={30} fill="white" />
          <circle cx={64} cy={41} r={26} fill="black" />
        </mask>
      </defs>
      <circle cx={50} cy={50} r={50} fill={`url(#${glow})`} />
      <g mask={`url(#${crescent})`}>
        <circle cx={50} cy={50} r={30} fill={`url(#${face})`} />
        <circle cx={33} cy={58} r={4.5} fill="hsl(42 60% 62%)" opacity={0.45} />
        <circle cx={41} cy={72} r={2.8} fill="hsl(42 60% 62%)" opacity={0.4} />
        <circle cx={27} cy={44} r={2.2} fill="hsl(42 60% 62%)" opacity={0.35} />
      </g>
    </svg>
  )
}
