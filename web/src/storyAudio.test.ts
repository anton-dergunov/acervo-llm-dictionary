/**
 * Hearing a story: what a press does at each state, how it reads on from part to part and story to
 * story, and what a passage touched does.
 *
 * The element is played the way a browser plays it rather than the way `testSetup` fakes it — there,
 * a clip "plays" by ending on the next tick, which would finish every part before a test could look
 * at it. Here `play` and `pause` move a flag, `currentTime` is written by the player and read back
 * from what the test says the recording has reached, and `tick()` is one turn of the clock. The
 * pattern is `loops.test.ts`'s, for the same reason.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Story, StoryPart, VocabularyGraph } from "./domain";
import { MemoryMediaStore } from "./mediaStore";
import { testGraph } from "./testGraph";

let reported = 0;
let asked: number | null = null;
let paused = true;
let made: HTMLAudioElement | null = null;
let frames: FrameRequestCallback[] = [];
let plays = 0;

function tick(): void {
  const due = frames;
  frames = [];
  due.forEach((run) => run(performance.now()));
}

type Player = typeof import("./storyAudio");
type Speech = typeof import("./pronunciation");
let player: Player;
let speech: Speech;
let api: typeof import("./api");
let counted: { recordPlay: ReturnType<typeof vi.fn> };
let listening: typeof import("./listening");

vi.mock("./plays", () => ({ recordPlay: vi.fn() }));

const graph = testGraph();
const story = graph.stories.find((one) => one.id === "storypicada0001")!;
const [recorded, unrecorded] = graph.storyParts;
const parts = [recorded, unrecorded];

/** One passage of a part the server has just recorded. */
const fresh = (digest: string) => ({
  text: unrecorded.text, direction: "", audioMime: "audio/ogg", durationSeconds: 2,
  audioRef: `stories/storypicada0001/storypart000002-00-${digest}.ogg`
});

async function playing(): Promise<void> {
  await vi.waitFor(() => expect(player.storyPlayback().status).toBe("playing"));
}

beforeEach(async () => {
  reported = 0; asked = null; paused = true; made = null; frames = []; plays = 0;

  Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
    configurable: true, get: () => reported, set: (value: number) => { asked = value; reported = value; }
  });
  Object.defineProperty(HTMLMediaElement.prototype, "paused", { configurable: true, get: () => paused });
  // jsdom has no media pipeline, so an element never reaches HAVE_METADATA on its own and never
  // fires `loadedmetadata`. The player waits for that before moving to a passage, so the fake says
  // what a browser says once a blob is in hand.
  Object.defineProperty(HTMLMediaElement.prototype, "readyState", { configurable: true, get: () => 1 });
  const originalPlay = HTMLMediaElement.prototype.play;
  const originalPause = HTMLMediaElement.prototype.pause;
  HTMLMediaElement.prototype.play = function play(this: HTMLMediaElement) {
    plays += 1;
    paused = false;
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  };
  HTMLMediaElement.prototype.pause = function pause(this: HTMLMediaElement) {
    if (paused) return;
    paused = true;
    this.dispatchEvent(new Event("pause"));
  };
  afterEachRestore = () => {
    HTMLMediaElement.prototype.play = originalPlay;
    HTMLMediaElement.prototype.pause = originalPause;
  };

  const Element = globalThis.Audio;
  vi.stubGlobal("Audio", class extends Element {
    constructor() { super(); made = this as unknown as HTMLAudioElement; }
  });
  vi.stubGlobal("requestAnimationFrame", (run: FrameRequestCallback) => { frames.push(run); return frames.length; });
  vi.stubGlobal("cancelAnimationFrame", () => { frames = []; });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: true, status: 200, blob: async () => new Blob(["ogg"], { type: "audio/ogg" })
  }));

  // A fresh module graph, so the element and the registry of players are this test's own.
  vi.resetModules();
  player = await import("./storyAudio");
  speech = await import("./pronunciation");
  api = await import("./api");
  speech.replaceStoreForTests(new MemoryMediaStore());
  player.replaceForTests();
  vi.spyOn(api.backendSession, "mediaFileUrl").mockImplementation((reference) => `https://acervo.example.com/media/${reference}`);
  vi.spyOn(api.backendSession, "mediaHeaders").mockReturnValue({ Authorization: "Bearer token" });
  counted = await import("./plays") as unknown as { recordPlay: ReturnType<typeof vi.fn> };
  counted.recordPlay.mockClear();
  listening = await import("./listening");
  listening.resetListeningForTests();
  const sync = await import("./sync");
  vi.spyOn(sync.syncEngine, "syncNow").mockResolvedValue(sync.syncEngine.getStatus());
});

