/**
 * Every status's label and colours (the modern app guide's STATUS-4): a
 * household's answer, and who has a dish or servies item.
 */

import type {
  DishResponse_3d8d65b,
  PartyResponse_3b8afed,
  TablewareResponse_3d8d65b,
} from '@/lib/api/generated/hooks'

type PartyAnswer = PartyResponse_3b8afed['answer']

/** A dish's or servies item's status for the household asking: nobody has it, it has it, or another one does. */
export type ClaimStatus = DishResponse_3d8d65b['status'] | TablewareResponse_3d8d65b['status']

/** /admin's Antwoord column. */
export function answerLabel(answer: PartyAnswer): string {
  switch (answer) {
    case 'unanswered':
      return 'Nog geen antwoord (schatting)'
    case 'coming':
      return 'Komt'
    case 'not_coming':
      return 'Komt niet'
    default: {
      const _exhaustive: never = answer
      return String(_exhaustive)
    }
  }
}

/**
 * The line over the tiles while the household can't take any: before it has
 * answered, and after it has declined. Null once it comes.
 */
export function tilesHintLabel(answer: PartyAnswer): string | null {
  switch (answer) {
    case 'unanswered':
      return 'Laat eerst weten of jullie komen, dan kiezen jullie hier wat jullie meenemen.'
    case 'not_coming':
      return 'Jullie komen niet, dus hier hoeven jullie niets te kiezen.'
    case 'coming':
      return null
    default: {
      const _exhaustive: never = answer
      return String(_exhaustive)
    }
  }
}

/** A dish tile's status line: "Nog vrij", "Dit maken jullie" or "Familie Jansen maakt dit". */
export function dishStatusLabel(status: ClaimStatus, madeBy: string | null): string {
  switch (status) {
    case 'free':
      return 'Nog vrij'
    case 'yours':
      return 'Dit maken jullie'
    case 'taken':
      return `${madeBy ?? 'Een ander huishouden'} maakt dit`
    default: {
      const _exhaustive: never = status
      return String(_exhaustive)
    }
  }
}

/** A servies tile's status line: "Nog vrij", "Dit nemen jullie mee" or "Familie Jansen neemt dit mee". */
export function serviesStatusLabel(status: ClaimStatus, broughtBy: string | null): string {
  switch (status) {
    case 'free':
      return 'Nog vrij'
    case 'yours':
      return 'Dit nemen jullie mee'
    case 'taken':
      return `${broughtBy ?? 'Een ander huishouden'} neemt dit mee`
    default: {
      const _exhaustive: never = status
      return String(_exhaustive)
    }
  }
}

/** A tile's colours: the frame around it and the band with its status line. */
export function claimStatusClasses(status: ClaimStatus): { frame: string; band: string } {
  switch (status) {
    case 'free':
      return {
        frame:
          'border-kerst-gold bg-kerst-cream shadow-[0_10px_22px_-10px_rgb(0_0_0/0.7)] hover:-translate-y-0.5 hover:shadow-[0_0_0_3px_var(--color-kerst-gold-light),0_14px_28px_-10px_rgb(0_0_0/0.7)]',
        band: 'bg-kerst-green text-white',
      }
    case 'yours':
      return {
        frame:
          'border-kerst-red bg-kerst-cream shadow-[0_0_0_4px_var(--color-kerst-gold-light),0_0_30px_6px_hsl(45_95%_60%/0.6)]',
        band: 'bg-kerst-red text-white',
      }
    case 'taken':
      return { frame: 'border-stone-400 bg-stone-200', band: 'bg-stone-400 text-stone-900' }
    default: {
      const _exhaustive: never = status
      return { frame: String(_exhaustive), band: '' }
    }
  }
}
