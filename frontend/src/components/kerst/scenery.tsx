import { FlyingBirds, Robin } from './birds'
import { LeapingDeer, Stag } from './deer'

/** A snow-capped pine tree standing on (x, y), `h` tall. */
function PineTree({ x, y, h }: { x: number; y: number; h: number }) {
  const w = h * 0.62
  const tier = (top: number, bottom: number, width: number) =>
    `M${x} ${y - h * top} L${x + width / 2} ${y - h * bottom} L${x - width / 2} ${y - h * bottom} Z`
  return (
    <g>
      <rect x={x - h * 0.05} y={y - h * 0.14} width={h * 0.1} height={h * 0.14} fill="#3b2614" />
      <path d={tier(0.5, 0.12, w)} fill="#0c4526" />
      <path d={tier(0.78, 0.36, w * 0.76)} fill="#0f5530" />
      <path d={tier(1, 0.6, w * 0.52)} fill="#136437" />
      <path
        d={`M${x} ${y - h} L${x + w * 0.12} ${y - h * 0.86} L${x} ${y - h * 0.9} L${x - w * 0.12} ${y - h * 0.86} Z`}
        fill="white"
      />
      <path d={`M${x - w * 0.36} ${y - h * 0.38} Q${x} ${y - h * 0.3} ${x + w * 0.36} ${y - h * 0.38}`} stroke="white" strokeWidth={h * 0.04} strokeLinecap="round" fill="none" opacity={0.9} />
      <path d={`M${x - w * 0.24} ${y - h * 0.64} Q${x} ${y - h * 0.57} ${x + w * 0.24} ${y - h * 0.64}`} stroke="white" strokeWidth={h * 0.035} strokeLinecap="round" fill="none" opacity={0.9} />
      <circle cx={x} cy={y - h * 1.03} r={h * 0.045} fill="#ffd23f" />
    </g>
  )
}

/**
 * A snowy field along the bottom of the page: pine trees, deer and robins,
 * birds flying over. On a phone the sides are cut off; the deer and the robin
 * stay in the middle.
 */
export function Scenery() {
  return (
    <div aria-hidden className="pointer-events-none relative z-0 mt-4 h-[clamp(13rem,24vw,19rem)] w-full shrink-0">
      <svg viewBox="0 0 1200 260" preserveAspectRatio="xMidYMax slice" className="absolute inset-0 h-full w-full">
        <path d="M0 170 Q200 118 420 158 T840 148 T1200 136 V260 H0 Z" fill="#dce9f2" />
        <PineTree x={110} y={176} h={130} />
        <PineTree x={215} y={160} h={92} />
        <PineTree x={330} y={160} h={64} />
        <PineTree x={880} y={150} h={118} />
        <PineTree x={985} y={146} h={84} />
        <PineTree x={1100} y={140} h={136} />
        <path d="M0 214 Q300 172 600 204 T1200 196 V260 H0 Z" fill="#ffffff" />
        <Stag x={372} y={58} width={142} height={154} className="text-kerst-gold-dark" />
        <LeapingDeer x={700} y={30} width={102} height={150} className="text-kerst-gold" />
        <Robin x={556} y={158} width={58} height={54} />
        <Robin x={872} y={66} width={40} height={37} />
        <FlyingBirds x={500} y={4} width={120} height={67} className="text-kerst-gold-light" />
        <FlyingBirds x={150} y={14} width={86} height={48} className="text-kerst-gold-light" />
      </svg>
    </div>
  )
}
