/**
 * Make a loop: which words, what kind of loop, and what it should sound like — on one screen, with
 * the button that makes it always in reach.
 *
 * **The words are shown before they are sent** (`WordPicker.tsx`): drawn from what you are looking at
 * with the words not in a loop yet first, ordered at random, by Anki's difficulty, by rarity or by
 * age; or the selection, as chosen. Either way they are posted as a list of ids and the server never
 * re-derives them.
 *
 * The kind of loop is three tiles (`LoopFormat.tsx`): a drill, a radio lesson, a story, each with its
 * variants and switches folded under Options, opening on the one last made on this device.
 *
 * The music is the owner's saved music, a section of its own, and then a carousel of pictures
 * (`ChoiceCarousel.tsx`): Surprise me or one of the generator's styles, the chosen one in the middle
 * with the sentence that says what it is; All shows every style at once. The section says the music
 * is composed new for each loop, since a style is a direction to a generator, not a recording. The styles are the generator's catalogue, read from
 * `GET /loops/schema` and never copied into Acervo. The music last asked for on this device is chosen
 * when the dialog opens.
 *
 * **Without the sample pack this refuses rather than warns.** Fifteen of the generator's sixteen bed
 * families name instruments loaded from its catalogue, so a pack-less render dies partway through on
 * a missing sample — after minutes of work, with a message about a file nobody has heard of. The
 * server refuses the same request for the same reason; this is only the earlier, kinder half of it.
 * Which engine and pack the server has is Settings ▸ Loops' to say, not this dialog's.
 */

import { useEffect, useState } from "react";
import { AcervoApiError, backendSession, type LoopSchema } from "./api";
import type { Bed, VocabularyGraph } from "./domain";
import { lastLoopFormat, lastLoopMusic, loopSwitchesFor, rememberLoopFormat, rememberLoopMusic } from "./editorPreferences";
import { KindChoices, formatUsable, switchesFor } from "./LoopFormat";
import { MusicBrowse, MusicSections, musicChoices, musicKey, musicOf, useLoopSchema, type MusicBrowsing } from "./LoopMusic";
import MakeDialog, { MakeSection } from "./MakeDialog";
import { stopPreview } from "./pronunciation";
import { loopCandidates, loopEligible, loopSecondsPerWord, favouriteBeds, type ListQuery, type SelectedWord } from "./selectors";
import { WordPicker, useWordDraw, wordsCount, type WordSource } from "./WordPicker";

const DEFAULT_WORDS = 12;

const barsOf = (schema: LoopSchema): Record<string, number> =>
  Object.fromEntries(schema.formats.map((one) => [one.id, one.barsPerItem]));
const FEWEST_WORDS = 4;

export default function LoopDialog({ graph, query, selection = [], from = "scope", deviceId, onClose, onMade, onNotify, onRemoveBed }: {
  graph: VocabularyGraph;
  /** The scope on screen, exactly as the list is drawing it. */
  query: ListQuery;
  /** The selected words in this language, in the order they were chosen. */
  selection?: SelectedWord[];
  /** Where the words start from: the selection bar opens this on the selection. */
  from?: WordSource;
  deviceId: string;
  onClose(): void;
  onMade(loopId: string): void;
  onNotify(message: string): void;
  /** Stop keeping a saved piece; the dialog stays open, and the piece leaves it once it is gone. */
  onRemoveBed?(bed: Bed): void;
}) {
  const { schema, trouble } = useLoopSchema(true);
  const [musicPicked, setMusic] = useState<string | null>(lastLoopMusic);
  const [browsing, setBrowsing] = useState<MusicBrowsing>(null);
  const [asking, setAsking] = useState(false);
  const noSamples = Boolean(schema && !schema.productionBundle);
  const draw = useWordDraw({
    graph, query, kind: "loop", candidatesOf: loopCandidates, eligible: loopEligible,
    why: "no single term to say", max: schema?.maxItems ?? 24, least: FEWEST_WORDS, initial: DEFAULT_WORDS,
    selection, from
  });
  /* The format last made here, while the generator still offers it and this server can make it;
     else the first it offers, which is the drill. */
  const [picked, setPicked] = useState<string | null>(lastLoopFormat);
  const formats = schema?.formats ?? [];
  const format = formats.find((one) => one.id === picked && formatUsable(one, schema!))
    ?? formats.find((one) => formatUsable(one, schema!)) ?? null;
  const [switches, setSwitches] = useState<Record<string, boolean | string>>({});
  const values = format ? switchesFor(format, { ...loopSwitchesFor(format.id), ...switches }) : {};
  const families = schema?.families ?? [];
  const favourites = favouriteBeds(graph);
  const music = musicChoices(graph, families, favourites).of(musicPicked);
  const shared = {
    graph, families, favourites, value: musicKey(music), onNotify, onRemove: onRemoveBed
  };
  // Closing the dialog, by Make or otherwise, ends what it was playing with it.
  useEffect(() => () => stopPreview(), []);

  const make = async () => {
    stopPreview();
    setAsking(true);
    try {
      const answer = await backendSession.makeLoop({
        deviceId, language: query.language, lexemeIds: draw.ids,
        ...(format ? { format: format.id, switches: values } : {}),
        ...musicOf(music)
      });
      if (format) rememberLoopFormat(format.id, values);
      rememberLoopMusic(musicKey(music));
      draw.remember();
      onMade(answer.loop.id);
      onClose();
    } catch (error) {
      setAsking(false);
      onNotify(error instanceof AcervoApiError ? error.message : "That loop could not be asked for.");
    }
  };

  const blocked = trouble ?? (noSamples
    ? "This server has no sample pack, so a loop cannot be made. Install it once with ./deploy.sh --install-samples."
    : null);
  const footer = <>
    {blocked && <p className="make-blocked warn">{blocked}</p>}
    <button
      className="tb-btn primary make-go"
      disabled={asking || draw.ids.length === 0 || Boolean(blocked) || !schema}
      onClick={() => void make()}
    >{asking ? "Asking…" : <>Make the loop<span className="make-go-count"> · {wordsCount(draw.ids.length)}</span></>}</button>
  </>;

  if (browsing) {
    return <MakeDialog title="Make a loop" footer={footer} onClose={onClose}
      back={{ title: browsing === "styles" ? "Music style" : "Saved music", onBack: () => setBrowsing(null) }}>
      <MusicBrowse {...shared} browsing={browsing} onChange={(key) => { setMusic(key); setBrowsing(null); }} />
    </MakeDialog>;
  }

  return <MakeDialog title="Make a loop" footer={footer} onClose={onClose}>
    <MakeSection label="Words">
      <WordPicker draw={draw} kind="loop" language={query.language} counter="slider"
        secondsPerWord={format ? loopSecondsPerWord(graph, format.id, barsOf(schema!)) : null} />
    </MakeSection>

    {schema && format && <MakeSection label="Kind of loop">
      <KindChoices
        schema={schema} value={format.id} switches={values}
        onChoose={(id) => { setPicked(id); setSwitches({}); }}
        onSwitch={(name, value) => setSwitches({ ...switches, [name]: value })}
      />
    </MakeSection>}

    <MusicSections {...shared} onChange={setMusic} onBrowse={setBrowsing} />
  </MakeDialog>;
}
