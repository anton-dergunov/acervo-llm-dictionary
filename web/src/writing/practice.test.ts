import { describe, expect, it } from "vitest";
import { attempt, feedback, FILL_AFTER, HINT_AFTER, isDone, markHinted, nextStroke, startRun, summarize, type Run } from "./practice";
import { fixture, traced } from "./testStrokes";

const kou = fixture("口");
const scribble = traced([{ x: 100, y: 100 }, { x: 900, y: 120 }, { x: 120, y: 700 }, { x: 880, y: 680 }]);

function writeAll(run: Run, symbol = kou): Run {
  let current = run;
  for (const stroke of symbol.strokes.slice(nextStroke(run))) {
    current = attempt(current, symbol, traced(stroke.median), { outline: true }).run;
  }
  return current;
}

describe("writing a character stroke by stroke", () => {
  it("accepts each stroke in order and finishes clean", () => {
    const run = writeAll(startRun());
    expect(isDone(run, kou)).toBe(true);
    expect(summarize(run)).toEqual({ strokes: 3, clean: 3, outOfOrder: 0, backwards: 0, filled: 0, precision: 100 });
  });

  it("refuses a stroke out of order, counts it, and says which stroke comes first", () => {
    const { run, outcome } = attempt(startRun(), kou, traced(kou.strokes[2].median), { outline: true });
    expect(nextStroke(run)).toBe(0);
    expect(outcome).toEqual({ kind: "refused", stroke: 0, why: { kind: "later", drawn: 2 }, hint: false });
    expect(feedback(outcome)).toBe("That's stroke 3 — stroke 1 comes first.");
    const finished = summarize(writeAll(run));
    expect(finished.outOfOrder).toBe(1);
    expect(finished.clean).toBe(2);
  });

  it("says a backwards stroke is the right one the other way round", () => {
    const { outcome } = attempt(startRun(), kou, traced(kou.strokes[0].median).reverse(), { outline: true });
    expect(feedback(outcome)).toBe("Right stroke, other way round — start at the dot.");
  });

  it(`shows the stroke after ${HINT_AFTER} misses and writes it in after ${FILL_AFTER}`, () => {
    let run = startRun();
    const outcomes = [];
    for (let index = 0; index < FILL_AFTER; index += 1) {
      const next = attempt(run, kou, scribble, { outline: true });
      run = next.run;
      outcomes.push(next.outcome);
    }
    expect(outcomes.map((one) => one.kind === "refused" && one.hint)).toEqual([false, true, true, false]);
    expect(outcomes[FILL_AFTER - 1]).toEqual({ kind: "filled", stroke: 0 });
    expect(feedback(outcomes[1])).toBe("Not quite — try stroke 1 again. Watch it once.");
    expect(nextStroke(run)).toBe(1);
    const summary = summarize(writeAll(run));
    expect(summary).toMatchObject({ strokes: 3, clean: 2, filled: 1, precision: 100 });
  });

  it("does not count a stroke shown by a hint as clean", () => {
    const run = writeAll(markHinted(startRun()));
    expect(summarize(run).clean).toBe(2);
  });

  it("refuses to go past the last stroke", () => {
    expect(() => attempt(writeAll(startRun()), kou, scribble, { outline: true })).toThrow();
  });
});
