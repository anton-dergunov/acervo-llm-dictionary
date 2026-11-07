/**
 * Make a story: which words, what kind of story, and what it should look like.
 *
 * **The words are shown before they are sent**, exactly as for a loop (`WordPicker.tsx`): drawn from
 * the words a *story* can use, which is most of them, with the words in no story yet first — or the
 * selection, as chosen. Either way a list of ids the server never re-derives.
 *
 * The kinds and the styles are the server's tracked config, read from `GET /stories/types` and never
 * copied into this file: a kind added to `config/story-types.yaml` appears here with nothing
 * changing on this side. Both are carousels of pictures (`ChoiceCarousel.tsx`), the styles each a
 * sample drawn in that style, in one order whatever the kind: a row that re-ordered itself when the
 * row above it changed looked as if it had scrolled with it. The styles a kind suggests are named
 * instead, under To suit the story, which is what picks from them.
 *
 * The count is **one to eight, three by default**, as segments rather than a slider. A story has to
 * weave every word it is given into twenty sentences, and the prose buckles long before a loop's
 * dozen would.
 *
 * The guidance box is the owner's own words to the writer, kept on the story so Try again writes the
 * story that was asked for. It is sent only when something is in it.
 */

import { useEffect, useState } from "react";
import { AcervoApiError, backendSession, type StoryTypes } from "./api";
import { Art } from "./art";
import { AllChoices, ChoiceCarousel, ChoiceGrid, centred, type CatalogueChoice } from "./ChoiceCarousel";
import type { VocabularyGraph } from "./domain";
import { DiceIcon, PictureIcon } from "./icons";
import MakeDialog, { MakeSection } from "./MakeDialog";
import { storyCandidates, storyEligible, type ListQuery, type SelectedWord } from "./selectors";
import { WordPicker, useWordDraw, wordsCount, type WordSource } from "./WordPicker";
import { lastStoryParts, rememberStoryParts } from "./editorPreferences";

const DEFAULT_WORDS = 3;
/** The server's bound (`GUIDANCE_LIMIT`), so the box stops where the route would refuse. */
const GUIDANCE_LIMIT = 1000;

type Browsing = null | "kind" | "pictures";

/** What To suit the story will pick from: the chosen kind's suggested styles, by name. */
function suits(offered: StoryTypes | null, kind: string): string {
  const type = offered?.types.find((one) => one.id === kind);
  if (!type || !offered) return "A style to suit whichever kind is written";
  const names = type.styles
    .map((id) => offered.styles.find((one) => one.id === id)?.label)
    .filter((name): name is string => Boolean(name));
  if (!names.length) return `A style to suit ${type.label.toLowerCase()}`;
  const shown = names.slice(0, 3).join(", ");
  return `For ${type.label}: ${shown}${names.length > 3 ? ` and ${names.length - 3} more` : ""}`;
}

/* The kinds and styles last offered, so the dialog opens at its full size while it asks again. */
let knownTypes: StoryTypes | null = null;

export function resetStoryTypesForTests(): void { knownTypes = null; }