let afterEachRestore: () => void = () => undefined;
afterEach(() => {
  player.stop();
  afterEachRestore();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  Reflect.deleteProperty(HTMLMediaElement.prototype, "currentTime");
  Reflect.deleteProperty(HTMLMediaElement.prototype, "paused");
  Reflect.deleteProperty(HTMLMediaElement.prototype, "readyState");
});

/** The passage that just ended, so the next one starts — what a browser does at the end of a file. */
const ended = () => made!.dispatchEvent(new Event("ended"));

/** A part of three passages, so "read on" has somewhere to go within a part. */
const three: StoryPart = {
  ...recorded,
  audioSegments: [0, 1, 2].map((index) => ({
    text: `Passage ${index}. `, direction: "", audioMime: "audio/ogg", durationSeconds: 1,
    audioRef: `stories/storypicada0001/storypart000001-0${index}-aaaa000${index}.ogg`
  }))
};
/** The second part, recorded, so a story reads on into it without asking the server. */
const second: StoryPart = { ...unrecorded, audioSegments: [fresh("bbbb2222")] };

describe("pressing play", () => {
  it("reads a recorded part from the start, fetching its recording once", async () => {
    player.toggleStory(story, [recorded], 0);
    await playing();

    expect(player.storyPlayback()).toMatchObject({ storyId: story.id, partId: recorded.id, partIndex: 0, passages: 2 });
    // Every passage is fetched before the first sounds, so the swap between them is an assignment.
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(String((fetch as unknown as { mock: { calls: string[][] } }).mock.calls[0][0]))
      .toBe(`https://acervo.example.com/media/${recorded.audioSegments[0].audioRef}`);
  });

  it("pauses when it is playing and carries on from where it was when pressed again", async () => {
    player.toggleStory(story, parts, 0);
    await playing();
    reported = 1.4;

    player.toggleStory(story, parts, 0);
    expect(player.storyPlayback().status).toBe("paused");
    expect(paused).toBe(true);

    player.toggleStory(story, parts, 0);
    expect(player.storyPlayback().status).toBe("playing");
  });

  it("is not ended by the silence that was started to keep the gesture", async () => {
    let arrive: (row: StoryPart) => void = () => undefined;
    vi.spyOn(api.backendSession, "recordStoryPart").mockReturnValue(new Promise((resolve) => { arrive = resolve; }));

    player.toggleStory(story, parts, 1);
    expect(player.storyPlayback().status).toBe("busy");
    ended();   // the silence finishing, long before the part exists
    expect(player.storyPlayback()).toMatchObject({ status: "busy", partId: unrecorded.id });

    arrive({ ...unrecorded, audioSegments: [fresh("aaaa1111")] });
    await playing();
  });

  it("pressing it while a part is still being recorded cancels that", async () => {
    vi.spyOn(api.backendSession, "recordStoryPart").mockReturnValue(new Promise(() => undefined));

    player.toggleStory(story, parts, 1);
    player.toggleStory(story, parts, 1);

    expect(player.storyPlayback()).toMatchObject({ status: "idle", storyId: null });
  });

  it("is what the lock screen speaks for, until it is stopped", async () => {
    player.toggleStory(story, parts, 0);
    await playing();
    expect(listening.listening()).toBe("story");

    player.stop();
    expect(listening.listening()).toBeNull();
  });
});

