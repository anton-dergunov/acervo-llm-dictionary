import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { DictionaryArticle } from "./dictionary";
import { lookup } from "./dictionaries";
import { Transcription } from "./ipa/Transcription";
import { CaretIcon } from "./icons";
import {
  externalEntryOf, genderOf, referenceTextOf, type ExternalEntry, type ExternalSection
} from "./externalEntries";
import { BookIcon, GlobeIcon } from "./icons";
import { languageOf } from "./languages";

/**
 * A word as an external dictionary has it.
 *
 * Deliberately built out of `LexemeArticle.tsx`'s own marks — `.masthead`, `.sec`, `.rail-l`,
 * `.sense-def`, `.ex` — rather than a second set of its own. Someone glancing at a word should be
 * reading, not adjusting to a different page; the things that differ here differ because they are
 * *true*, not because this is a different component. There is no emoji, because nobody chose one.
 * There are no study statistics, because this word is not being studied. There is no storage
 * footer, because nothing is stored.
 *
 * Several dictionaries land on one page with a section each, in resolution order, and the jump
 * chips move between them. Comparing what two dictionaries say about a word is most of the reason
 * for having two, so a tab that hides one behind the other would be working against the feature.
 */

/** What "add this to my words" asks for. The interface never writes: this becomes a capture. */
export interface DictionaryAddRequest {
  headword: string;
  language: string | null;
  reference: string;
  referenceMode: "faithful" | "expand" | null;
  note: string | null;
  /** The dictionaries it was read from, so the review surface can say where it came from. */
  sources: string[];
}

type AddMode = "faithful" | "expand" | "custom";

const MODES: [AddMode, string, string][] = [
  ["faithful", "Close to the source", "Say what this entry says, and no more."],
  ["expand", "Fill in the gaps", "Add the glosses, examples, notes and emoji it has no room for."],
  ["custom", "Tell it what to do", "Ask for exactly what you want from this word."]
];

const ORIGIN_LABEL: Record<ExternalSection["origin"], string> = {
  device: "stored on this device",
  server: "on your server",
  online: "looked up online"
};

/**
 * The source's name without its direction, for the section rail.
 *
 * Only the parenthetical goes: the rail wraps, so "Free Dictionary API" belongs there whole.
 * Truncating to fit one line turned it into "Free", which names nothing.
 */
