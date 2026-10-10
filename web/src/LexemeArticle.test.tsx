import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import LexemeArticle, { looseAttestations, quietTitle, type PictureSlot } from "./LexemeArticle";
import { play } from "./pronunciation";
import { articleFor } from "./selectors";
import { testGraph } from "./testGraph";
import { aimAt, forgetTaps, TAP } from "./testTap";

/* The bytes come from an authenticated route; what the article does with them is what is tested. */
vi.mock("./media", () => ({
  acquire: vi.fn(async () => "blob:picture"),
  release: vi.fn()
}));
vi.mock("./dictionaries", () => ({ lookup: vi.fn(async () => []) }));
/* What a press does with the audio is `pronunciation.test.ts`'s business; here, what it asks for. */
vi.mock("./pronunciation", async (importOriginal) => ({
  ...await importOriginal<typeof import("./pronunciation")>(),
  play: vi.fn(async () => ({ voice: "es-ES-Wavenet-F", stored: true })),
  playRuns: vi.fn(async () => undefined)
}));

const picar = () => articleFor(testGraph(), "lexemepicar0001")!;
const pictures = (): PictureSlot => ({ open: vi.fn(), retry: vi.fn(), busy: () => false });
/** Whether some paragraph reads exactly this, however emphasis has split it across elements. */
const reads = (text: string, root: ParentNode = document) =>
  [...root.querySelectorAll("p")].some((paragraph) => paragraph.textContent === text);

afterEach(() => { vi.clearAllMocks(); forgetTaps(); });

describe("a clip's title", () => {
  it("is made quiet by rule: no hashtags, no emoji, all lower case", () => {
    expect(quietTitle("#NADIEDICENADA | CONOCEMOS A MARTA, LA SEÑORA QUE ESTÁ POR CUMPLIR 101 AÑOS"))
      .toBe("conocemos a marta, la señora que está por cumplir 101 años");
    expect(quietTitle("En este pueblo humanos tienen prohibido vivir 🚫")).toBe("en este pueblo humanos tienen prohibido vivir");
    expect(quietTitle("Comiendo en un mercado 🌮🔥 #mexico #streetfood")).toBe("comiendo en un mercado");
    expect(quietTitle("REDDIT DRAMA IN SPANISH 🇪🇸 FOR SPANISH LEARNERS")).toBe("reddit drama in spanish for spanish learners");
    expect(quietTitle("Top 10 1️⃣ palabras")).toBe("top 10 palabras");
  });
});

