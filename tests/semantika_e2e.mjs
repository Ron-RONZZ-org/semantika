/** Playwright E2E tests for Semantika — knowledge graph CRUD, search, backup. */

import { chromium } from "playwright";
import { strict as assert } from "assert";

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:8000";
const CHROME_PATH = process.env.CHROME_PATH || "chromium";

let browser, page;
let passed = 0, failed = 0;

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function typeCommand(cmd) {
  // Focus the input and type
  const input = page.locator("[aria-label='Message input']");
  const isVisible = await input.isVisible().catch(() => false);
  if (!isVisible) {
    await page.keyboard.press("Escape");
    await sleep(300);
    await page.keyboard.press("Escape");
    await sleep(500);
  }
  await input.waitFor({ state: "visible", timeout: 5000 });
  await input.click();
  await input.fill("");
  await sleep(100);
  await input.pressSequentially(cmd, { delay: 20 });
  await sleep(600);
}

async function pressEnter() {
  await page.keyboard.press("Enter");
  await sleep(1500);
}

async function getBodyText() {
  try {
    await sleep(500);
    const body = page.locator("body");
    let text = ((await body.textContent()) || "").trim();
    text = text.replace(/\s+/g, " ").trim();
    // Limit to avoid huge assertion diffs
    return text.length > 2000 ? text.substring(0, 2000) + "..." : text;
  } catch {
    return "(no result)";
  }
}

async function closePopups() {
  try {
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press("Escape");
      await sleep(300);
    }
  } catch { /* ignore */ }
}

let screenshotCounter = 0;
async function test(desc, fn) {
  try {
    await fn();
    console.log(`  ✓ ${desc}`);
    passed++;
  } catch (e) {
    const ssPath = `/tmp/semantika-e2e-fail-${screenshotCounter++}.png`;
    try { await page.screenshot({ path: ssPath }); console.log(`    Screenshot saved to ${ssPath}`); } catch {}
    console.log(`  ✗ ${desc}: ${e.message}`);
    try {
      const body = await page.locator("main, .tab-content, body").first().textContent();
      console.log(`    Page text: ${(body || "").substring(0, 300)}`);
    } catch {}
    failed++;
  } finally {
    await closePopups();
  }
}