export default function StoryDialog({ graph, query, selection = [], from = "scope", deviceId, onClose, onMade, onNotify }: {
  graph: VocabularyGraph;
  /** The scope on screen, exactly as the list is drawing it. */
  query: ListQuery;
  /** The selected words in this language, in the order they were chosen. */
  selection?: SelectedWord[];
  /** Where the words start from: the selection bar opens this on the selection. */
  from?: WordSource;
  deviceId: string;
  onClose(): void;
  onMade(storyId: string): void;
  onNotify(message: string): void;
}) {
  const [offered, setOffered] = useState<StoryTypes | null>(knownTypes);
  const [trouble, setTrouble] = useState<string | null>(null);
  const [kind, setKind] = useState("auto");
  const [style, setStyle] = useState("auto");
  const [asking, setAsking] = useState(false);
  const [guidance, setGuidance] = useState("");
  const [partsPicked, setParts] = useState<number | null>(lastStoryParts);
  const [browsing, setBrowsing] = useState<Browsing>(null);
  const draw = useWordDraw({
    graph, query, kind: "story", candidatesOf: storyCandidates, eligible: storyEligible,
    why: "nothing yet says what it means", max: offered?.maxWords ?? 8, least: offered?.minWords ?? 1,
    initial: DEFAULT_WORDS, selection, from
  });

  useEffect(() => {
    void backendSession.storyTypes()
      .then((found) => { knownTypes = found; setOffered(found); })
      .catch((error: unknown) => setTrouble(error instanceof AcervoApiError
        ? error.message
        : "The kinds of story could not be read."));
  }, []);

  // The parts last asked for on this device, while the server still offers that many; else its default.
  const parts = offered
    ? partsPicked !== null && partsPicked >= offered.minParts && partsPicked <= offered.maxParts ? partsPicked : offered.defaultParts
    : null;
  const lengths = offered ? Array.from({ length: offered.maxParts - offered.minParts + 1 }, (_, index) => offered.minParts + index) : [];

  const make = async () => {
    setAsking(true);
    try {
      const answer = await backendSession.makeStory({
        deviceId, language: query.language, lexemeIds: draw.ids,
        ...(kind === "auto" ? {} : { typeId: kind }),
        ...(style === "auto" ? {} : { styleId: style }),
        ...(guidance.trim() ? { guidance: guidance.trim() } : {}),
        ...(parts ? { parts } : {})
      });
      if (parts) rememberStoryParts(parts);
      draw.remember();
      onMade(answer.story.id);
      onClose();
    } catch (error) {
      setAsking(false);
      onNotify(error instanceof AcervoApiError ? error.message : "That story could not be asked for.");
    }
  };

  const kinds: CatalogueChoice[] = [
    { id: "auto", label: "Surprise me", about: "Any kind of story",
      art: <span className="choice-stand-in icon" aria-hidden="true"><DiceIcon /></span> },
    ...(offered?.types ?? []).map((one) => ({
      id: one.id, label: one.label, art: <Art group="kinds" id={one.id} label={one.label} emoji={one.emoji} />
    }))
  ];
  const pictures: CatalogueChoice[] = [
    // "To suit the story" rather than "Surprise me": the server picks from the styles this kind of
    // story suggests, which is a judgement rather than a dice roll, and the caption names them.
    { id: "auto", label: "To suit the story", about: suits(offered, kind),
      art: <span className="choice-stand-in icon" aria-hidden="true"><PictureIcon /></span> },
    ...(offered?.styles ?? []).map((one) => ({ id: one.id, label: one.label, art: <Art group="styles" id={one.id} label={one.label} /> }))
  ];

  const footer = <>
    {trouble && <p className="make-blocked warn">{trouble}</p>}
    <button
      className="tb-btn primary make-go"
      disabled={asking || draw.ids.length === 0 || Boolean(trouble) || !offered}
      onClick={() => void make()}
    >{asking ? "Asking…" : <>Make the story<span className="make-go-count"> · {wordsCount(draw.ids.length)}</span></>}</button>
  </>;

  if (browsing) {
    const grid = browsing === "kind"
      ? { title: "Kind of story", choices: kinds, value: kind, set: setKind }
      : { title: "Picture style", choices: pictures, value: style, set: setStyle };
    return <MakeDialog title="Make a story" back={{ title: grid.title, onBack: () => setBrowsing(null) }} footer={footer} onClose={onClose}>
      <ChoiceGrid label={grid.title} choices={grid.choices} value={grid.value}
        onChange={(id) => { grid.set(id); setBrowsing(null); }} />
    </MakeDialog>;
  }

  return <MakeDialog title="Make a story" footer={footer} onClose={onClose}>
    <MakeSection label="Words">
      <WordPicker draw={draw} kind="story" language={query.language} counter="segments" />
    </MakeSection>

    {parts !== null && lengths.length > 1 && <MakeSection label="Parts">
      <div className="word-count">
        <span className="seg word-count-seg story-parts" role="radiogroup" aria-label="How many parts">
          {lengths.map((value) => <button
            key={value} type="button" role="radio" aria-checked={value === parts}
            className={value === parts ? "on" : ""} onClick={() => setParts(value)}
          >{value}</button>)}
        </span>
        <span className="word-tally"><output>{parts} parts</output><small className="word-pool">a picture each</small></span>
      </div>
    </MakeSection>}

    <MakeSection label="Kind of story"
      aside={<AllChoices count={kinds.length} label="Kind of story" onOpen={() => setBrowsing("kind")} />}>
      <ChoiceCarousel label="Kind of story" choices={centred(kinds[0], kinds.slice(1))} value={kind} onChange={setKind} />
    </MakeSection>

    <MakeSection label="Picture style"
      aside={<AllChoices count={pictures.length} label="Picture style" onOpen={() => setBrowsing("pictures")} />}>
      <ChoiceCarousel label="Picture style" choices={centred(pictures[0], pictures.slice(1))} value={style} onChange={setStyle} />
    </MakeSection>

    <textarea
      className="make-guidance" aria-label="Anything else? (optional)"
      value={guidance} maxLength={GUIDANCE_LIMIT} rows={guidance ? 3 : 1}
      placeholder="Anything else? Set it on a night train, tell it from the dog’s side…"
      onChange={(event) => setGuidance(event.target.value)}
    />
  </MakeDialog>;
}
