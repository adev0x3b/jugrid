import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const errors: string[] = [];

test.beforeEach(async ({ page }) => {
  errors.length = 0;
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    // The base map comes from the internet; CI may not reach it.
    if (message.type() === "error" && !message.text().includes("openfreemap")) {
      errors.push(message.text());
    }
  });
});

test.afterEach(() => {
  expect(errors).toEqual([]);
});

/** On a phone the lists live in a bottom sheet that starts closed. */
async function openLists(page: Page) {
  if ((page.viewportSize()?.width ?? 1024) < 768) {
    await page.getByRole("button", { name: "Hazards, assets and the most exposed" }).click();
  }
}

async function expectNoAxeViolations(page: Page) {
  const results = await new AxeBuilder({ page }).exclude(".maplibregl-canvas").analyze();
  expect(
    results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`),
  ).toEqual([]);
}

test("the map loads with the region's assets", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "JuGrid" })).toBeVisible();
  await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  await openLists(page);
  await expect(page.getByRole("button", { name: /Stazione Torino Nord/ }).first()).toBeVisible();
  await expectNoAxeViolations(page);
});

test("switching to 2050 and to wind changes the address and the list", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("radio", { name: /high emissions/ }).check({ force: true });
  await openLists(page);
  await page.getByRole("button", { name: "Wind", exact: true }).first().click();
  await expect(page).toHaveURL(/scenario=ssp585_2050/);
  await expect(page).toHaveURL(/view=wind/);
  await page.getByRole("button", { name: "Rising fastest" }).first().click();
  await expect(page.getByRole("button", { name: /Unnamed power line/ }).first()).toBeVisible();
});

test("an asset opens from the list and closes with Escape", async ({ page }) => {
  await page.goto("/?scenario=ssp585_2050");
  await openLists(page);
  await page
    .getByRole("button", { name: /Cabina Lingotto/ })
    .first()
    .click();
  const panel = page.getByRole("region", { name: "Cabina Lingotto" });
  await expect(panel).toBeVisible();
  await expect(panel.getByRole("row", { name: /^Heat/ })).toContainText("days/yr");
  await expectNoAxeViolations(page);
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(page).not.toHaveURL(/asset=/);
});

test("the data page explains the method, in dark mode too", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Switch to dark mode" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.getByRole("button", { name: "About the data" }).click();
  const dialog = page.getByRole("dialog", { name: /How JuGrid scores Piemonte/ });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("row", { name: /Underground cables/ })).toBeVisible();
  await expectNoAxeViolations(page);
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(dialog).toBeHidden();
});

test("the CSV export downloads", async ({ page }) => {
  await page.goto("/");
  await openLists(page);
  const download = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download this scenario as CSV" }).click();
  expect((await download).suggestedFilename()).toBe("jugrid-baseline.csv");
});
