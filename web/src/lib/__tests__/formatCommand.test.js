import { describe, it, expect } from "vitest";
import { formatCommand } from "../formatCommand.js";

describe("formatCommand", () => {
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

  it("formats command with multiple flags", () => {
    const result = formatCommand({
      tokens: ["search"],
      flags: { q: "hello", limit: "10" },
    });
    expect(result).toContain("!search");
    expect(result).toContain("--q hello");
    expect(result).toContain("--limit 10");
  });

  it("handles empty tokens gracefully", () => {
    expect(formatCommand({})).toBe("!");
  });

  it("handles null/undefined gracefully", () => {
    expect(formatCommand({ tokens: null, flags: null })).toBe("!");
  });
});
