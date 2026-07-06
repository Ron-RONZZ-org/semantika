/** Comprehensive Playwright E2E tests for Semantika.
 *
 * Covers every command in the tree with all flag/option variations,
 * GUI interaction (tabs, forms, popups), CLI→GUI routing, and LLM endpoints.
 *
 * Optimized for fast execution: minimal sleep, compact operations.
 */

import { chromium } from "playwright";
import { strict as assert } from "assert";

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:8000";
const CHROME_PATH = process.env.CHROME_PATH || "chromium";

let browser, page;
let passed = 0, failed = 0;
let browserErrors = [];

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function typeAndRun(cmd) {
  const input = page.locator("[aria-label='Message input']");
  await ensureInputVisible();
  await input.waitFor({ state: "visible", timeout: 5000 });
  await input.click();
  await input.fill("");
  await sleep(20);
  await input.pressSequentially(cmd, { delay: 3 });
  await sleep(200);
  await input.press("Enter");
  await sleep(600);
}

async function ensureInputVisible() {
  const input = page.locator("[aria-label='Message input']");
  for (let attempt = 0; attempt < 10; attempt++) {
    const vis = await input.isVisible().catch(() => false);
    if (vis) return true;
    try {
      const tabClose = page.locator(".tab-close").first();
      if (await tabClose.isVisible({ timeout: 300 }).catch(() => false)) {
        await tabClose.click({ timeout: 500 });
        await sleep(300);
        continue;
      }
    } catch {}
    try {
      const homeTabBtn = page.locator('button[role="tab"]', { hasText: "Home" });
      if (await homeTabBtn.isVisible({ timeout: 200 }).catch(() => false)) {
        await homeTabBtn.click();
        await sleep(300);
        continue;
      }
    } catch {}
    await page.keyboard.press("Escape");
    await sleep(250);
  }
  return await input.isVisible().catch(() => false);
}

async function closeResult() {
  await ensureInputVisible();
}

function collectBrowserErrors() {
  const errs = [...browserErrors];
  browserErrors = [];
  return errs;
}

async function verifyNoCrash() {
  if (browserErrors.length > 0) {
    const errs = collectBrowserErrors();
    assert(false, `Browser errors: ${errs.join("; ")}`);
  }
}

async function verifyResultContains(text) {
  await sleep(150);
  const body = page.locator("body");
  const bodyText = await body.textContent();
  assert.ok(
    bodyText.includes(text),
    `Page should contain "${text}", got: ${(bodyText || "").slice(0, 200)}`,
  );
}

async function screenshotOnFail(desc) {
  const ssPath = `/tmp/semantika-full-e2e-fail-${Date.now()}.png`;
  try { await page.screenshot({ path: ssPath }); console.log(`    Screenshot: ${ssPath}`); } catch {}
}

