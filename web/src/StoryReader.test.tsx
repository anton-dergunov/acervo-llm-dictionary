import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { QuickLookUp } from "./api";
import type { VocabularyGraph } from "./domain";
import { LookUpContext, type LookUpServices } from "./LookUpSheet";
import StoryReader from "./StoryReader";
import type { StoryPlayback } from "./storyAudio";
import { storyPartsOf, storyWordEntries, storyWordsOf } from "./selectors";
import { testGraph } from "./testGraph";
import { aimAt, forgetTaps, TAP } from "./testTap";

const picture = vi.fn((reference: string | null) => ({
  url: reference ? "blob:picture" : null, error: null
}));
vi.mock("./picture", () => ({ usePicture: (reference: string | null) => picture(reference) }));

/* What is heard is `storyAudio.test.ts`'s business. Here the player is only a state the reader reads
   and three calls it makes, so a test can say what the reader does at each state of a part. */
let heard: StoryPlayback = { partId: null, status: "idle", segment: null, failed: null };
const toggle = vi.fn();
const playSegment = vi.fn();
const stopPart = vi.fn();
vi.mock("./storyAudio", () => ({
  useStoryAudio: () => heard,
  toggle: (...args: unknown[]) => toggle(...args),
  playSegment: (...args: unknown[]) => playSegment(...args),
  stopPart: (...args: unknown[]) => stopPart(...args)
}));

/* jsdom does no layout, so a deck that snaps under the finger has to be faked: every page is one
   hundred wide, and scrolling to an offset is a scroll event at that offset. The reader reads only
   `scrollLeft / clientWidth`, which is all a real snap track would tell it too. */
beforeEach(() => {
  picture.mockClear();
  toggle.mockClear(); playSegment.mockClear(); stopPart.mockClear();
  heard = { partId: null, status: "idle", segment: null, failed: null };
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, value: 100 });
  Element.prototype.scrollTo = function scrollTo(this: Element, options?: ScrollToOptions | number) {
    this.scrollLeft = typeof options === "object" ? options.left ?? 0 : 0;
    this.dispatchEvent(new Event("scroll"));
  } as typeof Element.prototype.scrollTo;
});

afterEach(forgetTaps);

const ANSWER: QuickLookUp = {
  resolution: {
    language: "es", headword: "subir", lemma: "subir", pos: "verb",
    sentences: [{ text: "Marcos subió a la balsa al amanecer.", translation: null }],
    note: null, consumedLines: 1, consumedText: null, gloss: "climbed onto"
  },
  duplicates: [], foldable: null
};

function services(graph: VocabularyGraph): LookUpServices {
  return {
    graph,
    lookUp: vi.fn(async () => ANSWER),
    queue: vi.fn(async () => ({})),
    open: vi.fn(),
    notify: vi.fn()
  };
}

function reader(
  storyId = "storypicada0001", change: (graph: VocabularyGraph) => void = () => undefined, recording = false,
  startAt = 0
) {
  const graph = testGraph();
  change(graph);
  const story = graph.stories.find((one) => one.id === storyId)!;
  const onBack = vi.fn();
  const looking = services(graph);
  const view = render(
    <LookUpContext.Provider value={looking}>
      <StoryReader
        story={story}
        title={story.title ?? "untitled"}
        parts={storyPartsOf(graph, storyId)}
        words={storyWordsOf(graph, storyId)}
        entries={storyWordEntries(graph, storyId)}
        recording={recording}
        startAt={startAt}
        onBack={onBack}
      />
    </LookUpContext.Provider>
  );
  return { ...view, onBack, looking };
}

const next = () => fireEvent.click(screen.getByRole("button", { name: "The next part" }));
const previous = () => fireEvent.click(screen.getByRole("button", { name: "The part before" }));
const position = () => document.querySelector(".story-bar-count")?.textContent;
/** The translation on screen as one string: a marked word splits it across elements. */
const translation = () => document.querySelector(".story-tr")?.textContent ?? "";

