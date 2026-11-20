import { useState } from 'react'
import { Button } from '@/components/primitives/button'
import { ConfirmDialog } from '@/components/primitives/dialog'
import { ChoiceButton } from '@/components/kerst/choice-button'
import { Counter } from '@/components/kerst/counter'
import { FestiveCard } from '@/components/kerst/festive-card'
import { useConfirm } from '@/hooks/use-confirm'
import { useSaveAnswer } from '@/hooks/use-household'
import type { PartyResponse_3b8afed } from '@/lib/api/generated/hooks'
import { useUiStateInstrumentation } from '@/lib/test/ui-state'
import {
  attendanceSummary,
  GUEST_CATEGORIES,
  totalPeople,
  type GuestCounts,
} from '@/lib/utils/guest-categories'

interface AttendanceProps {
  token: string
  party: PartyResponse_3b8afed
  /** Whether the household makes a dish or brings servies, which declining gives back. */
  hasClaims: boolean
}

/**
 * "Komen jullie?" and "Met wie?" until the household has answered; after
 * that, its answer in one line with a Wijzigen link that opens them again.
 */
export function Attendance({ token, party, hasClaims }: AttendanceProps) {
  const [editing, setEditing] = useState(party.answer === 'unanswered')
  const save = useSaveAnswer(token)
  const { confirm, confirmProps } = useConfirm()

  useUiStateInstrumentation('household.answer', {
    isLoading: save.isPending,
    error: save.error,
    readyOnMount: false,
    getReadyMetadata: () => ({ answer: save.variables?.answer }),
  })

  const saveComing = (counts: GuestCounts) => {
    save.mutate({ answer: 'coming', counts }, { onSuccess: () => setEditing(false) })
  }

  const decline = async () => {
    const confirmed = await confirm({
      title: 'Komen jullie niet?',
      description: hasClaims
        ? 'Dan geven jullie de gerechten en het servies terug die jullie hadden gekozen.'
        : 'Dan weten we dat jullie er dit jaar niet bij zijn.',
      confirmText: 'Nee, we komen niet',
      cancelText: 'Terug',
      destructive: true,
    })
    if (confirmed) {
      save.mutate({ answer: 'not_coming' }, { onSuccess: () => setEditing(false) })
    }
  }

  return (
    <>
      {editing ? (
        <AttendanceForm party={party} saving={save.isPending} onSaveComing={saveComing} onDecline={decline} />
      ) : (
        <FestiveCard>
          <div className="flex flex-col gap-3 pr-14 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xl font-extrabold sm:text-2xl" data-testid="household.attendance.summary">
              {party.answer === 'coming' ? attendanceSummary(party.counts) : 'Jullie komen helaas niet'}
            </p>
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="self-start py-2 text-lg font-extrabold text-kerst-red underline underline-offset-4 hover:text-kerst-red-dark sm:self-auto"
              data-testid="household.attendance.edit"
            >
              Wijzigen
            </button>
          </div>
        </FestiveCard>
      )}
      <ConfirmDialog {...confirmProps} />
    </>
  )
}

interface AttendanceFormProps {
  party: PartyResponse_3b8afed
  saving: boolean
  onSaveComing: (counts: GuestCounts) => void
  onDecline: () => void
}

function AttendanceForm({ party, saving, onSaveComing, onDecline }: AttendanceFormProps) {
  const [coming, setComing] = useState(party.answer === 'coming')
  const [counts, setCounts] = useState<GuestCounts>(party.counts)
  const total = totalPeople(counts)

  const change = (key: keyof GuestCounts, delta: number) => {
    setCounts((current) => ({ ...current, [key]: Math.max(0, current[key] + delta) }))
  }

  return (
    <>
      <FestiveCard title="Komen jullie?">
        <div className="grid gap-3 sm:grid-cols-2">
          <ChoiceButton tone="yes" selected={coming} onClick={() => setComing(true)}>
            Ja, we komen
          </ChoiceButton>
          <ChoiceButton tone="no" selected={!coming && party.answer === 'not_coming'} onClick={onDecline}>
            Nee, helaas niet
          </ChoiceButton>
        </div>
      </FestiveCard>

      {coming && (
        <FestiveCard title="Met wie?">
          {party.answer === 'unanswered' && (
            <p className="text-lg text-muted-foreground">Dit is onze inschatting — klopt het?</p>
          )}
          <div className="mb-5 divide-y-2 divide-dashed divide-kerst-gold/50">
            {GUEST_CATEGORIES.map((category) => (
              <Counter
                key={category.key}
                label={category.label}
                value={counts[category.key]}
                onDecrement={() => change(category.key, -1)}
                onIncrement={() => change(category.key, 1)}
              />
            ))}
          </div>
          {total === 0 && <p className="mb-3 text-lg font-bold text-kerst-red">Tel minstens één persoon.</p>}
          <Button
            variant="primary"
            size="lg"
            className="w-full"
            disabled={total === 0 || saving}
            onClick={() => onSaveComing(counts)}
            data-testid="household.attendance.save"
          >
            Opslaan
          </Button>
        </FestiveCard>
      )}
    </>
  )
}
