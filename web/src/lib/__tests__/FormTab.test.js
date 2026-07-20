/**
 * FormTab component tests — post-submit redirect logic.
 *
 * Covers the root cause fix: when a form creates a node/predicate,
 * the form should close and redirect to the list tab with a highlight
 * animation, instead of leaving the form open with a confirmation tab.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { tick } from "svelte";
import FormTab from "../FormTab.svelte";

// ── Hoisted mocks ───────────────────────────────────────────────────────

const tabStoreMock = vi.hoisted(() => ({
  open: vi.fn(),
  close: vi.fn(),
  update: vi.fn(),
  setActive: vi.fn(),
  findByKey: vi.fn(),
  goHome: vi.fn(),
  get active() {
    return { id: "form-tab-1", type: "form" };
  },
  get tabs() {
    return [];
  },
}));

const findNodeMock = vi.hoisted(() =>
  vi.fn(() => ({
    params: [{ name: "labels", type: "string", required: true }],
    flags: [],
    name: "add",
  })),
);

// ── Module mocks ────────────────────────────────────────────────────────

vi.mock("../tabStore.svelte.js", () => ({
  tabStore: tabStoreMock,
}));

vi.mock("../commandTree.js", () => ({
  commandTree: [
    {
      name: "node",
      children: [
        {
          name: "add",
          params: [{ name: "labels", type: "string", required: true }],
          flags: [],
        },
        {
          name: "list",
          params: [],
          flags: [],
        },
      ],
    },
  ],
  findNode: findNodeMock,
}));

vi.mock("@lightercore/ui/cowrite/index.js", () => ({
  createCowrite: vi.fn(() => ({
    isActive: false, isLoading: false, error: "", instruction: "",
    fieldEdits: [], sessionId: "", hasUnprocessed: false, embedRequired: null,
    startCowrite: vi.fn(), openPanel: vi.fn(),
    acceptAll: vi.fn(), rejectAll: vi.fn(),
    acceptEdit: vi.fn(), rejectEdit: vi.fn(), close: vi.fn(),
  })),
  CowriteButton: function MockBtn() {},
  CowritePanel: function MockPanel() {},
}));
vi.mock("@lightercore/ui/cowrite/CowriteButton.svelte", () => ({
  default: function MockBtn() {},
}));
vi.mock("@lightercore/ui/cowrite/CowritePanel.svelte", () => ({
  default: function MockPanel() {},
}));

// ── Helpers ─────────────────────────────────────────────────────────────

/** Fill the form's required labels field and click Save. */
async function fillAndSubmit(labels = "en::Test") {
  const textbox = screen.getByRole("textbox");
  await fireEvent.input(textbox, { target: { value: labels } });
  const saveBtn = screen.getByText("Save");
  await fireEvent.click(saveBtn);
  await tick();
}

