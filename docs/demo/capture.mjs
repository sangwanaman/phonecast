// Records the demo as numbered PNG frames on a fixed clock, for docs/demo.webp.
//
//   node docs/demo/capture.mjs <stageshow folder> <out folder> [fps=20] [seconds=34] [slow=4]
//
// Needs the Stageshow playground running (npm run dev in the stageshow folder) with this demo
// copied to examples/phonecast. Time is slowed down `slow` times (the stage's clock and every CSS
// animation), so each frame lands exactly on schedule. Then: python docs/demo/encode.py <out folder>.

import { mkdirSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const [stageshow, out, fpsArg = '20', secondsArg = '34', slowArg = '4'] = process.argv.slice(2)
if (!stageshow || !out) {
  console.error('usage: node capture.mjs <stageshow folder> <out folder> [fps] [seconds] [slow]')
  process.exit(2)
}
const fps = Number(fpsArg)
const seconds = Number(secondsArg)
const slow = Number(slowArg)
const url = process.env.DEMO_URL ?? 'http://127.0.0.1:5173/?capture=phonecast'

const { chromium } = await import(pathToFileURL(join(resolve(stageshow), 'node_modules', 'playwright-core', 'index.mjs')).href)
mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ channel: 'chrome' })
const page = await browser.newPage({ viewport: { width: 520, height: 900 }, deviceScaleFactor: 2 })
await page.addInitScript((s) => { window.__stageshow = { slow: s } }, slow)
const cdp = await page.context().newCDPSession(page)
await cdp.send('Animation.enable')
await cdp.send('Animation.setPlaybackRate', { playbackRate: 1 / slow })
await page.goto(url)
const stage = page.locator('.ss-stage').first()
await stage.waitFor({ state: 'visible' })

const total = Math.round(fps * seconds)
const every = (1000 / fps) * slow
const start = Date.now()
for (let i = 0; i < total; i++) {
  const due = start + i * every
  const wait = due - Date.now()
  if (wait > 0) await page.waitForTimeout(wait)
  await stage.screenshot({ path: join(out, `f${String(i).padStart(4, '0')}.png`), animations: 'allow' })
}
console.log(`${total} frames at ${fps} fps -> ${resolve(out)} (late by ${Math.max(0, Date.now() - start - total * every)} ms)`)
await browser.close()
