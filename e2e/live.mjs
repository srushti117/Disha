// Real-data run through the actual UI: create the real Kuttanad 2018 event, analyse it, screenshot the results.
import { chromium } from "playwright-core";
import { existsSync, mkdirSync } from "node:fs";

const BASE = process.env.DISHA_URL || "http://localhost:3000";
const EDGE = ["C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "C:/Program Files/Google/Chrome/Application/chrome.exe"].find(existsSync);
mkdirSync("screenshots", { recursive: true });
const errors = [];
const browser = await chromium.launch({ executablePath: EDGE, headless: true, args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const page = await (await browser.newContext({ viewport: { width: 1560, height: 940 } })).newPage();
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => { if (m.type() === "error" && !/favicon|openstreetmap|ERR_|Failed to load resource/i.test(m.text())) errors.push(m.text()); });

await page.goto(`${BASE}/login`);
await page.screenshot({ path: "screenshots/R0-login.png" });
await page.getByRole("button", { name: /commander@disha.demo/ }).click();
await page.getByRole("button", { name: "Sign in", exact: true }).click();
await page.waitForURL("**/command-center");
await page.goto(`${BASE}/events`);
await page.getByText("Kerala floods 2018 - Kuttanad (real data)").first().click();
await page.waitForURL(/\/events\/\d+$/, { timeout: 30000 });
const id = page.url().match(/events\/(\d+)/)[1];
console.log("event", id);
await page.getByRole("button", { name: "Analyse event" }).first().click();
const t0 = Date.now();
await page.getByText("Real data").first().waitFor();
// wait for analysis to finish: the Re-analyse button appears
await page.getByRole("button", { name: "Re-analyse" }).waitFor({ timeout: 600000 });
console.log("analysis seconds", ((Date.now() - t0) / 1000).toFixed(0));
await page.waitForTimeout(1500);
await page.screenshot({ path: "screenshots/R1-overview.png", fullPage: false });
await page.goto(`${BASE}/events/${id}/map`);
await page.waitForSelector("canvas");
await page.getByText("Sentinel-2 true colour").first().click();   // real satellite layer on
await page.waitForTimeout(6000);
await page.screenshot({ path: "screenshots/R2-map-optical.png" });
await page.getByText("Sentinel-2 true colour").first().click();   // off, show detection over OSM
await page.waitForTimeout(5000);
const box = await page.locator('[data-testid="map"]').boundingBox();
for (const [fx, fy] of [[0.5, 0.5], [0.45, 0.5], [0.55, 0.5], [0.5, 0.4], [0.5, 0.6], [0.4, 0.45], [0.6, 0.55]]) {
  await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
  await page.waitForTimeout(900);
  if (await page.getByText(/Why is this P\d\?/).count()) break;
}
await page.screenshot({ path: "screenshots/R3-map-cell.png" });
for (const p of ["analysis", "priorities", "resources", "reports"]) { await page.goto(`${BASE}/events/${id}/${p}`); await page.waitForTimeout(2500); await page.screenshot({ path: `screenshots/R4-${p}.png` }); }
await page.goto(`${BASE}/guide`); await page.waitForTimeout(800); await page.screenshot({ path: "screenshots/R5-guide.png" });
console.log("errors:", errors.length, errors.slice(0, 5));
await browser.close();
