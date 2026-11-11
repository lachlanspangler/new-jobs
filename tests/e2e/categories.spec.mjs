// Category filter buttons on the board: counts, filtering, combining with the other filters, priority order kept.
import { test, expect } from "@playwright/test";

const titles = (page) => page.$$eval(".row .r-title", (els) => els.map((e) => e.textContent.trim()));
const cat = (page, label) => page.locator("#cats .cat", { hasText: label });

test("each category has a button with its count, and the buttons filter the board", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto("/index.html");
  await expect(page.locator(".row")).toHaveCount(8);

  const labels = await page.$$eval("#cats .cat", (els) => els.map((e) => e.textContent.replace(/\s+/g, " ").trim()));
  expect(labels).toEqual(["Software 3", "Quant 1", "Real estate 1", "Development 1", "Finance analyst 2"]);

  // every row carries its category label
  const rowCats = await page.$$eval(".row .r-cat", (els) => els.map((e) => e.dataset.c));
  expect(rowCats).toHaveLength(8);
  expect(new Set(rowCats)).toEqual(new Set(["software", "quant", "realestate", "development", "finance"]));

  await cat(page, "Real estate").click();
  await expect(cat(page, "Real estate")).toHaveAttribute("aria-pressed", "true");
  expect(await titles(page)).toEqual(["Acquisitions Analyst"]);

  await cat(page, "Development").click(); // buttons combine: real estate OR development
  expect((await titles(page)).sort()).toEqual(["Acquisitions Analyst", "Development Associate"]);
  // SF/Chicago/NYC priority still sorts first within the day: Chicago (★) above Houston
  expect(await titles(page)).toEqual(["Acquisitions Analyst", "Development Associate"]);
  await expect(page.locator(".row").first()).toContainText("★");

  await cat(page, "Real estate").click();
  await cat(page, "Development").click();
  await cat(page, "Finance analyst").click();
  expect((await titles(page)).sort()).toEqual(["Financial Analyst II", "Investment Banking Analyst"]);

  // categories combine with the existing filters (here: the search box and Entry level)
  await page.check("#entryonly");
  expect(await titles(page)).toEqual(["Investment Banking Analyst"]);
  await page.uncheck("#entryonly");
  await page.fill("#q", "analyst ii");
  expect(await titles(page)).toEqual(["Financial Analyst II"]);
  await page.fill("#q", "");

  await cat(page, "Finance analyst").click(); // all off again: everything shows
  await cat(page, "Software").click();
  expect((await titles(page)).sort()).toEqual(["Backend Engineer", "Python Engineer", "Software Engineer"]);
  await cat(page, "Quant").click();
  expect(await titles(page)).toContain("Quant Developer");
  await cat(page, "Software").click();
  await cat(page, "Quant").click();
  await expect(page.locator(".row")).toHaveCount(8);
  expect(errors).toEqual([]);
});

test("applying to a real estate job files it under Real Estate on the Applications page", async ({ page }) => {
  await page.goto("/index.html?guest");
  const [popup] = await Promise.all([page.waitForEvent("popup"), page.locator(".row", { hasText: "Acquisitions Analyst" }).click()]);
  await popup.close();
  await page.goto("/stats.html?guest");
  await expect(page.locator("#t-total")).toHaveText("1");
  await expect(page.locator("#by-role")).toContainText("Real Estate");
});
