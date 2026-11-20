import { Button } from '@/components/primitives/button'
import { ClaimTile, ClaimTileGrid } from '@/components/kerst/claim-tile'
import { FestiveCard } from '@/components/kerst/festive-card'
import { FestiveHeader, FestivePage, FestiveSectionTitle } from '@/components/kerst/festive-page'
import { useHouseholdQueries, useToggleClaim, type ClaimKind } from '@/hooks/use-household'
import { isUnauthorizedError } from '@/lib/api/api-error'
import { useListLoadingInstrumentation } from '@/lib/test/query-instrumentation'
import { useUiStateInstrumentation } from '@/lib/test/ui-state'
import {
  dishStatusLabel,
  serviesStatusLabel,
  tilesHintLabel,
  type ClaimStatus,
} from '@/lib/utils/status-labels'
import { Attendance } from './attendance'
import { InvalidLinkPage } from './invalid-link'

const EYEBROW = 'Kerstdiner 2026'

function peopleLine(people: number): string {
  return people === 1 ? 'Voor 1 persoon' : `Voor ${people} personen`
}

function photoUrl(folder: 'gerechten' | 'servies', image: string | null): string | undefined {
  return image ? `/${folder}/${encodeURIComponent(image)}` : undefined
}

/** The household's page, /p/<link token>: who comes, and what they bring. */
export function HouseholdPage({ token }: { token: string }) {
  const { party, dishes, tableware } = useHouseholdQueries(token)
  const claim = useToggleClaim(token)

  useUiStateInstrumentation('household.party', { isLoading: party.isLoading, error: party.error })
  useListLoadingInstrumentation({
    scope: 'household.dishes',
    isLoading: dishes.isLoading,
    isFetching: dishes.isFetching,
    error: dishes.error,
    getReadyMetadata: () => ({ count: dishes.data?.dishes.length }),
  })
  useListLoadingInstrumentation({
    scope: 'household.servies',
    isLoading: tableware.isLoading,
    isFetching: tableware.isFetching,
    error: tableware.error,
    getReadyMetadata: () => ({ count: tableware.data?.items.length }),
  })
  useUiStateInstrumentation('household.claim', {
    isLoading: claim.isPending,
    error: claim.error,
    readyOnMount: false,
    getReadyMetadata: () => ({ ...claim.variables }),
  })

  // An unknown or replaced link answers 401, also on a later refresh.
  if ([party.error, dishes.error, tableware.error].some((error) => isUnauthorizedError(error))) {
    return <InvalidLinkPage />
  }

  if (!party.data) {
    return (
      <FestivePage>
        <FestiveHeader eyebrow={EYEBROW} title="Kerstdiner" />
        {party.error && (
          <div className="mx-auto w-full max-w-2xl">
            <FestiveCard>
              <p className="mb-4 pr-14 text-xl font-extrabold">Er ging iets mis. Probeer het zo nog eens.</p>
              <Button variant="primary" onClick={() => void party.refetch()}>
                Opnieuw proberen
              </Button>
            </FestiveCard>
          </div>
        )}
      </FestivePage>
    )
  }

  const household = party.data
  const canClaim = household.answer === 'coming'
  const hint = tilesHintLabel(household.answer)
  const dishList = dishes.data?.dishes ?? []
  const serviesList = tableware.data?.items ?? []
  const hasClaims = [...dishList, ...serviesList].some((tile) => tile.status === 'yours')

  const isPending = (kind: ClaimKind, id: number) =>
    claim.isPending && claim.variables.kind === kind && claim.variables.id === id

  const toggle = (kind: ClaimKind, id: number, status: ClaimStatus) => {
    claim.mutate({ kind, id, take: status !== 'yours' })
  }

  return (
    <FestivePage>
      <FestiveHeader eyebrow={EYEBROW} title={household.name} />

      <div className="flex flex-col gap-8 sm:gap-12" data-testid="household.page">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
          <Attendance token={token} party={household} hasClaims={hasClaims} />
        </div>

        {dishList.length > 0 && (
          <section>
            <FestiveSectionTitle>Wat nemen jullie mee?</FestiveSectionTitle>
            {hint && (
              <p
                className="mx-auto mb-5 max-w-3xl rounded-2xl bg-kerst-cream/90 px-4 py-3 text-center text-lg font-bold text-kerst-ink"
                data-testid="household.tiles.hint"
              >
                {hint}
              </p>
            )}
            <ClaimTileGrid>
              {dishList.map((dish) => (
                <ClaimTile
                  key={dish.id}
                  testId={`household.dish.${dish.id}`}
                  photo={photoUrl('gerechten', dish.image)}
                  title={dish.name}
                  detail={peopleLine(dish.people)}
                  state={dish.status}
                  status={dishStatusLabel(dish.status, dish.made_by)}
                  disabled={!canClaim || isPending('dish', dish.id)}
                  onClick={() => toggle('dish', dish.id, dish.status)}
                />
              ))}
            </ClaimTileGrid>
          </section>
        )}

        {serviesList.length > 0 && (
          <section>
            <FestiveSectionTitle>Servies</FestiveSectionTitle>
            <ClaimTileGrid>
              {serviesList.map((item) => (
                <ClaimTile
                  key={item.id}
                  testId={`household.servies.${item.id}`}
                  photo={photoUrl('servies', item.image)}
                  title={item.text}
                  state={item.status}
                  status={serviesStatusLabel(item.status, item.brought_by)}
                  disabled={!canClaim || isPending('servies', item.id)}
                  onClick={() => toggle('servies', item.id, item.status)}
                />
              ))}
            </ClaimTileGrid>
          </section>
        )}
      </div>
    </FestivePage>
  )
}
