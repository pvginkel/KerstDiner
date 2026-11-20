/**
 * KerstDiner's test data: a small config that POST /api/testing/reset puts
 * in place of the worker's households, dishes and servies, and the calls a
 * spec makes as another household, through the backend's own API.
 *
 * The worker's backend runs without the notification bridge, so the reports
 * these changes queue are never sent: no spec reaches the Telegram group.
 */

import { expect, type APIRequestContext } from '@playwright/test'
import type { components } from '@/lib/api/generated/types'

type ResetConfig = components['schemas']['KerstDinerConfig.036ef7d']
type ResetResponse = components['schemas']['TestingResetResponse.d40c6ff']
type AnswerRequest = components['schemas']['PartyAnswerRequest.3b8afed']

/**
 * Three households, three dishes and two servies items. With the guesses, a
 * dish made for everyone is for 7: the kindermenu's never count.
 */
const TEST_CONFIG = {
  households: [
    { key: 'jansen', name: 'Familie Jansen', guess: { vegetarisch: 1, normaal: 2, kind: 2 } },
    { key: 'oma-opa', name: 'Oma en opa', guess: { normaal: 2 } },
    { key: 'de-boer', name: 'Familie de Boer', guess: { normaal: 2, kind: 1 } },
  ],
  dishes: [
    { key: 'soep', name: 'Pompoensoep' },
    { key: 'rollade', name: 'Rollade', for: ['normaal'] },
    { key: 'wellington', name: 'Linzen-wellington', for: ['vegan', 'vegetarisch'] },
  ],
  servies: [
    { key: 'borden', text: '20 borden' },
    { key: 'wijnglazen', text: '20 wijnglazen' },
  ],
} satisfies ResetConfig

type HouseholdKey = (typeof TEST_CONFIG.households)[number]['key']
type DishKey = (typeof TEST_CONFIG.dishes)[number]['key']
type ServiesKey = (typeof TEST_CONFIG.servies)[number]['key']

interface Household {
  id: number
  name: string
  token: string
}

interface Seed {
  households: Record<HouseholdKey, Household>
  dishes: Record<DishKey, number>
  servies: Record<ServiesKey, number>
}

export class KerstDinerData {
  constructor(
    private readonly request: APIRequestContext,
    private readonly backendUrl: string,
  ) {}

  /** Wipes the worker's data and applies TEST_CONFIG, every household on its guess with a new link. */
  async reset(): Promise<Seed> {
    const response = await this.request.post(`${this.backendUrl}/api/testing/reset`, { data: TEST_CONFIG })
    expect(response.status()).toBe(200)
    const body = (await response.json()) as ResetResponse
    return {
      households: Object.fromEntries(
        body.parties.map((party) => [party.key, { id: party.id, name: party.name, token: party.link_token }]),
      ) as Seed['households'],
      dishes: Object.fromEntries(body.dishes.map((dish) => [dish.key, dish.id])) as Seed['dishes'],
      servies: Object.fromEntries(body.servies.map((item) => [item.key, item.id])) as Seed['servies'],
    }
  }

  /** Answers for a household, as its page would. */
  async answer(household: Household, body: AnswerRequest): Promise<void> {
    const response = await this.request.put(`${this.backendUrl}/api/party/answer`, {
      headers: { 'X-Link-Token': household.token },
      data: body,
    })
    expect(response.status()).toBe(200)
  }

  /** Takes a dish for a household, as its page would. */
  async takeDish(household: Household, dishId: number): Promise<void> {
    const response = await this.request.put(`${this.backendUrl}/api/dishes/${dishId}/claim`, {
      headers: { 'X-Link-Token': household.token },
    })
    expect(response.status()).toBe(200)
  }

  /** Takes a servies item for a household, as its page would. */
  async takeServies(household: Household, itemId: number): Promise<void> {
    const response = await this.request.put(`${this.backendUrl}/api/tableware/${itemId}/claim`, {
      headers: { 'X-Link-Token': household.token },
    })
    expect(response.status()).toBe(200)
  }
}