describe("reading a story", () => {
  it("says which story it is and where you are in it, in the header", () => {
    reader();
    expect(document.querySelector(".story-bar-title")).toHaveTextContent("La balsa que picaba");
    // Two parts and the page of words after them.
    expect(position()).toBe("1 / 3");
  });

  it("numbers each part in front of its heading", () => {
    reader();
    expect(screen.getByRole("heading", { name: "1 · La balsa" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "2 · El picor" })).toBeInTheDocument();
  });

  it("moves to the next page and back again", () => {
    reader();
    next();
    expect(position()).toBe("2 / 3");
    previous();
    expect(position()).toBe("1 / 3");
  });

  it("cannot go back from the first page or on past the last", () => {
    reader();
    expect(screen.getByRole("button", { name: "The part before" })).toBeDisabled();
    next();
    next();
    expect(position()).toBe("3 / 3");
    expect(screen.getByRole("button", { name: "The next part" })).toBeDisabled();
  });

  it("moves with the arrow keys, but not while you are typing", () => {
    reader();
    fireEvent.keyDown(document.body, { key: "ArrowRight" });
    expect(position()).toBe("2 / 3");
    fireEvent.keyDown(document.body, { key: "ArrowLeft" });
    expect(position()).toBe("1 / 3");

    const field = document.body.appendChild(document.createElement("input"));
    fireEvent.keyDown(field, { key: "ArrowRight" });
    expect(position()).toBe("1 / 3");
    field.remove();
  });

  it("goes back with the arrow in the header", () => {
    const { onBack } = reader();
    fireEvent.click(screen.getByRole("button", { name: "Back to the stories" }));
    expect(onBack).toHaveBeenCalled();
  });

  /* The one rule this surface shares with the loop player: an answer must not be on screen before
     it has been asked for. */
  it("never draws a translation until it is asked for", () => {
    reader();
    expect(translation()).toBe("");
    fireEvent.click(screen.getAllByRole("button", { name: /read it in your own language/i })[0]);
    expect(translation()).toContain("Marcos climbed onto the raft");
  });

  it("does not reveal the next part's translation with this one's", () => {
    reader();
    fireEvent.click(screen.getAllByRole("button", { name: /read it in your own language/i })[0]);
    expect(screen.queryByText(/Something began to sting/)).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /read it in your own language/i })).toHaveLength(1);
  });

  it("keeps a revealed translation revealed when you come back to it", () => {
    reader();
    fireEvent.click(screen.getAllByRole("button", { name: /read it in your own language/i })[0]);
    next();
    previous();
    expect(translation()).toContain("Marcos climbed onto the raft");
  });

  it("can hide a translation again once it has been read", () => {
    reader();
    fireEvent.click(screen.getAllByRole("button", { name: /read it in your own language/i })[0]);
    expect(translation()).toContain("Marcos climbed onto the raft");

    fireEvent.click(screen.getByRole("button", { name: "Hide the translation" }));

    expect(translation()).toBe("");
    // Back to the withheld state, ready to be asked for again.
    expect(screen.getAllByRole("button", { name: /read it in your own language/i })).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Hide the translation" })).not.toBeInTheDocument();
  });

  it("hides only the translation it was pressed on", () => {
    reader();
    const reveals = () => screen.getAllByRole("button", { name: /read it in your own language/i });
    fireEvent.click(reveals()[0]);
    fireEvent.click(reveals()[0]);
    expect(document.querySelectorAll(".story-tr")).toHaveLength(2);

    fireEvent.click(screen.getAllByRole("button", { name: "Hide the translation" })[0]);

    expect(document.querySelectorAll(".story-tr")).toHaveLength(1);
    expect(document.querySelector(".story-tr")?.textContent).toContain("Something began to sting");
  });

  it("offers no way to hide what has not been revealed", () => {
    reader();
    expect(screen.queryByRole("button", { name: "Hide the translation" })).not.toBeInTheDocument();
  });

  it("marks the words the story was asked to teach", () => {
    const { container } = reader();
    const marks = Array.from(container.querySelectorAll(".story-mark")).map((one) => one.textContent);
    expect(marks).toEqual(["balsa", "picar"]);
  });

  it("marks the word in the translation too, once it has been asked for", () => {
    const { container } = reader();
    fireEvent.click(screen.getAllByRole("button", { name: /read it in your own language/i })[0]);
    const marks = Array.from(container.querySelectorAll(".story-tr .story-mark")).map((one) => one.textContent);
    expect(marks).toEqual(["raft"]);
  });

  it("shows a translation plainly when nothing was reported for it", () => {
    const { container } = reader("storypicada0001", (graph) => {
      graph.storyWords.forEach((word) => { word.translationForms = []; });
    });
    fireEvent.click(screen.getAllByRole("button", { name: /read it in your own language/i })[0]);
    expect(translation()).toContain("Marcos climbed onto the raft");
    expect(container.querySelectorAll(".story-tr .story-mark")).toHaveLength(0);
  });

  it("says a story with no parts has not been written", () => {
    reader("storyqueued0001");
    expect(screen.getByText(/has not been written yet/i)).toBeInTheDocument();
    // Nothing to move through, so nothing that pretends to.
    expect(screen.queryByRole("button", { name: "The next part" })).not.toBeInTheDocument();
  });
});

