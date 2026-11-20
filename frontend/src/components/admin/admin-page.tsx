import { Button } from '@/components/primitives/button'
import { ConfirmDialog } from '@/components/primitives/dialog'
import { UserDropdown } from '@/components/layout/user-dropdown'
import { FestiveCard } from '@/components/kerst/festive-card'
import { FestiveHeader, FestivePage } from '@/components/kerst/festive-page'
import { useConfirm } from '@/hooks/use-confirm'
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard'
import { useToast } from '@/hooks/use-toast'
import {
  useGetAdminParties,
  usePostAdminPartiesLinkByPartyId,
  type AdminPartyResponse_3b8afed,
} from '@/lib/api/generated/hooks'
import { useListLoadingInstrumentation } from '@/lib/test/query-instrumentation'
import { useUiStateInstrumentation } from '@/lib/test/ui-state'
import { GUEST_CATEGORIES } from '@/lib/utils/guest-categories'
import { answerLabel } from '@/lib/utils/status-labels'

const MONTHS = ['jan', 'feb', 'mrt', 'apr', 'mei', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec']

/** "21 nov 14:02", in the browser's time zone. */
function formatAnswered(answeredAt: string): string {
  const date = new Date(answeredAt)
  const time = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${time}`
}

const CELL = 'px-3 py-2.5'
const NUMBER_CELL = `${CELL} text-center tabular-nums`

/**
 * /admin: every household's answer and counts in config order, the totals
 * with the guesses of who hasn't answered, and each household's link.
 */
export function AdminPage() {
  const parties = useGetAdminParties()
  const replaceLink = usePostAdminPartiesLinkByPartyId()
  const { confirm, confirmProps } = useConfirm()
  const { showSuccess } = useToast()

  useListLoadingInstrumentation({
    scope: 'admin.parties',
    isLoading: parties.isLoading,
    isFetching: parties.isFetching,
    error: parties.error,
    getReadyMetadata: () => ({ count: parties.data?.parties.length }),
  })
  useUiStateInstrumentation('admin.link', {
    isLoading: replaceLink.isPending,
    error: replaceLink.error,
    readyOnMount: false,
    getReadyMetadata: () => ({ partyId: replaceLink.variables?.path.party_id }),
  })

  const replace = async (party: AdminPartyResponse_3b8afed) => {
    const confirmed = await confirm({
      title: `Nieuwe link voor ${party.name}?`,
      description: 'De oude link werkt daarna niet meer. Kopieer de nieuwe en stuur hem zelf door.',
      confirmText: 'Nieuwe link',
      cancelText: 'Annuleren',
      destructive: true,
    })
    if (confirmed) {
      replaceLink.mutate(
        { path: { party_id: party.id } },
        { onSuccess: () => showSuccess(`${party.name} heeft een nieuwe link. De oude werkt niet meer.`) },
      )
    }
  }

  const data = parties.data

  return (
    <FestivePage>
      <div className="flex justify-end pt-3">
        <div className="rounded-full bg-kerst-cream text-kerst-ink shadow-md">
          <UserDropdown />
        </div>
      </div>
      <FestiveHeader eyebrow="Kerstdiner 2026" title="Wie komen er?" />

      <FestiveCard title="Huishoudens">
        {parties.error && !data && (
          <p className="text-lg font-bold text-kerst-red">De huishoudens konden niet geladen worden.</p>
        )}
        {data && (
          <div className="-mx-2 overflow-x-auto px-2">
            <table className="w-full min-w-[56rem] border-collapse text-left text-base" data-testid="admin.parties.table">
              <thead>
                <tr className="border-b-[3px] border-kerst-gold font-extrabold text-kerst-red">
                  <th scope="col" className={CELL}>Huishouden</th>
                  <th scope="col" className={CELL}>Antwoord</th>
                  {GUEST_CATEGORIES.map((category) => (
                    <th key={category.key} scope="col" className={`${CELL} text-center`}>
                      {category.label}
                    </th>
                  ))}
                  <th scope="col" className={CELL}>Beantwoord</th>
                  <th scope="col" className={CELL}>Link</th>
                </tr>
              </thead>
              <tbody>
                {data.parties.map((party) => (
                  <PartyRow
                    key={party.id}
                    party={party}
                    replacing={replaceLink.isPending && replaceLink.variables.path.party_id === party.id}
                    onReplace={() => void replace(party)}
                  />
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-[3px] border-kerst-gold font-extrabold" data-testid="admin.parties.totals">
                  <th scope="row" className={CELL}>Totaal</th>
                  <td className={CELL} data-testid="admin.parties.totals.people">
                    {data.people === 1 ? '1 persoon' : `${data.people} personen`}
                  </td>
                  {GUEST_CATEGORIES.map((category) => (
                    <td key={category.key} className={NUMBER_CELL} data-testid={`admin.parties.totals.${category.key}`}>
                      {data.totals[category.key]}
                    </td>
                  ))}
                  <td className={CELL} colSpan={2} />
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </FestiveCard>
      <ConfirmDialog {...confirmProps} />
    </FestivePage>
  )
}

interface PartyRowProps {
  party: AdminPartyResponse_3b8afed
  replacing: boolean
  onReplace: () => void
}

function PartyRow({ party, replacing, onReplace }: PartyRowProps) {
  const { copyState, copy } = useCopyToClipboard()
  const rowId = `admin.parties.row.${party.id}`
  const copyLabel = copyState === 'success' ? 'Gekopieerd' : copyState === 'error' ? 'Mislukt' : 'Kopieer'

  return (
    <tr className="border-b border-dashed border-kerst-gold/60 even:bg-kerst-gold-light/15" data-testid={rowId}>
      <th scope="row" className={`${CELL} font-extrabold`}>{party.name}</th>
      <td className={CELL} data-testid={`${rowId}.answer`}>{answerLabel(party.answer)}</td>
      {GUEST_CATEGORIES.map((category) => (
        <td key={category.key} className={NUMBER_CELL} data-testid={`${rowId}.${category.key}`}>
          {party.counts[category.key]}
        </td>
      ))}
      <td className={`${CELL} whitespace-nowrap`} data-testid={`${rowId}.answered`}>
        {party.answered_at ? formatAnswered(party.answered_at) : '—'}
      </td>
      <td className={CELL}>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="secondary"
            className="min-w-24"
            onClick={() => copy(`${window.location.origin}/p/${party.link_token}`)}
            data-testid={`${rowId}.copy`}
            data-copy-state={copyState}
          >
            {copyLabel}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={replacing}
            onClick={onReplace}
            data-testid={`${rowId}.replace`}
          >
            Nieuwe link
          </Button>
        </div>
      </td>
    </tr>
  )
}
