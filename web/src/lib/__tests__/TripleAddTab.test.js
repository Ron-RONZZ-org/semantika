/**
 * TripleAddTab component tests.
 *
 * Covers the four root-cause fixes:
 *   1A — input type always "text" (never "number")
 *   1B — no <select> for bool, always <input> + <datalist>
 *   2  — datalist IDs follow "dl-" prefix so debouncedAutocomplete can find them
 *   4  --flag clears value via queueMicrotask (not synchronously)
 *
 * Pure-function tests for getBoolSuggestions / getFlagSuggestions /
 * interpretFlag / parseFlagFromValue / resolveObjectType live in
 * tripleAddTypeUtils.test.js.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { tick } from "svelte";
import TripleAddTab from "../TripleAddTab.svelte";

// Mock @lightercore/ui/cowrite for cowrite component testing
vi.mock("@lightercore/ui/cowrite/index.js", () => ({
  createCowrite: vi.fn(() => ({
    isActive: false,
    isLoading: false,
    error: "",
    instruction: "",
    fieldEdits: [],
    sessionId: "",
    hasUnprocessed: false,
    embedRequired: null,
    startCowrite: vi.fn(),
    openPanel: vi.fn(),
    acceptAll: vi.fn(),
    rejectAll: vi.fn(),
    acceptEdit: vi.fn(),
    rejectEdit: vi.fn(),
    close: vi.fn(),
  })),
  CowriteButton: function MockCowriteButton() {
    return { $$render: () => "" };
  },
  CowritePanel: function MockCowritePanel() {
    return { $$render: () => "" };
  },
}));

// Track the createCowrite mock for assertions
const cowriteModule = await vi.importMock("@lightercore/ui/cowrite/index.js");

// ── Module mocks ──────────────────────────────────────────────────────────

vi.mock("../historyStore.svelte.js", () => ({
  createHistory: () => ({
    push: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    canUndo: false,
    canRedo: false,
  }),
}));

vi.mock("../tabStore.svelte.js", () => ({
  tabStore: {
    close: vi.fn(),
    open: vi.fn(),
    active: null,
  },
}));

// ── Helpers ───────────────────────────────────────────────────────────────

/**
 * Wait for Svelte 5 $state updates AND queueMicrotask callbacks to flush.
 * Svelte 5 processes $state updates in a microtask. Our queueMicrotask
 * callbacks run in the same microtask batch.  tick() waits for all pending
 * state changes to be reflected in the DOM.  The additional macrotask wait
 * ensures queueMicrotask callbacks that themselves trigger $state updates
 * (the Fix-4 deferred value clearing) have had their downstream effects
 * applied as well.
 */
async function flushAll() {
  await tick();
  await new Promise((r) => setTimeout(r, 0));
  await tick();
}

/**
 * Find the first OBJECT <input> in the rendered component.
 * In happy-dom we fall back to container.querySelector for data-field selectors.
 */
function getObjInput(container) {
  return container.querySelector('input[data-field="object_value"]');
}

/** Find the first type <select> dropdown. */
function getTypeSelect(container) {
  return container.querySelector(".type-select");
}

/** Find a <datalist> whose id starts with prefix. */
function getDatalist(container, idPrefix) {
  return container.querySelector(`[id^="${idPrefix}"]`);
}

// ── Fixtures ──────────────────────────────────────────────────────────────

beforeEach(() => {
  // Mock fetch so autocomplete API calls return empty without hitting network
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ results: [] }),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── Tests: Fix 1A — input type is always "text" ───────────────────────────

