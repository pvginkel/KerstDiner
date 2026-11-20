/**
 * The style's preview: the household page's layout with test content, for
 * screenshots (`pnpm screenshots:preview`). Only the dev server serves it,
 * at /preview.html; the production build leaves it out.
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'
import { HouseholdPreview } from './household-preview'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <div className="flex h-screen flex-col overflow-hidden">
      <HouseholdPreview />
    </div>
  </StrictMode>,
)