describe("FormTab — post-submit redirect", () => {
  let fetchSpy;

  beforeEach(() => {
    vi.clearAllMocks();
    fetchSpy = vi.spyOn(globalThis, "fetch");
    // Default: first fetch returns a successful node creation response
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          type: "status",
          title: "Created",
          data: {
            message: "Created node TEST_1",
            node: { node_id: "TEST_1", labels: { en: "Test" } },
          },
        }),
    });
  });

  // ── Original behavior preservation (no redirect) ─────────────────────

  it("opens status tab when no returnType is set (original behavior)", async () => {
    render(FormTab, {
      props: {
        data: {
          form: "node-add",
          commandPath: ["node", "add", "concept"],
          initialData: {},
          // No returnType — should fall through to original behavior
        },
      },
    });

    await fillAndSubmit();

    // Should open a status tab with the creation data
    expect(tabStoreMock.open).toHaveBeenCalledWith(
      "status",
      "Created",
      expect.objectContaining({
        message: "Created node TEST_1",
        node: { node_id: "TEST_1", labels: { en: "Test" } },
      }),
    );
    // Should NOT close the form tab
    expect(tabStoreMock.close).not.toHaveBeenCalled();
  });

  it("opens status tab when backend returns error (original behavior)", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: false,
      status: 400,
      json: () =>
        Promise.resolve({
          type: "error",
          title: "Command Failed",
          data: { message: "Validation error" },
        }),
    });

    render(FormTab, {
      props: {
        data: {
          form: "node-add",
          commandPath: ["node", "add", "concept"],
          initialData: {},
          returnType: "node-list",
          returnTokens: ["node", "list"],
        },
      },
    });

    await fillAndSubmit();

    // Should NOT close form on error — original behavior
    expect(tabStoreMock.close).not.toHaveBeenCalled();
    // Should open error tab
    expect(tabStoreMock.open).toHaveBeenCalledWith(
      "error",
      "Command Failed",
      expect.objectContaining({
        message: "Validation error",
      }),
    );
  });

  it("opens status tab when response has no node_id/predicate_id", async () => {
    fetchSpy.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({
          type: "status",
          title: "Done",
          data: { message: "Something happened but no entity was created" },
        }),
    });

    render(FormTab, {
      props: {
        data: {
          form: "node-add",
          commandPath: ["node", "add", "concept"],
          initialData: {},
          returnType: "node-list",
          returnTokens: ["node", "list"],
        },
      },
    });

    await fillAndSubmit();

    // Should NOT close form (no entity created)
    expect(tabStoreMock.close).not.toHaveBeenCalled();
    expect(tabStoreMock.open).toHaveBeenCalledWith(
      "status",
      "Done",
      expect.objectContaining({
        message: "Something happened but no entity was created",
      }),
    );
  });

  // ── Redirect logic (the fix) ─────────────────────────────────────────

  it("closes form and opens list tab with highlight on node creation", async () => {
    // We need 2 fetch calls: 1 for creation, 1 for list re-fetch
    fetchSpy
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            type: "status",
            data: {
              message: "Created node TEST_1",
              node: { node_id: "TEST_1", labels: { en: "Test" } },
              semantic_triples: [],
            },
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            type: "node-list",
            title: "Nodes",
            data: { nodes: [{ node_id: "TEST_1", labels: { en: "Test" } }], total: 1 },
          }),
      });

    render(FormTab, {
      props: {
        data: {
          form: "node-add",
          commandPath: ["node", "add", "concept"],
          initialData: {},
          returnType: "node-list",
          returnTitle: "Nodes",
          returnTokens: ["node", "list"],
        },
      },
    });

    await fillAndSubmit();

    // Should close the form tab
    expect(tabStoreMock.close).toHaveBeenCalledWith("form-tab-1");

    // Should fetch fresh list data
    const listFetchCall = fetchSpy.mock.calls[1];
    expect(listFetchCall[0]).toBe("/api/v1/command");
    const listBody = JSON.parse(listFetchCall[1].body);
    expect(listBody.tokens).toEqual(["node", "list"]);

    // Should open list tab with highlight
    expect(tabStoreMock.open).toHaveBeenCalledWith(
      "node-list",
      "Nodes",
      expect.objectContaining({
        _highlight: "TEST_1",
        nodes: [{ node_id: "TEST_1", labels: { en: "Test" } }],
      }),
      { idKey: "node-list" },
    );
  });

  it("re-uses existing persistent tab when returnIdKey is provided", async () => {
    const existingTabId = "persistent-nodes-tab";
    tabStoreMock.findByKey.mockReturnValue(existingTabId);

    fetchSpy
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            type: "status",
            data: {
              message: "Created node TEST_2",
              node: { node_id: "TEST_2", labels: { en: "Test 2" } },
            },
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            type: "node-list",
            title: "Nodes",
            data: { nodes: [{ node_id: "TEST_2" }], total: 1 },
          }),
      });

    render(FormTab, {
      props: {
        data: {
          form: "node-add",
          commandPath: ["node", "add", "concept"],
          initialData: {},
          returnType: "node-list",
          returnTitle: "Nodes",
          returnTokens: ["node", "list"],
          returnIdKey: "persistent-nodes",
        },
      },
    });

    await fillAndSubmit();

    // Should find existing tab by idKey
    expect(tabStoreMock.findByKey).toHaveBeenCalledWith("persistent-nodes");
    // Should update existing tab (not open new one)
    expect(tabStoreMock.update).toHaveBeenCalledWith(
      existingTabId,
      expect.objectContaining({ _highlight: "TEST_2" }),
    );
    expect(tabStoreMock.setActive).toHaveBeenCalledWith(existingTabId);
    // Should NOT open a new tab
    expect(tabStoreMock.open).not.toHaveBeenCalled();
  });

  it("falls back to goHome when list re-fetch fails", async () => {
    fetchSpy
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            type: "status",
            data: {
              message: "Created node TEST_3",
              node: { node_id: "TEST_3" },
            },
          }),
      })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ detail: "Internal error" }),
      });

    render(FormTab, {
      props: {
        data: {
          form: "node-add",
          commandPath: ["node", "add", "concept"],
          initialData: {},
          returnType: "node-list",
          returnTokens: ["node", "list"],
        },
      },
    });

    await fillAndSubmit();

    // Should close form (node was created)
    expect(tabStoreMock.close).toHaveBeenCalled();
    // Should go to home tab
    expect(tabStoreMock.goHome).toHaveBeenCalled();
    // Should NOT open a new list tab
    expect(tabStoreMock.open).not.toHaveBeenCalled();
  });

  it("redirects with predicate_id for predicate creation", async () => {
    fetchSpy
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            type: "status",
            title: "Created",
            data: {
              message: "Created predicate rs:testPredicate",
              predicate: { predicate_id: "rs:testPredicate" },
            },
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            type: "predicate-list",
            title: "Predicates",
            data: { predicates: [{ predicate_id: "rs:testPredicate" }], total: 1 },
          }),
      });

    render(FormTab, {
      props: {
        data: {
          form: "predicate-add",
          commandPath: ["predicate", "add"],
          initialData: {},
          returnType: "predicate-list",
          returnTitle: "Predicates",
          returnTokens: ["predicate", "list"],
        },
      },
    });

    await fillAndSubmit();

    // Should close the form tab
    expect(tabStoreMock.close).toHaveBeenCalled();
    // Should open predicate list with highlight
    expect(tabStoreMock.open).toHaveBeenCalledWith(
      "predicate-list",
      "Predicates",
      expect.objectContaining({ _highlight: "rs:testPredicate" }),
      { idKey: "predicate-list" },
    );
  });

  it("closes the correct form tab even after tab switch", async () => {
    // Simulate that the form tab is no longer the active tab
    // (tabStoreMock.active returns { id: "form-tab-1" } by default)
    fetchSpy
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            type: "status",
            data: {
              message: "Created node FOO",
              node: { node_id: "FOO" },
            },
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            type: "node-list",
            title: "Nodes",
            data: { nodes: [{ node_id: "FOO" }], total: 1 },
          }),
      });

    render(FormTab, {
      props: {
        data: {
          form: "node-add",
          commandPath: ["node", "add", "concept"],
          initialData: {},
          returnType: "node-list",
          returnTokens: ["node", "list"],
        },
      },
    });

    await fillAndSubmit();

    // Should close the tab whose ID matches active.id
    expect(tabStoreMock.close).toHaveBeenCalledWith("form-tab-1");
  });
});
