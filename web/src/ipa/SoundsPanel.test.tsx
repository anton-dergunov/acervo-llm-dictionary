import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import * as pronunciation from "../pronunciation";
import { Transcription } from "./Transcription";
import { setIpaTrial } from "./trial";

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

  it("explains a mark inside its letter's row, or on a row of its own", async () => {
    const inside = await openPanel("/ku̯a/");
    expect(symbols(inside)).toEqual(["k", "u̯", "a"]);
    expect(within(inside).getByText("non-syllabic")).toBeTruthy();
    act(() => setIpaTrial("marks", "rows"));
    expect(symbols(inside)).toEqual(["k", "u", "◌̯", "a"]);
  });

  it("names stress once at the top inside, and as rows of their own otherwise", async () => {
    const panel = await openPanel("/əˈbaʊt/");
    expect(panel.querySelector(".ipa-stress")?.textContent).toBe("ˈ");
    expect(within(panel.querySelector(".ipa-marks-note") as HTMLElement).getByText("primary stress")).toBeTruthy();
    act(() => setIpaTrial("marks", "rows"));
    expect(symbols(panel)[0]).toBe("ə");
    expect(symbols(panel)).toContain("ˈ◌");
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
