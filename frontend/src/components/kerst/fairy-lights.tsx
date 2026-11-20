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
 * A string of fairy lights across the top of the page, its bulbs twinkling
 * one after the other. As wide as the page: the swags run off the right edge.
 */
export function FairyLights() {
  return (
    <div aria-hidden className="pointer-events-none relative z-10 flex shrink-0 overflow-hidden">
      {Array.from({ length: SWAGS }, (_, swag) => (
        <svg
          key={swag}
          viewBox="0 0 240 64"
          className="h-14 w-[210px] shrink-0 sm:h-16 sm:w-[240px]"
        >
          <path d="M0 6 Q120 40 240 6" fill="none" stroke="#123222" strokeWidth={2.5} />
          {BULBS.map((bulb, k) => {
            const colour = BULB_COLOURS[(swag * BULBS.length + k) % BULB_COLOURS.length]
            return (
              <g key={k} transform={`translate(${bulb.x} ${bulb.y}) rotate(${bulb.tilt})`}>
                <g
                  className="animate-twinkle"
                  style={{ animationDelay: `${-((swag * 7 + k * 3) % 13) * 0.2}s` }}
                >
                  <circle cy={13} r={13} fill={colour} opacity={0.18} />
                  <circle cy={13} r={8.5} fill={colour} opacity={0.35} />
                </g>
                <rect x={-3} y={0} width={6} height={6} rx={1.2} fill="#1f4a33" />
                <path d="M0 5 C5.5 7 6.5 15 0 22 C-6.5 15 -5.5 7 0 5 Z" fill={colour} />
                <ellipse cx={-1.8} cy={11} rx={1.4} ry={3} fill="white" opacity={0.55} />
              </g>
            )
          })}
        </svg>
      ))}
    </div>
  )
}
