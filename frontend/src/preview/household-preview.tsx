/**
 * The household page as t7 builds it, with test content and no behaviour:
 * every state a tile can be in, side by side.
 */

import { Button } from '@/components/primitives/button'
import { ChoiceButton } from '@/components/kerst/choice-button'
import { ClaimTile, ClaimTileGrid } from '@/components/kerst/claim-tile'
import { Counter } from '@/components/kerst/counter'
import { FestiveCard } from '@/components/kerst/festive-card'
import { FestiveHeader, FestivePage, FestiveSectionTitle } from '@/components/kerst/festive-page'
import pompoensoep from './photos/pompoensoep.jpg'
import groenten from './photos/groenten.jpg'
import rollade from './photos/rollade.jpg'
import chocolademousse from './photos/chocolademousse.jpg'
import borden from './photos/borden.jpg'
import glazen from './photos/glazen.jpg'
import bestek from './photos/bestek.jpg'

export function HouseholdPreview() {
  return (
    <FestivePage>
      <FestiveHeader eyebrow="Kerstdiner 2026" title="Familie de Boer" />

      <div className="flex flex-col gap-8 sm:gap-12">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
          <FestiveCard title="Komen jullie?">
            <div className="grid gap-3 sm:grid-cols-2">
              <ChoiceButton tone="yes" selected>
                Ja, we komen
              </ChoiceButton>
              <ChoiceButton tone="no">Nee, helaas niet</ChoiceButton>
            </div>
          </FestiveCard>

          <FestiveCard title="Met wie?">
            <p className="text-lg text-muted-foreground">Dit is onze inschatting — klopt het?</p>
            <div className="mb-5 divide-y-2 divide-dashed divide-kerst-gold/50">
              <Counter label="Vegan" value={1} />
              <Counter label="Vegetarisch" value={0} />
              <Counter label="Eet alles" value={2} />
              <Counter label="Kindermenu <6jr" value={1} />
            </div>
            <Button variant="primary" size="lg" className="w-full">
              Opslaan
            </Button>
          </FestiveCard>
        </div>

        <section>
          <FestiveSectionTitle>Wat nemen jullie mee?</FestiveSectionTitle>
          <ClaimTileGrid>
            <ClaimTile photo={pompoensoep} title="Pompoensoep" detail="Voor 8 personen" state="yours" status="Dit maken jullie" />
            <ClaimTile photo={groenten} title="Geroosterde groenten" detail="Voor 8 personen" state="free" status="Nog vrij" />
            <ClaimTile photo={rollade} title="Rollade" detail="Voor 8 personen" state="taken" status="Familie Jansen maakt dit" />
            <ClaimTile photo={chocolademousse} title="Chocolademousse" detail="Voor 8 personen" state="free" status="Nog vrij" />
          </ClaimTileGrid>
        </section>

        <section>
          <FestiveSectionTitle>Servies</FestiveSectionTitle>
          <ClaimTileGrid>
            <ClaimTile photo={borden} title="20 borden" state="free" status="Nog vrij" />
            <ClaimTile photo={glazen} title="20 wijnglazen" state="yours" status="Dit nemen jullie mee" />
            <ClaimTile photo={bestek} title="20 sets bestek" state="taken" status="Familie Jansen neemt dit mee" />
          </ClaimTileGrid>
        </section>
      </div>
    </FestivePage>
  )
}
