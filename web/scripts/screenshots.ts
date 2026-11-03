// Takes the README's screenshots from a running stack with real data.
// JUGRID_URL=http://127.0.0.1:8096 npx tsx scripts/screenshots.ts ../docs/screenshots
import { chromium, devices, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const base = process.env.JUGRID_URL ?? "http://127.0.0.1:8096";
const out = process.argv[2] ?? "screenshots";
mkdirSync(out, { recursive: true });

const browser = await chromium.launch(
  process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
);

async function settle(page: Page) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(2500); // tiles fade in
}

async function shoot(
  name: string,
  path: string,
  options: { phone?: boolean; dark?: boolean; act?: (page: Page) => Promise<void> } = {},
) {
  const context = await browser.newContext({
    ...(options.phone ? devices["Pixel 7"] : { viewport: { width: 1440, height: 900 } }),
    deviceScaleFactor: 2,
    colorScheme: options.dark ? "dark" : "light",
  });
  const page = await context.newPage();
  await page.goto(base + path);
  await settle(page);
  if (options.act) {
    await options.act(page);
    await settle(page);
  }
  await page.screenshot({ path: join(out, `${name}.png`) });
  await context.close();
  console.log(name);
}

const firstRanked = async (page: Page) => {
  await page.locator("aside ol button").first().click();
};

await shoot("map-today", "/");
await shoot("map-2050-heat", "/?scenario=ssp585_2050&view=heat&grid=1", { dark: true });
await shoot("asset", "/?scenario=ssp585_2050&view=overall", { act: firstRanked });
await shoot("rising-fastest", "/?scenario=ssp585_2050", {
  act: async (page) => {
    await page.locator("aside").getByRole("button", { name: "Rising fastest" }).click();
  },
});
await shoot("phone", "/?scenario=ssp245_2050&view=flood", { phone: true });
await shoot("phone-lists", "/?scenario=ssp585_2050", {
  phone: true,
  dark: true,
  act: async (page) => {
    await page.getByRole("button", { name: "Hazards, assets and the most exposed" }).click();
  },
});
await shoot("model-card", "/?scenario=ssp585_2050&view=heat&grid=1", {
  act: async (page) => {
    await page.getByRole("button", { name: "About the data" }).click();
    await page.locator("#correction-title").scrollIntoViewIfNeeded();
  },
});
await shoot("raw-grid", "/?scenario=ssp585_2050&view=heat&grid=1&raw=1", { dark: true });

await browser.close();
