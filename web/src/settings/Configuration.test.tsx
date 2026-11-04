/**
 * Settings ▸ Vocabularies: a vocabulary's accent is chosen beside its languages and saved with it,
 * through the repository like every other edit of the vocabulary.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { backendSession } from "../api";
import { repository } from "../repository";
import { testGraph } from "../testGraph";
import { VocabularyEditor } from "./Configuration";
import { SubPages } from "./testVoices";

afterEach(() => vi.restoreAllMocks());

describe("Settings ▸ Vocabularies", () => {
  it("saves an accent as a region code, and shows it on the list", async () => {
    vi.spyOn(backendSession, "pronunciationSettings").mockRejectedValue(new Error("away"));
    const saved = vi.spyOn(repository, "saveVocabulary").mockResolvedValue(undefined as never);
    const graph = testGraph();
    const snapshot = { ...graph, vocabularies: graph.vocabularies.map((entry) =>
      entry.language === "en" ? { ...entry, region: "GB" } : entry) };
    render(<SubPages><VocabularyEditor snapshot={snapshot as never} onNotify={() => undefined} onChanged={() => undefined} /></SubPages>);

    expect(screen.getByRole("button", { name: /English/ })).toHaveTextContent("en · United Kingdom");
    fireEvent.click(screen.getByRole("button", { name: /Spanish/ }));
    const accent = await screen.findByRole("combobox", { name: "Accent" });
    expect([...accent.querySelectorAll("option")].map((option) => option.textContent))
      .toEqual(expect.arrayContaining(["None", "Spain", "Mexico", "Argentina", "Latin America"]));
    fireEvent.change(accent, { target: { value: "AR" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saved).toHaveBeenCalledWith(
      expect.objectContaining({ language: "es", region: "AR" }), expect.any(String)));
  });
});
