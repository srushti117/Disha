// Captures documentation screenshots of the running app (used to build the project PDF).
import { chromium } from "playwright-core";
import { existsSync, mkdirSync, readFileSync } from "node:fs";

const BASE = process.env.DISHA_URL || "http://localhost:3000";
const OUT = "../docs/pdf_assets/shots";
mkdirSync(OUT, { recursive: true });
const ids = JSON.parse(readFileSync("../docs/pdf_assets/ids.json", "utf8"));
const EXE = [process.env.CHROME_PATH, "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "C:/Program Files/Google/Chrome/Application/chrome.exe", "/usr/bin/google-chrome"].filter(Boolean).find(existsSync);
const browser = await chromium.launch({ executablePath: EXE, headless: true, args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const page = await (await browser.newContext({ viewport: { width: 1500, height: 900 } })).newPage();
const snap = async (name, opts = {}) => { await page.waitForTimeout(opts.wait ?? 1200); await page.screenshot({ path: `${OUT}/${name}.jpg`, type: "jpeg", quality: 84, fullPage: !!opts.full }); console.log("shot", name); };
const go = async (path, wait) => { await page.goto(`${BASE}${path}`); await page.waitForLoadState("networkidle").catch(() => {}); await page.waitForTimeout(wait ?? 1500); };
const K = ids.kuttanad, S = ids.sindh, M = ids.sim;

// ---- login page, then sign in
await page.goto(`${BASE}/login`); await snap("01_login");
await page.getByRole("button", { name: /commander@disha.demo/ }).click();
await page.getByRole("button", { name: "Sign in", exact: true }).click();
await page.waitForURL("**/command-center");

// ---- command centre (real event) + events list + new event
await page.evaluate((id) => localStorage.setItem("disha_event", String(id)), K);
await go("/command-center", 5000); await snap("02_command_centre");
await go("/events", 1500); await snap("03_events");
await go("/events/new", 1500); await page.getByText("Kerala floods 2018 - Kuttanad (real data)").first().waitFor().catch(() => {}); await snap("04_new_event_scenarios");
await page.getByRole("button", { name: "Coordinates" }).click().catch(() => {}); await snap("05_new_event_coordinates");

// ---- Kuttanad (real): overview
await go(`/events/${K}`); await snap("10_overview");
await page.getByText("Data sources and method").click().catch(() => {}); await page.getByText("Analysis steps").click().catch(() => {}); await snap("11_overview_expanded", { full: true });

// ---- map: satellite image, detection + priority, P1 cell panel, +6 h
await go(`/events/${K}/map`, 6000);
await page.getByText("Satellite image").first().click(); await snap("20_map_satellite", { wait: 5000 });
await page.getByText("Satellite image").first().click(); await snap("21_map_streets", { wait: 4000 });
const box = await page.locator('[data-testid="map"]').boundingBox();
let found = false;
for (let fy = 0.2; fy <= 0.95 && !found; fy += 0.04) for (let fx = 0.12; fx <= 0.6 && !found; fx += 0.04) {
  await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy); await page.waitForTimeout(260);
  if (await page.getByText("Why is this P1?").count()) found = true;
}
console.log("P1 cell found:", found);
await snap("22_map_p1_cell", { wait: 800 });
await page.getByRole("button", { name: "Find safest route" }).click().catch(() => {}); await page.getByText("Compare all routes").waitFor({ timeout: 20000 }).catch(() => {}); await snap("23_map_route", { wait: 1500 });
await page.getByText("More details").click().catch(() => {}); await snap("24_cell_more_details", { wait: 800 });
await page.getByRole("button", { name: "+6 h", exact: true }).click().catch(() => {}); await snap("25_map_plus6h", { wait: 3000 });
await page.getByText("More layers…").click().catch(() => {}); await snap("26_map_more_layers", { wait: 800 });

// ---- other pages
await go(`/events/${K}/analysis`, 3000); await snap("30_analysis", { full: true });
await go(`/events/${K}/priorities?cell=1`, 2500); await snap("31_priorities");
await go(`/events/${K}/predictions`, 2500); await snap("32_predictions");
await go(`/events/${K}/routes`, 4000); await page.getByRole("button", { name: "Find safest route" }).click(); await page.waitForTimeout(3500); await snap("33_routes");
await go(`/events/${K}/shelters`, 2500); await snap("34_shelters");
await go(`/events/${K}/resources`, 2000); await page.getByRole("button", { name: "Plan resources" }).click(); await page.waitForTimeout(4000); await snap("35_resources_plan");
await page.getByRole("button", { name: "Dispatch", exact: true }).click().catch(() => {}); await page.waitForTimeout(2500); await snap("36_resources_dispatched");
await go(`/events/${K}/field`, 2500); await snap("37_field_missions");
await page.getByRole("button", { name: "Severe · flood water" }).click().catch(() => {}); await page.getByText("FIELD VERIFIED").waitFor({ timeout: 20000 }).catch(() => {}); await snap("38_field_verified", { wait: 1500, full: true });
await go(`/events/${K}`, 2500); await page.getByText("What changed since the last assessment").click().catch(() => {}); await snap("39_overview_after_field", { full: true });
await go(`/events/${K}/reports`, 2000); await snap("40_reports");
await go(`/events/${K}/timeline`, 2500); await snap("41_timeline", { full: true });
await go("/copilot", 2500);
for (const q of ["Which areas should we rescue first?", "Which hospital is most at risk?", "What is the capital of France?"]) {
  await page.getByLabel("Ask DISHA Copilot").fill(q); await page.getByRole("button", { name: "Ask", exact: true }).click(); await page.waitForTimeout(1800);
}
await snap("42_copilot", { wait: 800 });
await go("/guide", 1500); await snap("43_guide", { full: true });
await go("/dashboard", 2500); await snap("44_dashboard");
await go("/settings", 2500); await snap("45_settings", { full: true });

// ---- Sindh (real): satellite + detection
await go(`/events/${S}/map`, 6000);
await page.getByText("Satellite image").first().click(); await snap("50_sindh_map_satellite", { wait: 5000 });
await page.getByText("Satellite image").first().click(); await snap("51_sindh_map_detection", { wait: 3500 });
await go(`/events/${S}`, 2500); await snap("52_sindh_overview");

// ---- simulated demo event: command centre + presentation mode + guided demo
await page.evaluate((id) => localStorage.setItem("disha_event", String(id)), M);
await go(`/events/${M}/present`, 3500); await page.getByRole("button", { name: /Show priority/ }).click(); await page.waitForTimeout(3000); await snap("60_presentation_priority", { wait: 1500 });
await page.getByRole("button", { name: /Show prediction/ }).click(); await page.waitForTimeout(4000); await snap("61_presentation_prediction", { wait: 1500 });
await page.getByRole("button", { name: /Show route/ }).click(); await page.waitForTimeout(4500); await snap("62_presentation_route", { wait: 1500 });
await go("/command-center", 5000); await snap("63_command_centre_simulated");
await page.getByRole("button", { name: "Run guided demo" }).click(); await page.getByRole("button", { name: "Start demo" }).click();
await page.getByText("FIELD VERIFIED · closed loop complete").waitFor({ timeout: 240000 }); await snap("64_guided_demo_done", { wait: 1000 });
await browser.close();
console.log("done");
