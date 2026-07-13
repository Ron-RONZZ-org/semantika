import { describe, it, expect, vi } from "vitest";

// Mock commandTree with specialised node add subcommands.
// The tree structure mirrors the backend's: `add` is a node with both its
// own handler metadata AND children (photo, video, file, code).
vi.mock("../commandTree.js", () => {
  const tree = [
    {
      name: "node",
      description: "Node operations",
      children: [
        {
          name: "add",
          description: "Create a new entity node in the knowledge graph",
          params: [{ name: "labels", type: "string" }],
          interactive: true,
          children: [
            {
              name: "photo",
              description: "Create a photo node",
              interactive: true,
              flags: [
                { name: "path", type: "string", required: true },
                { name: "dimension", type: "string" },
                { name: "object", type: "string" },
                { name: "canonical-link", type: "string" },
                { name: "no-copy", type: "flag" },
              ],
            },
            {
              name: "video",
              description: "Create a video node",
              interactive: true,
              flags: [
                { name: "path", type: "string", required: true },
                { name: "dimension", type: "string" },
                { name: "object", type: "string" },
                { name: "canonical-link", type: "string" },
                { name: "no-copy", type: "flag" },
              ],
            },
            {
              name: "file",
              description: "Create a document node",
              interactive: true,
              flags: [
                { name: "path", type: "string", required: true },
                { name: "theme", type: "string" },
                { name: "canonical-link", type: "string" },
                { name: "no-copy", type: "flag" },
              ],
            },
            {
              name: "code",
              description: "Create a source code node",
              interactive: true,
              flags: [
                { name: "path", type: "string", required: true },
                { name: "lang", type: "string", required: true },
                { name: "canonical-link", type: "string" },
                { name: "no-copy", type: "flag" },
              ],
            },
          ],
        },
        {
          name: "list",
          description: "List all nodes",
          params: [{ name: "limit", type: "number" }],
          listIdKey: "nodes",
        },
      ],
    },
  ];

  function findNode(tokens) {
    let current = tree;
    let node = null;
    for (const token of tokens) {
      const matched = current.find(
        (n) => n.name.toLowerCase() === token.toLowerCase(),
      );
      if (!matched) return node;
      node = matched;
      if (!node.children || node.children.length === 0) return node;
      current = node.children;
    }
    return node;
  }

  return { commandTree: tree, findNode };
});

import { shouldIntercept } from "../commandRouter.js";

describe("commandRouter specialised node add", () => {
  it("intercepts !node add photo with missing --path", () => {
    const result = shouldIntercept("!node add photo");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-photo");
  });

  it("intercepts !node add video with missing --path", () => {
    const result = shouldIntercept("!node add video");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-video");
  });

  it("intercepts !node add file with missing --path", () => {
    const result = shouldIntercept("!node add file");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-file");
  });

  it("intercepts !node add code with missing --lang", () => {
    const result = shouldIntercept("!node add code");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-code");
  });

  it("does not intercept !node list", () => {
    const result = shouldIntercept("!node list");
    expect(result.intercept).toBe(false);
  });

  it("produces correct listTokens for !node add photo", () => {
    const result = shouldIntercept("!node add photo");
    // Falls back to parent-path pattern: ["node", "add", "list"]
    expect(result.listTokens).toEqual(["node", "add", "list"]);
    expect(result.listIdKey).toBe("adds");
  });
});
