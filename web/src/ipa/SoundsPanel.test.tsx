import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as pronunciation from "../pronunciation";
import { Transcription } from "./Transcription";

async function openPanel(ipa: string, reading: string | null = null, language: string | null = null) {
  render(<div className="pron-row"><Transcription ipa={ipa} reading={reading} language={language} /></div>);
  fireEvent.click(screen.getByRole("button", { name: ipa }));
  /* The panel is loaded on the first tap, which can take a moment on a busy test run. */
  return screen.findByRole("dialog", { name: `Sounds in ${ipa}` }, { timeout: 5000 });
}

const symbols = (panel: HTMLElement) => [...panel.querySelectorAll(":scope > .ipa-rows .ipa-sym")].map((cell) => cell.textContent);

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

describe("the IPA guide's panel", () => {
  it("lists each sound and tone of a Mandarin word once, then its Pinyin", async () => {
    const panel = await openPanel("/tʰu˧˥ ʂu˥ ku̯an˨˩˦/", "túshūguǎn", "zh-Hans");
    expect(symbols(panel)).toEqual(["tʰ", "u", "˧˥", "ʂ", "˥", "k", "u̯", "a", "n", "˨˩˦"]);
    expect(within(panel).getByText(/^Rising\./)).toBeTruthy();
    expect(within(panel).getByText(/2nd tone/)).toBeTruthy();
    const pinyin = within(panel).getByRole("region", { name: "Pinyin" });
    expect([...pinyin.querySelectorAll(".ipa-syllable-name")].map((name) => name.textContent)).toEqual(["tú", "shū", "guǎn"]);
  });

  it("explains a mark inside its letter's row, on a dotted circle", async () => {
    const panel = await openPanel("/ku̯a/");
    expect(symbols(panel)).toEqual(["k", "u̯", "a"]);
    expect(panel.querySelector(".ipa-mark-line .ipa-mark-sym")?.textContent).toBe("◌̯");
    expect(within(panel).getByText("non-syllabic")).toBeTruthy();
  });

  it("puts stress on a row of its own where the transcription has it, and lights it at the top", async () => {
    const panel = await openPanel("/əˈbaʊt/");
    expect(panel.querySelector(".ipa-stress")?.textContent).toBe("ˈ");
    expect(symbols(panel).slice(0, 3)).toEqual(["ə", "ˈ◌", "b"]);
    expect(within(panel).getByText(/^Primary stress\./)).toBeTruthy();
  });

  it("says what a recording says when it is a syllable, and shows a Pinyin tone by its mark", async () => {
    const panel = await openPanel("/tou̯˥˩ fu/", "dòufu", "zh-Hans");
    const pinyin = within(panel).getByRole("region", { name: "Pinyin" });
    const [initial] = pinyin.querySelectorAll(".ipa-row");
    expect(initial.textContent).toContain("The recording says dà.");
    expect([...pinyin.querySelectorAll(".ipa-tone-mark")].map((mark) => mark.textContent)).toEqual(["◌̀", "◌"]);
    expect(within(panel).getAllByText(/The recording says/).length).toBeGreaterThan(3);
  });

  it("plays a sound's recording through the app's one player", async () => {
    const preview = vi.spyOn(pronunciation, "playPreview").mockResolvedValue();
    const panel = await openPanel("/p/");
    fireEvent.click(within(panel).getByRole("button", { name: "Listen to voiceless bilabial plosive" }));
    expect(preview).toHaveBeenCalledWith(expect.stringMatching(/^ipa:[0-9a-f]{16}\.ogg$/), expect.any(Function));
  });

  it("closes on Escape and on its close button", async () => {
    await openPanel("/a/");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "/a/" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
