#!/usr/bin/env node
/**
 * Screenshots of the style's preview (preview.html), on a phone and on a
 * computer: the first screen as it opens, and the whole page.
 *
 *   pnpm screenshots:preview <out-dir>
 *
 * It starts its own Vite dev server on a free port, so nothing else needs to
 * run; the preview needs no backend.
 */

import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { chromium } from '@playwright/test'
import { createServer } from 'vite'

const outArg = process.argv[2]
if (!outArg) {
  console.error('Usage: pnpm screenshots:preview <out-dir>')
  process.exit(2)
}
const outDir = path.resolve(outArg)
mkdirSync(outDir, { recursive: true })

const DEVICES = [
  { name: 'telefoon', viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true },
  { name: 'computer', viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 },
]

const server = await createServer({
  server: { host: '127.0.0.1', port: 0, strictPort: false },
  logLevel: 'warn',
})
await server.listen()
const url = new URL('preview.html', server.resolvedUrls.local[0]).href

const browser = await chromium.launch()
try {
  for (const { name, ...device } of DEVICES) {
    const context = await browser.newContext(device)
    const page = await context.newPage()
    await page.goto(url, { waitUntil: 'networkidle' })
    await page.evaluate(() => document.fonts.ready)
    await page.waitForTimeout(1500)
    await page.screenshot({ path: path.join(outDir, `${name}-scherm.png`) })

    // The page scrolls inside its frame, not the document: make the window as
    // tall as the frame's content, and the whole page fits in one picture.
    const height = await page.evaluate(() =>
      Math.max(...Array.from(document.querySelectorAll('*'), (el) => el.scrollHeight)),
    )
    await page.setViewportSize({ width: device.viewport.width, height })
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(outDir, `${name}-hele-pagina.png`) })
    await context.close()
    console.log(`${name}: ${device.viewport.width}x${height}`)
  }
} finally {
  await browser.close()
  await server.close()
}
