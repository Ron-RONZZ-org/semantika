import { describe, it, expect } from "vitest";
import { formatCommand } from "../formatCommand.js";

// Note: Full ConfirmDialog component tests require @testing-library/svelte with
// Svelte 5 support (see vite.config.js for the svelte client alias setup).
// Until that infrastructure is stable, we test the formatting utility here.
//
// E2E Playwright tests in tests/ provide the full component interaction coverage.

describe("formatCommand (from ConfirmDialog)", () => {
  it("formats tokens-only command", () => {
    expect(formatCommand({ tokens: ["node", "list"] })).toBe("!node list");
  });

  it("formats command with value flags", () => {
    expect(
      formatCommand({ tokens: ["node", "add"], flags: { label: "Alice" } }),
    ).toBe("!node add --label Alice");
  });

  it("formats command with boolean flag", () => {
    expect(
      formatCommand({ tokens: ["node", "add"], flags: { force: "" } }),
    ).toBe("!node add --force");
  });

  it("formats command with mixed flags", () => {
    const cmd = formatCommand({
      tokens: ["triple", "add"],
      flags: { subject: "n1", predicate: "p1", object: "n2", force: "" },
    });
    expect(cmd).toBe("!triple add --subject n1 --predicate p1 --object n2 --force");
  });

  it("handles empty/null tokens", () => {
    expect(formatCommand({})).toBe("!");
  });
});
