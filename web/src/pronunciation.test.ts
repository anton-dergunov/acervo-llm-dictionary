import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AcervoApiError, backendSession } from "./api";
import type { Pronunciation } from "./domain";
import { setPronunciationCacheEnabled } from "./editorPreferences";
import { MemoryMediaStore } from "./mediaStore";
import {
  clipBytes, currentClip, fill, forgetPronunciations, play, playPreview, replaceStoreForTests, stopPreview, usePreviewProgress
} from "./pronunciation";
import { repository } from "./repository";
import { syncEngine } from "./sync";
import { TEST_OWNER, testGraph } from "./testGraph";

/**
 * Hearing a word, and the two things that make it offline-first: the clip in the replica, and the
 * bytes on the device. The audio element itself is jsdom's, filled in by `testSetup.ts`.
 */

const HEADWORD = { kind: "lexeme" as const, id: "lexemepicar0001", text: "picar", lang: "es" };
const CLIP = () => repository.snapshot().pronunciations[0];
const MP3 = () => new Blob(["ID3-audio"], { type: "audio/mpeg" });

let store: MemoryMediaStore;

function served(blob = MP3()) {
  const fetched = vi.fn().mockResolvedValue({ ok: true, status: 200, blob: async () => blob });
  vi.stubGlobal("fetch", fetched);
  return fetched;
}

function recorded(overrides: Partial<Pronunciation> = {}) {
  return vi.spyOn(backendSession, "pronounce").mockImplementation(async () => ({
    ...CLIP(), audioRef: "audio/lexemepicar0001/hl08nur0wl9h0n1-99999999.mp3", ...overrides
  }));
}

describe("playing a pronunciation", () => {
  beforeEach(async () => {
    store = new MemoryMediaStore();
    replaceStoreForTests(store);
    setPronunciationCacheEnabled(true);
    await repository.clear();
    await repository.load(TEST_OWNER);
    await repository.applyRemote(testGraph(), 1, "dataset00000001");
    vi.spyOn(syncEngine, "syncNow").mockResolvedValue(syncEngine.getStatus());
    vi.spyOn(backendSession, "mediaFileUrl").mockImplementation((reference) => `https://acervo.example.com/media/${reference}`);
    vi.spyOn(backendSession, "mediaHeaders").mockReturnValue({ Authorization: "Bearer token" });
  });
  afterEach(async () => { vi.unstubAllGlobals(); vi.restoreAllMocks(); await forgetPronunciations(); });

  it("plays the clip the replica names without asking the server for a recording", async () => {
    const fetched = served();
    const pronounce = vi.spyOn(backendSession, "pronounce");
    expect(await play(HEADWORD)).toEqual({ voice: "es-ES-Wavenet-F", stored: true });
    expect(pronounce).not.toHaveBeenCalled();
    expect(fetched).toHaveBeenCalledOnce();
  });

  it("asks the server only once, then plays from this device with nothing on the wire", async () => {
    const fetched = served();
    await play(HEADWORD);
    await play(HEADWORD);
    expect(fetched).toHaveBeenCalledOnce();
    expect(await store.read(CLIP().audioRef)).not.toBeNull();
  });

  it("keeps nothing on the device when keeping is switched off", async () => {
    setPronunciationCacheEnabled(false);
    served();
    await play(HEADWORD);
    expect(await store.read(CLIP().audioRef)).toBeNull();
  });

  it("records again when the record no longer says what the clip says", async () => {
    served();
    const pronounce = recorded();
    const edited = { ...HEADWORD, text: "picarse" };
    expect(currentClip(repository.snapshot(), edited)).toBeNull();
    await play(edited);
    expect(pronounce).toHaveBeenCalledWith("lexemes", "lexemepicar0001", expect.any(String), false);
  });

  it("says plainly that a clip is neither here nor reachable, and queues nothing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(play(HEADWORD)).rejects.toThrow(/not on this device yet/);
  });

  it("says that recording needs the server when the server is away", async () => {
    served();
    vi.spyOn(backendSession, "pronounce").mockRejectedValue(new AcervoApiError("no", 0, "offline"));
    await expect(play({ ...HEADWORD, text: "picarse" })).rejects.toThrow(/needs the server/);
  });

  it("reads an unsaved proposal aloud and stores nothing", async () => {
    const utterance = vi.spyOn(backendSession, "utterance").mockResolvedValue({ audio: MP3(), voice: "es-ES-Wavenet-F" });
    const pronounce = vi.spyOn(backendSession, "pronounce");
    expect(await play({ ...HEADWORD, id: null })).toEqual({ voice: "es-ES-Wavenet-F", stored: false });
    expect(utterance).toHaveBeenCalledWith("picar", "es");
    expect(pronounce).not.toHaveBeenCalled();
  });

  it("brings the clips the replica names onto this device, and nothing when keeping is off", async () => {
    const fetched = served();
    // The word's clip, and **every passage** of the one story part that has been read aloud: a story
    // is kept with the clips, so it plays offline too, and a part is a file per passage.
    expect(await fill(repository.snapshot())).toBe(3);
    expect(fetched.mock.calls.map(([url]) => String(url)).sort()).toEqual([
      "https://acervo.example.com/media/audio/lexemepicar0001/hl08nur0wl9h0n1-1a2b3c4d.mp3",
      "https://acervo.example.com/media/stories/storypicada0001/storypart000001-00-9a3c1d7e.ogg",
      "https://acervo.example.com/media/stories/storypicada0001/storypart000001-01-4b2e8f01.ogg"
    ].sort());
    expect(await fill(repository.snapshot())).toBe(0);

    await forgetPronunciations();
    setPronunciationCacheEnabled(false);
    fetched.mockClear();
    expect(await fill(repository.snapshot())).toBe(0);
    expect(fetched).not.toHaveBeenCalled();
  });

  it("hands the export the bytes it holds rather than fetching them again", async () => {
    const fetched = served();
    await play(HEADWORD);
    fetched.mockClear();
    expect(new TextDecoder().decode(await clipBytes(CLIP().audioRef))).toBe("ID3-audio");
    expect(fetched).not.toHaveBeenCalled();
  });
});


