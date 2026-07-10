import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import DynamicForm from "../DynamicForm.svelte";

// Mock the commandTree module so DynamicForm can find nodes
vi.mock("../commandTree.js", () => ({
  commandTree: [
    {
      name: "node",
      description: "Node operations",
      children: [
        {
          name: "add",
          description: "Add a new node",
          params: [{ name: "labels", type: "string", required: true }],
          flags: [
            { name: "color", type: "string", required: false, help: "Node color" },
            { name: "pin", type: "flag", required: false, help: "Pin the node" },
          ],
        },
      ],
    },
  ],
  findNode: (tokens) => {
    let current = [
      {
        name: "node",
        children: [
          {
            name: "add",
            description: "Add a new node",
            params: [{ name: "labels", type: "string", required: true }],
            flags: [
              { name: "color", type: "string", required: false, help: "Node color" },
              { name: "pin", type: "flag", required: false, help: "Pin the node" },
            ],
          },
        ],
      },
    ];
    let node = null;
    for (const token of tokens) {
      const matched = current.find((n) => n.name.toLowerCase() === token.toLowerCase());
      if (!matched) return node;
      node = matched;
      if (!node.children || node.children.length === 0) return node;
      current = node.children;
    }
    return node;
  },
}));

describe("DynamicForm", () => {
  it("renders form with params and flags from command tree", () => {
    render(DynamicForm, {
      props: {
        commandPath: ["node", "add"],
      },
    });

    // Param label should be rendered
    expect(screen.getByText("labels")).toBeTruthy();
    // Flag labels should be rendered
    expect(screen.getByText("color")).toBeTruthy();
    expect(screen.getByText("pin")).toBeTruthy();
  });

  it("shows required badge for required params", () => {
    render(DynamicForm, {
      props: {
        commandPath: ["node", "add"],
      },
    });

    expect(screen.getByText("required")).toBeTruthy();
  });

  it("calls onsubmit with tokens, flags, and remaining when form is submitted", async () => {
    const onsubmit = vi.fn();
    render(DynamicForm, {
      props: {
        commandPath: ["node", "add"],
        onsubmit,
      },
    });

    // Fill in the required param (labels)
    const textboxes = screen.getAllByRole("textbox");
    const labelsInput = textboxes[0];
    await fireEvent.input(labelsInput, { target: { value: "TestNode" } });

    // Fill in the color flag
    const colorInput = textboxes[1];
    await fireEvent.input(colorInput, { target: { value: "red" } });

    // Check the pin flag via checkbox
    const pinCheckbox = screen.getByRole("checkbox", { name: /Pin the node/i });
    await fireEvent.click(pinCheckbox);

    // Submit the form (button text is "Save")
    const saveBtn = screen.getByText("Save");
    await fireEvent.click(saveBtn);

    expect(onsubmit).toHaveBeenCalledOnce();
    expect(onsubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        tokens: ["node", "add"],
        flags: expect.objectContaining({ color: "red", pin: "true" }),
        remaining: ["TestNode"],
      })
    );
  });

  it("shows validation error when required field is empty on submit", async () => {
    render(DynamicForm, {
      props: {
        commandPath: ["node", "add"],
      },
    });

    // Submit without filling required field (button text is "Save")
    const saveBtn = screen.getByText("Save");
    await fireEvent.click(saveBtn);

    // Should show error message
    expect(screen.getByText("labels is required")).toBeTruthy();
  });

  it("renders Save button text", () => {
    render(DynamicForm, {
      props: {
        commandPath: ["node", "add"],
      },
    });

    expect(screen.getByText("Save")).toBeTruthy();
  });
});
