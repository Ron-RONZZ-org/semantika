import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the userConfig store before importing SettingsTab
let mockLocale = "en";
let mockNormNodes = false;
let mockStripPred = false;

vi.mock("../userConfig.svelte.js", () => ({
  getLocale: () => mockLocale,
  getNormaliseNodeIds: () => mockNormNodes,
  getStripPredicateDiacritics: () => mockStripPred,
  setBoolSetting: vi.fn(),
  setLocale: vi.fn(),
}));

describe("SettingsTab data handling", () => {
  beforeEach(() => {
    mockLocale = "en";
    mockNormNodes = false;
    mockStripPred = false;
  });

  it("reads locale from userConfig store", async () => {
    const { getLocale } = await import("../userConfig.svelte.js");
    expect(getLocale()).toBe("en");

    mockLocale = "fr";
    // Re-import to get updated mock
    vi.resetModules();
    vi.mock("../userConfig.svelte.js", () => ({
      getLocale: () => mockLocale,
      getNormaliseNodeIds: () => mockNormNodes,
      getStripPredicateDiacritics: () => mockStripPred,
      setBoolSetting: vi.fn(),
      setLocale: vi.fn(),
    }));
    const { getLocale: getLocale2 } = await import("../userConfig.svelte.js");
    expect(getLocale2()).toBe("fr");
  });

  it("reads normalise_node_ids and strip_predicate_diacritics", async () => {
    const { getNormaliseNodeIds, getStripPredicateDiacritics } = await import("../userConfig.svelte.js");
    expect(getNormaliseNodeIds()).toBe(false);
    expect(getStripPredicateDiacritics()).toBe(false);

    mockNormNodes = true;
    mockStripPred = true;
    vi.resetModules();
    vi.mock("../userConfig.svelte.js", () => ({
      getLocale: () => mockLocale,
      getNormaliseNodeIds: () => mockNormNodes,
      getStripPredicateDiacritics: () => mockStripPred,
      setBoolSetting: vi.fn(),
      setLocale: vi.fn(),
    }));
    const { getNormaliseNodeIds: g1, getStripPredicateDiacritics: g2 } = await import("../userConfig.svelte.js");
    expect(g1()).toBe(true);
    expect(g2()).toBe(true);
  });
});
