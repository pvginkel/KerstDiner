import type { ReactNode } from 'react'
import { Stag } from './deer'
import { HangingBaubles } from './baubles'
import { FairyLights } from './fairy-lights'
import { Holly } from './holly'
import { Scenery } from './scenery'
import { Snowfall, Snowflake } from './snowfall'
import { Sparkles } from './sparkles'

/**
 * Every page's frame: the green night with gold stars, fairy lights and
 * baubles along the top, falling snow, and a snowy field with deer and birds at the bottom. The
 * content goes in the middle column. It is the page's scroll container, so it
 * fills the rest of the root layout.
 */
export function FestivePage({ children }: { children: ReactNode }) {
  return (
    <div className="festive-backdrop relative flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden text-foreground">
      <Snowfall />
      <FairyLights />
      <HangingBaubles className="pointer-events-none absolute left-[2%] top-9 hidden w-28 lg:block" />
      <HangingBaubles className="pointer-events-none absolute right-[2%] top-9 hidden w-28 -scale-x-100 lg:block" />
      <main className="relative z-10 mx-auto w-full max-w-6xl flex-1 px-4 pb-6 sm:px-6">
        <Sparkles />
        {children}
      </main>
      <Scenery />
    </div>
  )
}

interface FestiveHeaderProps {
  /** A small line above the title, such as "Kerstdiner 2026". */
  eyebrow?: string
  title: string
}

/** The page's title in gold, between sprigs of holly, with a stag on either side. */
export function FestiveHeader({ eyebrow, title }: FestiveHeaderProps) {
  return (
    <header className="flex items-end justify-center gap-4 pb-8 pt-1 sm:gap-8 sm:pb-12">
      <Stag className="hidden h-36 shrink-0 text-kerst-gold drop-shadow-[0_0_12px_hsl(45_95%_60%/0.45)] md:block lg:h-44" />
      <div className="text-center">
        <div className="mb-2 flex items-end justify-center gap-3">
          <Stag className="h-16 shrink-0 text-kerst-gold md:hidden" />
          {eyebrow && (
            <p className="pb-1 text-sm font-extrabold uppercase tracking-[0.3em] text-kerst-gold-light sm:text-base">
              {eyebrow}
            </p>
          )}
          <Stag className="h-16 shrink-0 -scale-x-100 text-kerst-gold md:hidden" />
        </div>
        <div className="flex items-center justify-center gap-2 sm:gap-4">
          <Holly className="w-12 shrink-0 -rotate-12 sm:w-20" />
          <h1 className="font-festive gold-foil text-balance text-[3.2rem] sm:text-7xl">{title}</h1>
          <Holly className="w-12 shrink-0 rotate-12 -scale-x-100 sm:w-20" />
        </div>
      </div>
      <Stag className="hidden h-36 shrink-0 -scale-x-100 text-kerst-gold drop-shadow-[0_0_12px_hsl(45_95%_60%/0.45)] md:block lg:h-44" />
    </header>
  )
}

/** A heading over a group of tiles, in gold between two snowflakes. */
export function FestiveSectionTitle({ children }: { children: ReactNode }) {
  return (
    <h2 className="mb-5 flex items-center justify-center gap-3 text-center sm:mb-7">
      <Snowflake className="size-7 shrink-0 text-kerst-gold-light sm:size-9" />
      <span className="font-festive gold-foil text-[2.6rem] sm:text-6xl">{children}</span>
      <Snowflake className="size-7 shrink-0 text-kerst-gold-light sm:size-9" />
    </h2>
  )
}
