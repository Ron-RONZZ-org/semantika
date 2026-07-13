/** E2E tests for the SPARQL query editor GUI. */

import { chromium } from "playwright";
import { strict as assert } from "assert";

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:8000";
const CHROME_PATH = process.env.CHROME_PATH || "chromium";

let browser, page;
let passed = 0, failed = 0;
let pageErrors = [];
let consoleErrors = [];

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
  await sleep(1500);
}

async function ensureInputVisible() {
  const input = page.locator("[aria-label='Message input']");
  for (let attempt = 0; attempt < 15; attempt++) {
    const vis = await input.isVisible().catch(() => false);
    if (vis) return true;
    try {
      const homeBtn = page.locator('button[role="tab"]', { hasText: "Home" });
      if (await homeBtn.isVisible({ timeout: 300 }).catch(() => false)) {
        await homeBtn.click({ timeout: 500 });
        await sleep(400);
        continue;
      }
    } catch {}
    await page.keyboard.press("Escape");
    await sleep(300);
  }
  return false;
}

async function closeAllTabs() {
  for (let i = 0; i < 10; i++) {
    const closeBtn = page.locator(".tab-close").first();
    if (await closeBtn.isVisible().catch(() => false)) {
      await closeBtn.click();
      await sleep(300);
    } else {
      break;
    }
  }
}

async function verifyNoCrash() {
  const pErr = [...pageErrors];
  const cErr = consoleErrors.filter((e) =>
    !e.includes("404") && !e.includes("400") && !e.includes("favicon"),
  );
  pageErrors = [];
  consoleErrors = [];
  const all = [...pErr, ...cErr];
  if (all.length > 0) {
    throw new Error(`Browser errors: ${all.join("; ")}`);
  }
}

async function openEditorAndType(query) {
  await closeAllTabs();
  await typeAndRun("!sparql query");
  await sleep(800);

  const cmEditor = page.locator(".cm-editor");
  await cmEditor.waitFor({ state: "visible", timeout: 3000 });
  await cmEditor.click();
  await sleep(100);
  await page.keyboard.press("Control+a");
  await sleep(50);
  await page.keyboard.press("Backspace");
  await sleep(50);
  await page.keyboard.type(query);
}

async function test(name, fn) {
  try {
    await fn();
    passed++;
    console.log(`  ✓ ${name}`);
  } catch (err) {
    failed++;
    console.log(`  ✗ ${name}: ${err.message}`);
  }
}

