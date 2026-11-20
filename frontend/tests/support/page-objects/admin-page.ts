import { expect, type Locator, type Page } from '@playwright/test'
import { BasePage } from './base-page'
import { waitForListLoading, waitForUiState } from '../helpers'

/** /admin: the households' table. */
export class AdminPage extends BasePage {
  constructor(page: Page) {
    super(page)
  }

  /** Opens /admin and waits until the table has loaded. */
  async open(): Promise<void> {
    await this.goto('/admin')
    await waitForListLoading(this.page, 'admin.parties', 'ready')
  }

  get table(): Locator {
    return this.page.getByTestId('admin.parties.table')
  }

  /** The households' names, in the table's order. */
  get rowNames(): Locator {
    return this.table.locator('tbody th[scope="row"]')
  }

  get columnHeaders(): Locator {
    return this.table.locator('thead th')
  }

  row(partyId: number): Locator {
    return this.page.getByTestId(`admin.parties.row.${partyId}`)
  }

  /** One of a row's cells: answer, vegan, vegetarisch, normaal, kind or answered. */
  cell(partyId: number, column: string): Locator {
    return this.page.getByTestId(`admin.parties.row.${partyId}.${column}`)
  }

  /** One of the totals row's cells: people, vegan, vegetarisch, normaal or kind. */
  total(column: string): Locator {
    return this.page.getByTestId(`admin.parties.totals.${column}`)
  }

  copyButton(partyId: number): Locator {
    return this.page.getByTestId(`admin.parties.row.${partyId}.copy`)
  }

  /** Copies a household's link, and answers what the clipboard then holds. */
  async copyLink(partyId: number): Promise<string> {
    const button = this.copyButton(partyId)
    // A copy shows "Gekopieerd" for a moment; wait it out, so this copy is the one read.
    await expect(button).toHaveAttribute('data-copy-state', 'idle')
    await button.click()
    await expect(button).toHaveAttribute('data-copy-state', 'success')
    return this.page.evaluate(() => navigator.clipboard.readText())
  }

  /** Replaces a household's link, confirmed, and waits until the table holds the new one. */
  async replaceLink(partyId: number): Promise<void> {
    await this.page.getByTestId(`admin.parties.row.${partyId}.replace`).click()
    await this.page.getByRole('dialog').getByRole('button', { name: 'Nieuwe link' }).click()
    await waitForUiState(this.page, 'admin.link', 'ready')
    await waitForListLoading(this.page, 'admin.parties', 'ready')
  }
}
