import { describe, it, expect, vi } from "vitest";

// Mock commandTree with the current backend shape (post-refactoring):
//   node → add → concept (leaf, interactive)
//              → attachment (group) → photo, video, file, code (leaf, interactive)
//              → media (group) → book, film, song, game, podcast (leaf, interactive)
//              → scholarly (group) → paper, patent, conference (leaf, interactive)
//        → list (leaf, listIdKey="nodes")
vi.mock("../commandTree.js", () => {
  const tree = [
    {
      name: "node",
      description: "Node operations",
      children: [
        {
          name: "add",
          description: "Node add commands",
          children: [
            {
              name: "concept",
              description: "Create a new entity node in the knowledge graph",
              params: [{ name: "labels", type: "string", required: true }],
              interactive: true,
            },
            {
              name: "attachment",
              description: "Create file-attachment nodes",
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
                    { name: "path", type: "string" },
                    { name: "lang", type: "string", required: true },
                    { name: "canonical-link", type: "string" },
                    { name: "no-copy", type: "flag" },
                  ],
                },
              ],
            },
            {
              name: "media",
              description: "Create media-type nodes",
              children: [
                {
                  name: "book",
                  description: "Create a book node",
                  interactive: true,
                  flags: [
                    { name: "id", type: "string" },
                    { name: "labels", type: "string" },
                    { name: "isbn", type: "string" },
                    { name: "author", type: "string" },
                    { name: "theme", type: "string" },
                    { name: "year", type: "string" },
                  ],
                },
                {
                  name: "film",
                  description: "Create a film node",
                  interactive: true,
                  flags: [
                    { name: "id", type: "string" },
                    { name: "labels", type: "string" },
                    { name: "isan", type: "string" },
                    { name: "director", type: "string" },
                    { name: "producer", type: "string" },
                    { name: "actor", type: "string" },
                    { name: "duration", type: "string" },
                    { name: "year", type: "string" },
                  ],
                },
                {
                  name: "song",
                  description: "Create a song node",
                  interactive: true,
                  flags: [
                    { name: "id", type: "string" },
                    { name: "labels", type: "string" },
                    { name: "iswc", type: "string" },
                    { name: "author", type: "string" },
                    { name: "singer", type: "string" },
                  ],
                },
                {
                  name: "game",
                  description: "Create a game node",
                  interactive: true,
                  flags: [
                    { name: "id", type: "string" },
                    { name: "labels", type: "string" },
                    { name: "platform", type: "string" },
                    { name: "genre", type: "string" },
                    { name: "developer", type: "string" },
                    { name: "publisher", type: "string" },
                    { name: "year", type: "string" },
                  ],
                },
                {
                  name: "podcast",
                  description: "Create a podcast node",
                  interactive: true,
                  flags: [
                    { name: "id", type: "string" },
                    { name: "labels", type: "string" },
                    { name: "host", type: "string" },
                    { name: "episode-count", type: "string" },
                    { name: "feed-url", type: "string" },
                    { name: "language", type: "string" },
                  ],
                },
              ],
            },
            {
              name: "scholarly",
              description: "Create scholarly-type nodes",
              children: [
                {
                  name: "paper",
                  description: "Create a paper node",
                  interactive: true,
                  flags: [
                    { name: "id", type: "string" },
                    { name: "labels", type: "string" },
                    { name: "doi", type: "string" },
                    { name: "author", type: "string" },
                    { name: "journal", type: "string" },
                    { name: "year", type: "string" },
                    { name: "keywords", type: "string" },
                    { name: "url", type: "string" },
                  ],
                },
                {
                  name: "patent",
                  description: "Create a patent node",
                  interactive: true,
                  flags: [
                    { name: "id", type: "string" },
                    { name: "labels", type: "string" },
                    { name: "patent-number", type: "string" },
                    { name: "inventor", type: "string" },
                    { name: "year", type: "string" },
                    { name: "assignee", type: "string" },
                  ],
                },
                {
                  name: "conference",
                  description: "Create a conference node",
                  interactive: true,
                  flags: [
                    { name: "id", type: "string" },
                    { name: "labels", type: "string" },
                    { name: "series", type: "string" },
                    { name: "year", type: "string" },
                    { name: "location", type: "string" },
                    { name: "url", type: "string" },
                  ],
                },
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
  // ── Legacy path (still works: concept is a direct child of add) ──────
  it("intercepts !node add concept with missing --labels", () => {
    const result = shouldIntercept("!node add concept");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add");
  });

  // ── Attachment sub-group ────────────────────────────────────────────
  it("intercepts !node add attachment photo with missing --path", () => {
    const result = shouldIntercept("!node add attachment photo");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-attachment-photo");
  });

  it("intercepts !node add attachment video with missing --path", () => {
    const result = shouldIntercept("!node add attachment video");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-attachment-video");
  });

  it("intercepts !node add attachment file with missing --path", () => {
    const result = shouldIntercept("!node add attachment file");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-attachment-file");
  });

  it("intercepts !node add attachment code with missing --lang", () => {
    const result = shouldIntercept("!node add attachment code");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-attachment-code");
  });

  // ── Media sub-group ─────────────────────────────────────────────────
  it("intercepts !node add media book", () => {
    const result = shouldIntercept("!node add media book");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-media-book");
  });

  it("intercepts !node add media film", () => {
    const result = shouldIntercept("!node add media film");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-media-film");
  });

  it("intercepts !node add media song", () => {
    const result = shouldIntercept("!node add media song");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-media-song");
  });

  it("intercepts !node add media game", () => {
    const result = shouldIntercept("!node add media game");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-media-game");
  });

  it("intercepts !node add media podcast", () => {
    const result = shouldIntercept("!node add media podcast");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-media-podcast");
  });

  // ── Scholarly sub-group ─────────────────────────────────────────────
  it("intercepts !node add scholarly paper", () => {
    const result = shouldIntercept("!node add scholarly paper");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-scholarly-paper");
  });

  it("intercepts !node add scholarly patent", () => {
    const result = shouldIntercept("!node add scholarly patent");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-scholarly-patent");
  });

  it("intercepts !node add scholarly conference", () => {
    const result = shouldIntercept("!node add scholarly conference");
    expect(result.intercept).toBe(true);
    expect(result.addFormType).toBe("node-add-scholarly-conference");
  });

  // ── Should NOT intercept ────────────────────────────────────────────
  it("does not intercept !node list", () => {
    const result = shouldIntercept("!node list");
    expect(result.intercept).toBe(false);
  });

  it("does not intercept !node add media (group, no subcommand)", () => {
    const result = shouldIntercept("!node add media");
    expect(result.intercept).toBe(false);
  });

  // ── listTokens resolution ───────────────────────────────────────────
  it("produces correct listTokens for !node add concept", () => {
    const result = shouldIntercept("!node add concept");
    // Parent is ["node", "add"] (no "list") → walks up to ["node", "list"]
    expect(result.listTokens).toEqual(["node", "list"]);
    expect(result.listIdKey).toBe("nodes");
  });

  it("produces correct listTokens for !node add attachment photo", () => {
    const result = shouldIntercept("!node add attachment photo");
    // Walks up: ["node", "add", "attachment"]→ no list,
    //           ["node", "add"]→ no list,
    //           ["node"]→ "node.list" found
    expect(result.listTokens).toEqual(["node", "list"]);
    expect(result.listIdKey).toBe("nodes");
  });

  it("produces correct listTokens for !node add media book", () => {
    const result = shouldIntercept("!node add media book");
    expect(result.listTokens).toEqual(["node", "list"]);
    expect(result.listIdKey).toBe("nodes");
  });

  it("produces correct listTokens for !node add scholarly paper", () => {
    const result = shouldIntercept("!node add scholarly paper");
    expect(result.listTokens).toEqual(["node", "list"]);
    expect(result.listIdKey).toBe("nodes");
  });

  // ── commandPath resolution ──────────────────────────────────────────
  it("returns correct commandPath for !node add attachment photo", () => {
    const result = shouldIntercept("!node add attachment photo");
    expect(result.commandPath).toEqual(["node", "add", "attachment", "photo"]);
  });

  it("returns correct commandPath for !node add media book", () => {
    const result = shouldIntercept("!node add media book");
    expect(result.commandPath).toEqual(["node", "add", "media", "book"]);
  });

  it("returns correct commandPath for !node add scholarly paper", () => {
    const result = shouldIntercept("!node add scholarly paper");
    expect(result.commandPath).toEqual(["node", "add", "scholarly", "paper"]);
  });

  it("returns correct commandPath for !node add concept", () => {
    const result = shouldIntercept("!node add concept");
    expect(result.commandPath).toEqual(["node", "add", "concept"]);
  });
});
