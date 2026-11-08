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
import { AcervoApiError, backendSession, type LoopFamily, type LoopSchema } from "./api";
import { AllChoices, ChoiceCarousel, ChoiceGrid, centred } from "./ChoiceCarousel";
import type { VocabularyGraph } from "./domain";
import { lastLoopFormat, lastLoopMusic, loopSwitchesFor, rememberLoopFormat, rememberLoopMusic } from "./editorPreferences";
import { KindChoices, formatUsable, switchesFor } from "./LoopFormat";
import { SavedCards, SavedMusic, musicChoices, musicKey, musicOf, useLoopSchema } from "./LoopMusic";
import MakeDialog, { MakeSection } from "./MakeDialog";
import { prefetch, sampleMusic } from "./music";
import { MusicPlay, hear, previewKey } from "./MusicPlay";
import { stopPreview, useSpeechState } from "./pronunciation";
import { loopCandidates, loopEligible, loopSecondsPerWord, favouriteBeds, type ListQuery, type SelectedWord } from "./selectors";
import { WordPicker, useWordDraw, wordsCount, type WordSource } from "./WordPicker";

const DEFAULT_WORDS = 12;

const barsOf = (schema: LoopSchema): Record<string, number> =>
  Object.fromEntries(schema.formats.map((one) => [one.id, one.barsPerItem]));
const FEWEST_WORDS = 4;

/** What a style's sample is heard under; a saved piece's key starts differently. */
const SAMPLE = previewKey("style:");

export default function LoopDialog({ graph, query, selection = [], from = "scope", deviceId, onClose, onMade, onNotify }: {
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
}) {
  const { schema, trouble } = useLoopSchema(true);
  const [musicPicked, setMusic] = useState<string | null>(lastLoopMusic);
  const [browsing, setBrowsing] = useState<null | "styles" | "saved">(null);
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
  const tiles = musicChoices(graph, families, favouriteBeds(graph));
  const music = tiles.of(musicPicked);
  const row = centred(tiles.styles[0], tiles.styles.slice(1));
  const familyOf = (key: string): LoopFamily | undefined => families.find((family) => `style:${family.id}` === key);

  /* Hearing a style. ▶ on the middle picture plays its sample; while one is playing — or on its way —
     the row coming to rest on another style plays that one instead, and resting on Surprise me stops
     it, so swiping through the styles is listening through them. */
  const speech = useSpeechState();
  const auditioning = [speech.playing, speech.busy].some((key) => key?.startsWith(SAMPLE));
  const stopSample = () => { if (auditioning) stopPreview(); };
  const [resting, setResting] = useState<string | null>(null);
  const settled = (key: string) => {
    setResting(key);
    if (!auditioning || speech.playing === previewKey(key) || speech.busy === previewKey(key)) return;
    const family = familyOf(key);
    if (family) hear(key, () => sampleMusic(family), onNotify);
    else stopPreview();
  };
  // The middle sample and its neighbours are what ▶ and a swipe will reach for next.
  const found = row.findIndex((choice) => choice.id === (resting ?? musicKey(music)));
  const middle = found >= 0 ? found : Math.floor((row.length - 1) / 2);
  const near = [row[middle], row[middle - 1], row[middle + 1]].map((choice) => choice && familyOf(choice.id))
    .filter((family): family is LoopFamily => Boolean(family?.sample));
  const nearKey = near.map((family) => family.sample).join();
  useEffect(() => { void prefetch([], near); }, [nearKey]);
  // Closing the dialog, by Make or otherwise, ends what it was playing with it.
  useEffect(() => () => stopPreview(), []);

  const make = async () => {
    stopSample();
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

  if (browsing === "styles") {
    return <MakeDialog title="Make a loop" back={{ title: "Music style", onBack: () => setBrowsing(null) }} footer={footer} onClose={onClose}>
      <ChoiceGrid
        label="Music style" choices={tiles.styles} value={musicKey(music)}
        onChange={(key) => { setMusic(key); setBrowsing(null); }}
      />
    </MakeDialog>;
  }
  if (browsing === "saved") {
    return <MakeDialog title="Make a loop" back={{ title: "Saved music", onBack: () => setBrowsing(null) }} footer={footer} onClose={onClose}>
      <SavedCards graph={graph} families={families} favourites={tiles.favourites} onNotify={onNotify}
        value={musicKey(music)} onChange={(key) => { stopSample(); setMusic(key); setBrowsing(null); }} />
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

    <SavedMusic graph={graph} families={families} favourites={tiles.favourites} onNotify={onNotify}
      value={musicKey(music)} onChange={(key) => { stopSample(); setMusic(key); }} onAll={() => setBrowsing("saved")} />

    <MakeSection label="Music style" note="composed new for each loop"
      aside={<AllChoices count={tiles.styles.length} label="Music style" onOpen={() => setBrowsing("styles")} />}>
      <ChoiceCarousel
        label="Music style" choices={row} onChange={setMusic}
        idle="Saved music chosen above"
        value={music.kind === "bed" ? null : musicKey(music)}
        action={(choice) => {
          const family = familyOf(choice.id);
          return family && <MusicPlay choice={choice.id} label={family.label}
            fetch={() => sampleMusic(family)} onError={onNotify} />;
        }}
        onSettle={(choice) => settled(choice.id)}
      />
    </MakeSection>
  </MakeDialog>;
}
