import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/svelte";
import FormField from "../FormField.svelte";

describe("FormField", () => {
  it("renders label and hint", () => {
    render(FormField, {
      props: {
        label: "Username",
        hint: "Your login name",
      },
    });
    expect(screen.getByText("Username")).toBeTruthy();
    expect(screen.getByText("Your login name")).toBeTruthy();
  });

  it("shows required badge when required", () => {
    render(FormField, {
      props: {
        label: "Email",
        required: true,
      },
    });
    expect(screen.getByText(/required/)).toBeTruthy();
  });

  it("does not show required badge when not required", () => {
    render(FormField, {
      props: {
        label: "Nickname",
        required: false,
      },
    });
    expect(screen.queryByText("required")).toBeNull();
  });

  it("shows error message when error is provided", () => {
    render(FormField, {
      props: {
        label: "Password",
        error: "Password is too short",
      },
    });
    expect(screen.getByText("Password is too short")).toBeTruthy();
  });

  it("has-error class when error is present", () => {
    const { container } = render(FormField, {
      props: {
        label: "Code",
        error: "Invalid code",
      },
    });
    expect(container.querySelector(".has-error")).toBeTruthy();
  });

  it("no has-error class when error is absent", () => {
    const { container } = render(FormField, {
      props: {
        label: "Code",
      },
    });
    expect(container.querySelector(".has-error")).toBeNull();
  });
});