describe("hearing a preview", () => {
  beforeEach(() => { replaceStoreForTests(new MemoryMediaStore()); });
  afterEach(() => { vi.restoreAllMocks(); });

  it("reports how far a preview has got while it plays, and nothing once it ends", async () => {
    let end: (() => void) | null = null;
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
      end = () => this.dispatchEvent(new Event("ended"));
      return Promise.resolve();
    });
    vi.spyOn(HTMLMediaElement.prototype, "currentTime", "get").mockReturnValue(6);
    vi.spyOn(HTMLMediaElement.prototype, "duration", "get").mockReturnValue(24);
    const { result } = renderHook(() => usePreviewProgress("music:style:organic"));
    const playing = playPreview("music:style:organic", async () => MP3());
    await waitFor(() => expect(result.current).toEqual({ at: 6, duration: 24 }));
    act(() => end!());
    await playing;
    await waitFor(() => expect(result.current).toEqual({ at: 0, duration: 0 }));
  });

  it("does not play a preview stopped while it was being fetched", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
    let arrive: ((blob: Blob) => void) | null = null;
    const playing = playPreview("music:style:organic", () => new Promise<Blob>((done) => { arrive = done; }));
    stopPreview();
    arrive!(MP3());
    await playing;
    // The press primes the element on silence; the sample itself is never put in it.
    expect(play.mock.contexts.every((element) => (element as HTMLMediaElement).src.startsWith("data:"))).toBe(true);
  });

  it("lets the second of two previews end on its own after replacing the first", async () => {
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
    const first = playPreview("music:style:organic", async () => MP3());
    await waitFor(() => expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2));
    const second = playPreview("music:style:meditative", async () => MP3());
    await first;
    await waitFor(() => expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(4));
    // The first one's ending must not have taken the second one's end with it.
    const element = (vi.mocked(HTMLMediaElement.prototype.play).mock.contexts.at(-1)) as HTMLMediaElement;
    element.dispatchEvent(new Event("ended"));
    await expect(second).resolves.toBeUndefined();
  });
});