describe("Fix 1A: OBJECT input type is always 'text'", () => {
  it("renders with type='text' by default (type=node)", () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const input = getObjInput(container);
    expect(input).not.toBeNull();
    expect(input.getAttribute("type")).toBe("text");
  });

  it("stays type='text' when type is changed to Int via dropdown", async () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const sel = getTypeSelect(container);
    await fireEvent.change(sel, { target: { value: "int" } });
    await flushAll();
    const input = getObjInput(container);
    expect(input.getAttribute("type")).toBe("text");
  });

  it("stays type='text' when type is changed to Float via dropdown", async () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const sel = getTypeSelect(container);
    await fireEvent.change(sel, { target: { value: "float" } });
    await flushAll();
    const input = getObjInput(container);
    expect(input.getAttribute("type")).toBe("text");
  });

  it("stays type='text' when type is changed to Bool via dropdown", async () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const sel = getTypeSelect(container);
    await fireEvent.change(sel, { target: { value: "bool" } });
    await flushAll();
    const input = getObjInput(container);
    expect(input.getAttribute("type")).toBe("text");
  });

  it("stays type='text' after --int flag is typed", async () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const input = getObjInput(container);
    await fireEvent.input(input, { target: { value: "--int " } });
    await flushAll();
    expect(input.getAttribute("type")).toBe("text");
  });
});

// ── Tests: Fix 1B — no <select> for bool, <input>+<datalist> instead ─────

describe("Fix 1B: Bool uses <input> with <datalist> (not <select>)", () => {
  it("renders <input> not <select> when default type is node", () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const selects = container.querySelectorAll(
      'span.col-obj select, span.col-obj select[data-field="object_value"]'
    );
    expect(selects.length).toBe(0);
  });

  it("renders <input> not <select> when type changed to Bool via dropdown", async () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const sel = getTypeSelect(container);
    await fireEvent.change(sel, { target: { value: "bool" } });
    await flushAll();
    const selects = container.querySelectorAll(
      'span.col-obj select, span.col-obj select[data-field="object_value"]'
    );
    expect(selects.length).toBe(0);
    // Must still be an INPUT
    const input = getObjInput(container);
    expect(input).not.toBeNull();
  });

  it("renders <input> not <select> after --bool flag is typed", async () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const input = getObjInput(container);
    await fireEvent.input(input, { target: { value: "--bool " } });
    await flushAll();
    const selects = container.querySelectorAll(
      'span.col-obj select, span.col-obj select[data-field="object_value"]'
    );
    expect(selects.length).toBe(0);
  });

  it("shows TRUE/FALSE suggestions in datalist for bool type", async () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    // Change type to Bool via dropdown
    const sel = getTypeSelect(container);
    await fireEvent.change(sel, { target: { value: "bool" } });
    await flushAll();
    // Type a character to trigger updateObjectDatalist
    const input = getObjInput(container);
    await fireEvent.input(input, { target: { value: "t" } });
    await flushAll();
    // The OBJECT datalist should contain true/false options
    const dl = getDatalist(container, "dl-");
    // The datalist id ends with "-obj" and has content
    const objDatalist = container.querySelector('[id$="-obj"]');
    expect(objDatalist).not.toBeNull();
    const html = objDatalist.innerHTML.toLowerCase();
    expect(html).toContain("true");
    expect(html).toContain("false");
  });
});

// ── Tests: Fix 2 — datalist IDs use dl- prefix ────────────────────────────

describe("Fix 2: Datalist IDs follow dl- prefix pattern", () => {
  it("SUBJECT datalist id starts with dl-", () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const subjectDl = container.querySelector('[id$="-nodes"]');
    expect(subjectDl).not.toBeNull();
    expect(subjectDl.id).toMatch(/^dl-/);
  });

  it("SUBJECT input list attribute matches datalist id", () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const subjectInput = container.querySelector('input[data-field="subject_id"]');
    const subjectDl = container.querySelector('[id$="-nodes"]');
    expect(subjectInput.getAttribute("list")).toBe(subjectDl.id);
  });

  it("PREDICATE datalist id starts with dl-", () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const predDl = container.querySelector('[id$="-preds"]');
    expect(predDl).not.toBeNull();
    expect(predDl.id).toMatch(/^dl-/);
  });

  it("PREDICATE input list attribute matches datalist id", () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const predInput = container.querySelector('input[data-field="predicate_id"]');
    const predDl = container.querySelector('[id$="-preds"]');
    expect(predInput.getAttribute("list")).toBe(predDl.id);
  });

  it("OBJECT datalist id starts with dl-", () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const objDl = container.querySelector('[id$="-obj"]');
    expect(objDl).not.toBeNull();
    expect(objDl.id).toMatch(/^dl-/);
  });

  it("OBJECT input list attribute matches datalist id", () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const objInput = getObjInput(container);
    const objDl = container.querySelector('[id$="-obj"]');
    expect(objInput.getAttribute("list")).toBe(objDl.id);
  });
});