let testIdx = 0;
async function test(desc, fn) {
  testIdx++;
  browserErrors = [];
  try {
    await fn();
    await verifyNoCrash();
    console.log(`  ✓ ${desc}`);
    passed++;
  } catch (e) {
    await screenshotOnFail(desc);
    console.log(`  ✗ ${desc}: ${e.message}`);
    if (browserErrors.length) console.log(`    JS errors: ${browserErrors.join("; ")}`);
    failed++;
  } finally {
    await closeResult();
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
  page.on("pageerror", (err) => {
    browserErrors.push(err.message);
    console.log("  [BROWSER ERROR]", err.message);
  });
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const text = msg.text();
      if (text.includes("Failed to load resource")) return;
      browserErrors.push(`console.error: ${text}`);
    }
  });

  console.log("=".repeat(70));
  console.log("SEMANTIKA — FULL COVERAGE E2E");
  console.log("=".repeat(70));
  console.log();

  await page.goto(FRONTEND_URL, { waitUntil: "networkidle" });
  console.log("✓ Page loaded:", await page.title());
  await sleep(1500);

  // Dismiss initial notice
  try {
    const btn = page.locator("button", { hasText: "Dismiss" });
    if (await btn.isVisible({ timeout: 500 })) { await btn.click(); await sleep(300); }
  } catch { /* */ }

  // ═══════════════════════════════════════════
  //  NODE — full flag coverage
  // ═══════════════════════════════════════════
  console.log("\n═══ NODE — full options ═══");

  await test("!node add with --copy", async () => {
    await typeAndRun('!node add --node-id FTest1 --labels \'{"en":"Full Test 1"}\' --copy');
  });
  await test("!node add auto-generated ID", async () => {
    await typeAndRun('!node add --labels \'{"en":"Full Test 2"}\'');
  });
  await test("!node list with limit", async () => {
    await typeAndRun("!node list 50");
    await verifyResultContains("FTest1");
  });
  await test("!node search", async () => {
    await typeAndRun("!node search 'Full Test'");
  });
  await test("!node view", async () => {
    await typeAndRun("!node view FTest1");
  });
  await test("!node update labels", async () => {
    await typeAndRun('!node update FTest1 --labels \'{"en":"Updated Full Test 1"}\'');
  });
  await test("!node update --new-id", async () => {
    await typeAndRun("!node update FTest1 --new-id FTestRenamed");
  });
  await test("!node rename back", async () => {
    await typeAndRun("!node rename FTestRenamed FTest1");
  });
  await test("!node delete", async () => {
    await typeAndRun("!node delete FTest1");
  });

  // ═══════════════════════════════════════════
  //  PREDICATE — full coverage
  // ═══════════════════════════════════════════
  console.log("\n═══ PREDICATE — full options ═══");

  await test("!predicate view", async () => {
    await typeAndRun("!predicate view rdfs:label");
  });
  await test("!predicate search", async () => {
    await typeAndRun("!predicate search rdfs");
  });
  await test("!predicate add", async () => {
    await typeAndRun("!predicate add ex:fullTestPred");
  });
  await test("!predicate update with labels", async () => {
    await typeAndRun('!predicate update ex:fullTestPred --labels \'{"en":"Full Test Predicate"}\'');
  });
  await test("!predicate rename", async () => {
    await typeAndRun("!predicate rename ex:fullTestPred ex:fullPredRenamed");
  });
  await test("!predicate rename back", async () => {
    await typeAndRun("!predicate rename ex:fullPredRenamed ex:fullTestPred");
  });
  await test("!predicate delete", async () => {
    await typeAndRun("!predicate delete ex:fullTestPred");
  });

  // ═══════════════════════════════════════════
  //  PREDICATE GROUP — full coverage
  // ═══════════════════════════════════════════
  console.log("\n═══ PREDICATE GROUP ═══");

  await test("!predicate group list", async () => {
    await typeAndRun("!predicate group list");
  });
  await test("!predicate group add", async () => {
    await typeAndRun("!predicate group add ft-group");
  });
  await test("!predicate group search", async () => {
    await typeAndRun("!predicate group search ft-group");
  });
  await test("!predicate group add-member", async () => {
    await typeAndRun("!predicate group add-member ft-group rdfs:label");
  });
  await test("!predicate group view", async () => {
    await typeAndRun("!predicate group view ft-group");
  });
  await test("!predicate group remove-member", async () => {
    await typeAndRun("!predicate group remove-member ft-group rdfs:label");
  });
  await test("!predicate group rename", async () => {
    await typeAndRun("!predicate group rename ft-group ft-group-ren");
  });
  await test("!predicate group rename back", async () => {
    await typeAndRun("!predicate group rename ft-group-ren ft-group");
  });
  await test("!predicate group delete", async () => {
    await typeAndRun("!predicate group delete ft-group");
  });

  // ═══════════════════════════════════════════
  //  TRIPLE — full coverage
  // ═══════════════════════════════════════════
  console.log("\n═══ TRIPLE — full options ═══");

  await test("(setup) !node add for triples", async () => {
    await typeAndRun('!node add --node-id TSubj --labels \'{"en":"Triple Subj"}\'');
  });
  await test("!triple add URI triple", async () => {
    await typeAndRun("!triple add TSubj rdfs:label 'Test Triple'");
  });
  await test("!triple add --int", async () => {
    await typeAndRun("!triple add TSubj ex:count 42 --int");
  });
  await test("!triple add --float", async () => {
    await typeAndRun("!triple add TSubj ex:ratio 3.14 --float");
  });
  await test("!triple add --bool", async () => {
    await typeAndRun("!triple add TSubj ex:active true --bool");
  });
  await test("!triple list", async () => {
    await typeAndRun("!triple list");
  });
  await test("!triple search", async () => {
    await typeAndRun("!triple search TSubj");
  });
  await test("!triple search with --limit", async () => {
    await typeAndRun("!triple search TSubj --limit 5");
  });
  await test("!triple view", async () => {
    await typeAndRun("!triple view TSubj");
  });
  await test("!triple modify", async () => {
    await typeAndRun("!triple modify TSubj rdfs:label --new-object 'Updated Triple'");
  });

  // ═══════════════════════════════════════════
  //  GRAPH — full options
  // ═══════════════════════════════════════════
  console.log("\n═══ GRAPH — full options ═══");

  await test("!graph search", async () => {
    await typeAndRun("!graph search TSubj");
  });
  await test("!graph view", async () => {
    await typeAndRun("!graph view TSubj");
  });
  await test("!graph export with --base-uri", async () => {
    await typeAndRun("!graph export --base-uri http://example.org/");
  });
  await test("!graph stats", async () => {
    await typeAndRun("!graph stats");
  });

  // ═══════════════════════════════════════════
  //  REVIEW + PROOF — full coverage
  // ═══════════════════════════════════════════
  console.log("\n═══ REVIEW / PROOF ═══");

  await test("!review start", async () => {
    await typeAndRun("!review start");
  });
  await test("!review start with date filter", async () => {
    await typeAndRun("!review start view --date-from 2020-01-01");
  });
  await test("!review sessions", async () => {
    await typeAndRun("!review sessions");
  });
  await test("!proof add with flags", async () => {
    await typeAndRun("!proof add TSubj rdfs:label 'Updated Triple' --proof-type observation --source 'E2E Test'");
  });
  await test("!proof view", async () => {
    await typeAndRun("!proof view TSubj rdfs:label 'Updated Triple'");
  });

  // ═══════════════════════════════════════════
  //  UNIT — full coverage
  // ═══════════════════════════════════════════
  console.log("\n═══ UNIT ═══");

  await test("!unit list", async () => {
    await typeAndRun("!unit list");
  });
  await test("!unit view", async () => {
    await typeAndRun("!unit view meter");
  });
  await test("!unit resolve", async () => {
    await typeAndRun("!unit resolve '1 m to cm'");
  });
  await test("!unit decompose", async () => {
    await typeAndRun("!unit decompose meter");
  });

  // ═══════════════════════════════════════════
  //  LLM — full coverage
  // ═══════════════════════════════════════════
  console.log("\n═══ LLM ═══");

  await test("!llm show", async () => {
    await typeAndRun("!llm show");
  });
  await test("!llm new with flags", async () => {
    await typeAndRun("!llm new ollama --alias ft-e2e --model llama3.2");
  });
  await test("!llm set", async () => {
    await typeAndRun("!llm set --model llama3.2");
  });
  await test("!llm profiles", async () => {
    await typeAndRun("!llm profiles");
  });
  await test("!llm profile list", async () => {
    await typeAndRun("!llm profile list");
  });
  await test("!llm profile show", async () => {
    await typeAndRun("!llm profile show");
  });
  await test("!llm profile load", async () => {
    await typeAndRun("!llm profile load ft-e2e");
  });
  await test("!llm profile delete", async () => {
    await typeAndRun("!llm profile delete ft-e2e");
  });
  await test("!llm clear", async () => {
    await typeAndRun("!llm clear");
  });

  // ═══════════════════════════════════════════
  //  BACKUP — full coverage
  // ═══════════════════════════════════════════
  console.log("\n═══ BACKUP ═══");

  await test("!backup now", async () => {
    await typeAndRun("!backup now");
  });
  await test("!backup list", async () => {
    await typeAndRun("!backup list");
  });
  await test("!backup list --stem", async () => {
    await typeAndRun("!backup list --stem semantika");
  });
  await test("!backup config", async () => {
    await typeAndRun("!backup config");
  });
  await test("!backup config list", async () => {
    await typeAndRun("!backup config list");
  });
  await test("!backup config add with all flags", async () => {
    await typeAndRun("!backup config add --id ft-weekly --label 'FT Weekly' --interval 10080 --max-copies 3");
  });
  await test("!backup config modify", async () => {
    await typeAndRun("!backup config modify ft-weekly --max-copies 5");
  });
  await test("!backup config test", async () => {
    await typeAndRun("!backup config test ft-weekly");
  });
  await test("!backup config delete", async () => {
    await typeAndRun("!backup config delete ft-weekly");
  });
  await test("!backup export", async () => {
    await typeAndRun("!backup export");
  });

  // ═══════════════════════════════════════════
  //  TRASH — full coverage
  // ═══════════════════════════════════════════
  console.log("\n═══ TRASH ═══");

  await test("setup node for trash", async () => {
    await typeAndRun('!node add --node-id TrashT --labels \'{"en":"Trash Test"}\'');
  });
  await test("!node delete for trash", async () => {
    await typeAndRun("!node delete TrashT");
  });
  await test("!node trash list", async () => {
    await typeAndRun("!node trash list");
  });
  await test("!node trash restore", async () => {
    await typeAndRun("!node trash restore TrashT");
  });
  // Delete again for permanent delete test
  await test("setup delete again", async () => {
    await typeAndRun("!node delete TrashT");
  });
  await test("!node trash delete", async () => {
    await typeAndRun("!node trash delete TrashT");
  });

  // Predicate trash
  await test("setup predicate for trash", async () => {
    await typeAndRun("!predicate add ex:tPred");
  });
  await test("!predicate delete for trash", async () => {
    await typeAndRun("!predicate delete ex:tPred");
  });
  await test("!predicate trash list", async () => {
    await typeAndRun("!predicate trash list");
  });
  await test("!predicate trash restore", async () => {
    await typeAndRun("!predicate trash restore ex:tPred");
  });
  await test("!predicate delete again", async () => {
    await typeAndRun("!predicate delete ex:tPred");
  });
  await test("!predicate trash delete", async () => {
    await typeAndRun("!predicate trash delete ex:tPred");
  });

  // ═══════════════════════════════════════════
  //  USER CONFIG
  // ═══════════════════════════════════════════
  console.log("\n═══ USER CONFIG ═══");

  await test("!user.config", async () => {
    await typeAndRun("!user.config");
  });
  await test("!user.config --locale en", async () => {
    await typeAndRun("!user.config --locale en");
  });

  // ═══════════════════════════════════════════
  //  GUI: autocomplete
  // ═══════════════════════════════════════════
  console.log("\n═══ GUI ═══");

  await test("GUI: autocomplete root commands", async () => {
    const input = page.locator("[aria-label='Message input']");
    await input.click();
    await input.fill("!");
    await sleep(300);
    const suggestions = page.locator(".suggestion-text");
    const count = await suggestions.count();
    assert.ok(count > 5, `Expected many suggestions, got ${count}`);
  });

  await test("GUI: autocomplete subcommands", async () => {
    const input = page.locator("[aria-label='Message input']");
    await input.fill("!node ");
    await sleep(300);
    const suggestions = page.locator(".suggestion-text");
    const count = await suggestions.count();
    assert.ok(count >= 5, `Expected node subcommands, got ${count}`);
  });

  // ═══════════════════════════════════════════
  //  CLI → GUI routing
  // ═══════════════════════════════════════════
  console.log("\n═══ CLI → GUI ROUTING ═══");

  await test("CLI→GUI: !node add opens form tab", async () => {
    // This should trigger the intercept routing which opens list + form
    await typeAndRun("!node add");
    await sleep(400);
    // The intercept should create a form tab — verify no crash
  });

  await test("CLI→GUI: !triple add opens form", async () => {
    await typeAndRun("!triple add");
    await sleep(400);
  });

  await test("CLI→GUI: !unit add opens form", async () => {
    await typeAndRun("!unit add");
    await sleep(400);
  });

  // ═══════════════════════════════════════════
  //  LLM API ENDPOINTS
  // ═══════════════════════════════════════════
  console.log("\n═══ LLM API ENDPOINTS ═══");

  await test("API: GET /api/v1/llm/config", async () => {
    const r = await page.evaluate(() =>
      fetch("/api/v1/llm/config").then((r) => r.status)
    );
    assert.equal(r, 200, `Expected 200, got ${r}`);
  });

  await test("API: POST /api/v1/llm/chat (empty msg)", async () => {
    const r = await page.evaluate(() =>
      fetch("/api/v1/llm/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "hello", context: [] }),
      }).then(async (r) => ({ status: r.status }))
    );
    assert.ok(r.status === 200 || r.status === 503,
      `Expected 200 or 503, got ${r.status}`);
  });

  await test("API: POST /api/v1/llm/confirm", async () => {
    const r = await page.evaluate(() =>
      fetch("/api/v1/llm/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tokens: ["graph", "stats"], flags: {} }),
      }).then((r) => r.json())
    );
    assert.equal(r.type, "status", `Expected status, got ${JSON.stringify(r)}`);
  });

  await test("API: POST /api/v1/llm/confirm empty (400)", async () => {
    const r = await page.evaluate(() =>
      fetch("/api/v1/llm/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tokens: [], flags: {} }),
      }).then(async (r) => r.status)
    );
    assert.equal(r, 400, `Expected 400, got ${r}`);
  });

  // ═══════════════════════════════════════════
  //  COMMAND TREE API
  // ═══════════════════════════════════════════
  console.log("\n═══ COMMAND TREE API ═══");

  await test("API: GET /api/v1/command/tree", async () => {
    const r = await page.evaluate(() =>
      fetch("/api/v1/command/tree").then(async (r) => ({ status: r.status, data: await r.json() }))
    );
    assert.equal(r.status, 200);
    assert.ok(Array.isArray(r.data), "Tree should be array");
    assert.ok(r.data.length >= 9, `Expected 9+ root cmds, got ${r.data.length}`);
  });

  await test("API: tree contains node.add interactive", async () => {
    const r = await page.evaluate(() =>
      fetch("/api/v1/command/tree").then((r) => r.json())
    );
    const node = r.find((c) => c.name === "node");
    assert.ok(node && node.children, "Node should have children");
    const add = node.children.find((c) => c.name === "add");
    assert.ok(add && add.interactive, "node.add should be interactive");
  });

  // ═══════════════════════════════════════════
  //  CHAT
  // ═══════════════════════════════════════════
  console.log("\n═══ CHAT ═══");

  await test("Chat: NL message (no LLM configured)", async () => {
    await typeAndRun("how many nodes?");
    await sleep(500);
    // Should not crash — may show setup modal or error message
  });

  // ═══════════════════════════════════════════
  //  SUMMARY
  // ═══════════════════════════════════════════
  console.log(`\n${"=".repeat(50)}`);
  console.log(`RESULTS: ${passed} passed, ${failed} failed`);
  console.log(`Tests: ${testIdx} total`);

  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
}

run().catch((e) => {
  console.error("FATAL:", e.message);
  process.exit(1);
});
