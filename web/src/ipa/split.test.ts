import { describe, expect, it } from "vitest";
import { distinctUnits, soundOf, splitTranscription, type Unit } from "./split";
import { readTone } from "./table";

const shown = (units: Unit[]) => units.map((unit) => `${unit.kind}:${unit.text}`);

describe("splitTranscription", () => {
  it("cuts a Mandarin transcription into sounds and tones", () => {
    expect(shown(splitTranscription("/tʰu˧˥ ʂu˥ ku̯an˨˩˦/"))).toEqual([
      "sound:tʰ", "sound:u", "tone:˧˥", "sound:ʂ", "sound:u", "tone:˥", "sound:k", "sound:u̯", "sound:a", "sound:n", "tone:˨˩˦"
    ]);
  });

  it("matches a letter with a recorded mark whole, and keeps other marks on their letter", () => {
    const [aspirated, glide] = splitTranscription("tʰu̯");
    expect(aspirated.kind === "sound" && aspirated.rows[0].symbol).toBe("tʰ");
    expect(aspirated.kind === "sound" && aspirated.marks).toEqual([]);
    expect(glide.kind === "sound" && glide.rows[0].symbol).toBe("u");
    expect(glide.kind === "sound" && glide.marks.map((mark) => mark.row.name)).toEqual(["non-syllabic"]);
  });

  it("plays a combination's own recording and a marked letter's bare one", () => {
    const [aspirated, labialized] = splitTranscription("tʰkʷ");
    expect(soundOf(aspirated)).toBe(splitTranscription("tʰ").map(soundOf)[0]);
    expect(soundOf(labialized)).toBe(soundOf(splitTranscription("k")[0]));
    expect(soundOf(labialized)).toBeTruthy();
  });

  it("keeps stress and phrasing between sounds, and length on its letter", () => {
    expect(shown(splitTranscription("/prəˌnʌnsiˈeɪʃən/")).slice(0, 5)).toEqual(["sound:p", "sound:r", "sound:ə", "mark:ˌ", "sound:n"]);
    const [long] = splitTranscription("siː").slice(1);
    expect(long.kind === "sound" && long.marks.map((mark) => mark.row.name)).toEqual(["long"]);
    expect(splitTranscription("a:")[0].text).toBe("a:");
  });

  it("reads an affricate as one sound with or without a tie bar, and joins any two tied letters", () => {
    for (const written of ["ts", "t͡s", "ʦ"]) {
      const units = splitTranscription(written);
      expect(units).toHaveLength(1);
      expect(units[0].kind === "sound" && units[0].rows[0].symbol).toBe("ts");
    }
    const [doubly] = splitTranscription("k͡p");
    expect(doubly.kind === "sound" && doubly.rows.map((row) => row.symbol)).toEqual(["k", "p"]);
    expect(soundOf(doubly)).toBeUndefined();
  });

  it("maps aliases, reads precomposed letters as letter and mark, and keeps what it does not know", () => {
    const [typed, nasal, palatal] = splitTranscription("gãç");
    expect(typed.kind === "sound" && typed.rows[0].symbol).toBe("ɡ");
    expect(nasal.kind === "sound" && nasal.marks.map((mark) => mark.row.name)).toEqual(["nasalized"]);
    expect(palatal.kind === "sound" && [palatal.rows[0].symbol, palatal.marks.length]).toEqual(["ç", 0]);
    expect(shown(splitTranscription("a7"))).toEqual(["sound:a", "unknown:7"]);
    expect(splitTranscription("[ ]. /")).toEqual([]);
  });

  it("lists each unit once", () => {
    expect(shown(distinctUnits(splitTranscription("/ˈbænənə/")))).toEqual(["mark:ˈ", "sound:b", "sound:æ", "sound:n", "sound:ə"]);
  });
});

describe("readTone", () => {
  it("names the table's contours and describes any other", () => {
    expect(readTone("˧˥")).toMatchObject({ name: "rising", mandarin: expect.stringContaining("2nd tone"), levels: [3, 5] });
    expect(readTone("˩˧").name).toBe("rising");
    expect(readTone("˩˧").how).toBe("The pitch moves from extra low, then mid.");
    expect(readTone("˧˧").name).toBe("mid level");
  });
});
