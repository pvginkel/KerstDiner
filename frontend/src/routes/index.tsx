/**
 * The bare address: no household link, so it points the visitor to theirs.
 * Public, as every household route is (docs/design.md, Access).
 */

import { createFileRoute } from '@tanstack/react-router'
import { InvalidLinkPage } from '@/components/household/invalid-link'

export const Route = createFileRoute('/')({
  staticData: { public: true },
  component: InvalidLinkPage,
})
