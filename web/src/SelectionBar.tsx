/**
 * The selection bar: the words picked to make something from, and what they are for.
 *
 * On the left, what is selected — how many, and as many whole words as fit and then "+N". On the
 * right, the two things a selection is for today, Loop and Story, and × to forget it. The words are
 * a button: they open the list of every selected word, where one can be opened or taken out
 * without finding it again among a thousand.
 *
 * **Where it is drawn is `App`'s decision and `styles.css`'s**: over the list, the map and an
 * article, never over Add, the loops or the stories. Over an article only on a wide window and only
 * while the ask dock rests — on a phone the word has the whole screen, and its foot is the dock's.
 * On a phone, over the list, it takes the Made bar's place; a loop that is playing keeps its bar,
 * under this one. The prototype draws the same bar in `renderSelBar`.
 */

import { useEffect, useRef, useState } from "react";
import FitWords from "./FitWords";
import { CloseIcon, NoteIcon, SelectIcon } from "./icons";
import { languageOf } from "./languages";
import type { SelectedWord } from "./selectors";

function wordsCount(count: number): string {
  return `${count} word${count === 1 ? "" : "s"}`;
}

export default function SelectionBar({ words, language, onOpen, onRemove, onClear, onLoop, onStory }: {
  /** The selected words that still exist, in the order they were chosen. Never empty. */
  words: SelectedWord[];
  language: string;
  onOpen(lexemeId: string): void;
  onRemove(lexemeId: string): void;
  onClear(): void;
  onLoop(): void;
  onStory(): void;
}) {
  const [listing, setListing] = useState(false);
  const bar = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!listing) return;
    /* A press anywhere but the bar puts the list away, as the article's menu does. */
    const away = (event: PointerEvent) => {
      if (event.target instanceof Node && bar.current?.contains(event.target)) return;
      setListing(false);
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setListing(false); };
    window.addEventListener("pointerdown", away);
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("pointerdown", away);
      window.removeEventListener("keydown", escape);
    };
  }, [listing]);

  const count = wordsCount(words.length);
  return <div className="selbar" ref={bar}>
    <button
      className="selbar-what" aria-haspopup="menu" aria-expanded={listing}
      aria-label={`Your selection: ${count}. Show them`}
      onClick={() => setListing((open) => !open)}
    >
      <span className="selbar-badge" aria-hidden="true"><SelectIcon on /></span>
      <span className="selbar-text">
        <span className="selbar-title">{count} selected</span>
        <FitWords className="selbar-words" words={words.map((word) => word.headword)} count lang={language} />
      </span>
    </button>
    <button className="tb-btn selbar-make" aria-label="Make a loop from these words" onClick={() => { setListing(false); onLoop(); }}>
      <NoteIcon /><span>Loop</span>
    </button>
    <button className="tb-btn selbar-make" aria-label="Make a story from these words" onClick={() => { setListing(false); onStory(); }}>
      <span className="selbar-ic" aria-hidden="true">📖</span><span>Story</span>
    </button>
    <button className="icon-btn selbar-clear" aria-label="Forget the selection" title="Forget the selection" onClick={() => { setListing(false); onClear(); }}>
      <CloseIcon />
    </button>

    {listing && <div className="menu open sel-menu" role="menu" aria-label="Selected words">
      <div className="label menu-label">Your selection · {languageOf(language).name}</div>
      <div className="sel-items">
        {words.map((word) => <div className="sel-item" key={word.id}>
          <button className="sel-open" role="menuitem" onClick={() => { setListing(false); onOpen(word.id); }}>
            <span className="plate" aria-hidden="true">{word.emoji || "📄"}</span>
            <span className="sel-id">
              <span className="sel-word" lang={language}>{word.headword}</span>
              <span className="sel-gloss">{word.shortGloss}</span>
            </span>
          </button>
          <button
            className="sel-drop" aria-label={`Remove ${word.headword} from the selection`} title="Remove from the selection"
            onClick={() => onRemove(word.id)}
          ><CloseIcon /></button>
        </div>)}
      </div>
      <div className="menu-sep" />
      <button role="menuitem" onClick={() => { setListing(false); onClear(); }}>Clear the selection</button>
    </div>}
  </div>;
}
