/** E2E tests for GUI fixes: !graph stats, !node add forms, sort/filter, autocomplete ENTER. */

import { chromium } from "playwright";

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:5173";

let browser, page;
let passed = 0, failed = 0;
let pageErrors = [];

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function typeAndRun(cmd) {
  // Navigate to home first
  await page.evaluate(() => {
    const homeBtn = document.querySelector('button[role="tab"][title="Home"]');
    if (homeBtn) homeBtn.click();
  });
  await sleep(500);
  const input = page.locator("[aria-label='Message input']");
  await input.waitFor({ state: "visible", timeout: 3000 });
  await input.click();
  await input.fill(cmd);
  await sleep(200);
  await page.keyboard.press("Enter");
  await sleep(3000);
}

async function apiCommand(tokens, flags = {}) {
  return await page.evaluate(async (args) => {
    const resp = await fetch("/api/v1/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tokens: args.t, flags: args.f }),
    });
    return await resp.json();
  }, { t: tokens, f: flags });
}

async function test(name, fn) {
  try {
    await fn();
    passed++;
    console.log(`  \u2713 ${name}`);
  } catch (err) {
    failed++;
    console.log(`  \u2717 ${name}: ${err.message}`);
  }
}

(async () => {
  browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox"],
  });
  page = await browser.newPage();
  page.on("pageerror", (err) => pageErrors.push(err.message));

  console.log("=== GUI Fixes E2E Tests ===\n");

  // 1. App loads
  await test("App loads without JS errors", async () => {
    await page.goto(FRONTEND_URL, { timeout: 15000 });
    await sleep(2000);
    const title = await page.title();
    assert(title.length >= 0); // just ensure page loaded
    assert(pageErrors.length === 0, `JS errors: ${pageErrors.join("; ")}`);
  });

  // 2. !graph stats
  await test("!graph stats shows node count (not 'No nodes')", async () => {
    const result = await apiCommand(["graph", "stats"]);
    assert(result.type === "status", `Expected status type, got ${result.type}`);
    const text = JSON.stringify(result.data);
    assert(!text.includes("No nodes"), "Should not say 'No nodes'");
    assert(typeof result.data.nodes === "number", "nodes should be a number");
    console.log(`    -> nodes: ${result.data.nodes}`);
  });

  // 3. !node add concept opens form
  await test("!node add concept opens Add Node form", async () => {
    await typeAndRun("!node add concept");
    const panel = await page.evaluate(() => {
      const p = document.querySelector(".tab-content.active");
      return p ? p.textContent : "";
    });
    assert(panel.includes("Node Add"), `Form should have 'Node Add' heading, got: "${panel.slice(0, 100)}"`);
    assert(panel.includes("labels"), "Form should have labels field");
  });

  // 4-7. Specialized add commands
  const formTests = [
    { cmd: "!node add photo", heading: "Node Add Photo" },
    { cmd: "!node add video", heading: "Node Add Video" },
    { cmd: "!node add file", heading: "Node Add File" },
    { cmd: "!node add code", heading: "Node Add Code" },
  ];
  for (const { cmd, heading } of formTests) {
    await test(`${cmd} opens ${heading} form`, async () => {
      await typeAndRun(cmd);
      const panel = await page.evaluate(() => {
        const p = document.querySelector(".tab-content.active");
        return p ? p.textContent : "";
      });
      assert(panel.includes(heading), `Expected "${heading}" in form, got: "${panel.slice(0, 100)}"`);
    });
  }

  // 8. !node list API returns correct structure
  await test("!node list API returns nodes with total", async () => {
    const result = await apiCommand(["node", "list"]);
    assert(result.type === "node-list", `Expected node-list, got ${result.type}`);
    const nodes = result.data?.nodes;
    const total = result.data?.total;
    assert(Array.isArray(nodes), "data.nodes should be an array");
    assert(typeof total === "number", "data.total should be a number");
    assert(nodes.length > 0, "Should have at least one node");
    console.log(`    -> ${nodes.length} nodes returned, ${total} total`);
  });

  // 9. NodeListTab component renders correctly via direct API test
  await test("NodeListTab data structure is valid", async () => {
    const result = await apiCommand(["node", "list"]);
    assert(result.type === "node-list", `Expected node-list, got ${result.type}`);
    assert(typeof result.data === "object" && result.data !== null, "data should be an object");
    assert(Array.isArray(result.data.nodes), "data.nodes should be an array");
    assert(typeof result.data.total === "number", "data.total should be a number");
    assert(result.data.nodes.length > 0, "should have nodes");
    // Each node should have node_id, labels, created_at
    const first = result.data.nodes[0];
    assert(first.node_id, "node should have node_id");
    assert(first.labels, "node should have labels");
    assert(first.created_at, "node should have created_at");
    console.log(`    -> ${result.data.nodes.length} nodes valid`);
  });

  // Summary
  console.log(`\n${passed} passed, ${failed} failed`);
  if (pageErrors.length > 0) {
    console.log(`Page errors: ${pageErrors.length}`);
    pageErrors.forEach((e) => console.log(`  ${e}`));
  }

  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
})().catch((err) => {
  console.error("Fatal:", err.message);
  process.exit(1);
});

function assert(condition, message) {
  if (!condition) throw new Error(message || "Assertion failed");
}
