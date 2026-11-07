import "@testing-library/jest-dom/vitest";
import { beforeEach } from "vitest";

/**
 * Every test starts on a device that remembers nothing. Local storage holds per-device conveniences
 * — the editor's wrapping, the view an article opens in, the place a cold start reopens — and one
 * left behind by the test before changes where the next one lands: a word opened in one test was
 * reopened at the start of the next file's first test.
 */
beforeEach(async () => {
  try { localStorage.clear(); } catch { /* an environment without storage has nothing to clear */ }
  /* Settings remembers what the server said while the app is open, which in a test file is every
     test. Imported here rather than at the top so it is the instance the test file's own mocks
     reached, not one bound to the real API before they were in place. */
  const { forgetServerSettings } = await import("./settings/cache");
  forgetServerSettings();
});

/**
 * jsdom's `Blob` predates `Blob.prototype.arrayBuffer` and `Blob.prototype.text`, both of which
 * every browser Acervo targets has had for years and both of which the dictionary code uses to read
 * a stored artifact.
 *
 * This fills the gap in the test environment only. It is not compatibility code for a browser: if
 * production ever needed it, that would be a reason to change the reader rather than to ship this.
 */
function readBlob<T extends ArrayBuffer | string>(blob: Blob, as: "buffer" | "text"): Promise<T> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as T);
    reader.onerror = () => reject(reader.error);
    if (as === "buffer") reader.readAsArrayBuffer(blob); else reader.readAsText(blob);
  });
}

if (typeof Blob !== "undefined" && typeof Blob.prototype.arrayBuffer !== "function") {
  Blob.prototype.arrayBuffer = function arrayBuffer(this: Blob) {
    return readBlob<ArrayBuffer>(this, "buffer");
  };
}

if (typeof Blob !== "undefined" && typeof Blob.prototype.text !== "function") {
  Blob.prototype.text = function text(this: Blob) {
    return readBlob<string>(this, "text");
  };
}

/**
 * jsdom does no layout, so it implements no scrolling at all — `Element.prototype.scrollIntoView`
 * simply is not there.
 *
 * The review bar brings the first change into view on every proposal, so without this every test
 * that reviews one throws. A no-op rather than a spy by default: a test that cares about *where* it
 * scrolled spies on this itself. Same standing as the `Blob` fills above — the test environment is
 * missing something every browser has, and production calls it unguarded.
 */
if (typeof Element !== "undefined" && typeof Element.prototype.scrollIntoView !== "function") {
  Element.prototype.scrollIntoView = function scrollIntoView() { /* jsdom has no layout */ };
}

/**
 * jsdom has no media pipeline and no object URLs: `HTMLMediaElement.prototype.play` logs "not
 * implemented" and returns nothing, and `URL.createObjectURL` is simply absent.
 *
 * A pronunciation is fetched, turned into an object URL and played to its end, so without these
 * every test that presses a play button would fail on the environment rather than on the code. A
 * clip here "plays" by finishing on the next tick. A test that cares whether playback was refused
 * replaces `play` itself.
 */
if (typeof URL !== "undefined" && typeof URL.createObjectURL !== "function") {
  let made = 0;
  URL.createObjectURL = () => `blob:test/${++made}`;
  URL.revokeObjectURL = () => undefined;
}

if (typeof HTMLMediaElement !== "undefined") {
  HTMLMediaElement.prototype.play = function play(this: HTMLMediaElement) {
    setTimeout(() => this.dispatchEvent(new Event("ended")));
    return Promise.resolve();
  };
  HTMLMediaElement.prototype.pause = function pause() { /* nothing is playing in jsdom */ };
}

/**
 * jsdom has no `matchMedia` or `IntersectionObserver`, which every browser Acervo targets has and
 * which the make dialogs' carousel (Embla) uses. jsdom does no layout, so there is nothing for them to
 * report: these answer "no match" and never call back. `ResizeObserver` is left missing on purpose:
 * its absence is how the components that measure text know there is no layout to measure.
 * Test environment only, for `Blob`'s reason above.
 */
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string) => ({
    matches: false, media: query, onchange: null,
    addListener: () => undefined, removeListener: () => undefined,
    addEventListener: () => undefined, removeEventListener: () => undefined, dispatchEvent: () => false
  }) as MediaQueryList;
}
class Unobserved {
  observe(): void { /* jsdom does no layout */ }
  unobserve(): void { /* jsdom does no layout */ }
  disconnect(): void { /* jsdom does no layout */ }
  takeRecords(): [] { return []; }
}
if (typeof globalThis.IntersectionObserver === "undefined") {
  globalThis.IntersectionObserver = Unobserved as unknown as typeof IntersectionObserver;
}
