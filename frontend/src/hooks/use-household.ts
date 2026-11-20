/**
 * The household page's data: its household, the dishes and the servies, and
 * the changes it makes. Every request carries the household's link token in
 * the X-Link-Token header. The generated query hooks pass it as a header
 * parameter; the generated mutation hooks pass none, so the mutations here
 * call the API client themselves.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, useGetDishes, useGetParty, useGetTableware } from '@/lib/api/client'
import type { PartyAnswerRequest_3b8afed } from '@/lib/api/generated/hooks'
import { toApiError } from '@/lib/api/api-error'

/** The tiles refresh this often, and whenever the page regains focus. */
const TILE_REFRESH_MS = 30_000

const TILE_QUERY_OPTIONS = {
  refetchInterval: TILE_REFRESH_MS,
  refetchOnWindowFocus: true,
  staleTime: 0,
}

/** The kind of tile a claim is on. */
export type ClaimKind = 'dish' | 'servies'

interface ClaimVariables {
  kind: ClaimKind
  id: number
  /** True takes it, false gives it back. */
  take: boolean
}

function linkHeader(token: string) {
  return { 'X-Link-Token': token }
}

async function unwrap(request: Promise<{ error?: unknown; response: Response }>): Promise<void> {
  const result = await request
  if (result.error !== undefined) {
    throw toApiError(result.error, result.response.status)
  }
}

export function useHouseholdQueries(token: string) {
  const params = { header: linkHeader(token) }
  return {
    party: useGetParty(params),
    dishes: useGetDishes(params, TILE_QUERY_OPTIONS),
    tableware: useGetTableware(params, TILE_QUERY_OPTIONS),
  }
}

/**
 * Saves komt with the counts, or komt niet. It stays pending until the page's
 * data has refreshed, declining's released tiles included.
 */
export function useSaveAnswer(token: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: PartyAnswerRequest_3b8afed) =>
      unwrap(api.PUT('/api/party/answer', { params: { header: linkHeader(token) }, body })),
    onSuccess: () => queryClient.invalidateQueries(),
  })
}

/**
 * Takes a dish or servies item, or gives it back. Win or lose (another
 * household may just have taken it), the tiles refresh before it settles.
 */
export function useToggleClaim(token: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ kind, id, take }: ClaimVariables) => {
      const header = linkHeader(token)
      if (kind === 'dish') {
        const options = { params: { header, path: { dish_id: id } } }
        return unwrap(
          take
            ? api.PUT('/api/dishes/{dish_id}/claim', options)
            : api.DELETE('/api/dishes/{dish_id}/claim', options),
        )
      }
      const options = { params: { header, path: { item_id: id } } }
      return unwrap(
        take
          ? api.PUT('/api/tableware/{item_id}/claim', options)
          : api.DELETE('/api/tableware/{item_id}/claim', options),
      )
    },
    onSettled: () => queryClient.invalidateQueries(),
  })
}
