import { chromium } from "playwright-core";
import { existsSync } from "node:fs";
const EXE = ["C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe", "C:/Program Files/Google/Chrome/Application/chrome.exe", "/usr/bin/google-chrome"].find(existsSync);
const browser = await chromium.launch({ executablePath: EXE, headless: true });
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
for (const [name, url] of [["70_github_repo", "https://github.com/srushti117/Disha"], ["71_github_actions", "https://github.com/srushti117/Disha/actions?query=branch%3Amain"], ["72_github_commits", "https://github.com/srushti117/Disha/commits/main"]]) {
  await page.goto(url, { waitUntil: "domcontentloaded" }); await page.waitForTimeout(3500);
  await page.screenshot({ path: `../docs/pdf_assets/shots/${name}.jpg`, type: "jpeg", quality: 84 }); console.log("shot", name);
}
await browser.close();
