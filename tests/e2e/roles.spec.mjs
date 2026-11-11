// Finance roles and the "Entry level" toggle on the board.
import { test, expect } from "@playwright/test";

const titles = (page) => page.$$eval(".row .r-title", (els) => els.map((e) => e.textContent.trim()).sort());

test("the Finance role and the Entry level toggle filter the board", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/index.html");
  await expect(page.locator(".row")).toHaveCount(8);

  await page.selectOption("#role", "Finance");
  expect(await titles(page)).toEqual(["Financial Analyst II", "Investment Banking Analyst"]);

  await page.check("#entryonly"); // "II" is mid level, not entry level
  expect(await titles(page)).toEqual(["Investment Banking Analyst"]);

  await page.selectOption("#role", ""); // entry level across every role: none of the plain engineering titles say so
  expect(await titles(page)).toEqual(["Acquisitions Analyst", "Development Associate", "Investment Banking Analyst"]);

  await page.uncheck("#entryonly");
  await expect(page.locator(".row")).toHaveCount(8);
  await expect(page.locator("#tags .tag[data-t=\"finance\"]")).toBeVisible();
  expect(errors).toEqual([]);
});

test("applying to a finance role records it as Finance on the Applications page", async ({ page }) => {
  await page.goto("/index.html?guest");
  const [popup] = await Promise.all([page.waitForEvent("popup"),
    page.locator(".row", { hasText: "Investment Banking Analyst" }).click()]);
  await popup.close();
  await page.goto("/stats.html?guest");
  await expect(page.locator("#by-role")).toContainText("Finance");
});