describe("reading on", () => {
  it("goes on to the next part when a part ends, and counts the read on reaching it", async () => {
    player.toggleStory(story, [recorded, second], 0);
    await playing();
    expect(counted.recordPlay).not.toHaveBeenCalled();

    ended();
    await vi.waitFor(() => expect(player.storyPlayback().segment).toBe(1));
    ended();
    await vi.waitFor(() => expect(player.storyPlayback()).toMatchObject({ partIndex: 1, partId: second.id, status: "playing" }));
    expect(counted.recordPlay).toHaveBeenCalledWith("story", story.id);
  });

  it("records a part on the way that has no recording, and reads it", async () => {
    const record = vi.spyOn(api.backendSession, "recordStoryPart").mockResolvedValue(second);
    player.toggleStory(story, parts, 0);
    await playing();

    ended();
    await vi.waitFor(() => expect(player.storyPlayback().segment).toBe(1));
    ended();
    await vi.waitFor(() => expect(player.storyPlayback()).toMatchObject({ partIndex: 1, status: "playing" }));
    expect(record).toHaveBeenCalledWith(unrecorded.storyId, unrecorded.id, expect.any(String));
  });

  it("rests at the end with the story still loaded, so play reads it again", async () => {
    player.toggleStory(story, [three], 0);
    await playing();
    ended();
    await vi.waitFor(() => expect(player.storyPlayback().segment).toBe(1));
    ended();
    await vi.waitFor(() => expect(player.storyPlayback().segment).toBe(2));
    ended();

    expect(player.storyPlayback()).toMatchObject({ storyId: story.id, status: "idle", segment: null });
    player.toggleStory(story, [three], 0);
    await playing();
    expect(player.storyPlayback().segment).toBe(0);
  });

  it("goes on to the next story in the list when asked to, and only then", async () => {
    const next: Story = { ...story, id: "storysecond0001", title: "La segunda" };
    const nextPart: StoryPart = { ...second, id: "storypartsecond", storyId: next.id };
    const repository = await import("./repository");
    vi.spyOn(repository.repository, "snapshot").mockReturnValue({
      ...graph, stories: [story, next], storyParts: [recorded, nextPart]
    } as VocabularyGraph as ReturnType<typeof repository.repository.snapshot>);
    const preferences = await import("./editorPreferences");
    player.setStoryQueue([story.id, next.id]);
    expect((() => { player.toggleStory(story, [recorded], 0); return player.hasNextStory(); })()).toBe(true);
    await playing();

    preferences.setStoryAutoplay(true);
    ended();
    await vi.waitFor(() => expect(player.storyPlayback().segment).toBe(1));
    ended();
    await vi.waitFor(() => expect(player.storyPlayback()).toMatchObject({ storyId: next.id, status: "playing" }));
    preferences.setStoryAutoplay(false);
  });

  it("steps a part at a time, back to the top of this one first", async () => {
    player.toggleStory(story, [recorded, second], 1);
    await playing();
    reported = 5;

    player.stepPart(-1);
    await vi.waitFor(() => expect(player.storyPlayback()).toMatchObject({ partIndex: 1, segment: 0, status: "playing" }));
    reported = 0;
    player.stepPart(-1);
    await vi.waitFor(() => expect(player.storyPlayback()).toMatchObject({ partIndex: 0, status: "playing" }));
  });
});

describe("a part that cannot be recorded", () => {
  it("says why when the server could not, and leaves play pressable", async () => {
    vi.spyOn(api.backendSession, "recordStoryPart")
      .mockRejectedValue(new api.AcervoApiError("The speech model is temporarily rate limited.", 503, "llm_rate_limited"));

    player.toggleStory(story, parts, 1);
    await vi.waitFor(() => expect(player.storyPlayback().failed).not.toBeNull());

    expect(player.storyPlayback()).toMatchObject({
      partId: unrecorded.id, status: "idle", failed: "The speech model is temporarily rate limited."
    });
    expect(made!.getAttribute("src")).toBeNull();
  });

  it("says the server is needed when it cannot be reached", async () => {
    vi.spyOn(api.backendSession, "recordStoryPart")
      .mockRejectedValue(new api.AcervoApiError("offline", 0, "offline"));

    player.toggleStory(story, parts, 1);
    await vi.waitFor(() => expect(player.storyPlayback().failed).toMatch(/needs the server/));
  });
});

describe("a passage touched", () => {
  it("plays only that passage when nothing of the story is sounding, and is not a read", async () => {
    player.playSegment(story, [three], 0, 1);
    await playing();

    expect(player.storyPlayback().segment).toBe(1);
    ended();

    expect(player.storyPlayback()).toMatchObject({ status: "idle", segment: null });
    expect(counted.recordPlay).not.toHaveBeenCalled();
  });

  it("moves the voice there and reads on when the story is sounding", async () => {
    player.toggleStory(story, [three], 0);
    await playing();

    player.playSegment(story, [three], 0, 1);
    await vi.waitFor(() => expect(player.storyPlayback().segment).toBe(1));
    ended();
    await vi.waitFor(() => expect(player.storyPlayback().segment).toBe(2));
  });

  it("ignores a passage the part does not have", () => {
    player.playSegment(story, [recorded], 0, 7);
    expect(player.storyPlayback().status).toBe("idle");
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("one sound at a time", () => {
  it("stops a word being read, and pauses every other player, before it plays", async () => {
    const stopSpeech = vi.spyOn(speech, "stop");
    const other = vi.fn();
    speech.registerPlayer(other);

    player.toggleStory(story, parts, 0);
    await playing();

    expect(stopSpeech).toHaveBeenCalled();
    expect(other).toHaveBeenCalled();
  });

  it("is paused by whatever else starts to play", async () => {
    player.toggleStory(story, parts, 0);
    await playing();

    speech.silencePlayers();   // what a word being read, or a loop, does before it makes a sound

    expect(player.storyPlayback().status).toBe("paused");
    expect(paused).toBe(true);
  });

  it("does not fetch again to pause and carry on", async () => {
    player.toggleStory(story, parts, 0);
    await playing();
    (fetch as unknown as { mockClear(): void }).mockClear();

    player.toggleStory(story, parts, 0);
    player.toggleStory(story, parts, 0);

    expect(fetch).not.toHaveBeenCalled();
    expect(plays).toBeGreaterThanOrEqual(2);
  });
});
