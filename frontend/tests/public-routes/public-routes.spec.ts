/**
 * The public routes (docs/design.md, Access): `/` and `/p/$token` carry
 * `staticData: { public: true }`, so they render without a login, and the
 * 401-to-login redirect leaves them alone; /admin does not.
 *
 * The worker's backend runs without OIDC, so "no login" is the testing
 * endpoint's forced 401 on the next GET /api/auth/self. Every route asks it,
 * so each test that forces one also uses it up.
 */

import type { Page, Request } from '@playwright/test'
import type { QueryErrorTestEvent } from '@/lib/test/test-events'
import { test, expect } from '../support/fixtures'
import { waitTestEvent } from '../support/helpers'

/** Records every request for the login, from here on. */
function recordLoginRequests(page: Page): Request[] {
  const requests: Request[] = []
  page.on('request', (request) => {
    if (request.url().includes('/api/auth/login')) {
      requests.push(request)
    }
  })
  return requests
}

/** Waits until a query has failed with a 401: the redirect, if any, has been decided by then. */
async function waitForUnauthorized(page: Page, queryKey: string): Promise<void> {
  await waitTestEvent<QueryErrorTestEvent>(
    page,
    'query_error',
    (event) => event.status === 401 && event.queryKey.startsWith(queryKey),
  )
}

test.describe('Public routes', () => {
  test('the bare address asks for the personal link, without a login', async ({ page, auth, householdPage }) => {
    const loginRequests = recordLoginRequests(page)
    await auth.forceError(401)

    await householdPage.goto('/')

    await waitForUnauthorized(page, 'getAuthSelf')
    await expect(householdPage.invalidLink).toHaveText('Gebruik de persoonlijke link uit je e-mail')
    expect(new URL(page.url()).pathname).toBe('/')
    expect(loginRequests).toHaveLength(0)
  })

  test("a household's page renders without a login", async ({ page, auth, kerstdiner, householdPage }) => {
    const seed = await kerstdiner.reset()
    const loginRequests = recordLoginRequests(page)
    await auth.forceError(401)

    await householdPage.open(seed.households.jansen.token)

    await waitForUnauthorized(page, 'getAuthSelf')
    await expect(householdPage.title).toHaveText('Familie Jansen')
    await expect(householdPage.yes).toBeVisible()
    expect(new URL(page.url()).pathname).toBe(`/p/${seed.households.jansen.token}`)
    expect(loginRequests).toHaveLength(0)
  })

  test('an unknown link asks for the personal link, without a redirect', async ({ page, householdPage }) => {
    const loginRequests = recordLoginRequests(page)

    await householdPage.goto('/p/not-a-household-link')

    // The household endpoints answer 401 for it, which a public route handles itself.
    await waitForUnauthorized(page, 'getParty')
    await expect(householdPage.invalidLink).toHaveText('Gebruik de persoonlijke link uit je e-mail')
    expect(new URL(page.url()).pathname).toBe('/p/not-a-household-link')
    expect(loginRequests).toHaveLength(0)
  })

  test('/admin is not public: without a login it goes to the login', async ({ page, auth }) => {
    await auth.forceError(401)

    const loginRequest = page.waitForRequest((request) => request.url().includes('/api/auth/login'))
    await page.goto('/admin')

    const url = new URL((await loginRequest).url())
    expect(url.searchParams.get('redirect')).toBe('/admin')
  })
})
