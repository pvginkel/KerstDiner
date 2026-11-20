import { useId, type SVGProps } from 'react'

/** Light, middle and dark shade of each bauble colour. */
const SHADES = {
  red: ['#ff6b7a', '#c8102e', '#5e0410'],
  gold: ['#fff1b0', '#e0a91c', '#7a5208'],
  green: ['#6fe39a', '#16803f', '#063d1c'],
}

const BAUBLES = [
  { x: 22, drop: 34, r: 17, colour: 'red' },
  { x: 62, drop: 92, r: 21, colour: 'gold' },
  { x: 100, drop: 18, r: 14, colour: 'green' },
] as const

/** Three glass baubles hanging on ribbons from the fairy lights. */
export function HangingBaubles(props: SVGProps<SVGSVGElement>) {
  const id = useId()
  return (
    <svg viewBox="0 0 124 160" aria-hidden {...props}>
      <defs>
        {Object.entries(SHADES).map(([name, [light, mid, dark]]) => (
          <radialGradient key={name} id={`${id}-${name}`} cx="0.35" cy="0.32" r="0.75">
            <stop offset="0" stopColor={light} />
            <stop offset="0.45" stopColor={mid} />
            <stop offset="1" stopColor={dark} />
          </radialGradient>
        ))}
      </defs>
      {BAUBLES.map(({ x, drop, r, colour }) => {
        const cy = drop + 6 + r
        return (
          <g key={x}>
            <path d={`M${x} 0 V${drop}`} stroke="#c8102e" strokeWidth={2.5} />
            <rect x={x - 4.5} y={drop} width={9} height={7} rx={1.5} fill="#e0a91c" stroke="#7a5208" strokeWidth={0.8} />
            <circle cx={x} cy={cy} r={r} fill={`url(#${id}-${colour})`} />
            <path
              d={`M${x - r * 0.92} ${cy + 2} Q${x} ${cy + r * 0.5} ${x + r * 0.92} ${cy + 2}`}
              stroke="#ffe08a"
              strokeWidth={2}
              fill="none"
              strokeDasharray="1 3"
              strokeLinecap="round"
            />
            <ellipse cx={x - r * 0.38} cy={cy - r * 0.4} rx={r * 0.2} ry={r * 0.32} fill="white" opacity={0.7} transform={`rotate(-30 ${x - r * 0.38} ${cy - r * 0.4})`} />
          </g>
        )
      })}
    </svg>
  )
}
