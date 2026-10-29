// Guest mode never touches the owner's real tracker, and "Reset everything" clears every store.
import { test, expect } from "@playwright/test";

const PAGES = ["index.html", "stats.html", "pipeline.html", "companies.html", "recruiters.html"];

// The owner's real data: every store the site keeps, plus a future nj-* store and an unrelated key.
const REAL = {
  "nj-apps": JSON.stringify([
    { key: "greenhouse:acme:0", company: "Acme", title: "Software Engineer", role: "Software Engineer", tags: ["tech"],
      url: "https://example.com/jobs/0", ts: "2026-10-20T12:00:00.000Z" },
    { key: "greenhouse:bolt:2", company: "Bolt", title: "Backend Engineer", role: "Software Engineer", tags: ["tech"],
      url: "https://example.com/jobs/2", ts: "2026-10-21T12:00:00.000Z" },
  ]),
  "nj-dismissed": JSON.stringify(["greenhouse:cog:3"]),
  "nj-status": JSON.stringify({ Acme: "Interviewing" }),
  "nj-future-store": JSON.stringify({ any: "thing" }),
  "unrelated-site-key": "keep me",
};

const errors = [];
test.beforeEach(async ({ page }) => {
  errors.length = 0;
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && !/favicon/.test(m.text()) && errors.push(m.text()));
});
test.afterEach(() => expect(errors, "console errors").toEqual([]));

async function seedReal(page) {
  await page.goto("/index.html");
  await page.evaluate((real) => { localStorage.clear(); for (const [k, v] of Object.entries(real)) localStorage.setItem(k, v); }, REAL);
}
const localDump = (page) => page.evaluate(() => Object.fromEntries(Object.keys(localStorage).sort().map((k) => [k, localStorage.getItem(k)])));

test("a guest session starts empty, stays guest on every page, and leaves the real data byte-for-byte identical", async ({ page }) => {
  await seedReal(page);
  const before = await localDump(page);
  expect(Object.keys(before)).toHaveLength(5);

  // every page in guest mode: empty tracker, a guest pill, and every internal link keeps ?guest
  for (const p of PAGES) {
    await page.goto(`/${p}?guest`);
    await expect(page.locator(".guest-pill")).toHaveText("guest");
    const internal = await page.$$eval("nav.tabs a", (as) => as.map((a) => a.getAttribute("href")));
    expect(internal.length).toBeGreaterThan(0);
    for (const href of internal) expect(href, `${p} link ${href}`).toMatch(/\?guest$/);
  }
  await page.goto("/index.html?guest");
  await expect(page.locator(".row")).toHaveCount(4); // no dismissed job hidden: the guest has dismissed nothing
  await expect(page.locator("#s-apps")).toHaveText("0");
  await expect(page.locator("#nav-count")).toHaveText("0");
  await page.goto("/stats.html?guest");
  await expect(page.locator("#t-total")).toHaveText("0");
  await page.goto("/pipeline.html?guest");
  await expect(page.locator(".pstatus")).toHaveCount(0); // no applications -> no pipeline rows, no statuses

  // the guest uses the tracker: apply, dismiss, set a pipeline status, navigating only by the site's own links
  await page.goto("/index.html?guest");
  const [popup] = await Promise.all([page.waitForEvent("popup"), page.locator(".row", { hasText: "Quant Developer" }).click()]);
  await popup.close();
  await page.locator(".row", { hasText: "Python Engineer" }).locator(".r-trash").click();
  await expect(page.locator("#s-apps")).toHaveText("1");
  await page.locator("nav.tabs a", { hasText: "Pipeline" }).click();
  await expect(page).toHaveURL(/pipeline\.html\?guest$/);
  await page.locator(".pstatus").first().selectOption({ index: 2 });
  await page.locator("nav.tabs a", { hasText: "Applications" }).click();
  await expect(page).toHaveURL(/stats\.html\?guest$/);
  await expect(page.locator("#t-total")).toHaveText("1");

  // the real localStorage never changed while the guest worked
  expect(await localDump(page)).toEqual(before);

  // leave guest mode (the pill is the way out): the real data is all there, untouched
  await page.locator(".guest-pill").click();
  await expect(page).toHaveURL(/stats\.html$/);
  await expect(page.locator(".guest-pill")).toHaveCount(0);
  await expect(page.locator("#t-total")).toHaveText("2");
  await page.goto("/index.html");
  await expect(page.locator("#s-apps")).toHaveText("2");
  await expect(page.locator(".row")).toHaveCount(3); // the owner's dismissed job is still hidden
  expect(await localDump(page)).toEqual(before);
});

test("a guest's 'Reset everything' only clears the guest session", async ({ page }) => {
  await seedReal(page);
  const before = await localDump(page);
  await page.goto("/index.html?guest");
  const [popup] = await Promise.all([page.waitForEvent("popup"), page.locator(".row").first().click()]);
  await popup.close();
  await page.goto("/stats.html?guest");
  await expect(page.locator("#t-total")).toHaveText("1");
  await page.locator("#reset").click();
  await expect(page.locator("#reset-what")).toHaveText("Clears this guest session: 1 application, 0 dismissed jobs, 0 pipeline statuses.");
  await page.locator("#reset-confirm").click();
  await expect(page.locator("#t-total")).toHaveText("0");
  expect(await localDump(page)).toEqual(before);
});

test("'Reset everything' offers an export, asks first, and then clears every store (only this site's)", async ({ page }) => {
  await seedReal(page);
  await page.goto("/stats.html");
  await expect(page.locator("#t-total")).toHaveText("2");

  // nothing happens until confirmed; cancel leaves everything
  await page.locator("#reset").click();
  await expect(page.locator("#reset-box")).toBeVisible();
  await expect(page.locator("#reset-what")).toHaveText(
    "Deletes everything this browser has saved for new-jobs: 2 applications, 1 dismissed job, 1 pipeline status, 1 other saved setting.");
  await page.locator("#reset-cancel").click();
  await expect(page.locator("#reset-box")).toBeHidden();
  expect(Object.keys(await localDump(page))).toHaveLength(5);

  // the export holds every store
  await page.locator("#reset").click();
  const [dl] = await Promise.all([page.waitForEvent("download"), page.locator("#reset-export").click()]);
  expect(dl.suggestedFilename()).toMatch(/^new-jobs-backup-\d{4}-\d{2}-\d{2}\.json$/);
  const backup = JSON.parse(await (await dl.createReadStream()).toArray().then((c) => Buffer.concat(c).toString()));
  expect(Object.keys(backup).sort()).toEqual(["nj-apps", "nj-dismissed", "nj-future-store", "nj-status"]);
  expect(backup["nj-apps"]).toHaveLength(2);

  // confirm: every nj-* store is gone, the unrelated key is kept, and every page shows an empty tracker
  await page.locator("#reset-confirm").click();
  expect(await localDump(page)).toEqual({ "unrelated-site-key": "keep me" });
  await expect(page.locator("#t-total")).toHaveText("0");
  await page.goto("/index.html");
  await expect(page.locator("#s-apps")).toHaveText("0");
  await expect(page.locator(".row")).toHaveCount(4); // no dismissed jobs any more
  await page.goto("/pipeline.html");
  await expect(page.locator(".pstatus")).toHaveCount(0);
});
