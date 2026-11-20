import type { CSSProperties, SVGProps } from 'react'

/** A six-armed snowflake crystal, drawn in currentColor. */
export function Snowflake(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="-12 -12 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...props}
    >
      {[0, 60, 120].map((angle) => (
        <path
          key={angle}
          transform={`rotate(${angle})`}
          d="M0 -11 V11 M-3.5 -8.5 L0 -5.5 L3.5 -8.5 M-3.5 8.5 L0 5.5 L3.5 8.5"
        />
      ))}
    </svg>
  )
}

/** A stable pseudo-random number in [0, 1) for flake `i`, property `n`. */
function scatter(i: number, n: number): number {
  const x = Math.sin(i * 12.9898 + n * 78.233) * 43758.5453
  return x - Math.floor(x)
}

const FLAKES = Array.from({ length: 44 }, (_, i) => ({
  left: scatter(i, 1) * 100,
  size: 0.3 + scatter(i, 2) * 0.55,
  duration: 10 + scatter(i, 3) * 14,
  delay: -scatter(i, 4) * 24,
  drift: (scatter(i, 5) - 0.5) * 10,
  opacity: 0.55 + scatter(i, 6) * 0.45,
  crystal: i % 3 === 0,
}))

/**
 * Snow falling over the whole page, behind the cards and tiles so it never
 * hides their text. It never takes a tap, and it stops for
 * whoever asks their device for less motion (app-theme.css).
 */
export function Snowfall() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
      {FLAKES.map((flake, i) => (
        <span
          key={i}
          className="absolute top-0 block animate-snowfall text-white"
          style={
            {
              left: `${flake.left}%`,
              opacity: flake.opacity,
              animationDuration: `${flake.duration}s`,
              animationDelay: `${flake.delay}s`,
              '--snow-drift': `${flake.drift}rem`,
            } as CSSProperties
          }
        >
          {flake.crystal ? (
            <Snowflake
              style={{ width: `${flake.size * 2.2}rem`, height: `${flake.size * 2.2}rem` }}
              className="drop-shadow-[0_0_3px_rgb(255_255_255/0.8)]"
            />
          ) : (
            <span
              className="block rounded-full bg-white shadow-[0_0_6px_2px_rgb(255_255_255/0.6)]"
              style={{ width: `${flake.size}rem`, height: `${flake.size}rem` }}
            />
          )}
        </span>
      ))}
    </div>
  )
}
