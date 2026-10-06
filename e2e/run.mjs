// Browser end-to-end test of the real UI against a running stack (frontend :3000, backend :8000).
// Uses the system Microsoft Edge/Chrome via playwright-core (no browser download).
import { chromium } from "playwright-core";
import { existsSync, mkdirSync } from "node:fs";

const BASE = process.env.DISHA_URL || "http://localhost:3000";
const EDGE = [process.env.CHROME_PATH, "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "C:/Program Files/Google/Chrome/Application/chrome.exe", "C:/Program Files/Microsoft/Edge/Application/msedge.exe", "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"].filter(Boolean).find(existsSync);
if (!EDGE) { console.error("No Chrome/Edge found. Set CHROME_PATH."); process.exit(2); }
mkdirSync("screenshots", { recursive: true });

const errors = [];
let failed = 0;
const ok = (c, m) => { console.log(`${c ? "PASS" : "FAIL"}  ${m}`); if (!c) failed++; };

const browser = await chromium.launch({ executablePath: EDGE, headless: true, args: ["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist", "--enable-unsafe-swiftshader"] });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 950 } });
const page = await ctx.newPage();
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => {
  if (m.type() !== "error") return;
  const t = m.text();
  if (/favicon|tile\.openstreetmap|ERR_INTERNET|Failed to load resource.*(404|net::)/i.test(t)) return;
  errors.push(`console: ${t}`);
});

// ---- login
await page.goto(`${BASE}/login`);
await page.getByRole("button", { name: /commander@disha.demo/ }).click();
await page.getByRole("button", { name: "Sign in", exact: true }).click();
await page.waitForURL("**/command-center", { timeout: 20000 });
ok(true, "login as commander -> command centre");

// ---- RUN DISHA DEMO (full loop)
await page.getByRole("button", { name: /Run DISHA demo/i }).first().click();
await page.getByRole("button", { name: "Start demo" }).click();
const t0 = Date.now();
await page.getByText("FIELD VERIFIED · closed loop complete").waitFor({ timeout: 180000 });
const secs = (Date.now() - t0) / 1000;
ok(secs > 20 && secs < 120, `demo loop completed in ${secs.toFixed(0)} s (target 30-90 s)`);
await page.screenshot({ path: "screenshots/01-demo-complete.png" });
const demoText = await page.locator("div.fixed").innerText();
for (const w of ["ALERT", "DETECT", "PRIORITISE", "PREDICT", "PLAN", "DISPATCH", "VERIFY", "RECALCULATED"]) ok(demoText.includes(w), `demo narrative contains ${w}`);
const href = await page.getByRole("link", { name: "Open map" }).getAttribute("href");
const id = href.match(/events\/(\d+)/)[1];
await page.getByRole("button", { name: "Close", exact: true }).click();

// ---- command centre live view
await page.waitForSelector("text=P1 locations", { timeout: 20000 });
await page.screenshot({ path: "screenshots/02-command-centre.png" });
ok(await page.getByText("DEMONSTRATION DATA").count() > 0, "command centre labels demonstration data");

// ---- map: render + click a cell + WHY panel
await page.goto(`${BASE}/events/${id}/map`);
await page.waitForSelector("canvas", { timeout: 20000 });
await page.waitForTimeout(3500);
await page.screenshot({ path: "screenshots/03-map.png" });
ok(await page.getByText("Time slider").count() > 0, "map shows time slider");
ok(await page.getByText("P1 Critical").count() > 0, "map layer panel present");
const box = await page.locator('[data-testid="map"]').boundingBox();
let opened = false;
for (const [fx, fy] of [[0.5, 0.5], [0.45, 0.55], [0.55, 0.45], [0.4, 0.5], [0.6, 0.55], [0.5, 0.65], [0.5, 0.35]]) {
  await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
  await page.waitForTimeout(900);
  if (await page.getByText(/Why is this P\d\?/).count()) { opened = true; break; }
}
ok(opened, "clicking an H3 cell opens the 'Why is this P?' panel");
if (opened) {
  await page.screenshot({ path: "screenshots/04-cell-panel.png" });
  await page.getByRole("button", { name: "Find safest route" }).click();
  await page.getByText("Route comparison").waitFor({ timeout: 20000 });
  ok(true, "FIND SAFEST ROUTE shows route comparison");
  await page.waitForTimeout(800);
  await page.screenshot({ path: "screenshots/05-route.png" });
}
// time machine
await page.getByRole("button", { name: "+6 h" }).click();
await page.waitForSelector("text=ESTIMATE +6h", { timeout: 15000 });
ok(true, "time machine +6 h shows ESTIMATE label");

// ---- every page renders without errors
const pages = [["", "Processing pipeline"], ["/analysis", "Detection result"], ["/priorities", "Impact Priority Index"], ["/predictions", "Risk prediction"], ["/resources", "Resource command"],
  ["/routes", "Rescue route optimiser"], ["/shelters", "Evacuation planner"], ["/field", "Field mode"], ["/reports", "Reports & exports"], ["/timeline", "Incident timeline"], ["/present", "Live DISHA demonstration"]];
for (const [p, text] of pages) {
  await page.goto(`${BASE}/events/${id}${p}`);
  try { await page.getByText(text, { exact: false }).first().waitFor({ timeout: 20000 }); ok(true, `page /events/${id}${p || ""} renders "${text}"`); }
  catch { ok(false, `page /events/${id}${p} did not render "${text}"`); }
  await page.waitForTimeout(500);
}
await page.screenshot({ path: "screenshots/06-present.png" });
for (const [p, text] of [["/dashboard", "Dashboard"], ["/events", "Events"], ["/events/new", "New event"], ["/copilot", "DISHA Copilot"], ["/settings", "Alert engine"], ["/command-center", "Command Centre"]]) {
  await page.goto(`${BASE}${p}`);
  try { await page.getByText(text).first().waitFor({ timeout: 15000 }); ok(true, `page ${p} renders`); } catch { ok(false, `page ${p} did not render "${text}"`); }
}

// ---- copilot
await page.goto(`${BASE}/copilot`);
await page.getByLabel("Ask DISHA Copilot").fill("Which areas should we rescue first?");
await page.getByRole("button", { name: "Ask", exact: true }).click();
await page.getByText(/P1 locations/).first().waitFor({ timeout: 20000 });
ok(true, "copilot answers from event data");
await page.getByLabel("Ask DISHA Copilot").fill("What is the capital of France?");
await page.getByRole("button", { name: "Ask", exact: true }).click();
await page.getByText("DISHA does not currently have sufficient data to determine this.").waitFor({ timeout: 20000 });
ok(true, "copilot refuses to hallucinate");
await page.screenshot({ path: "screenshots/07-copilot.png" });

// ---- RBAC in UI: observer cannot analyse
await page.evaluate(() => localStorage.clear());
await page.goto(`${BASE}/login`);
await page.getByRole("button", { name: /observer@disha.demo/ }).click();
await page.getByRole("button", { name: "Sign in", exact: true }).click();
await page.waitForURL("**/command-center");
ok(await page.getByRole("button", { name: /Run DISHA demo/i }).count() === 0, "observer has no 'Run demo' control");

ok(errors.length === 0, `no browser console/page errors (${errors.length})`);
errors.slice(0, 15).forEach((e) => console.log("   ", e.slice(0, 300)));
await browser.close();
console.log(failed ? `\n${failed} CHECK(S) FAILED` : "\nALL E2E CHECKS PASSED");
process.exit(failed ? 1 : 0);
