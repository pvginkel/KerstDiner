import { FestiveCard } from '@/components/kerst/festive-card'
import { FestiveHeader, FestivePage } from '@/components/kerst/festive-page'

/**
 * What the bare address and a household link that is unknown or replaced
 * show: the household's own link is the way in.
 */
export function InvalidLinkPage() {
  return (
    <FestivePage>
      <FestiveHeader eyebrow="25 december 2026" title="Kerstdiner" />
      <div className="mx-auto w-full max-w-2xl">
        <FestiveCard>
          <p className="pr-14 text-xl font-extrabold sm:text-2xl" data-testid="household.invalid-link">
            Gebruik de persoonlijke link uit je e-mail
          </p>
        </FestiveCard>
      </div>
    </FestivePage>
  )
}
