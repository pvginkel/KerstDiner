/**
 * The household page (docs/design.md, What a household sees): answering,
 * taking and giving back a dish and servies, a lost race, and declining.
 */

import { test, expect } from '../support/fixtures'

test.describe('Household page', () => {
  test('answers who comes, starting from the guess', async ({ kerstdiner, householdPage }) => {
    const seed = await kerstdiner.reset()
    const jansen = seed.households.jansen

    await householdPage.open(jansen.token)

    await expect(householdPage.title).toHaveText('Familie Jansen')
    // Before answering, the tiles are shown but can't be clicked.
    await expect(householdPage.tilesHint).toBeVisible()
    await expect(householdPage.dish(seed.dishes.soep)).toBeDisabled()
    await expect(householdPage.servies(seed.servies.borden)).toBeDisabled()
    // The kindermenu's never count towards a dish: 1 vegetarisch and 2 + 2 + 2 eet alles.
    await expect(householdPage.dish(seed.dishes.soep)).toContainText('Voor 7 personen')

    await householdPage.yes.click()
    await expect(householdPage.guessLine).toBeVisible()
    await expect(householdPage.count('Vegan')).toHaveText('0')
    await expect(householdPage.count('Vegetarisch')).toHaveText('1')
    await expect(householdPage.count('Eet alles')).toHaveText('2')
    await expect(householdPage.count('Kindermenu <6jr')).toHaveText('2')

    await householdPage.increment('Vegan')
    await expect(householdPage.count('Vegan')).toHaveText('1')
    await householdPage.save()

    await expect(householdPage.summary).toHaveText(
      "Jullie komen met 6: 1 vegan, 1 vegetarisch, 2 eet alles, 2 kindermenu's",
    )
    await expect(householdPage.tilesHint).toBeHidden()
    await expect(householdPage.dish(seed.dishes.soep)).toBeEnabled()
    await expect(householdPage.dish(seed.dishes.soep)).toContainText('Voor 8 personen')

    // The answer is the household's own now: a new visit shows it, and Wijzigen starts from it.
    await householdPage.open(jansen.token)
    await expect(householdPage.summary).toHaveText(
      "Jullie komen met 6: 1 vegan, 1 vegetarisch, 2 eet alles, 2 kindermenu's",
    )
    await householdPage.editLink.click()
    await expect(householdPage.guessLine).toBeHidden()
    await expect(householdPage.count('Vegan')).toHaveText('1')
    await householdPage.decrement('Kindermenu <6jr')
    await householdPage.decrement('Kindermenu <6jr')
    await householdPage.save()
    await expect(householdPage.summary).toHaveText('Jullie komen met 4: 1 vegan, 1 vegetarisch, 2 eet alles')
  })

  test('takes a dish and a servies item, and gives them back', async ({ kerstdiner, householdPage }) => {
    const seed = await kerstdiner.reset()
    const jansen = seed.households.jansen
    await kerstdiner.answer(jansen, { answer: 'coming', counts: { vegan: 0, vegetarisch: 1, normaal: 2, kind: 2 } })

    await householdPage.open(jansen.token)
    const soep = householdPage.dish(seed.dishes.soep)
    const borden = householdPage.servies(seed.servies.borden)
    await expect(soep).toContainText('Nog vrij')
    await expect(borden).toContainText('Nog vrij')
    // A servies tile says nothing about how many it is for.
    await expect(borden).not.toContainText('personen')

    await householdPage.toggle(soep)
    await expect(soep).toHaveAttribute('data-state', 'yours')
    await expect(soep).toContainText('Dit maken jullie')

    await householdPage.toggle(borden)
    await expect(borden).toHaveAttribute('data-state', 'yours')
    await expect(borden).toContainText('Dit nemen jullie mee')

    // Another household sees who has them, and can't take them.
    await householdPage.open(seed.households['oma-opa'].token)
    await expect(soep).toContainText('Familie Jansen maakt dit')
    await expect(soep).toBeDisabled()
    await expect(borden).toContainText('Familie Jansen neemt dit mee')
    await expect(borden).toBeDisabled()

    await householdPage.open(jansen.token)
    await householdPage.toggle(soep)
    await expect(soep).toHaveAttribute('data-state', 'free')
    await expect(soep).toContainText('Nog vrij')

    await householdPage.toggle(borden)
    await expect(borden).toHaveAttribute('data-state', 'free')
    await expect(borden).toContainText('Nog vrij')
  })

  test('loses the race for a dish and for servies', async ({ kerstdiner, householdPage, toastHelper }) => {
    const seed = await kerstdiner.reset()
    const jansen = seed.households.jansen
    const deBoer = seed.households['de-boer']
    const counts = { vegan: 0, vegetarisch: 0, normaal: 2, kind: 0 }
    await kerstdiner.answer(jansen, { answer: 'coming', counts })
    await kerstdiner.answer(deBoer, { answer: 'coming', counts })

    await householdPage.open(jansen.token)
    const rollade = householdPage.dish(seed.dishes.rollade)
    const glazen = householdPage.servies(seed.servies.wijnglazen)
    await expect(rollade).toContainText('Nog vrij')
    await expect(glazen).toContainText('Nog vrij')

    // Familie de Boer takes the dish while Jansen's page still shows it free.
    await kerstdiner.takeDish(deBoer, seed.dishes.rollade)
    await householdPage.toggle(rollade)
    await toastHelper.expectErrorToast('Dit gerecht is net door Familie de Boer gekozen')
    await expect(rollade).toContainText('Familie de Boer maakt dit')
    await expect(rollade).toBeDisabled()

    // The lost race refreshed every tile; now the servies goes the same way.
    await expect(glazen).toContainText('Nog vrij')
    await kerstdiner.takeServies(deBoer, seed.servies.wijnglazen)
    await householdPage.toggle(glazen)
    await toastHelper.expectErrorToast('Dit servies is net door Familie de Boer gekozen')
    await expect(glazen).toContainText('Familie de Boer neemt dit mee')
    await expect(glazen).toBeDisabled()
  })

  test('declining gives back the dishes and servies', async ({ kerstdiner, householdPage, page }) => {
    const seed = await kerstdiner.reset()
    const jansen = seed.households.jansen
    await kerstdiner.answer(jansen, { answer: 'coming', counts: { vegan: 0, vegetarisch: 1, normaal: 2, kind: 2 } })
    await kerstdiner.takeDish(jansen, seed.dishes.soep)
    await kerstdiner.takeServies(jansen, seed.servies.borden)

    await householdPage.open(jansen.token)
    const soep = householdPage.dish(seed.dishes.soep)
    const borden = householdPage.servies(seed.servies.borden)
    await expect(soep).toContainText('Dit maken jullie')
    await expect(borden).toContainText('Dit nemen jullie mee')

    await householdPage.editLink.click()
    await householdPage.no.click()
    // Thinking better of it keeps everything as it was.
    const dialog = page.getByRole('dialog')
    await expect(dialog).toContainText('Dan geven jullie de gerechten en het servies terug')
    await dialog.getByRole('button', { name: 'Terug' }).click()
    await expect(dialog).toBeHidden()
    await expect(soep).toContainText('Dit maken jullie')

    await householdPage.decline()

    await expect(householdPage.summary).toHaveText('Jullie komen helaas niet')
    await expect(householdPage.tilesHint).toHaveText('Jullie komen niet, dus hier hoeven jullie niets te kiezen.')
    await expect(soep).toContainText('Nog vrij')
    await expect(soep).toBeDisabled()
    await expect(borden).toContainText('Nog vrij')
    await expect(borden).toBeDisabled()
    // Who doesn't come is counted nowhere: 2 eet alles from Oma en opa and 2 from Familie de Boer.
    await expect(soep).toContainText('Voor 4 personen')
  })
})
