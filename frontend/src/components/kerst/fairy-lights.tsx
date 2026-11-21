/** Red, gold, green, blue and orange bulbs, in turn along the wire. */
const BULB_COLOURS = ['#ff3349', '#ffd23f', '#35d873', '#47b5ff', '#ff8c2e']

/** Six bulbs hanging along one swag of wire, a curve from (0,6) via (120,40) to (240,6). */
const BULBS = [1, 2, 3, 4, 5, 6].map((k) => {
  const t = k / 7
  return {
    x: 240 * t,
    y: (1 - t) ** 2 * 6 + 2 * (1 - t) * t * 40 + t ** 2 * 6,
    tilt: k % 2 === 0 ? 9 : -9,
  }
})

const SWAGS = 12

/**
 * A string of fairy lights across the top of the page, its bulbs flashing on
 * and off one after the other. Each bulb is drawn twice: dimmed, as it looks
 * off, and lit with its glow on top, which fades out and in again
 * (app-theme.css, bulb-flash). As wide as the page: the swags run off the
 * right edge.
 */
export function FairyLights() {
  return (
    <div aria-hidden className="pointer-events-none relative z-10 flex shrink-0 overflow-hidden">
      {Array.from({ length: SWAGS }, (_, swag) => (
        <svg
          key={swag}
          viewBox="0 0 240 64"
          overflow="visible"
          className="h-14 w-[210px] shrink-0 sm:h-16 sm:w-[240px]"
        >
          <path d="M0 6 Q120 40 240 6" fill="none" stroke="#123222" strokeWidth={2.5} />
          {BULBS.map((bulb, k) => {
            const colour = BULB_COLOURS[(swag * BULBS.length + k) % BULB_COLOURS.length]
            return (
              <g key={k} transform={`translate(${bulb.x} ${bulb.y}) rotate(${bulb.tilt})`}>
                <rect x={-3} y={0} width={6} height={6} rx={1.2} fill="#1f4a33" />
                <path d="M0 5 C5.5 7 6.5 15 0 22 C-6.5 15 -5.5 7 0 5 Z" fill={colour} opacity={0.4} />
                <g
                  className="animate-bulb-flash"
                  style={{ animationDelay: `${-((swag * 7 + k * 3) % 13) * 0.13}s` }}
                >
                  <circle cy={14} r={18} fill={colour} opacity={0.22} />
                  <circle cy={14} r={11} fill={colour} opacity={0.45} />
                  <path d="M0 5 C5.5 7 6.5 15 0 22 C-6.5 15 -5.5 7 0 5 Z" fill={colour} />
                  <ellipse cx={-1.8} cy={11} rx={1.4} ry={3} fill="white" opacity={0.7} />
                </g>
              </g>
            )
          })}
        </svg>
      ))}
    </div>
  )
}
