/**
 * Which player is the one playing, and the lock screen that speaks for it: claimed by whichever starts
 * last, and given up only by its own player.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { claim, listening, release, resetListeningForTests } from "./listening";

const screen = (title: string) => ({
  title, artist: "", play: vi.fn(), pause: vi.fn(), previous: vi.fn(), next: vi.fn()
});

afterEach(() => resetListeningForTests());

describe("the one playing", () => {
  it("is whichever started last", () => {
    claim("loop", screen("la obra"));
    claim("story", screen("La balsa"));
    expect(listening()).toBe("story");
  });

  /* A loop stopped after a story started must not take the story's lock screen with it. */
  it("is let go only by its own player", () => {
    claim("loop", screen("la obra"));
    claim("story", screen("La balsa"));
    release("loop");
    expect(listening()).toBe("story");
    release("story");
    expect(listening()).toBeNull();
  });
});