// ── Tests: Fix 4 — --flag changes type metadata ──────────────────────────
//
// NOTE: input.value clearing via queueMicrotask is verified in the E2E
// Playwright test (real browser).  In happy-dom, Svelte 5's value={expr}
// binding does not propagate to the input.value property after $state
// updates.  We verify the TYPE metadata change here, which proves the
// handler ran and processed the flag correctly.

describe("Fix 4: --flag changes type metadata", () => {
  const FLAG_CASES = [
    { input: "--int ",   type: "int" },
    { input: "--str ",   type: "literal" },
    { input: "--float ", type: "float" },
    { input: "--bool ",  type: "bool" },
    { input: "--url ",   type: "url" },
    { input: "--katex ", type: "katex" },
  ];

  for (const { input: typed, type } of FLAG_CASES) {
    it(`--${typed.replace(/ --/g, "").trim()} changes type to ${type}`, async () => {
      const { container } = render(TripleAddTab, { props: { data: {} } });
      const inp = getObjInput(container);
      await fireEvent.input(inp, { target: { value: typed } });
      await flushAll();
      const sel = getTypeSelect(container);
      expect(sel.value).toBe(type);
    });
  }

  it("--str AFTER --int still works (regression: was broken by type=number)", async () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const input = getObjInput(container);
    await fireEvent.input(input, { target: { value: "--int " } });
    await flushAll();
    await fireEvent.input(input, { target: { value: "--str " } });
    await flushAll();
    const sel = getTypeSelect(container);
    expect(sel.value).toBe("literal");
  });

  it("unknown flag shows inline warning", async () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const input = getObjInput(container);
    await fireEvent.input(input, { target: { value: "--foobar " } });
    await flushAll();
    const typeWarning = container.querySelector(".type-warning");
    expect(typeWarning).not.toBeNull();
    expect(typeWarning.textContent).toContain("foobar");
  });
});

// ── Tests: Flag suggestions in OBJECT datalist ────────────────────────────

describe("--flag suggestions in OBJECT datalist", () => {
  it("shows --flag suggestions when value starts with --", async () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const input = getObjInput(container);
    await fireEvent.input(input, { target: { value: "--" } });
    await flushAll();
    const objDl = container.querySelector('[id$="-obj"]');
    const html = objDl.innerHTML;
    expect(html).toContain("--int");
    expect(html).toContain("--str");
    expect(html).toContain("--bool");
    expect(html).toContain("--katex");
    expect(html).toContain("--url");
    expect(html).toContain("--float");
    expect(html).toContain("--string"); // full form
  });
});

// ── Tests: Cowrite integration ────────────────────────────────────────────

describe("TripleAddTab cowrite", () => {
  it("renders Ask LLM button in toolbar", () => {
    const { container } = render(TripleAddTab, { props: { data: {} } });
    const askBtn = container.querySelector(".cowrite-btn");
    expect(askBtn).not.toBeNull();
  });

  it("serializes editing rows via getCowriteContent", () => {
    // createCowrite was called with getCurrentContent; we test the logic
    // by verifying that the createCowrite import was called
    const { createCowrite } = require("@lightercore/ui/cowrite/index.js");
    expect(createCowrite).toHaveBeenCalled();

    // Verify createCowrite was called with the right formType
    const callArgs = createCowrite.mock.calls[0][0];
    expect(callArgs.formType).toBe("triple-add-batch");
    expect(typeof callArgs.getCurrentContent).toBe("function");
    expect(typeof callArgs.applyEdit).toBe("function");
  });

  it("cowrite formType is triple-add-batch", () => {
    const { createCowrite } = require("@lightercore/ui/cowrite/index.js");
    const callArgs = createCowrite.mock.calls[0][0];
    expect(callArgs.formType).toBe("triple-add-batch");
  });
});