describe("the last page", () => {
  it("lists the words the story was made from as the word list draws them", () => {
    reader();
    const page = document.querySelector<HTMLElement>(".story-words-page")!;
    const rows = Array.from(page.querySelectorAll(".row"));
    expect(rows.map((row) => row.querySelector(".word")?.textContent)).toEqual(["la balsa", "picar"]);
    expect(within(rows[1] as HTMLElement).getByText("to itch; to chop")).toBeInTheDocument();
    expect(rows[1].querySelector(".plate")).toHaveTextContent("🌶️");
  });

  it("dims a word the story was asked for and could not use", () => {
    reader("storypicada0001", (graph) => {
      graph.storyWords.find((word) => word.id === "storyword000002")!.forms = [];
    });
    const rows = document.querySelectorAll(".story-words-page .row");
    expect(rows[0]).not.toHaveClass("unused");
    expect(rows[1]).toHaveClass("unused");
  });

  it("keeps a word that has been deleted since, on the words the story kept", () => {
    reader("storypicada0001", (graph) => {
      graph.lexemes = graph.lexemes.filter((lexeme) => lexeme.id !== "lexemebalsa0001");
    });
    const first = document.querySelector(".story-words-page .row")!;
    expect(first.querySelector(".word")).toHaveTextContent("la balsa");
    expect(first.querySelector(".plate")).toHaveTextContent("📄");
  });
});

describe("pictures", () => {
  it("fetches only the page in view and its neighbours", () => {
    const graph = testGraph();
    const story = graph.stories[0];
    const parts = [0, 1, 2, 3].map((index) => ({
      ...graph.storyParts[0], id: `storypart00000${index}`, position: index, imageRef: `stories/x/ref${index}.webp`
    }));
    render(<StoryReader
      story={story} title="x" parts={parts} words={[]} entries={[]} onBack={() => undefined}
    />);
    const asked = new Set(picture.mock.calls.map(([reference]) => reference).filter(Boolean));
    expect(asked).toEqual(new Set(["stories/x/ref0.webp", "stories/x/ref1.webp"]));
  });
});


