import { useId, type SVGProps } from 'react'

/** One spiky holly leaf, pointing along the x axis from its stalk at (0,0). */
const LEAF =
  'M0 0 Q5 -7 14 -11 Q20 -5 30 -13 Q36 -6 46 -11 Q53 -5 62 0 Q53 5 46 11 Q36 6 30 13 Q20 5 14 11 Q5 7 0 0 Z'

/** A sprig of holly: three glossy leaves and a bunch of red berries. */
export function Holly(props: SVGProps<SVGSVGElement>) {
  const id = useId()
  return (
    <svg viewBox="-66 -48 132 96" aria-hidden {...props}>
      <defs>
        <linearGradient id={`${id}-leaf`} x1="0" y1="-1" x2="0" y2="1" gradientUnits="objectBoundingBox">
          <stop offset="0" stopColor="#2a9d55" />
          <stop offset="1" stopColor="#0b5a2c" />
        </linearGradient>
        <radialGradient id={`${id}-berry`} cx="0.35" cy="0.35" r="0.7">
          <stop offset="0" stopColor="#ff5a6b" />
          <stop offset="0.6" stopColor="#d0102a" />
          <stop offset="1" stopColor="#8a0616" />
        </radialGradient>
      </defs>
      {[
        { angle: 200, scale: 1 },
        { angle: -22, scale: 1 },
        { angle: 95, scale: 0.78 },
      ].map(({ angle, scale }) => (
        <g key={angle} transform={`rotate(${angle}) scale(${scale})`}>
          <path d={LEAF} fill={`url(#${id}-leaf)`} stroke="#07401f" strokeWidth={1.2} strokeLinejoin="round" />
          <path d="M3 0 L56 0" stroke="#7fd39a" strokeWidth={1.4} strokeLinecap="round" opacity={0.8} />
        </g>
      ))}
      {[
        { cx: -6, cy: -3 },
        { cx: 6, cy: -4 },
        { cx: 0, cy: 6 },
      ].map((berry) => (
        <g key={`${berry.cx},${berry.cy}`}>
          <circle {...berry} r={7.5} fill={`url(#${id}-berry)`} stroke="#6d0512" strokeWidth={0.8} />
          <circle cx={berry.cx - 2.4} cy={berry.cy - 2.6} r={1.8} fill="white" opacity={0.85} />
        </g>
      ))}
    </svg>
  )
}
