/**
 * The four guest categories, in the order the pages show them, with the
 * words for each. Only children under 6 count as kind, the kindermenu; older
 * children count as adults do.
 */

import type { PartyResponse_3b8afed } from '@/lib/api/generated/hooks'

export type GuestCounts = PartyResponse_3b8afed['counts']

type GuestCategory = keyof GuestCounts

interface GuestCategoryWords {
  key: GuestCategory
  /** The counter's and /admin's column's label. */
  label: string
  singular: string
  plural: string
}

export const GUEST_CATEGORIES: readonly GuestCategoryWords[] = [
  { key: 'vegan', label: 'Vegan', singular: 'vegan', plural: 'vegan' },
  { key: 'vegetarisch', label: 'Vegetarisch', singular: 'vegetarisch', plural: 'vegetarisch' },
  { key: 'normaal', label: 'Eet alles', singular: 'eet alles', plural: 'eet alles' },
  { key: 'kind', label: 'Kindermenu <6jr', singular: 'kindermenu', plural: "kindermenu's" },
]

/** Everyone the counts bring, the young children included. */
export function totalPeople(counts: GuestCounts): number {
  return GUEST_CATEGORIES.reduce((total, category) => total + counts[category.key], 0)
}

/**
 * The household's line after saving, as the Telegram report words it:
 * "Jullie komen met 5: 1 vegetarisch, 2 eet alles, 2 kindermenu's". The
 * groups at zero are left out.
 */
export function attendanceSummary(counts: GuestCounts): string {
  const parts = GUEST_CATEGORIES.filter((category) => counts[category.key] > 0).map((category) => {
    const people = counts[category.key]
    return `${people} ${people === 1 ? category.singular : category.plural}`
  })
  return `Jullie komen met ${totalPeople(counts)}: ${parts.join(', ')}`
}
