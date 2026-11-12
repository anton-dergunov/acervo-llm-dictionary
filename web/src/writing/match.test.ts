import { describe, expect, it } from "vitest";
import { gradeStroke } from "./grade";
import { judge, strokeMatches } from "./match";
import { fixture, shaky, shifted, traced } from "./testStrokes";

describe("a stroke is accepted only when it is the next one, written the right way", () => {
  it.each(["人", "口", "妈", "水"] as const)("every stroke of %s, drawn along its median in order, is accepted", (symbol) => {
    const character = fixture(symbol);
    for (const stroke of character.strokes) {
      expect(strokeMatches(traced(stroke.median), character, stroke.index, { outline: true }).isMatch).toBe(true);
    }
  });

  it("is the same without an outline", () => {
    const character = fixture("妈");
    for (const stroke of character.strokes) {
      expect(judge(traced(stroke.median), character, stroke.index)).toEqual({ kind: "match" });
    }
  });

  it("refuses a stroke drawn from its end to its start, and says so", () => {
    const character = fixture("人");
    const reversed = traced(character.strokes[0].median).reverse();
    expect(strokeMatches(reversed, character, 0).isMatch).toBe(false);
    expect(judge(reversed, character, 0)).toEqual({ kind: "backwards" });
  });

  it("names a later stroke drawn before its turn", () => {
    // 口: the left vertical, then the top-and-right, then the bottom. The bottom drawn first:
    const character = fixture("口");
    expect(judge(traced(character.strokes[2].median), character, 0)).toEqual({ kind: "later", drawn: 2 });
  });

  it("names a stroke already written when it is drawn again", () => {
    const character = fixture("水");
    expect(judge(traced(character.strokes[0].median), character, 2)).toEqual({ kind: "earlier", drawn: 0 });
  });

  it("refuses a scribble as a miss", () => {
    const character = fixture("人");
    const scribble = [{ x: 100, y: 100 }, { x: 900, y: 120 }, { x: 120, y: 700 }, { x: 880, y: 680 }];
    expect(judge(traced(scribble), character, 0)).toEqual({ kind: "miss" });
  });

  it("refuses a tap", () => {
    const character = fixture("人");
    const at = character.strokes[0].median[0];
    expect(judge([at, at], character, 0)).toEqual({ kind: "miss" });
  });

  it("accepts a rough but right stroke, and grades it lower than a clean one", () => {
    const character = fixture("水");
    const median = character.strokes[0].median;
    const rough = shaky(median, 30);
    expect(judge(rough, character, 0, { outline: true })).toEqual({ kind: "match" });
    expect(gradeStroke(rough, median).score).toBeLessThan(gradeStroke(traced(median), median).score);
  });
});

describe("the precision grade", () => {
  const median = fixture("妈").strokes[4].median;

  it("is full for a stroke drawn on its median", () => {
    expect(gradeStroke(traced(median), median).score).toBe(100);
  });

  it("falls as the stroke moves off its line", () => {
    const near = gradeStroke(shifted(median, 20, 0), median).score;
    const far = gradeStroke(shifted(median, 70, 0), median).score;
    expect(near).toBeLessThan(100);
    expect(far).toBeLessThan(near);
  });

  it("does not grade a stroke that stops halfway as close", () => {
    const half = traced(median).slice(0, Math.floor(traced(median).length / 2));
    expect(gradeStroke(half, median).score).toBeLessThan(80);
  });
});