describe("reading a part aloud", () => {
  const first = () => testGraph().storyParts[0];
  const listen = (index = 0) => screen.getAllByRole("button", { name: /read this part aloud|pause|carry on|waiting to be recorded|recording this part|loading/i })[index];

  it("puts a button in each part's heading, and pressing it asks for that part", () => {
    reader();
    expect(screen.getAllByRole("button", { name: "Read this part aloud" })).toHaveLength(2);

    fireEvent.click(listen(0));

    expect(toggle).toHaveBeenCalledTimes(1);
    expect(toggle.mock.calls[0][0]).toMatchObject({ id: first().id });
  });

  it("says pause while the part plays", () => {
    heard = { partId: first().id, status: "playing", segment: 0, failed: null };
    reader();
    expect(listen(0)).toHaveAccessibleName("Pause");
    expect(listen(0)).toHaveClass("playing");
    expect(listen(1)).toHaveAccessibleName("Read this part aloud");
  });

  it("says carry on while it is paused, and stays lit", () => {
    heard = { partId: first().id, status: "paused", segment: 0, failed: null };
    reader();
    expect(listen(0)).toHaveAccessibleName("Carry on");
    expect(listen(0)).toHaveClass("playing");
  });

  it("offers to record a part the job has not reached, rather than disabling it", () => {
    /* A job resting out a daily quota holds a part for twenty-five minutes. A dead button with no
       explanation was all you got; now it says what is happening and records it on the spot. */
    reader("storypicada0001", () => undefined, true);

    expect(listen(1)).not.toBeDisabled();
    expect(listen(1)).toHaveAccessibleName("Waiting to be recorded — press to record it now");
    fireEvent.click(listen(1));
    expect(toggle.mock.calls[0][0]).toMatchObject({ id: "storypart000002" });
  });

  it("says why a recording could not be made, under the heading of that part", () => {
    heard = { partId: "storypart000002", status: "idle", segment: null, failed: "The speech model is temporarily rate limited." };
    reader();
    expect(screen.getByRole("status")).toHaveTextContent("The speech model is temporarily rate limited.");
  });

  it("stops the audio of a page that is no longer the one on screen", () => {
    reader();
    stopPart.mockClear();

    next();

    expect(stopPart).toHaveBeenCalledWith("storypart000001");
    expect(stopPart).not.toHaveBeenCalledWith("storypart000002");
  });

  it("stops what it was playing when it is left", () => {
    const { unmount } = reader();
    stopPart.mockClear();

    unmount();

    expect(stopPart).toHaveBeenCalledWith("storypart000001");
  });
});

