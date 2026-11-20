/**
 * A household's page, opened from its personal link. Public: the link token
 * is the household's key, sent with each request as X-Link-Token.
 */

import { createFileRoute } from '@tanstack/react-router'
import { HouseholdPage } from '@/components/household/household-page'

export const Route = createFileRoute('/p/$token')({
  staticData: { public: true },
  component: HouseholdRoute,
})

function HouseholdRoute() {
  const { token } = Route.useParams()
  // A new link is a new household: nothing of the previous one's state stays.
  return <HouseholdPage key={token} token={token} />
}