function railLabel(name: string): string {
  return name.replace(/\s*[([].*$/, "").trim() || name;
}

const sectionId = (section: ExternalSection) => `ext-${section.dictionaryId}`;

/**
 * The source's own words about the word, minus anything the masthead has already said.
 *
 * A section that repeats `n · ja` under a masthead reading "n · Japanese · external dictionary" is
 * pure noise, and it was on almost every entry of the single-article dictionaries. What survives
 * here is what this *source* adds: a second part of speech for a homograph, a register, a language
 * that genuinely differs from the entry's.
 */
function GrammarLine({ article, entry }: { article: DictionaryArticle; entry: ExternalEntry }) {
  // The source's own word for the part of speech, verbatim (§11.3). Acervo's enum is for records
  // that are stored, and bucketing `preposition` into `expression` to satisfy it would be a lie.
  const pos = article.posLabel ?? article.pos;
  const language = article.language && article.language !== entry.language ? article.language : null;
  const gender = genderOf(article);
  const bits = [pos && pos !== entry.posLabel ? pos : null, gender && gender !== entry.gender ? gender : null,
                language, article.register ?? null]
    .filter((bit): bit is string => Boolean(bit));
  if (!bits.length) return null;
  return <p className="gram">{bits.map((bit, index) =>
    <span key={`${bit}:${index}`}>{index > 0 && <span className="sep">·</span>}{bit}</span>)}</p>;
}

function FieldsArticle({ article, entry, single }: {
  article: DictionaryArticle; entry: ExternalEntry; single: boolean;
}) {
  return <div className="ext-entry">
    {!single && <p className="ext-headword">{article.headword}{article.reading && <span className="rdg">{article.reading}</span>}</p>}
    <GrammarLine article={article} entry={entry} />
    <ol className="ext-senses">
      {article.senses.map((sense, index) => <li key={index}>
        <p className="sense-def">{sense.definition}</p>
        {sense.domain && <span className="ext-tag">{sense.domain}</span>}
        {sense.examples?.map((example, position) => <div key={position} className="ex ext-ex">
          <p className="t">{example.text}</p>
          {example.translation && <p className="tr">{example.translation}</p>}
        </div>)}
      </li>)}
    </ol>
  </div>;
}

function Section({ section, entry, scrollMargin }: {
  section: ExternalSection; entry: ExternalEntry; scrollMargin?: number;
}) {
  return <section
    className="sec ext-sec" id={sectionId(section)}
    // Measured, not guessed: the jump nav wraps to two or three rows once a word is held by five or
    // six dictionaries, and a fixed offset then drops the heading behind it again.
    style={scrollMargin ? { scrollMarginTop: scrollMargin } : undefined}
  >
    <div className="rail-l"><div className="inner">
      <span className="num">{section.origin === "online" ? "🌐" : "📖"}</span>
      <span className="label">{railLabel(section.name)}</span>
    </div></div>
    <div className="body">
      {section.tier === "html"
        // Sanitised and restyled by `externalHtml.ts`, which is the only place this markup is
        // trusted. Nothing reaches here that was not rebuilt from an allow-list.
        ? <div className="ext-body" dangerouslySetInnerHTML={{ __html: section.html }} />
        : section.articles.map((article, index) =>
            <FieldsArticle key={index} article={article} entry={entry}
                           single={section.articles.length === 1} />)}
      {/* Shown wherever the content is, not once at the foot: CC BY-SA asks this of whoever
          displays the text, and each section is a different source under a different licence. */}
      <p className="ext-credit">
        <span>{section.attribution}</span>
        {/* Most artifacts end their attribution with the licence already, and printing it twice
            reads as a mistake in the very line whose job is to be exact. */}
        {!section.attribution.includes(section.licence) && <>
          <span className="sep">·</span><span>{section.licence}</span>
        </>}
        <span className="sep">·</span><span>{ORIGIN_LABEL[section.origin]}</span>
      </p>
    </div>
  </section>;
}

function AddPanel({ entry, onAdd, onCancel, busy }: {
  entry: ExternalEntry; onAdd(request: DictionaryAddRequest): void; onCancel(): void; busy: boolean;
}) {
  const [mode, setMode] = useState<AddMode>("expand");
  const [note, setNote] = useState("");

  function submit() {
    onAdd({
      headword: entry.word,
      language: entry.language,
      reference: referenceTextOf(entry),
      // A free-text instruction is its own thing: the note carries it, and the two canned modes
      // are wordings that live in `prompts/`, not here.
      referenceMode: mode === "custom" ? null : mode,
      note: mode === "custom" ? note.trim() || null : null,
      sources: entry.sections.map((section) => section.name)
    });
  }

  return <div className="ext-add" role="group" aria-label={`Add ${entry.word} to your words`}>
    <p className="ext-add-title">Add “{entry.word}” to your words</p>
    {MODES.map(([value, label, help]) => <label key={value} className={`ext-mode ${mode === value ? "on" : ""}`}>
      <input type="radio" name="ext-add-mode" checked={mode === value} onChange={() => setMode(value)} />
      <span><strong>{label}</strong><span className="hint">{help}</span></span>
    </label>)}
    {mode === "custom" && <input
      className="capture-word" value={note} autoComplete="off" autoFocus
      placeholder="contrast it with picante, and keep only the cooking senses"
      onChange={(event) => setNote(event.target.value)}
    />}
    <p className="hint">
      The entry above is sent as reference, so the article is built from what you just read. It
      arrives in <b>Inbox</b> for review — nothing is saved until you approve it.
    </p>
    <div className="composer-buttons">
      <span className="spacer" />
      <button className="tb-btn" onClick={onCancel} disabled={busy}>Cancel</button>
      <button
        className="tb-btn primary" disabled={busy || (mode === "custom" && !note.trim())}
        onClick={submit}
      >{busy ? "Building…" : "Build entry"}</button>
    </div>
  </div>;
}

export default function ExternalArticle({ entry, onAdd, busy = false }: {
  entry: ExternalEntry;
  /** Absent on the reference fold inside your own article: that word is already yours. */
  onAdd?(request: DictionaryAddRequest): void;
  busy?: boolean;
}) {
  const [adding, setAdding] = useState(false);
  const jump = useRef<HTMLElement>(null);
  const [jumpHeight, setJumpHeight] = useState(0);

  /* How far a jump has to clear. The nav is sticky and its height is not a constant: it wraps with
     the number of sources and with the width of the window, so anything hard-coded is right for one
     entry and wrong for the next. */
  useLayoutEffect(() => {
    const nav = jump.current;
    if (!nav) { setJumpHeight(0); return; }
    const measure = () => setJumpHeight(nav.getBoundingClientRect().height);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(nav);
    return () => observer.disconnect();
  }, [entry]);
  const online = entry.sections.length > 0 && entry.sections.every((section) => section.origin === "online");
  const language = entry.language ? languageOf(entry.language) : null;

  return <>
    <div className="masthead">
      <div className="head-row">
        <div className="emoji-plate ext">{online ? <GlobeIcon /> : <BookIcon />}</div>
        <div className="head-text">
          <h1 className="headword">{entry.word}</h1>
          {entry.reading && <div className="reading">{entry.reading}</div>}
          {entry.ipa && <div className="pron-row">
            <Transcription ipa={entry.ipa} reading={entry.reading} language={entry.language} />
          </div>}
          <p className="gram">
            {[entry.posLabel, entry.gender, language?.name, "external dictionary"]
              .filter((bit): bit is string => Boolean(bit))
              .map((bit, index) => <span key={bit}>{index > 0 && <span className="sep">·</span>}{bit}</span>)}
          </p>
        </div>
      </div>
      <div className="chips">
        <span className="chip ext">not in your words</span>
        {/* With several sources the jump nav below already names them, and saying it twice in two
            rows of chips reads as a mistake. One source has no nav, so the chip is where it goes. */}
        {entry.sections.length === 1
          && <span className="chip">{entry.sections[0].name}</span>}
      </div>
    </div>

    {/* Everything is on this one page; these only move you down it. Sticky, because the reason to
        want one is that you are already several screens into another source. */}
    {entry.sections.length > 1 && <nav className="ext-jump" aria-label="Sources" ref={jump}>
      {entry.sections.map((section) => <button
        key={section.dictionaryId}
        onClick={() => document.getElementById(sectionId(section))
          ?.scrollIntoView({ behavior: "smooth", block: "start" })}
      >{section.name}</button>)}
    </nav>}

    {onAdd && (adding
      ? <AddPanel entry={entry} onAdd={onAdd} busy={busy} onCancel={() => setAdding(false)} />
      : <div className="ext-actions">
          <button className="tb-btn primary" onClick={() => setAdding(true)}>Add to my words</button>
        </div>)}

    {entry.sections.length
      ? entry.sections.map((section) =>
          <Section key={section.dictionaryId} section={section} entry={entry}
                   scrollMargin={jumpHeight ? Math.round(jumpHeight) + 14 : undefined} />)
      : <p className="empty">No dictionary here holds this word.</p>}
  </>;
}


/**
 * What the dictionaries say about a word that is already yours.
 *
 * Read-only, and with no "add" — you have it. It looks nothing up until it is shown: an article you
 * are reading should not be quietly issuing byte-range reads on the chance you are curious, and on a
 * phone that chance is mostly no. So the article mounts this only when its section is unfolded or
 * its card is reached, and mounting is what asks.
 */
export function DictionaryEntries({ headword, lemma, language, onLoaded }: {
  headword: string; lemma: string; language: string;
  /**
   * What is on screen, reported upward so a question can be asked against it.
   *
   * Only what is actually shown: unmounted, nothing is loaded and nothing is reported, which is the
   * honest answer. Chat sends the dictionary text as read-only context, never as something it may
   * propose changing.
   */
  onLoaded?(entry: ExternalEntry | null): void;
}) {
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [entry, setEntry] = useState<ExternalEntry | null>(null);
  const spellings = [...new Set([headword.trim(), lemma.trim()].filter(Boolean))];

  useEffect(() => {
    let live = true;
    setState("loading");
    // Only what is at hand: this is a footnote on a word you already have, which is not a reason to
    // spend an online source's rate limit. Both spellings, because a dictionary is keyed on the
    // lemma and Acervo's headword keeps the article that tells a learner the gender.
    void lookup(headword, language, ["device", "server"], [lemma])
      .then((results) => {
        if (!live) return;
        const found = externalEntryOf(headword, results);
        setEntry(found);
        setState("ready");
        onLoaded?.(found);
      })
      .catch(() => { if (live) setState("failed"); });
    return () => {
      live = false;
      onLoaded?.(null);
    };
    // `onLoaded` is a setter from the caller and deliberately not a reason to look the word up again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [headword, lemma, language]);

  return <div className="ext-fold-article">
    {state === "loading" && <p className="ext-status">Looking through your dictionaries…</p>}
    {state === "failed" && <p className="ext-status">Your dictionaries could not be read just now.</p>}
    {state === "ready" && (entry?.sections.length
      ? entry.sections.map((section) =>
          <Section key={section.dictionaryId} section={section} entry={entry} />)
      : <p className="ext-status">
          No dictionary on this device or your server holds{" "}
          {spellings.map((spelling, index) =>
            <Fragment key={spelling}>{index > 0 && " or "}“{spelling}”</Fragment>)}.
        </p>)}
  </div>;
}
