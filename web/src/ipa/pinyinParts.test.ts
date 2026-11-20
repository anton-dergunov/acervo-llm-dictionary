import { describe, expect, it } from "vitest";
import vectors from "../testFixtures/pinyinPartsVectors.json";
import { finalRow, initialAndFinal, pinyinParts } from "./pinyinParts";

describe("initialAndFinal", () => {
  it("cuts every syllable where the server does", () => {
    for (const [syllable, initial, final] of vectors.parts as [string, string, string][]) {
      expect([syllable, ...initialAndFinal(syllable)]).toEqual([syllable, initial, final]);
    }
  });

  it("finds a row for every final the server reaches", () => {
    for (const [, initial, final] of vectors.parts as [string, string, string][]) {
      expect(finalRow(initial, final)?.letters ?? `${initial}+${final}`).not.toContain("+");
    }
  });
});

describe("pinyinParts", () => {
  it("names each syllable's initial, final and tone as the learner sees them written", () => {
    const parts = pinyinParts("túshūguǎn")!;
    expect(parts.map((part) => [part.initial?.letters ?? null, part.final?.letters, part.tone?.number])).toEqual([
      ["t", "u", 2], ["sh", "u", 1], ["g", "uan", 3]
    ]);
  });

  it("maps full spellings back to the rows and finds the apical i and erhua", () => {
    expect(pinyinParts("yǒu")![0].final?.letters).toBe("iu");
    expect(pinyinParts("shì")![0].final?.letters).toBe("-i (zh ch sh r)");
    expect(pinyinParts("jù")![0].final?.letters).toBe("ü");
    const [point] = pinyinParts("diǎnr")!;
    expect([point.final?.letters, point.erhua?.letters]).toEqual(["ian", "r (erhua)"]);
  });

  it("refuses what is not Pinyin", () => {
    expect(pinyinParts("hello world")).toBeNull();
  });
});
