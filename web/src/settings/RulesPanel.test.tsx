/** Settings ▸ Rules: read from the server, saved with a button, and capped where the server caps. */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const promptRules = vi.fn();
const savePromptRules = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    backendSession: {
      ...actual.backendSession,
      promptRules: () => promptRules(),
      savePromptRules: (rules: string) => savePromptRules(rules)
    }
  };
});

const { default: RulesPanel } = await import("./RulesPanel");

afterEach(() => vi.clearAllMocks());

describe("RulesPanel", () => {
  it("shows the stored rules and saves an edit only when asked", async () => {
    promptRules.mockResolvedValue({ rules: "I am vegan.", chosen: true, limit: 4000 });
    savePromptRules.mockImplementation(async (rules: string) => ({ rules, chosen: true, limit: 4000 }));
    const onNotify = vi.fn();
    render(<RulesPanel onNotify={onNotify} />);

    const box = await screen.findByLabelText("Rules for generated content");
    expect(box).toHaveValue("I am vegan.");
    const save = screen.getByRole("button", { name: "Save" });
    expect(save).toBeDisabled();

    fireEvent.change(box, { target: { value: "I am vegan. Keep examples at B2." } });
    expect(savePromptRules).not.toHaveBeenCalled();
    fireEvent.click(save);

    await waitFor(() => expect(savePromptRules).toHaveBeenCalledWith("I am vegan. Keep examples at B2."));
    await waitFor(() => expect(onNotify).toHaveBeenCalledWith("Rules saved."));
  });

  it("will not save more than the server keeps", async () => {
    promptRules.mockResolvedValue({ rules: "", chosen: false, limit: 10 });
    render(<RulesPanel onNotify={vi.fn()} />);

    fireEvent.change(await screen.findByLabelText("Rules for generated content"),
      { target: { value: "far too many characters" } });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("says so when the server cannot be reached", async () => {
    promptRules.mockRejectedValue(new Error("offline"));
    render(<RulesPanel onNotify={vi.fn()} />);
    expect(await screen.findByText(/on the server, which could not be reached/)).toBeInTheDocument();
  });
});
