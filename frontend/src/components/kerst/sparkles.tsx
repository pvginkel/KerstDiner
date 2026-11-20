/** Where the sparkles sit, in % of the page, and how big they are, in rem. */
const SPARKLES = [
  { left: 4, top: 9, size: 1.1 },
  { left: 93, top: 14, size: 1.4 },
  { left: 12, top: 31, size: 0.8 },
  { left: 88, top: 37, size: 1 },
  { left: 3, top: 52, size: 1.3 },
  { left: 96, top: 58, size: 0.9 },
  { left: 9, top: 71, size: 1 },
  { left: 91, top: 79, size: 1.2 },
  { left: 50, top: 47, size: 0.7 },
  { left: 28, top: 4, size: 0.8 },
  { left: 70, top: 6, size: 0.9 },
]

/** Gold four-pointed stars twinkling behind the page's content. */
export function Sparkles() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10">
      {SPARKLES.map(({ left, top, size }, i) => (
        <svg
          key={i}
          viewBox="-10 -10 20 20"
          className="absolute animate-twinkle text-kerst-gold-light drop-shadow-[0_0_6px_hsl(45_95%_65%/0.9)]"
          style={{ left: `${left}%`, top: `${top}%`, width: `${size}rem`, height: `${size}rem`, animationDelay: `${-i * 0.7}s` }}
        >
          <path d="M0 -10 C1 -2 2 -1 10 0 C2 1 1 2 0 10 C-1 2 -2 1 -10 0 C-2 -1 -1 -2 0 -10 Z" fill="currentColor" />
        </svg>
      ))}
    </div>
  )
}