describe("the page", () => {
  it("keeps a sentence you supplied out of where you met it, since it is already in its sense", () => {
    expect(looseAttestations(picar())).toEqual([]);
  });

  it("places the progress line between the header and the first sense, and only on the page", () => {
    const line = <div role="status">Recording audio</div>;
    const { container, unmount } = render(<LexemeArticle article={picar()} onNotify={() => undefined} progress={line} />);
    const status = screen.getByRole("status");
    expect(status.previousElementSibling).toBe(container.querySelector(".masthead"));
    expect(status.nextElementSibling?.classList.contains("sec")).toBe(true);
    unmount();

    render(<LexemeArticle article={picar()} onNotify={() => undefined} view="cards" progress={line} />);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("folds each section on its own, and starts Details folded", () => {
    render(<LexemeArticle article={picar()} onNotify={() => undefined} />);
    const details = screen.getByText("Details").closest("button")!;
    expect(details.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("demo-model")).toBeNull();

    fireEvent.click(details);
    expect(details.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText(/demo-painter/)).toBeInTheDocument();

    // Folding a sense hides its body and nothing else.
    const sense = screen.getByText("🔪 cooking").closest("button")!;
    fireEvent.click(sense);
    expect(reads("Chop the onion very finely.")).toBe(false);
    expect(reads("My nose itches.")).toBe(true);
  });

  it("asks for a missing picture from an icon in the sense heading, with no empty frame", () => {
    const slot = pictures();
    render(<LexemeArticle article={picar()} onNotify={() => undefined} pictures={slot} />);
    // The cooking sense has no picture record at all.
    const cooking = document.querySelector<HTMLElement>('[data-record="sensepicarchop0"]')!;
    expect(cooking.querySelector(".sense-image")).toBeNull();
    fireEvent.click(within(cooking).getByRole("button", { name: "Add a picture" }));
    expect(slot.open).toHaveBeenCalledWith("sensepicarchop0", null);
    // A sense whose picture exists shows it, and no icon.
    const itch = document.querySelector<HTMLElement>('[data-record="sensepicaritch0"]')!;
    expect(itch.querySelector(".sense-image")).not.toBeNull();
    expect(within(itch).queryByRole("button", { name: "Add a picture" })).toBeNull();
  });

  it("shows no frame for a picture that was removed", () => {
    const graph = testGraph();
    graph.imagePrompts[0] = { ...graph.imagePrompts[0], imageRef: null, suppressed: true };
    render(<LexemeArticle article={articleFor(graph, "lexemepicar0001")!} onNotify={() => undefined} pictures={pictures()} />);
    const itch = document.querySelector<HTMLElement>('[data-record="sensepicaritch0"]')!;
    expect(itch.querySelector(".sense-image")).toBeNull();
    expect(within(itch).getByRole("button", { name: "Add a picture" })).toBeInTheDocument();
  });

  it("tells each play button what it reads, in that text's own language", async () => {
    const told = vi.fn();
    render(<LexemeArticle article={picar()} onNotify={told} />);
    fireEvent.click(screen.getByRole("button", { name: "Listen to picar" }));
    expect(play).toHaveBeenLastCalledWith({ kind: "lexeme", id: "lexemepicar0001", text: "picar", lang: "es" }, { again: false });
    fireEvent.click(screen.getAllByRole("button", { name: "Listen" })[0]);
    expect(vi.mocked(play).mock.calls[1][0]).toMatchObject({ kind: "sense", id: "sensepicaritch0", lang: "es" });
  });

  it("offers to record a stored clip again from the toast, and nothing else on the page", async () => {
    const told = vi.fn();
    render(<LexemeArticle article={picar()} onNotify={told} />);
    fireEvent.click(screen.getByRole("button", { name: "Listen to picar" }));
    await waitFor(() => expect(told).toHaveBeenCalledWith("Playing · es-ES-Wavenet-F", expect.objectContaining({ label: "Record again" })));
    told.mock.calls[0][1].run();
    expect(play).toHaveBeenLastCalledWith(expect.objectContaining({ kind: "lexeme" }), { again: true });
  });

  it("reads an unsaved proposal aloud as it stands and keeps nothing", () => {
    render(<LexemeArticle article={picar()} onNotify={() => undefined} meta={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Listen to picar" }));
    expect(play).toHaveBeenLastCalledWith(expect.objectContaining({ id: null, text: "picar" }), { again: false });
  });

  it("marks every spoken block with its language, so a selection can be read in the right one", () => {
    const { container } = render(<LexemeArticle article={picar()} onNotify={() => undefined} />);
    expect(container.querySelector("h1.headword")?.getAttribute("lang")).toBe("es");
    const example = container.querySelector('[data-say="example:examplepicar010"]');
    expect(example?.getAttribute("lang")).toBe("es");
    expect(example?.parentElement?.querySelector(".tr")?.getAttribute("lang")).toBe("en");
  });
});

describe("cards", () => {
  it("gives each sense a card per sentence, then the sections after them", () => {
    render(<LexemeArticle article={picar()} view="cards" onNotify={() => undefined} pictures={pictures()} />);
    const nav = within(screen.getByRole("navigation", { name: "Senses and sections" }));
    // A sense with no label is its number; one with a label shows its emoji and the label.
    expect(nav.getByRole("button", { name: "1" })).toBeInTheDocument();
    expect(nav.getByRole("button", { name: "🔪 cooking" })).toBeInTheDocument();
    expect(nav.getByRole("button", { name: "Details" })).toBeInTheDocument();
    // picar's two senses have one sentence each, then its notes, then the two asides.
    expect(nav.getByRole("button", { name: "✎ Notes" })).toBeInTheDocument();
    expect(document.querySelectorAll(".card")).toHaveLength(5);
    // No ask anchors on a card: a conversation edits the whole entry, which is read on the page.
    expect(document.querySelector(".ask-anchor")).toBeNull();
  });

  it("keeps the definition on the card with its sentence and marks your own", () => {
    render(<LexemeArticle article={picar()} view="cards" onNotify={() => undefined} pictures={pictures()} />);
    const first = document.querySelector<HTMLElement>('[data-card="0"]')!;
    expect(reads("My nose itches.", first)).toBe(true);
    expect(first.querySelector(".card-def")!.textContent).toBe("Producir comezón.");
    expect(within(first).getByText("your sentence")).toBeInTheDocument();
  });

  it("shows a picture still being drawn in the page's own frame, not in place of the emoji", () => {
    const graph = testGraph();
    graph.imagePrompts[0] = { ...graph.imagePrompts[0], imageRef: null, attempts: 0 };
    const busy: PictureSlot = { open: vi.fn(), retry: vi.fn(), busy: () => true };
    render(<LexemeArticle article={articleFor(graph, "lexemepicar0001")!} view="cards" onNotify={() => undefined} pictures={busy} />);
    const itch = document.querySelector<HTMLElement>('[data-card="0"]')!;
    expect(itch.querySelector(".card-frame .sense-image-frame")).not.toBeNull();
    expect(within(itch).getByText("Drawing…")).toBeInTheDocument();
    expect(itch.querySelector(".card-tile")).toBeNull();
  });

  it("sets a card that is only words as a quotation", () => {
    const graph = testGraph();
    graph.examples.push({
      ...graph.examples.find((example) => example.id === "examplepicar010")!,
      id: "examplepicar011", origin: "tatoeba", sourceAttestationId: null,
      text: "La lana pica.", translation: "Wool itches.", matchedForm: "pica", matchedTranslationForm: "itches"
    });
    render(<LexemeArticle article={articleFor(graph, "lexemepicar0001")!} view="cards" onNotify={() => undefined} pictures={pictures()} />);
    const second = document.querySelector<HTMLElement>('[data-card="1"]')!;
    // Between two ivy leaves, and closed as well as opened — the marks are not part of the text.
    expect(second.querySelector(".card-main.quoted .card-ornament.above")).not.toBeNull();
    expect(second.querySelector(".card-main.quoted .card-ornament.below")).not.toBeNull();
    expect(second.querySelector(".card-ex .t")!.textContent).toBe("“La lana pica.”");
    expect([...second.querySelectorAll(".quote-mark")].every((mark) => mark.getAttribute("aria-hidden") === "true")).toBe(true);
    // The picture stays on the card of the sentence it was drawn from.
    expect(second.querySelector(".card-pic")).toBeNull();
    // The arrows are outside the track, so they can move to the margins or to the foot of the card.
    expect(document.querySelector(".cards-edges .cards-edge.next")).not.toBeNull();
  });

  it("puts a picture on the card it was drawn from, and nothing where there is none", async () => {
    render(<LexemeArticle article={picar()} view="cards" onNotify={() => undefined} pictures={pictures()} />);
    const itch = document.querySelector<HTMLElement>('[data-card="0"]')!;
    expect(await within(itch).findByRole("img")).toBeInTheDocument();
    // A card is for reading: the picture does not open the picture dialog.
    expect(itch.querySelector("button.card-pic")).toBeNull();
    // The cooking sense has no picture: no placeholder and no control, just its sentence as a quote.
    const cooking = document.querySelector<HTMLElement>('[data-card="1"]')!;
    expect(cooking.querySelector(".card-pic, .card-frame, .sense-image")).toBeNull();
    expect(cooking.querySelector(".card-main.quoted")).not.toBeNull();
    // Its clip is a quiet, plainly pressable line, and the **channel leads**: it is what says what
    // kind of speech this is, while the video's title is about a topic nobody opens the clip for.
    const play = within(cooking).getByRole("button",
      { name: /Play the clip: easy spanish · comiendo en un mercado/ });
    expect(play).toBeInTheDocument();
    // The title is the half that gives way when there is no room; the channel and the mark that
    // says this opens something are both outside the text that truncates.
    expect(play.querySelector(".ch")!.textContent).toBe("easy spanish");
    expect(play.querySelector(".ti")!.textContent).toBe("comiendo en un mercado");
    expect(play.querySelector(".go svg")).not.toBeNull();
  });
});

describe("a clip still to come", () => {
  const clips = (search: "searching" | "none" | "failed" | null, retry = vi.fn()) =>
    ({ search, retry, remove: vi.fn() });

  it("holds a place at the end of a sense with no clip, and none where one is already", () => {
    render(<LexemeArticle article={picar()} onNotify={() => undefined} clips={clips("searching")} />);
    // The itching sense has no clip yet; the cooking sense already holds one.
    expect(screen.getAllByRole("status", { name: "Looking for a recorded example" })).toHaveLength(1);
  });

  it("settles into one quiet line when nothing was found", () => {
    render(<LexemeArticle article={picar()} onNotify={() => undefined} clips={clips("none")} />);
    expect(screen.queryByRole("status", { name: "Looking for a recorded example" })).toBeNull();
    expect(screen.getAllByText("No recorded example")).toHaveLength(1);
  });

  it("says a failed search once, with Try again", () => {
    const retry = vi.fn();
    render(<LexemeArticle article={picar()} onNotify={() => undefined} clips={clips("failed", retry)} />);
    expect(screen.getAllByText(/Couldn't search recorded speech/)).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("shows nothing once the word is opened again", () => {
    render(<LexemeArticle article={picar()} onNotify={() => undefined} clips={clips(null)} />);
    expect(screen.queryByText("No recorded example")).toBeNull();
    expect(screen.queryByRole("status", { name: "Looking for a recorded example" })).toBeNull();
  });
});

describe("a picture that could not be drawn", () => {
  const declined = () => {
    const graph = testGraph();
    Object.assign(graph.imagePrompts[0], {
      imageRef: null, imageModelId: null, failureReason: "The provider declined this prompt."
    });
    return articleFor(graph, "lexemepicar0001")!;
  };

  it("says why, and asks the server to draw it again", () => {
    const slot = pictures();
    render(<LexemeArticle article={declined()} onNotify={() => undefined} pictures={slot} />);
    expect(screen.getByText("The provider declined this prompt.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(slot.retry).toHaveBeenCalledWith(expect.objectContaining({ id: "imagepicar00010" }));
    fireEvent.click(screen.getByRole("button", { name: "Change…" }));
    expect(slot.open).toHaveBeenCalledWith("sensepicaritch0", expect.objectContaining({ id: "imagepicar00010" }));
  });

  it("says nothing while it is being drawn again", () => {
    const busy: PictureSlot = { open: vi.fn(), retry: vi.fn(), busy: () => true };
    render(<LexemeArticle article={declined()} onNotify={() => undefined} pictures={busy} />);
    expect(screen.queryByText("The provider declined this prompt.")).toBeNull();
  });
});

describe("a sense's name, and opening on a sense", () => {
  /* Most senses have an emoji and no domain; the emoji used to be shown only beside a domain, so the
     article showed them as bare numbers while the map showed the same senses by their emoji. */
  const emojiOnly = () => {
    const graph = testGraph();
    graph.senses = graph.senses.map((sense) => (sense.id === "sensepicaritch0" ? { ...sense, emoji: "🤧" } : sense));
    return articleFor(graph, "lexemepicar0001")!;
  };

  it("names a sense by its emoji when it has no domain, on the page and on the chips", () => {
    const { unmount } = render(<LexemeArticle article={emojiOnly()} onNotify={() => undefined} />);
    expect(screen.getByText("🤧")).toBeInTheDocument();
    expect(screen.getByText("🔪 cooking")).toBeInTheDocument();
    unmount();
    render(<LexemeArticle article={emojiOnly()} view="cards" onNotify={() => undefined} />);
    expect(screen.getByRole("button", { name: "🤧 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "🔪 cooking" })).toBeInTheDocument();
  });

  it("opens the cards on the sense it was opened for", () => {
    render(<LexemeArticle article={picar()} view="cards" focusSense="sensepicarchop0" onNotify={() => undefined} />);
    expect(screen.getByRole("button", { name: "🔪 cooking" })).toHaveAttribute("aria-current", "true");
  });

  it("shows a sense on the map, from the page and from its card, and never for an unsaved one", () => {
    const onMap = vi.fn();
    const { unmount } = render(<LexemeArticle article={picar()} onNotify={() => undefined} onMap={onMap} />);
    fireEvent.click(screen.getAllByRole("button", { name: "Show on the map" })[1]);
    expect(onMap).toHaveBeenCalledWith("sensepicarchop0");
    unmount();
    render(<LexemeArticle article={picar()} view="cards" onNotify={() => undefined} onMap={onMap} />);
    fireEvent.click(screen.getAllByRole("button", { name: "Show on the map" })[0]);
    expect(onMap).toHaveBeenLastCalledWith("sensepicaritch0");
  });

  it("offers no map for a proposal, whose senses are not stored", () => {
    render(<LexemeArticle article={picar()} meta={false} onNotify={() => undefined} onMap={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Show on the map" })).not.toBeInTheDocument();
  });
});

describe("looking a word up", () => {
  const exampleText = () => [...document.querySelectorAll<HTMLElement>("[lang='es']")]
    .find((block) => block.textContent === "Me pica la nariz.")!;

  it("hands a word tapped in an example to the caller, with its sentence", () => {
    const onWordTap = vi.fn();
    render(<LexemeArticle article={picar()} onNotify={() => undefined} onWordTap={onWordTap} />);
    const block = exampleText();
    aimAt(block, "nariz");
    fireEvent.click(block, TAP);
    expect(onWordTap).toHaveBeenCalledTimes(1);
    expect(onWordTap.mock.calls[0][0]).toMatchObject({
      word: "nariz", sentence: { text: "Me pica la nariz.", selection: { start: 11, end: 16 } }
    });
  });

  it("does not look up the headword, which is this word", () => {
    const onWordTap = vi.fn();
    const onTapAway = vi.fn();
    render(<LexemeArticle article={picar()} onNotify={() => undefined} onWordTap={onWordTap} onTapAway={onTapAway} />);
    const headword = document.querySelector('[data-say="lexeme:lexemepicar0001"]')!;
    aimAt(headword, "picar");
    fireEvent.click(headword, TAP);
    expect(onWordTap).not.toHaveBeenCalled();
    expect(onTapAway).toHaveBeenCalled();
  });

  it("offers Look up beside Listen for a selection, and not where nothing is looked up", async () => {
    const box = Range.prototype.getBoundingClientRect;
    Range.prototype.getBoundingClientRect = () => ({ left: 10, top: 100, width: 40, height: 20 }) as DOMRect;
    /* The first two letters of the example, selected. */
    const select = () => {
      const range = document.createRange();
      range.setStart(exampleText().firstChild!, 0);
      range.setEnd(exampleText().firstChild!, 2);
      window.getSelection()!.removeAllRanges();
      window.getSelection()!.addRange(range);
      fireEvent(document, new Event("selectionchange"));
    };
    try {
      const onWordTap = vi.fn();
      const { unmount } = render(<LexemeArticle article={picar()} onNotify={() => undefined} onWordTap={onWordTap} />);
      select();
      const pill = await screen.findByRole("toolbar", { name: "The selection" });
      expect(within(pill).getByRole("button", { name: "Listen" })).toBeInTheDocument();
      fireEvent.click(within(pill).getByRole("button", { name: "Look up" }));
      expect(onWordTap.mock.calls[0][0]).toMatchObject({ word: "Me" });
      unmount();

      render(<LexemeArticle article={picar()} onNotify={() => undefined} />);
      select();
      const alone = await screen.findByRole("toolbar", { name: "The selection" });
      expect(within(alone).queryByRole("button", { name: "Look up" })).toBeNull();
    } finally {
      Range.prototype.getBoundingClientRect = box;
      window.getSelection()!.removeAllRanges();
    }
  });
});