async function main() {
  browser = await chromium.launch({
    headless: true,
    executablePath: CHROME_PATH === "chromium" ? undefined : CHROME_PATH,
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
  });
  page = await context.newPage();

  page.on("pageerror", (err) => {
    pageErrors.push(err.message);
  });
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  });

  await page.goto(FRONTEND_URL, { waitUntil: "networkidle" });
  await sleep(2000);

  console.log(`\nSPARQL Editor E2E tests on ${FRONTEND_URL}\n`);

  // ── Seed data via fetch API (Node.js native fetch) ────────────────────
  const api = FRONTEND_URL + "/api/v1/graph";
  async function seed(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      const text = await r.text();
      throw new Error(`Seed ${url} failed: ${r.status} ${text}`);
    }
    return r;
  }

  try {
    await seed(`${api}/nodes`, { node_id: "E2E_S", labels: { en: "E2E Subject" } });
    await seed(`${api}/nodes`, { node_id: "E2E_O", labels: { en: "E2E Object" } });
    await seed(`${api}/predicates`, { predicate_id: "ex:e2ePred", labels: { en: "e2e predicate" } });
    const tr = await seed(`${api}/triples`, {
      subject_id: "E2E_S", predicate_id: "ex:e2ePred",
      object_value: "E2E_O", object_type: "uri",
    });
    console.log("  Seed data created OK");
  } catch (err) {
    console.log("  SEED WARNING:", err.message);
  }
  await sleep(500);

  // -----------------------------------------------------------------------
  // Test 1: !sparql query opens the editor tab
  // -----------------------------------------------------------------------
  await test("!sparql query opens SPARQL editor tab", async () => {
    await closeAllTabs();
    await typeAndRun("!sparql query");

    const editorTab = page.locator('button[role="tab"]', { hasText: "SPARQL" });
    await editorTab.waitFor({ state: "visible", timeout: 5000 });
    const tabText = await editorTab.first().textContent();
    assert.ok(
      tabText.includes("SPARQL"),
      `Tab should include "SPARQL", got: "${tabText}"`,
    );

    const editorPane = page.locator(".editor-pane");
    await editorPane.waitFor({ state: "visible", timeout: 3000 });
  });

  // -----------------------------------------------------------------------
  // Test 2: Editor contains CodeMirror with Run button
  // -----------------------------------------------------------------------
  await test("Editor shows CodeMirror with Run button", async () => {
    const cmEditor = page.locator(".cm-editor");
    await cmEditor.waitFor({ state: "visible", timeout: 3000 });
    const cmText = await cmEditor.textContent();
    assert.ok(
      cmText.includes("SELECT") || cmText.includes("WHERE"),
      `Editor should contain SPARQL keywords, got: "${(cmText || "").slice(0, 200)}"`,
    );

    const runBtn = page.locator(".btn-run");
    await runBtn.waitFor({ state: "visible", timeout: 1000 });
    const runText = await runBtn.textContent();
    assert.ok(runText.includes("Run"), `Run button should say "Run", got: "${runText}"`);
  });

  // -----------------------------------------------------------------------
  // Test 3: Run a SELECT query and see results
  // -----------------------------------------------------------------------
  await test("Running SELECT shows results", async () => {
    await openEditorAndType("SELECT * WHERE { ?s ?p ?o } LIMIT 5");
    await page.locator(".btn-run").click();
    await sleep(2000);

    const resultArea = page.locator(".result-area");
    await resultArea.waitFor({ state: "visible", timeout: 5000 });
    const resultText = await resultArea.textContent();
    assert.ok(
      resultText && resultText.includes("row"),
      `Result should show row count, got: "${(resultText || "").slice(0, 300)}"`,
    );
  });

  // -----------------------------------------------------------------------
  // Test 4: ASK query shows Yes/No
  // -----------------------------------------------------------------------
  await test("ASK query shows result", async () => {
    await openEditorAndType("ASK { ?s ?p ?o }");
    await page.locator(".btn-run").click();
    await sleep(2000);

    const resultArea = page.locator(".result-area");
    await resultArea.waitFor({ state: "visible", timeout: 5000 });
    const resultText = await resultArea.textContent();
    assert.ok(
      resultText && (resultText.includes("Yes") || resultText.includes("No")),
      `ASK should show Yes/No, got: "${(resultText || "").slice(0, 300)}"`,
    );
  });

  // -----------------------------------------------------------------------
  // Test 5: Syntax error shows error
  // -----------------------------------------------------------------------
  await test("Syntax error shows error", async () => {
    await openEditorAndType("SELECT BROKEN {");
    await page.locator(".btn-run").click();
    await sleep(2000);

    // The error appears in the error bar above the results
    const errorBar = page.locator(".error-bar");
    await errorBar.waitFor({ state: "visible", timeout: 5000 });
    const errText = await errorBar.textContent();
    assert.ok(
      errText && errText.length > 0,
      `Error bar should show message, got: "${errText}"`,
    );
  });

  // -----------------------------------------------------------------------
  // Test 6: No unhandled page errors
  // -----------------------------------------------------------------------
  await test("No unhandled page errors", async () => {
    await verifyNoCrash();
  });

  // ── Final check ──────────────────────────────────────────────────────
  await sleep(500);
  await verifyNoCrash();

  console.log(`\nResults: ${passed} passed, ${failed} failed\n`);
  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((err) => {
  console.error(`Fatal: ${err.message}`);
  process.exit(1);
});