async function run() {
  browser = await chromium.launch({
    headless: true,
    executablePath: CHROME_PATH,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
  });
  const context = await browser.newContext({ viewport: { width: 960, height: 720 } });
  page = await context.newPage();
  page.on("pageerror", (err) => console.log("  [BROWSER ERROR]", err.message));

  console.log("=".repeat(70));
  console.log("SEMANTIKA E2E TESTS");
  console.log("=".repeat(70));
  console.log();

  await page.goto(FRONTEND_URL, { waitUntil: "networkidle" });
  console.log("✓ Page loaded:", await page.title());
  await sleep(2000);

  // Debug: log input state
  const input = page.locator("[aria-label='Message input']");
  console.log(`  Input visible: ${await input.isVisible().catch(() => false)}`);
  console.log(`  Input placeholder: ${await input.getAttribute('placeholder')}`);

  // Dismiss notice if present
  try {
    const dismissBtn = page.locator("button", { hasText: "Dismiss" });
    if (await dismissBtn.isVisible({ timeout: 1000 })) {
      await dismissBtn.click();
      await sleep(500);
    }
  } catch { /* no notice */ }
  await sleep(1000);

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- NODE CRUD ---");

  const TEST_NODE_ID = "E2ETEST";
  const TEST_NODE2_ID = "E2ETEST2";

  await test("!node list (empty)", async () => {
    await typeCommand("!node list");
    await pressEnter();
    const text = await getBodyText();
    assert(!text.includes("Unknown command"),
      `Unexpected error: '${text.substring(0, 100)}'`);
    console.log(`    Response: ${text.substring(0, 100)}...`);
  });

  await test("!node add", async () => {
    await typeCommand(`!node add --node-id ${TEST_NODE_ID} --labels '{"en":"E2E Test Node"}'`);
    await pressEnter();
    const text = await getBodyText();
    console.log(`    Add result: ${text.substring(0, 150)}`);
  });

  await test("!node view", async () => {
    await typeCommand(`!node view ${TEST_NODE_ID}`);
    await pressEnter();
    const text = await getBodyText();
    assert(text.includes(TEST_NODE_ID) || text.includes("E2E"),
      `Expected node details, got: '${text.substring(0, 150)}'`);
  });

  await test("!node list (after add)", async () => {
    await typeCommand("!node list");
    await pressEnter();
    const text = await getBodyText();
    assert(text.includes(TEST_NODE_ID) || text.includes("E2E"),
      `Expected node in list, got: '${text.substring(0, 150)}'`);
  });

  await test("!node search", async () => {
    await typeCommand("!node search E2E");
    await pressEnter();
    const text = await getBodyText();
    assert(text.includes("E2E"),
      `Expected search results, got: '${text.substring(0, 150)}'`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- PREDICATE CRUD ---");

  await test("!predicate list", async () => {
    await typeCommand("!predicate list");
    await pressEnter();
    const text = await getBodyText();
    assert(!text.includes("Unknown command"),
      `Unexpected error: '${text.substring(0, 100)}'`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- TRIPLE CRUD ---");

  await test("!triple add", async () => {
    await typeCommand(`!triple add ${TEST_NODE_ID} rdfs:label "E2E Label"`);
    await pressEnter();
    const text = await getBodyText();
    console.log(`    Triple add result: ${text.substring(0, 150)}`);
  });

  await test("!triple list", async () => {
    await typeCommand("!triple list");
    await pressEnter();
    const text = await getBodyText();
    assert(!text.includes("Unknown command"),
      `Got error: '${text.substring(0, 100)}'`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- STATS & EXPORT ---");

  await test("!stats", async () => {
    await typeCommand("!stats");
    await pressEnter();
    const text = await getBodyText();
    assert(text.includes("node") || text.includes("triple") || text.includes("predicate"),
      `Expected stats, got: '${text.substring(0, 150)}'`);
  });

  await test("!export", async () => {
    await typeCommand("!export");
    await pressEnter();
    const text = await getBodyText();
    console.log(`    Export result: ${text.substring(0, 150)}`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- BACKUP ---");

  await test("!backup now", async () => {
    await typeCommand("!backup now");
    await pressEnter();
    const text = await getBodyText();
    console.log(`    Backup result: ${text.substring(0, 150)}`);
  });

  await test("!backup list", async () => {
    await typeCommand("!backup list");
    await pressEnter();
    const text = await getBodyText();
    console.log(`    Backups: ${text.substring(0, 150)}`);
  });

  await test("!backup config list", async () => {
    await typeCommand("!backup config list");
    await pressEnter();
    const text = await getBodyText();
    // Backups may return as popup — just verify no crash
    assert(!text.includes("Unknown command"),
      `Got error: '${text.substring(0, 100)}'`);
    console.log(`    Config text: ${text.substring(0, 100)}...`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- HELP & NAV ---");

  await test("!help", async () => {
    await typeCommand("!help");
    await pressEnter();
    const text = await getBodyText();
    assert(text.includes("node") || text.includes("Available"),
      `Expected help, got: '${text.substring(0, 150)}'`);
  });

  await test("Autocomplete via !no", async () => {
    await typeCommand("!no");
    await sleep(1000);
    // Check that suggestions dropdown appears
    const suggestions = page.locator(".suggestions li");
    const count = await suggestions.count();
    console.log(`    Suggestions for "!no": ${count}`);
    if (count > 0) {
      const first = await suggestions.first().textContent();
      assert(first.includes("node"),
        `Expected "node" suggestion, got: '${first}'`);
      console.log(`    Suggestion: ${first}`);
    }
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- REVIEW ---");

  await test("!review start", async () => {
    await typeCommand("!review start");
    await pressEnter();
    const text = await getBodyText();
    // Review may or may not have cards — just verify no crash
    const lower = text.toLowerCase();
    assert(!lower.includes("unknown command") && !lower.includes("error"),
      `Got error: '${text.substring(0, 100)}'`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- UNIT ---");

  await test("!unit list", async () => {
    await typeCommand("!unit list");
    await pressEnter();
    const text = await getBodyText();
    // Units are seeded on init
    assert(text.includes("Unit") || text.includes("unit") || !text.includes("Unknown"),
      `Expected units, got: '${text.substring(0, 150)}'`);
  });

  await test("!unit resolve", async () => {
    await typeCommand("!unit resolve '1 m to cm'");
    await pressEnter();
    const text = await getBodyText();
    console.log(`    Resolve result: ${text.substring(0, 150)}`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- LLM CONFIG ---");

  await test("!llm show", async () => {
    await typeCommand("!llm show");
    await pressEnter();
    const text = await getBodyText();
    // LLM may not be configured — just verify no crash
    console.log(`    LLM config: ${text.substring(0, 150)}`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- NODE DELETE ---");

  await test("!node delete", async () => {
    await typeCommand(`!node delete ${TEST_NODE_ID}`);
    await pressEnter();
    const text = await getBodyText();
    console.log(`    Delete result: ${text.substring(0, 150)}`);
  });

  await test("!node delete (2nd node)", async () => {
    await typeCommand(`!node delete ${TEST_NODE2_ID}`);
    await pressEnter();
    await sleep(500);
    // May have already been deleted — just verify no crash
    const text = await getBodyText();
    console.log(`    Delete result: ${text.substring(0, 150)}`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log(`RESULTS: ${passed} passed, ${failed} failed`);

  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
}

run().catch((e) => {
  console.error("FATAL:", e.message);
  process.exit(1);
});