describe("the passages of a part read aloud", () => {
  const passages = () => Array.from(document.querySelectorAll(".story-seg"));

  it("draws the text exactly as it was, cut into the passages the recording has", () => {
    reader();
    expect(passages().map((one) => one.textContent)).toEqual(["Marcos subió a la balsa ", "al amanecer."]);
    expect(document.querySelector(".story-text")?.textContent).toBe("Marcos subió a la balsa al amanecer.");
  });

  it("keeps the words the story teaches marked inside a passage", () => {
    reader();
    expect(passages()[0].querySelector(".story-mark")).toHaveTextContent("balsa");
  });

  it("offers nothing to touch on a part read whole", () => {
    reader();
    expect(passages()).toHaveLength(2);   // only the first part has passages
    next();
    expect(document.querySelectorAll(".story-text")[1]).not.toHaveClass("tappable");
    expect(document.querySelectorAll(".story-text")[1].querySelector(".story-seg")).toBeNull();
  });

  it("tints the passage that is sounding, and only while that part is heard", () => {
    heard = { partId: "storypart000001", status: "playing", segment: 1, failed: null };
    reader();
    expect(passages().map((one) => one.classList.contains("on"))).toEqual([false, true]);
  });

  it("keeps the tint on the passage where a paused part stopped", () => {
    heard = { partId: "storypart000001", status: "paused", segment: 0, failed: null };
    reader();
    expect(passages()[0]).toHaveClass("on");
  });

  it("tints nothing when it is another part that is playing", () => {
    heard = { partId: "storypart000002", status: "playing", segment: 0, failed: null };
    reader();
    expect(passages().some((one) => one.classList.contains("on"))).toBe(false);
  });

  it("starts from a passage that is touched", () => {
    reader();

    fireEvent.click(passages()[1]);

    expect(playSegment).toHaveBeenCalledTimes(1);
    expect(playSegment.mock.calls[0][0]).toMatchObject({ id: "storypart000001" });
    expect(playSegment.mock.calls[0][1]).toBe(1);
  });

  it("plays the passage a tap off any word lands in", () => {
    reader();
    fireEvent.click(passages()[0].querySelector(".story-mark")!);
    expect(playSegment.mock.calls[0][1]).toBe(0);
  });

  it("does not take the end of a text selection for a touch", () => {
    reader();
    const selection = vi.spyOn(window, "getSelection").mockReturnValue({ toString: () => "la balsa" } as Selection);

    fireEvent.click(passages()[1]);

    expect(playSegment).not.toHaveBeenCalled();
    selection.mockRestore();
  });

  it("looks up a word you hold from your words, and plays nothing until asked", () => {
    const { looking } = reader();
    const text = document.querySelector(".story-text")!;
    aimAt(text, "balsa", 2);
    fireEvent.click(text, TAP);

    expect(playSegment).not.toHaveBeenCalled();
    expect(looking.lookUp).not.toHaveBeenCalled();
    const sheet = screen.getByRole("dialog", { name: "Look up a word" });
    expect(sheet).toHaveTextContent("la balsa");
    expect(sheet).toHaveTextContent("in your words");

    fireEvent.click(within(sheet).getByRole("button", { name: "This passage" }));
    expect(playSegment.mock.calls[0][1]).toBe(0);

    fireEvent.click(within(sheet).getByRole("button", { name: "Open la balsa" }));
    expect(looking.open).toHaveBeenCalledWith("lexemebalsa0001", { kind: "story", storyId: "storypicada0001", page: 0 });
  });

  it("asks about a word you do not hold, and Add files it in the Inbox", async () => {
    const { looking } = reader();
    const text = document.querySelector(".story-text")!;
    aimAt(text, "subió");
    fireEvent.click(text, TAP);

    expect(looking.lookUp).toHaveBeenCalledWith(
      { text: "Marcos subió a la balsa al amanecer.", selection: { start: 7, end: 12 }, source: "reading" },
      expect.any(AbortSignal));
    const sheet = screen.getByRole("dialog", { name: "Look up a word" });
    expect(await within(sheet).findByText("subir")).toBeInTheDocument();
    expect(sheet).toHaveTextContent("climbed onto");

    fireEvent.click(within(sheet).getByRole("button", { name: "Add" }));
    expect(looking.queue).toHaveBeenCalledWith({
      text: "Marcos subió a la balsa al amanecer.", resolution: ANSWER.resolution,
      sourceTitle: "Story · La balsa que picaba"
    });
    expect(await within(sheet).findByText("Added to your Inbox")).toBeInTheDocument();
    expect(playSegment).not.toHaveBeenCalled();
  });

  it("says why a look-up failed, and offers to try again", async () => {
    const { looking } = reader();
    vi.mocked(looking.lookUp).mockRejectedValueOnce(new Error("The server can't be reached."));
    const text = document.querySelector(".story-text")!;
    aimAt(text, "amanecer");
    fireEvent.click(text, TAP);
    const sheet = screen.getByRole("dialog", { name: "Look up a word" });
    expect(await within(sheet).findByText("The server can't be reached.")).toBeInTheDocument();
    fireEvent.click(within(sheet).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(looking.lookUp).toHaveBeenCalledTimes(2));
  });

  it("puts the sheet away on a tap that is not on a word, which then plays as before", () => {
    reader();
    const text = document.querySelector(".story-text")!;
    aimAt(text, "balsa");
    fireEvent.click(text, TAP);
    expect(screen.getByRole("dialog", { name: "Look up a word" })).toBeInTheDocument();

    forgetTaps();
    fireEvent.click(passages()[1]);
    expect(screen.queryByRole("dialog", { name: "Look up a word" })).toBeNull();
    expect(playSegment.mock.calls[0][1]).toBe(1);
  });

  it("opens on the page it is asked to", () => {
    reader("storypicada0001", () => undefined, false, 1);
    expect(position()).toBe("2 / 3");
  });

  it("falls back to plain text when the passages no longer join to the text", () => {
    // A recording made from words that have since changed must not paint its cuts over new ones.
    reader("storypicada0001", (graph) => { graph.storyParts[0].text = "Marcos subió a otra cosa."; });
    expect(passages()).toHaveLength(0);
    expect(document.querySelector(".story-text")).toHaveTextContent("Marcos subió a otra cosa.");
  });
});
