import type { Locator, Page } from '@playwright/test'
import { BasePage } from './base-page'
import { waitForListLoading, waitForUiState } from '../helpers'

/** The household page, /p/<link token>, and the bare address's message. */
export class HouseholdPage extends BasePage {
  constructor(page: Page) {
    super(page)
  }

  /** Opens a household's link and waits until its household and tiles have loaded. */
  async open(token: string): Promise<void> {
    await this.goto(`/p/${token}`)
    await Promise.all([
      waitForUiState(this.page, 'household.party', 'ready'),
      waitForListLoading(this.page, 'household.dishes', 'ready'),
      waitForListLoading(this.page, 'household.servies', 'ready'),
    ])
  }

  get root(): Locator {
    return this.page.getByTestId('household.page')
  }

  get title(): Locator {
    return this.page.getByRole('heading', { level: 1 })
  }

  get invalidLink(): Locator {
    return this.page.getByTestId('household.invalid-link')
  }

  get yes(): Locator {
    return this.page.getByRole('button', { name: 'Ja, we komen' })
  }

  get no(): Locator {
    return this.page.getByRole('button', { name: 'Nee, helaas niet' })
  }

  get guessLine(): Locator {
    return this.page.getByText('Dit is onze inschatting — klopt het?')
  }

  /** A "Met wie?" counter's number, by its label, such as "Eet alles". */
  count(label: string): Locator {
    return this.page.getByRole('status', { name: label, exact: true })
  }

  async increment(label: string): Promise<void> {
    await this.page.getByRole('button', { name: `${label}: één meer` }).click()
  }

  async decrement(label: string): Promise<void> {
    await this.page.getByRole('button', { name: `${label}: één minder` }).click()
  }

  get saveButton(): Locator {
    return this.page.getByTestId('household.attendance.save')
  }

  get summary(): Locator {
    return this.page.getByTestId('household.attendance.summary')
  }

  get editLink(): Locator {
    return this.page.getByTestId('household.attendance.edit')
  }

  get tilesHint(): Locator {
    return this.page.getByTestId('household.tiles.hint')
  }

  dish(id: number): Locator {
    return this.page.getByTestId(`household.dish.${id}`)
  }

  servies(id: number): Locator {
    return this.page.getByTestId(`household.servies.${id}`)
  }

  /** Saves the counters as they stand, and waits for the save and the refresh after it. */
  async save(): Promise<void> {
    await this.saveButton.click()
    await waitForUiState(this.page, 'household.answer', 'ready')
  }

  /** Clicks a tile, and waits for the claim to settle and the tiles to refresh. */
  async toggle(tile: Locator): Promise<void> {
    await tile.click()
    await waitForUiState(this.page, 'household.claim', 'ready')
  }

  /** Says no, confirms it, and waits for the save. */
  async decline(): Promise<void> {
    await this.no.click()
    const dialog = this.page.getByRole('dialog')
    await dialog.getByRole('button', { name: 'Nee, we komen niet' }).click()
    await waitForUiState(this.page, 'household.answer', 'ready')
  }
}
