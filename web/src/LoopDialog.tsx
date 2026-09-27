/**
 * Make a loop: how many words, what kind of loop, and what it should sound like.
 *
 * **The words are the selection, or a draw from what you are looking at.** Either way they are
 * posted as a list of ids and the server never re-derives them, which is what let words chosen by
 * hand use the same route with no server change at all (`MakeFrom.tsx`). The scope on screen — this
 * language, this topic, this search — is sampled here; the selection is sent as chosen, less any
 * word a loop cannot say.
 *
 * The kind of loop is chosen from `FormatChoices`: the generator's formats — a drill, a radio lesson,
 * a story — each with its switches, opening on the one last made on this device.
 *
 * The music is chosen from `MusicChoices`: Surprise me, a favourite the owner kept, or one of the
 * generator's styles with the sentence it gives to choose it by. The styles are its own catalogue,
 * read from `GET /loops/schema` and never copied into Acervo.
 *
 * **Without the sample pack this refuses rather than warns.** Fifteen of the generator's sixteen bed
 * families name instruments loaded from its catalogue, so a pack-less render dies partway through on
 * a missing sample — after minutes of work, with a message about a file nobody has heard of. The
 * server refuses the same request for the same reason; this is only the earlier, kinder half of it.
 *
 * A word with no single term to say is not eligible — a loop has to choose one meaning — and the
 * count says how many there are rather than letting you ask for more than exist.
 */

import { useEffect, useState } from "react";
import { AcervoApiError, backendSession } from "./api";
import type { VocabularyGraph } from "./domain";
import { lastLoopFormat, loopSwitchesFor, rememberLoopFormat } from "./editorPreferences";
import { BookIcon } from "./icons";
import { languageOf } from "./languages";
import { FormatChoices, formatUsable, switchesFor } from "./LoopFormat";
import { MusicChoices, musicOf, useLoopSchema, type MusicChoice } from "./LoopMusic";
import { ChosenWords, SourceSwitch, wordsCount, type WordSource } from "./MakeFrom";
import {
  chosenFor, favouriteBeds, loopCandidates, loopEligible, sampleLexemeIds, type ListQuery, type SelectedWord
} from "./selectors";

const DEFAULT_WORDS = 12;

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
  const [music, setMusic] = useState<MusicChoice>({ kind: "surprise" });
  const favourites = favouriteBeds(graph);
  const eligible = loopCandidates(graph, query).length;
  const noSamples = Boolean(schema && !schema.productionBundle);
  const most = Math.min(schema?.maxItems ?? 24, Math.max(4, eligible));
  const [words, setWords] = useState(Math.min(DEFAULT_WORDS, Math.max(4, eligible)));
  const [asking, setAsking] = useState(false);
  const [source, setSource] = useState<WordSource>(selection.length && from === "selection" ? "selection" : "scope");
  const fromSelection = source === "selection" && selection.length > 0;
  const chosen = chosenFor(graph, selection, {
    eligible: loopEligible, why: "no single term to say", max: schema?.maxItems ?? 24, noun: "loop"
  });
  const usable = chosen.filter((word) => !word.skip).map((word) => word.id);
  /* The format last made here, while the generator still offers it and this server can make it;
     else the first it offers, which is the drill. */
  const [picked, setPicked] = useState<string | null>(lastLoopFormat);
  const formats = schema?.formats ?? [];
  const format = formats.find((one) => one.id === picked && formatUsable(one, schema!))
    ?? formats.find((one) => formatUsable(one, schema!)) ?? null;
  const [switches, setSwitches] = useState<Record<string, boolean | string>>({});
  const values = format ? switchesFor(format, { ...loopSwitchesFor(format.id), ...switches }) : {};

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const make = async () => {
    setAsking(true);
    try {
      const answer = await backendSession.makeLoop({
        deviceId, language: query.language,
        lexemeIds: fromSelection ? usable : sampleLexemeIds(graph, query, Math.min(words, eligible), Date.now()),
        ...(format ? { format: format.id, switches: values } : {}),
        ...musicOf(music)
      });
      if (format) rememberLoopFormat(format.id, values);
      onMade(answer.loop.id);
      onClose();
    } catch (error) {
      setAsking(false);
      onNotify(error instanceof AcervoApiError ? error.message : "That loop could not be asked for.");
    }
  };

  const where = query.topic === "all" ? languageOf(query.language).name
    : query.topic === "inbox" ? `${languageOf(query.language).name} · Inbox`
      : `${languageOf(query.language).name} · ${graph.topics.find((topic) => topic.id === query.topic)?.name ?? "this topic"}`;

  return <div
    className="modal-backdrop" role="presentation"
    onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
  >
    <section className="settings loop-dialog" role="dialog" aria-modal="true" aria-labelledby="loop-dialog-title">
      <header>
        <h2 id="loop-dialog-title">Make a loop</h2>
        <button className="close" onClick={onClose} aria-label="Close">×</button>
      </header>
      <div className="settings-body">
        <p className="config-help">Your words, set to music with their translations.</p>
        {selection.length > 0 && <SourceSwitch source={source} onSource={setSource} selected={selection.length} where={where} />}
        {fromSelection ? <ChosenWords words={chosen} language={query.language} noun="loop" /> : <>
          <div className="loop-scope">
            <BookIcon />
            <span><strong>{where}</strong> · {eligible} {eligible === 1 ? "word can" : "words can"} be in a loop</span>
          </div>

          <label className="config-field">
            <span>How many words</span>
            <span className="loop-count">
              <input
                type="range" min={Math.min(4, most)} max={most} value={Math.min(words, most)}
                disabled={eligible === 0}
                onChange={(event) => setWords(Number(event.target.value))}
              />
              <output>{Math.min(words, most)} words</output>
            </span>
          </label>
        </>}

        {schema && format && <div className="config-field">
          <span>Kind of loop</span>
          <FormatChoices
            schema={schema} value={format.id} switches={values}
            onChoose={(id) => { setPicked(id); setSwitches({}); }}
            onSwitch={(name, value) => setSwitches({ ...switches, [name]: value })}
          />
        </div>}

        <div className="config-field">
          <span>Music</span>
          <MusicChoices
            graph={graph} families={schema?.families ?? []} favourites={favourites}
            value={music} onChange={setMusic}
          />
        </div>

        <p className="config-help">
          A word with no single term to say is not eligible: a loop has to choose one meaning, and a
          word whose <em>one term</em> has not been written down has none to choose.
        </p>

        {noSamples && <p className="config-help warn">
          This server has no sample pack, so a loop cannot be made. Install it once with{" "}
          <code>./deploy.sh --install-samples</code>.
        </p>}

        <div className="loop-engine">
          {trouble
            ? <span className="warn">{trouble}</span>
            : schema
              ? `engine ${schema.engineVersion} · ${schema.productionBundle
                ? "sample pack installed"
                : "no sample pack"}`
              : "asking the generator what it can do…"}
        </div>

        <div className="loop-actions">
          <button className="tb-btn" onClick={onClose}>Cancel</button>
          <button
            className="tb-btn primary"
            disabled={asking || (fromSelection ? usable.length === 0 : eligible === 0) || Boolean(trouble) || noSamples}
            onClick={() => void make()}
          >{asking ? "Asking…" : fromSelection ? `Make the loop from ${wordsCount(usable.length)}` : "Make the loop"}</button>
        </div>
      </div>
    </section>
  </div>;
}
