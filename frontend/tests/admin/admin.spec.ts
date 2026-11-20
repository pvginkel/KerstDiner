/**
 * /admin (docs/design.md, What we see): the table with its totals, copying
 * a household's link and replacing one. The worker's backend runs without
 * OIDC, so the browser is the local admin.
 */

import { test, expect } from '../support/fixtures'

test.describe('Admin page', () => {
  test('shows every household in config order, with the totals', async ({ kerstdiner, adminPage }) => {
    const seed = await kerstdiner.reset()
    const { jansen, 'oma-opa': omaOpa, 'de-boer': deBoer } = seed.households
    await kerstdiner.answer(jansen, { answer: 'coming', counts: { vegan: 1, vegetarisch: 1, normaal: 2, kind: 2 } })
    await kerstdiner.answer(deBoer, { answer: 'not_coming' })

    await adminPage.open()

    await expect(adminPage.columnHeaders).toHaveText([
      'Huishouden',
      'Antwoord',
      'Vegan',
      'Vegetarisch',
      'Eet alles',
      'Kindermenu <6jr',
      'Beantwoord',
      'Link',
    ])
    await expect(adminPage.rowNames).toHaveText(['Familie Jansen', 'Oma en opa', 'Familie de Boer'])

    await expect(adminPage.cell(jansen.id, 'answer')).toHaveText('Komt')
    await expect(adminPage.cell(jansen.id, 'vegan')).toHaveText('1')
    await expect(adminPage.cell(jansen.id, 'vegetarisch')).toHaveText('1')
    await expect(adminPage.cell(jansen.id, 'normaal')).toHaveText('2')
    await expect(adminPage.cell(jansen.id, 'kind')).toHaveText('2')
    await expect(adminPage.cell(jansen.id, 'answered')).toHaveText(/^\d{1,2} [a-z]{3} \d{2}:\d{2}$/)

    // Who hasn't answered shows the guess.
    await expect(adminPage.cell(omaOpa.id, 'answer')).toHaveText('Nog geen antwoord (schatting)')
    await expect(adminPage.cell(omaOpa.id, 'normaal')).toHaveText('2')
    await expect(adminPage.cell(omaOpa.id, 'answered')).toHaveText('—')

    await expect(adminPage.cell(deBoer.id, 'answer')).toHaveText('Komt niet')
    await expect(adminPage.cell(deBoer.id, 'normaal')).toHaveText('0')
    await expect(adminPage.cell(deBoer.id, 'kind')).toHaveText('0')

    // The totals take in the guesses, and the young children count among who comes.
    await expect(adminPage.total('vegan')).toHaveText('1')
    await expect(adminPage.total('vegetarisch')).toHaveText('1')
    await expect(adminPage.total('normaal')).toHaveText('4')
    await expect(adminPage.total('kind')).toHaveText('2')
    await expect(adminPage.total('people')).toHaveText('8 personen')
  })

  test("copies a household's link", async ({ kerstdiner, adminPage, context, frontendUrl }) => {
    const seed = await kerstdiner.reset()
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])

    await adminPage.open()

    const copied = await adminPage.copyLink(seed.households.jansen.id)
    expect(copied).toBe(`${frontendUrl}/p/${seed.households.jansen.token}`)
  })

  test("replaces a household's link, and the old one stops working", async ({
    kerstdiner,
    adminPage,
    householdPage,
    toastHelper,
    context,
  }) => {
    const seed = await kerstdiner.reset()
    const jansen = seed.households.jansen
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])

    await adminPage.open()
    const oldLink = await adminPage.copyLink(jansen.id)

    await adminPage.replaceLink(jansen.id)
    await toastHelper.expectSuccessToast('Familie Jansen heeft een nieuwe link. De oude werkt niet meer.')

    const newLink = await adminPage.copyLink(jansen.id)
    expect(newLink).not.toBe(oldLink)

    await householdPage.goto(oldLink)
    await expect(householdPage.invalidLink).toHaveText('Gebruik de persoonlijke link uit je e-mail')

    await householdPage.goto(newLink)
    await expect(householdPage.title).toHaveText('Familie Jansen')
    await expect(householdPage.root).toBeVisible()
  })
})
