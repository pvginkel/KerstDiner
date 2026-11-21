import type { ReactNode } from 'react'
import { BirdFlight } from './birds'
import { Fawn, GrazingDeer, WalkingDoe } from './deer'
import { HangingBaubles } from './baubles'
import { FairyLights } from './fairy-lights'
import { Holly } from './holly'
import { Moon } from './moon'
import { Scenery } from './scenery'
import { Snowfall, Snowflake } from './snowfall'
import { Sparkles } from './sparkles'

/**
 * Every page's frame: the green night with gold stars and a crescent moon,
 * fairy lights and baubles along the top, falling snow, birds crossing the
 * sky, and a snowy field with deer, birds and a squirrel at the bottom. The
 * content goes in the middle column. It is the page's scroll container, so it
 * fills the rest of the root layout.
 */
export function FestivePage({ children }: { children: ReactNode }) {
  return (
    <div className="festive-backdrop relative flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden text-foreground">
      <Snowfall />
      <BirdFlight />
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

/**
 * The page's title in gold, between sprigs of holly, with deer and the moon
 * beside it: on a computer a doe walking towards it with her fawn behind her
 * on the left, a deer grazing on the right and the crescent moon above, right
 * of the title; on a phone the fawn and the moon on either side of the line
 * above the title. Each deer stands in a pose of its own, none mirrored.
 */
export function FestiveHeader({ eyebrow, title }: FestiveHeaderProps) {
  return (
    <header className="relative flex items-end justify-center gap-4 pb-8 pt-1 sm:gap-8 sm:pb-12">
      <Moon className="pointer-events-none absolute -top-6 left-[calc(50%+10rem)] hidden w-20 md:block" />
      <div className="hidden shrink-0 items-end drop-shadow-[0_0_12px_hsl(45_95%_60%/0.45)] md:flex">
        <Fawn className="-mr-3 mb-0.5 h-16 text-kerst-gold-light lg:h-20" />
        <WalkingDoe className="h-28 text-kerst-gold lg:h-32" />
      </div>
      <div className="text-center">
        <div className="mb-2 flex items-end justify-center gap-3">
          <Fawn className="h-14 shrink-0 text-kerst-gold md:hidden" />
          {eyebrow && (
            <p className="pb-1 text-sm font-extrabold uppercase tracking-[0.3em] text-kerst-gold-light sm:text-base">
              {eyebrow}
            </p>
          )}
          <Moon className="-my-2 w-16 shrink-0 md:hidden" />
        </div>
        <div className="flex items-center justify-center gap-2 sm:gap-4">
          <Holly className="w-12 shrink-0 -rotate-12 sm:w-20" />
          <h1 className="font-festive gold-foil text-balance text-[3.2rem] sm:text-7xl">{title}</h1>
          <Holly className="w-12 shrink-0 rotate-12 -scale-x-100 sm:w-20" />
        </div>
      </div>
      <GrazingDeer className="mb-1 hidden h-24 shrink-0 text-kerst-gold drop-shadow-[0_0_12px_hsl(45_95%_60%/0.45)] md:block lg:h-28" />
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
