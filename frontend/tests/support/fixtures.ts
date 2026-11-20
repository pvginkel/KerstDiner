/**
 * Domain-specific test fixtures.
 * App-owned — extends infrastructure fixtures with domain page objects.
 *
 * A fixture's `use` callback reads to eslint as React's `use` hook, so
 * react-hooks/rules-of-hooks reports it: the block comment below turns that
 * rule off for the fixtures.
 */

/* eslint-disable react-hooks/rules-of-hooks */

import { infrastructureFixtures } from './fixtures-infrastructure'
import { KerstDinerData } from './kerstdiner-data'
import { AdminPage } from './page-objects/admin-page'
import { HouseholdPage } from './page-objects/household-page'

interface DomainFixtures {
  /** Resets the worker's data and acts as another household (kerstdiner-data.ts). */
  kerstdiner: KerstDinerData
  householdPage: HouseholdPage
  adminPage: AdminPage
}

export const test = infrastructureFixtures.extend<DomainFixtures>({
  kerstdiner: async ({ request, backendUrl }, use) => {
    await use(new KerstDinerData(request, backendUrl))
  },
  householdPage: async ({ page }, use) => {
    await use(new HouseholdPage(page))
  },
  adminPage: async ({ page }, use) => {
    await use(new AdminPage(page))
  },
})

export type { InfrastructureFixtures } from './fixtures-infrastructure'
export { expect } from '@playwright/test'
