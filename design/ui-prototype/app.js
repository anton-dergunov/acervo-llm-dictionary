/* Acervo — UI prototype behaviour.
   Everything here is view logic over the fixtures in data.js. No storage, no
   network: buttons that would call the repository or a provider are stubs. */

const state = {
  lang: "es",
  topic: "all",
  sort: "recent",
  query: "",
  openId: null,
  add: false,       // composing a new entry, which replaces the list
  mode: "read",     // read | yaml | edit
  /* External dictionaries. `openExt` is a word, not an id: an external entry has no id, which is
     most of what distinguishes it from one of yours. `onlineDone` is what ⏎ sets. */
  openExt: null,
  onlineDone: false,
  scope: { device: true, server: true, online: true },
  /* How far the ask dock is open, and which block a question is bounded to. Three detents and no
     intermediate state: dock | half | full (article-chat §7.3). */
  ask: "dock",   // dock | open | full
  askFocus: null,
  /* A proposal under review. Painted rather than applied — the prototype has no applier — so the
     marks, the review bar and the struck-through removal can all be looked at. */
  review: false,
  /* The article redesign spike. `view` null means "the default for this device" (`currentView`);
     `card` is which card Cards is showing; and `sayTranslations` puts listen buttons after
     translations too. */
  view: null,
  card: 0,
  sayTranslations: false,
  /* Loops. `loops` is whether the surface is open — it replaces the list, the way an article does —
     and `loopLayout` is the shape it takes, which is the thing being chosen between. Which loop is
     loaded and where it has got to belong to `player`, not here: they survive leaving the surface,
     because a loop keeps playing while you read a word. */
  loops: false,
  /* Which loop the surface is showing. What is *playing* is `player`'s, not this: a loop goes on
     playing while you read a word, which is most of the point of having one. */
  loopOpen: null,
  /* Which row has been right-clicked — `word:<id>`, `loop:<id>` or `story:<id>`, because a word, a
     loop and a story are one kind of row (`swipeRow`). A pointer has a gesture for this and a finger
     does not, so the finger gets the row itself: it is wider than the list and its actions are the
     second snap point. */
  rowMenu: null,
  /* Where in that row, so the menu opens under the pointer. */
  rowMenuAt: { x: 0, y: 0 },
  /* Whether the selection bar's list of words is open. */
  selList: false,
  /* Stories, the same shape as loops: `stories` is whether the surface is open, `storyOpen` is
     which one is being read, and `storyAt` is which part of it. `storyShown` is the set of parts
     whose translation has been turned over — per part, because revealing one answer must not
     reveal the next. */
  stories: false,
  storyOpen: null,
  storyAt: 0,
  storyShown: {},
  /* The map, the same shape again: whether it is open, which sense is peeked at (an index into the
     map's points), and whether an article was opened from it, so Back returns there. `mapStyle` and
     `mapLabels` are the choices being made by looking; `mapState` is a prototype-only stand-in for
     the first draw and for a device that has never reached the server. */
  map: false,
  mapSel: -1,
  mapReturn: false,
  /* Where Back from an article goes when it was opened from a word tapped in a story or a loop. */
  readingReturn: null,
  mapStyle: "atlas",
  mapLabels: "model",
  mapState: null,
  mapSample: false
};

const $  = (sel, root = document) => root.querySelector(sel);
const el = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };
const topicOf = (key) => TOPICS.find((t) => t.key === key);
const langOf  = (code) => LANGUAGES.find((l) => l.code === code);
const strip   = (s) => String(s).replace(/<[^>]+>/g, "");
const esc     = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const ICON = {
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.6-3.6"/></svg>',
  back:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg>',
  forward:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5l7 7-7 7"/></svg>',
  plus:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  play:   '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>',
  caret:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5l7 7-7 7"/></svg>',
  pencil: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4l10-10-4-4L4 16z"/><path d="M13.5 6.5l4 4"/></svg>',
  trash:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13"/></svg>',
  /* File it: the Inbox tray with an arrow leaving it, so it reads as the opposite of how the word
     got there. */
  file:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 13h4l1.5 3h7l1.5-3h4"/><path d="M3 13l3-7h12l3 7v5H3z"/><path d="M12 10V2M9 5l3-3 3 3"/></svg>',
  close:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  book:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H18v14H5.5A1.5 1.5 0 0 0 4 19.5z"/><path d="M4 19.5A1.5 1.5 0 0 1 5.5 18H20v2.5H5.5"/><path d="M8 8h6"/></svg>',
  globe:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.2 2.3 3.3 5.2 3.3 8.5S14.2 18.2 12 20.5c-2.2-2.3-3.3-5.2-3.3-8.5S9.8 5.8 12 3.5z"/></svg>',
  /* Asking about a word — deliberately not `✳`, which is already "where you met it". */
  ask:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 14.5A2.5 2.5 0 0 1 17.5 17H12l-4.5 3.5V17H6.5A2.5 2.5 0 0 1 4 14.5v-8A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5z"/><path d="M10.2 8.6a1.9 1.9 0 1 1 2.6 1.8c-.5.2-.8.7-.8 1.2v.3"/><path d="M12 14.2v.1"/></svg>',
  chevron:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 15l7-7 7 7"/></svg>',
  /* A clip, drawn as a strip of film: a play triangle alone reads as "audio". */
  film:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="5" width="17" height="14" rx="2"/><path d="M3.5 9h17M3.5 15h17M7.5 5v4M12 5v4M16.5 5v4M7.5 15v4M12 15v4M16.5 15v4"/></svg>',
  /* The corner arrow that says a control opens something, drawn as plainly as it can be: the pill
     it sits in is already carrying a film strip and a line of text. */
  open:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17L17 7"/><path d="M9 7h8v8"/></svg>',
  info:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5"/><path d="M12 7.6v.1"/></svg>',
  picture:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="5" width="17" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M4 16.5l4.5-4 3.5 3 3-2.5 5 4"/></svg>',
  /* The printer's ivy leaf, pointing right (❧); mirrored in CSS for ☙. Drawn, not typed, because
     Literata has no such glyph and every platform's fallback draws a different one. */
  /* U+2767 from EB Garamond (Georg Duffner, Octavio Pardo), SIL Open Font License 1.1. */
  more:   '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5.5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="18.5" cy="12" r="1.7"/></svg>',
  hedera: '<svg viewBox="0 0 910 508" aria-hidden="true"><path fill="currentColor" d="M135 508Q107 508 86 489Q66 470 51 447Q35 447 18 443Q0 439 0 414Q0 382 16 350Q33 319 58 296Q83 272 107 266Q100 258 98 248Q96 239 96 229Q96 215 110 202Q124 189 146 179Q167 169 190 163Q214 157 232 157Q244 157 256 158Q269 158 281 160Q281 138 272 117Q262 96 248 82Q233 68 218 68Q206 68 200 74Q193 79 187 86Q180 94 171 101Q162 108 144 108Q113 108 92 86Q70 63 70 32Q70 18 80 9Q89 0 102 0Q110 0 114 6Q117 12 120 18Q123 24 126 28Q129 33 134 33Q139 33 142 28Q146 24 150 18Q154 12 158 7Q163 2 170 2Q212 2 246 22Q279 43 298 77Q318 111 318 150Q318 154 318 158Q317 162 317 166Q348 173 371 188Q394 202 410 216Q414 220 419 218Q424 216 420 214Q410 206 398 189Q387 172 387 153Q387 127 400 106Q412 86 433 74Q454 62 480 62Q519 62 547 78Q575 93 598 118Q620 142 640 168Q668 203 696 232Q725 260 766 260Q790 260 813 252Q836 245 851 230Q866 214 866 190Q866 157 844 134Q839 135 834 136Q830 136 826 136Q804 137 794 126Q785 114 785 96Q785 75 802 64Q819 54 840 54Q865 54 880 72Q895 91 902 118Q910 146 910 172Q910 224 886 268Q861 311 819 345Q777 379 726 403Q675 427 622 440Q568 452 520 452Q480 452 438 436Q397 421 370 391Q342 361 342 318Q342 292 358 276Q373 259 396 248Q404 244 404 242Q404 240 396 236Q377 225 356 218Q336 210 312 206Q305 238 290 266Q275 294 254 312Q234 329 208 329Q195 329 184 326Q174 323 165 319Q157 317 149 314Q141 312 133 312Q108 312 93 333Q78 354 78 380Q78 408 92 433Q107 458 130 458Q138 458 144 455Q149 452 153 448Q158 443 164 440Q170 436 178 436Q187 436 192 444Q196 453 196 462Q196 484 178 496Q159 508 135 508ZM190 286Q215 286 238 260Q260 234 272 202H254Q234 202 210 206Q186 211 169 220Q152 230 152 244Q152 260 163 273Q174 286 190 286Z"/></svg>',
  send:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h14"/><path d="M13 6l6 6-6 6"/></svg>',
  /* The transport. Filled rather than stroked, because at 22 px a stroked triangle reads as an
     outline of a play button and every music player on the device draws a solid one. */
  pause:  '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="7" y="5.5" width="3.6" height="13" rx="1.1"/><rect x="13.4" y="5.5" width="3.6" height="13" rx="1.1"/></svg>',
  prev:   '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="5.5" y="6.5" width="2.4" height="11" rx="1"/><path d="M16.5 6.5v11L8 12z"/></svg>',
  next:   '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7.5 6.5v11L16 12z"/><rect x="16.1" y="6.5" width="2.4" height="11" rx="1"/></svg>',
  /* A loop's own mark: a beamed pair, which says music without saying "audio file". */
  note:   '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19 4.2L9.2 6.4v9.05a2.9 2.9 0 1 0 1.5 2.55V9.1l6.8-1.5v5.6a2.9 2.9 0 1 0 1.5 2.55z"/></svg>',
  /* Play it again, and go on to the next one: the two glyphs every player uses, so neither needs a
     label to be understood. */
  star:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.8l2.5 5.2 5.7.8-4.1 4 1 5.7-5.1-2.7-5.1 2.7 1-5.7-4.1-4 5.7-.8z"/></svg>',
  starOn: '<svg viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.8l2.5 5.2 5.7.8-4.1 4 1 5.7-5.1-2.7-5.1 2.7 1-5.7-4.1-4 5.7-.8z"/></svg>',
  down:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>',
  repeat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M6 7h11a3 3 0 0 1 3 3v1"/><path d="M18 17H7a3 3 0 0 1-3-3v-1"/><path d="M8.5 4.5L6 7l2.5 2.5"/><path d="M15.5 19.5L18 17l-2.5-2.5"/></svg>',
  continue:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h11M4 12h8M4 17h8"/><path d="M16 11.5v7l5.5-3.5z" fill="currentColor" stroke-width="1"/></svg>',
  /* The map: a folded sheet, and the four corners of "show all of it". */
  map:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 4.5L3.5 6.5v13L9 17.5l6 2 5.5-2v-13L15 6.5z"/><path d="M9 4.5v13M15 6.5v13"/></svg>',
  fit:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
  minus:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14"/></svg>',
  /* Selecting a word: a circle with a plus, and the same circle with a check once it is selected.
     `check` alone is the badge a selected word wears, in the list and on the map. */
  select: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 8.5v7M8.5 12h7"/></svg>',
  selected:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M8.3 12.3l2.5 2.5 5-5.2"/></svg>',
  check:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 12.5l4 4 8-8.5"/></svg>',
  hourglass:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4h10M7 20h10"/><path d="M8 4c0 4 4 5 4 8s-4 4-4 8"/><path d="M16 4c0 4-4 5-4 8s4 4 4 8"/></svg>'
};

/* ── external dictionaries ───────────────────────────────────────────────
   Below a rule, after every one of your own words, and never interleaved with them. Carries no
   emoji, no sense count and no strength bars, because it has none of those things. */

function externalHits() {
  const q = state.query.trim().toLowerCase();
  if (!q) return [];
  return EXTERNAL.filter((x) => x.word.toLowerCase().startsWith(q.slice(0, 3))
    && (x.origin !== "online" || state.onlineDone)
    && (x.origin !== "device" || state.scope.device)
    && (x.origin !== "online" || state.scope.online));
}

function externalOf(word) { return EXTERNAL.find((x) => x.word === word); }

function sourceLabel(x) {
  return x.sources.length > 2 ? `${x.sources.length} sources` : x.sources.map((s) => s.name).join(" · ");
}

function renderExternal() {
  const q = state.query.trim();
  const hits = externalHits();
  const anyScope = state.scope.device || state.scope.server || state.scope.online;
  if (!q || !anyScope) return "";
  return `
    <div class="ext-section">
      <div class="list-sep"><span class="label">Other dictionaries</span></div>
      <div class="rows">
        ${hits.map((x) => `
          <button class="row ext" data-ext="${esc(x.word)}">
            <span class="plate ext">${x.origin === "online" ? ICON.globe : ICON.book}</span>
            <span data-sources="${esc(sourceLabel(x))}">
              <span class="word">${esc(x.word)}</span>
              <span class="gloss">${esc(x.gloss)}</span>
            </span>
            <span class="meta"><span class="src">${esc(sourceLabel(x))}</span></span>
          </button>`).join("")}
      </div>
      ${hits.length ? "" : `<p class="ext-status">No dictionary here holds “${esc(q)}”.</p>`}
      ${state.scope.online && !state.onlineDone ? `
        <button class="ext-online" id="onlineBtn">${ICON.globe}
          <span>Press ⏎ to look “${esc(q)}” up online</span></button>` : ""}
    </div>`;
}

function renderExternalArticle(x) {
  const section = (s) => `
    <section class="sec ext-sec" id="ext-${esc(s.id)}">
      <div class="rail-l"><div class="inner">
        <span class="num">${s.origin === "online" ? "\u{1F310}" : "\u{1F4D6}"}</span>
        <span class="label">${esc(s.name.replace(/\s*[([].*$/, ""))}</span>
      </div></div>
      <div class="body">
        ${s.tier === "html" ? `<div class="ext-body">${s.html}</div>` : `
          <div class="ext-entry">
            <p class="gram"><span>${esc(x.posLabel || "")}</span><span class="sep">·</span><span>${esc(state.lang)}</span></p>
            <ol class="ext-senses">
              ${s.senses.map((sense) => `
                <li><p class="sense-def">${esc(sense.definition)}</p>
                  ${(sense.examples || []).map((e) => `
                    <div class="ex ext-ex"><p class="t">${esc(e.text)}</p>
                      ${e.translation ? `<p class="tr">${esc(e.translation)}</p>` : ""}</div>`).join("")}
                </li>`).join("")}
            </ol>
          </div>`}
        <p class="ext-credit"><span>${esc(s.attribution)}</span><span class="sep">·</span>
          <span>${s.origin === "device" ? "stored on this device" : s.origin === "server" ? "on your server" : "looked up online"}</span></p>
      </div>
    </section>`;

  return `
    ${review}
    <div class="masthead">
      <div class="head-row">
        <div class="emoji-plate ext">${x.online ? ICON.globe : ICON.book}</div>
        <div class="head-text">
          <h1 class="headword">${esc(x.word)}</h1>
          ${x.ipa ? `<div class="pron-row"><span class="ipa">${esc(x.ipa)}</span></div>` : ""}
          <p class="gram"><span>${esc(x.posLabel || "")}</span><span class="sep">·</span>
            <span>${esc(langOf(state.lang).name)}</span><span class="sep">·</span><span>external dictionary</span></p>
        </div>
      </div>
      <div class="chips">
        <span class="chip ext">not in your words</span>
        ${x.sections.length === 1 ? `<span class="chip">${esc(x.sections[0].name)}</span>` : ""}
      </div>
    </div>
    ${x.sections.length > 1 ? `<nav class="ext-jump" aria-label="Sources">
      ${x.sections.map((s) => `<button data-jump="ext-${esc(s.id)}">${esc(s.name)}</button>`).join("")}
    </nav>` : ""}
    <div class="ext-actions"><button class="tb-btn primary" id="extAdd">Add to my words</button></div>
    ${x.sections.map(section).join("")}`;
}

/* ── selection helpers ───────────────────────────────────────────────── */

function inLanguage()  { return LEXEMES.filter((x) => x.language === state.lang); }
function inboxCount()  { return inLanguage().filter((x) => x.status === "inbox").length; }
function topicCount(k) { return inLanguage().filter((x) => x.topics.includes(k) && x.status !== "inbox").length; }

/**
 * Out of the Inbox and into its topics — one word, or the whole tab at once.
 *
 * The rail drops the Inbox tab once it is empty, so standing on it would leave you looking at a list
 * with no way back to itself; only the tab moves, and an open word stays open.
 */
function fileWords(ids) {
  const filing = LEXEMES.filter((x) => ids.includes(x.id) && x.status === "inbox");
  if (!filing.length) return;
  filing.forEach((x) => { x.status = "active"; });
  if (state.topic === "inbox" && !inboxCount()) state.topic = "all";
  render();
  toast(filing.length === 1 ? "Filed — it is in its topics now" : `Filed ${filing.length} words`);
}

function visible() {
  let rows = inLanguage();
  const q = state.query.trim().toLowerCase();
  if (q) {
    rows = rows.filter((x) => {
      const hay = [x.headword, x.lemma, x.reading || "", x.shortGloss || "",
        ...x.senses.map((s) => s.definition),
        ...x.senses.flatMap((s) => s.glosses.flatMap((g) => g.terms))].join(" ").toLowerCase();
      return hay.includes(q);
    });
  } else if (state.topic === "inbox") {
    rows = rows.filter((x) => x.status === "inbox");
  } else {
    rows = rows.filter((x) => x.status !== "inbox");
    if (state.topic !== "all") rows = rows.filter((x) => x.topics.includes(state.topic));
  }
  const key = (x) => x.headword.replace(/^(el|la|los|las) /, "");
  const sorters = {
    recent: (a, b) => b.createdAt.localeCompare(a.createdAt),
    alpha:  (a, b) => key(a).localeCompare(key(b), state.lang),
    hard:   (a, b) => (b.study ? b.study.difficulty : 99) - (a.study ? a.study.difficulty : 99)
  };
  return rows.slice().sort(sorters[state.sort]);
}

function shortGlossOf(x) {
  if (x.shortGloss) return x.shortGloss;
  const first = x.senses[0];
  const pref = langOf(x.language).glossLangs[0];
  const g = first.glosses.find((y) => y.lang === pref) || first.glosses[0];
  return g ? g.terms.join("; ") : strip(first.definition);
}

/* ── the selection ────────────────────────────────────────────────────────
   Words put aside to make a loop or a story from. A word is *marked* — from a row's menu or swipe,
   the article's bar, or the map's peek — never ticked: a thousand words across a dozen topics is not
   a list anyone ticks through, and a mark survives changing topic, searching and opening things,
   which a checkbox in one view never quite does.

   One selection per language, in the order the words were chosen, because a loop and a story are
   each in one language. In the application it is `selection.ts`: this device's, kept in local
   storage, never synced. Here it is memory.

   An entry is a lexeme id, or `map:<w>` for a word the prototype has only on its map — the map and
   the articles are separate fixtures, so a word marked there may have no article to open. */
const picks = {};
/* What the prototype knows about a map-only entry, captured when it was marked. */
const pickedFromMap = {};
let pickUndo = null;

function pickEntry(key) {
  const x = LEXEMES.find((y) => y.id === key);
  if (x) return { key, headword: x.headword, emoji: x.emoji, gloss: shortGlossOf(x), loopable: Boolean(x.primaryGloss), article: x.id };
  const m = pickedFromMap[key];
  return m ? { key, headword: m.headword, emoji: m.emoji, gloss: m.gloss, loopable: Boolean(m.gloss), article: null } : null;
}
function picked(lang = state.lang) { return (picks[lang] || []).map(pickEntry).filter(Boolean); }
const isPicked = (key, lang = state.lang) => (picks[lang] || []).includes(key);
const wordsCount = (n) => `${n} word${n === 1 ? "" : "s"}`;

/* Toggle one word. Says so in a toast only where the bar is not on screen to say it — over an
   article on a phone — since everywhere else the mark and the bar changing is the answer. */
function togglePick(key, lang = state.lang) {
  const list = picks[lang] || (picks[lang] = []);
  const at = list.indexOf(key);
  if (at >= 0) list.splice(at, 1); else list.push(key);
  if (state.openId && !selBarOverArticle()) toast(at >= 0 ? "Removed from your selection" : `Added to your selection · ${wordsCount(list.length)}`);
  if (!list.length) state.selList = false;
  render();
}
/* Forgetting is one tap, so it is undoable: a selection can be twenty words gathered over an hour. */
function clearPicks(lang = state.lang) {
  const before = (picks[lang] || []).slice();
  if (!before.length) return;
  picks[lang] = [];
  state.selList = false;
  pickUndo = () => { picks[lang] = before; render(); };
  render();
  toast("Selection cleared", { label: "Undo", run: () => pickUndo && pickUndo() });
}

/* The key a map point is marked under: the lexeme the prototype has an article for, else the point's
   own word. */
const lexemeByHeadword = new Map();
function pointKey(p) {
  const want = fold(p.headword);
  if (!lexemeByHeadword.has(want)) {
    const hit = LEXEMES.find((x) => fold(x.headword) === want || fold(x.lemma) === want);
    lexemeByHeadword.set(want, hit ? hit.id : null);
  }
  return lexemeByHeadword.get(want) || `map:${p.w}`;
}

/* ── a row with actions ───────────────────────────────────────────────────
   Words, loops and stories are one kind of row, with two ways to the same actions because a
   pointer and a finger do not have the same gestures. A pointer right-clicks and gets `.row-menu`. A
   finger pushes the row aside and finds `.swipe-actions` behind it — scroll-snap rather than touch
   handling, the way the cards already swipe, so there is no pointer arithmetic to get wrong and a
   trackpad gets it for free. `SwipeRow.tsx` in the application.

   Each action is `{ label, menu, tone, attrs, sep }`: the short label the swipe shows, the longer one
   the menu reads, `danger` for red, the data attribute the click handler acts on, and whether a rule
   goes above it in the menu. */
function swipeRow(key, row, actions, shellClass = "") {
  const open = state.rowMenu === key;
  return `<div class="swipe-item" data-row-menu="${key}">
    <div class="swipe-shell${shellClass ? ` ${shellClass}` : ""}">
      ${row}
      <div class="swipe-actions">${actions.map((a) =>
        `<button class="swipe-act${a.tone ? ` ${a.tone}` : ""}" ${a.attrs}>${a.label}</button>`).join("")}</div>
    </div>
    ${open ? `<div class="menu open row-menu" role="menu" style="--menu-x:${state.rowMenuAt.x}px;--menu-y:${state.rowMenuAt.y}px">
      ${actions.map((a) => `${a.sep ? '<div class="menu-sep"></div>' : ""}<button role="menuitem"${a.tone === "danger" ? ' class="danger"' : ""} ${a.attrs}>${a.menu}</button>`).join("")}
    </div>` : ""}
  </div>`;
}

/* ── chrome ──────────────────────────────────────────────────────────── */

function renderRail() {
  const rail = $("#rail");
  const tab = (id, icon, name, count, on) => `
    <button class="tab ${on ? "on" : ""}" data-topic="${id}" title="${name}">
      <span class="ic">${icon}</span><span class="nm">${name}</span>
      ${count !== null ? `<span class="cnt">${count}</span>` : ""}
    </button>`;
  const all = inLanguage().filter((x) => x.status !== "inbox").length;
  rail.innerHTML =
    tab("all", "\u{1F4D6}", "All", all, state.topic === "all" && !state.map) +
    (inboxCount() ? tab("inbox", "\u{1F4E5}", "Inbox", inboxCount(), state.topic === "inbox" && !state.map) : "") +
    /* A view of every word rather than a topic, so it sits with All and not among the topics. */
    `<button class="tab ${state.map ? "on" : ""}" data-map-open title="Map">
      <span class="ic">\u{1F5FA}\uFE0F</span><span class="nm">Map</span></button>` +
    '<div class="rail-sep"></div>' +
    TOPICS.map((t) => tab(t.key, t.icon, t.name, topicCount(t.key) || null, state.topic === t.key && !state.map)).join("");
}

function renderLangButton() {
  const l = langOf(state.lang);
  $("#langBtn").innerHTML = `<span class="flag">${l.flag}</span><span class="code">${l.code.toUpperCase()}</span>`;
  $("#langMenu").innerHTML =
    '<div class="label menu-label">Vocabulary language</div>' +
    LANGUAGES.map((x) => `<button data-lang="${x.code}" class="${x.code === state.lang ? "on" : ""}">
        <span>${x.flag}</span><span>${x.name}</span>
        <span class="cnt">${LEXEMES.filter((y) => y.language === x.code).length}</span>
      </button>`).join("");
}

/* ── list view ───────────────────────────────────────────────────────── */

function renderList() {
  const rows = visible();
  const q = state.query.trim();
  let title, icon, sub;
  if (q) {
    title = "Search"; icon = "\u{1F50D}";
    sub = `${rows.length} match${rows.length === 1 ? "" : "es"} for “${esc(q)}” in ${langOf(state.lang).name}`;
  } else if (state.topic === "inbox") {
    title = "Inbox"; icon = "\u{1F4E5}";
    sub = "Captured, processed, waiting for your review";
  } else if (state.topic === "all") {
    title = "All words"; icon = "\u{1F4D6}";
    sub = `${rows.length} in ${langOf(state.lang).name}`;
  } else {
    const t = topicOf(state.topic);
    title = t.name; icon = t.icon;
    sub = `${rows.length} word${rows.length === 1 ? "" : "s"} in ${langOf(state.lang).name}`;
  }

  // Only the Inbox tab itself, never a search that happens to turn up unreviewed words: those rows
  // are an answer to a question, not a pile to be emptied.
  const fileable = !q && state.topic === "inbox" ? rows : [];

  const sortBtn = (id, text) => `<button class="sort-btn ${state.sort === id ? "on" : ""}" data-sort="${id}">${text}</button>`;
  const strength = (x) => {
    const s = x.study ? Math.min(4, Math.max(1, Math.round(Math.log10(Math.max(x.study.stability, 1.1)) * 1.7 + 1))) : 0;
    return `<span class="strength" title="${x.study ? `stability ${x.study.stability} d · difficulty ${x.study.difficulty}` : "not scheduled yet"}">` +
      [1, 2, 3, 4].map((i) => `<i class="${i <= s ? "f" : ""}"></i>`).join("") + "</span>";
  };

  return `
    <div class="list-head">
      <div>
        <h1><span class="ic">${icon}</span>${esc(title)}</h1>
        <p class="label sub">${sub}</p>
      </div>
      <div class="sortbar">
        ${fileable.length ? `<button class="sort-btn" id="fileAllBtn">File all ${fileable.length}</button>` : ""}
        ${sortBtn("recent", "Recent")}${sortBtn("alpha", "A–Z")}${sortBtn("hard", "Hardest")}
      </div>
    </div>
    <div class="rows">
      ${rows.length ? rows.map((x) => { const on = isPicked(x.id); return swipeRow(`word:${x.id}`, `
        <button class="row${x.status === "inbox" ? " inbox" : ""}${on ? " picked" : ""}" data-open="${x.id}">
          <span class="plate">${x.emoji || "\u{1F4C4}"}${on ? `<span class="pick-badge" role="img" aria-label="Selected">${ICON.check}</span>` : ""}</span>
          <span>
            <span class="word">${esc(x.headword)}${x.reading ? `<span class="rdg">${esc(x.reading)}</span>` : ""}</span>
            <span class="gloss">${esc(shortGlossOf(x))}</span>
          </span>
          <span class="meta">
            ${fillingOf(x) ? '<span class="working-mark" role="img" aria-label="Still filling in" title="Still filling in"></span>' : ""}
            ${x.senses.length > 1 ? `<span class="senses">${x.senses.length} senses</span>` : ""}
            ${x.status === "inbox" ? '<span class="prov">unreviewed</span>' : strength(x)}
          </span>
        </button>`, [
          { label: on ? "Unselect" : "Select", menu: on ? "Remove from selection" : "Add to selection", tone: "pick", attrs: `data-pick="${x.id}"` },
          { label: "Delete", menu: "Delete this word", tone: "danger", attrs: `data-word-delete="${x.id}"`, sep: true }
        ]); }).join("")
      : q ? `<p class="ext-status none-yours">No words of yours match “${esc(q)}”.</p>`
          : '<p class="empty">Nothing here yet.</p>'}
    </div>
    ${renderExternal()}`;
}

/* ── article view ────────────────────────────────────────────────────────
   One article, two ways to read it. **Page** is the whole entry scrolled top to bottom, and is where
   the conversation lives, because an edit that reorders senses needs every sense in view. **Cards**
   is one thing at a time, swiped left and right, for glancing at a word on a phone. Both draw from
   the same record and neither has anything the other lacks except the ask dock.

   Everything that used to sit under a sentence as a badge — origin, model, "unapproved", the
   picture's style, where a clip starts — is gone from the reading surface. Nobody reads them while
   learning a word, and what little is worth keeping lives in Details. */

/* Plain words rather than a grammarian's abbreviations: "noun, feminine", not "n. · f.". */
const POS_WORD = { noun: "noun", verb: "verb", adj: "adjective", adv: "adverb", phrase: "phrase", idiom: "idiom", expression: "expression" };
const REGISTER_WORD = { colloquial: "informal", formal: "formal", slang: "slang", vulgar: "vulgar" };
const DIALECT_WORD = { "es-ES": "Spain", "es-MX": "Mexico", "es-AR": "Argentina", "en-GB": "British", "en-US": "American" };

function grammarWords(x) {
  const bits = [(POS_WORD[x.pos] || x.pos) + (x.gender ? `, ${x.gender}` : "")];
  if (x.register && x.register !== "neutral") bits.push(REGISTER_WORD[x.register] || x.register);
  if (x.dialect) bits.push(DIALECT_WORD[x.dialect] || x.dialect);
  return bits.join(" · ");
}

/* Where the word is filed, as a quiet line rather than a row of chips. */
function placeLine(x) {
  const status = x.status === "inbox" ? "Inbox" : x.status === "learned" ? "Learned" : null;
  const topics = x.topics.map((k) => topicOf(k).name).join(", ");
  return [status, topics].filter(Boolean).join(" — ");
}

/* A small listen button after a sentence. `always` keeps it visible where hovering is possible. */
function say(text, extra = "") {
  return `<button class="say${extra ? ` ${extra}` : ""}" data-say="${esc(strip(text))}" aria-label="Listen">${ICON.play}</button>`;
}
const sayTranslation = (text) => (state.sayTranslations ? say(text, "say-tr") : "");

/* A sentence with its listen button glued to the last word, so the button never wraps onto a line
   of its own. Left alone when the last word is inside markup, which only a painted proposal has. */
function spoken(html, button) {
  if (!button) return html;
  const tail = html.match(/(\S+)$/);
  if (!tail || /[<>]/.test(tail[1])) return html + button;
  return `${html.slice(0, tail.index)}<span class="say-tail">${tail[1]}${button}</span>`;
}

/* A video title is the loudest text a creator can write and the least useful thing on the page, so
   it is made quiet by rule rather than by taste: hashtags and emoji out, everything lower case. */
function quietTitle(s) {
  return String(s)
    .replace(/#[\p{L}\p{N}_]+/gu, " ")
    .replace(/[0-9#*]\u{FE0F}?\u{20E3}/gu, "")
    .replace(/\p{Extended_Pictographic}|\p{Regional_Indicator}|\p{Emoji_Presentation}|[\u{FE0F}\u{200D}\u{20E3}\u{E0020}-\u{E007F}\u{1F3FB}-\u{1F3FF}]/gu, "")
    .replace(/\s*[|•]\s*/g, " · ")
    .replace(/\s+/g, " ")
    .replace(/^[\s·:\-–—]+|[\s·:\-–—]+$/g, "")
    .toLowerCase();
}

const isClip = (e) => Boolean(e.clip);
const isOwn = (e) => e.origin === "attestation" || e.origin === "manual";

/* Written examples first, clips last: a clip is the least legible way to meet a sentence. */
function orderedExamples(s) {
  const items = s.examples.map((e, at) => ({ e, at }));
  return [...items.filter(({ e }) => !isClip(e)), ...items.filter(({ e }) => isClip(e))];
}

/* A sentence you supplied is shown once, in its sense. "Where you met it" keeps only the ones no
   example was drawn from. */
function looseAttestations(x) {
  const used = new Set(x.senses.flatMap((s) => s.examples.map((e) => e.sourceAttestationId).filter(Boolean)));
  return x.attestations.filter((a) => !a.id || !used.has(a.id));
}

/* A sense's own emoji and its domain, whichever it has: most real senses have an emoji and no domain,
   and showing the emoji only beside a domain left them as bare numbers. */
const senseName = (s) => [s.emoji, s.domain].filter(Boolean).join(" ");

function clipLine(e) {
  /* Calm, but plainly a thing to press: an outlined pill with a film icon, in ink rather than teal.
     The channel leads — it says what kind of speech this is, which is why you would open it — and
     the video's own title follows, quieter, and is what truncation eats first. The corner arrow is
     the one mark that says this opens something rather than captioning the sentence above it. */
  const channel = e.clip.channel ? e.clip.channel.toLowerCase() : "";
  const title = quietTitle(e.clip.title);
  const parts = [];
  if (channel) parts.push(`<span class="ch">${esc(channel)}</span>`);
  if (channel && title) parts.push(" · ");
  if (title) parts.push(`<span class="ti">${esc(title)}</span>`);
  return `
    <button class="clip-line" data-clip="1" aria-label="Play the clip">
      <span class="film">${ICON.film}</span><span class="src">${parts.join("") || "clip"}</span><span class="go">${ICON.open}</span>
    </button>`;
}

/* ── the server's work on a word ──────────────────────────────────────
   A word still being filled in carries `filling`. The application reads the same states from its
   job stream; here they are a fixture, overridable with `?fill=searching|none|failed|off`. */
function fillingOf(x) {
  const asked = new URLSearchParams(location.search).get("fill");
  if (!x.filling || asked === "off") return null;
  return asked ? { ...x.filling, clips: asked } : x.filling;
}

function progressStrip(x) {
  const filling = fillingOf(x);
  if (!filling) return "";
  if (filling.clips === "failed") {
    return `<div class="progress-strip failed" role="status"><span>Couldn't search recorded speech</span>`
      + '<span class="sep">·</span><button class="strip-action">Try again</button>'
      + '<button class="strip-dismiss" aria-label="Dismiss">×</button></div>';
  }
  const phases = filling.phases.filter(([text]) => filling.clips === "searching" || !text.startsWith("Finding"));
  return `<div class="progress-strip" role="status">${phases.map(([text, now], i) =>
    `${i ? '<span class="sep">·</span>' : ""}<span${now ? ' class="now"' : ""}>${esc(text)}</span>`).join("")}</div>`;
}

function clipSlot(s, i, x) {
  const filling = fillingOf(x);
  if (!filling || s.examples.some(isClip)) return "";
  if (filling.clips === "searching") {
    return `<div class="clip-slot" role="status" aria-label="Looking for a recorded example">
      <span class="clip-slot-play"></span><span class="clip-slot-bars"><span></span><span></span><span></span></span></div>`;
  }
  if (filling.clips === "none") return '<p class="clip-none">No recorded example</p>';
  if (filling.clips === "failed" && i === 0) {
    return '<p class="clip-none failed">Couldn\'t search recorded speech <span class="sep">·</span> <button class="strip-action">Try again</button></p>';
  }
  return "";
}

function pictureFrame(im) {
  /* `drawing` stands in for a picture the queue is drawing right now: the frame holds its place and
     says so, the same on the page and on a card. */
  return im.drawing ? `
    <figure class="sense-image">
      <button class="sense-image-frame is-pending is-busy" data-picture><span class="sense-image-empty">Drawing…</span></button>
    </figure>` : `
    <figure class="sense-image">
      <button class="sense-image-frame" data-picture aria-label="Open the picture"><img src="${im.src}" alt="" loading="lazy"></button>
    </figure>`;
}

function attestationBlock(a) {
  return `
    <div class="att${a.photo ? " has-photo" : ""}">
      ${a.photo ? `<button class="att-photo" data-photo="${esc(a.photo)}" aria-label="Open the photo"><img src="${a.photo}" alt=""></button>` : ""}
      <div class="att-text">
        <p class="t">${spoken(esc(a.text), say(a.text))}</p>
        ${a.translation ? `<p class="tr">${spoken(esc(a.translation), sayTranslation(a.translation))}</p>` : ""}
        <p class="src">
          ${a.sourceTitle ? (a.sourceUrl ? `<a href="${a.sourceUrl}">${esc(a.sourceTitle)}</a>` : `<span>${esc(a.sourceTitle)}</span>`) : ""}
          <span class="when">${esc(a.capturedAt)}</span>
        </p>
      </div>
    </div>`;
}

/* Which blocks a painted proposal touches. Position-based on purpose: this is a picture of the
   design, and the application computes the real thing from `diffDrafts`. */
function reviewMark(kind, index) {
  if (!state.review) return "";
  if (kind === "example" && index === 0) return " mark mark-add mark-current";
  if (kind === "example" && index === 1) return " mark mark-cut";
  if (kind === "example" && index === 2) return " mark mark-change";
  if (kind === "sense" && index === 0) return " mark mark-change";
  if (kind === "sense" && index === 1) return " mark mark-moved";
  if (kind === "note" && index === 0) return " mark mark-change";
  if (kind === "note" && index === 1) return " mark mark-cut";
  return "";
}

/* ── Page ── */

/* Every section folds on its own. Kept across re-renders per word, so opening Details stays open
   while a play button or the dock redraws the article. */
const folded = new Map();
const isFolded = (key, byDefault) => (folded.has(key) ? folded.get(key) : byDefault);

function section(key, byDefault, rail, body, extra = "") {
  const shut = isFolded(key, byDefault);
  return `
    <section class="sec${shut ? " folded" : ""}${extra}" data-fold="${esc(key)}">
      <div class="rail-l"><button class="inner sec-toggle" aria-expanded="${!shut}">
        <span class="caret">${ICON.caret}</span>${rail}
      </button></div>
      <div class="body">${body}</div>
    </section>`;
}

function exampleBlock(e, at) {
  const mark = reviewMark("example", at);
  const glyph = mark.includes("mark-add") ? "+" : mark.includes("mark-cut") ? "−" : mark ? "~" : "";
  /* The glyph is a direct child of the block and absolutely positioned — never inside the
     paragraph, which is what used to push a marked block's text right of its neighbours. */
  const text = mark.includes("mark-change")
    ? `${e.text.replace(/\.$/, "")} <span class="wd-del">un montón</span><span class="wd-ins">muchísimo</span>.`
    : e.text;
  return `
    <div class="ex${isOwn(e) ? " own" : ""}${isClip(e) ? " clip-ex" : ""}${mark}" data-record="${esc(e.id || "")}">
      ${glyph ? `<span class="mark-glyph">${glyph}</span>` : ""}
      <div class="ex-text">
        <p class="t">${spoken(text, say(e.text))}</p>
        ${e.translation ? `<p class="tr">${spoken(e.translation, sayTranslation(e.translation))}</p>` : ""}
        ${isOwn(e) ? '<span class="own-tag">your sentence</span>' : ""}
        ${e.note ? `<p class="tr ex-note">✎ ${esc(e.note)}</p>` : ""}
        ${isClip(e) ? clipLine(e) : ""}
      </div>
      <button class="ask-anchor" aria-label="Ask about this example">${ICON.ask}</button>
    </div>`;
}

function senseSection(s, i, x) {
  const mark = reviewMark("sense", i);
  const glossLine = (g) => `<div class="gloss-line"><span class="lg">${esc(g.lang)}</span><span class="tm">${g.terms.map((t) => `<b>${esc(t)}</b>`).join(" · ")}</span></div>`;
  const rail = `
    <span class="num">${state.review && mark
      ? `<span class="mark-glyph">${mark.includes("mark-moved") ? "↕" : "~"}</span>` : ""}${String(i + 1).padStart(2, "0")}</span>
    <span class="label">${senseName(s) ? esc(senseName(s)) : "Sense"}</span>
    ${state.review && mark.includes("mark-moved") ? '<span class="label mark-was">was 01</span>' : ""}`;
  const body = `
    <div class="sense-head">
      <p class="sense-def${state.review && mark.includes("mark-change") ? " field-change" : ""}">${spoken(esc(s.definition), say(s.definition))}</p>
      ${s.images.length ? "" : `<button class="ask-anchor picture-anchor" data-add-picture aria-label="Add a picture" title="Add a picture">${ICON.picture}</button>`}
      <button class="ask-anchor map-anchor" data-map-show="${esc(x.headword)}" data-map-order="${i}"
        aria-label="Show on the map" title="Show on the map">${ICON.map}</button>
      <button class="ask-anchor" aria-label="Ask about this meaning">${ICON.ask}</button>
    </div>
    <div class="glosses">${s.glosses.map(glossLine).join("")}</div>
    ${s.images.map(pictureFrame).join("")}
    ${orderedExamples(s).map(({ e, at }) => exampleBlock(e, at)).join("")}
    ${clipSlot(s, i, x)}`;
  return section(`${x.id}:sense:${i}`, false, rail, body, mark);
}

function detailsBody(x) {
  const models = [...new Set([
    ...x.senses.flatMap((s) => s.examples.map((e) => e.modelId)),
    x.imageModelId
  ].filter(Boolean))];
  const fact = (k, v) => `<div><dt>${k}</dt><dd>${v}</dd></div>`;
  return `
    <dl class="facts">
      ${fact("id", esc(x.id))}${fact("added", esc(x.createdAt))}${fact("edited", esc(x.editedAt))}${fact("rev", x.revision)}
      ${models.length ? `<div class="wide"><dt>made with</dt><dd>${models.map(esc).join(", ")}</dd></div>` : ""}
    </dl>
    ${x.study ? `
      <div class="stats">
        <div class="stat"><div class="label">Stability</div><div class="v">${x.study.stability}<small> d</small></div></div>
        <div class="stat"><div class="label">Difficulty</div><div class="v">${x.study.difficulty}<small>/10</small></div></div>
        <div class="stat"><div class="label">Retrievability</div><div class="v">${Math.round(x.study.retrievability * 100)}<small>%</small></div></div>
        <div class="stat"><div class="label">Reps · lapses</div><div class="v">${x.study.reps}<small> · ${x.study.lapses}</small></div></div>
        <div class="stat"><div class="label">Last review</div><div class="v" style="font-size:14px">${esc(x.study.lastReview)}</div></div>
      </div>` : ""}`;
}

const dictionaryBody = (x) =>
  `<p class="hint">Looked up in the dictionaries you have switched on, when this opens. Nothing is fetched in the prototype for «${esc(x.lemma)}».</p>`;

function notesList(x) {
  return `<ul class="notes">${x.notes.map((n, i) => {
    const mark = reviewMark("note", i);
    const glyph = mark.includes("mark-add") ? "+" : mark.includes("mark-cut") ? "−" : mark ? "~" : "";
    /* A reworded note is one change with the words that moved, not a delete beside an add. */
    const body = mark.includes("mark-change")
      ? `${n.replace(/\.$/, "")} <span class="wd-del">verb</span><span class="wd-ins">verbo</span>.`
      : n;
    return `<li class="${mark.replace(" mark ", "mark ").trim()}" data-note="${i}">${
      glyph ? `<span class="mark-glyph">${glyph}</span>` : ""}${body}</li>`;
  }).join("")}</ul>`;
}

function masthead(x) {
  const place = placeLine(x);
  /* Two lines beside the plate: the word with its play button, then how it sounds and what it is.
     Where it is filed trails that second line in small mono — it says something about the word, so
     it stays in view, but it should not cost a line of its own. */
  return `
    <div class="masthead">
      <div class="head-row">
        <div class="emoji-plate">${x.emoji || "\u{1F4C4}"}</div>
        <div class="head-text">
          <div class="head-line"><h1 class="headword">${esc(x.headword)}</h1>${say(x.headword, "always head")}</div>
          ${x.reading ? `<div class="reading">${esc(x.reading)}</div>` : ""}
          <div class="pron-row">
            ${x.ipa ? `<span class="ipa">${esc(x.ipa)}</span>` : ""}
            <span class="gram">${esc(grammarWords(x))}</span>
            ${place ? `<span class="place">${esc(place)}</span>` : ""}
          </div>
        </div>
      </div>
    </div>`;
}

/* ── the ask dock ─────────────────────────────────────────────────────
   `docs/features/article-chat.md` §7. Pinned to the bottom of the article pane and growing upward
   into a sheet; one component and one set of states at every width, because a side pane would cut
   the 780 px article column to about 400 px on the tablet this is mostly read on.

   Painted here at whichever detent `state.ask` names, the way the editor pane is painted rather
   than run: the prototype has no bundler and nothing here talks to a server. The application's
   `AskDock.tsx` is the same surface with the same classes. */
function renderAsk(x) {
  const at = state.ask || "dock";
  const thread = at === "dock" ? "" : `
    <header class="ask-head">
      <button class="ask-grab" aria-label="Expand the conversation">${ICON.chevron}</button>
      ${at === "full" ? `<span class="ask-subject"><span class="ask-emoji">${x.emoji || "📄"}</span>${esc(x.headword)}</span>` : ""}
      <span class="spacer"></span>
      <button class="link-btn">Clear</button>
      <button class="icon-btn" aria-label="Close the conversation">${ICON.close}</button>
    </header>
    <div class="ask-thread">
      <div class="ask-turn you"><span class="ask-who">you</span><p>How is this different from «el traje»?</p></div>
      <div class="ask-turn acervo">
        <span class="ask-who">${ICON.ask}</span>
        <p>${"«el traje» is any outfit or suit — a business suit, a regional costume. «el disfraz» is worn to be taken for someone else: carnival, theatre, a party. You already have «el traje» under Appearance."}</p>
      </div>
      <div class="ask-card">
        <div class="ask-card-head"><span class="ask-card-mark">✎</span>Adds the contrast with «el traje» to the notes.</div>
        <div class="ask-card-foot">
          <span class="label">1 change · notes</span>
          <span class="spacer"></span>
          <button class="tb-btn primary">Review</button>
        </div>
      </div>
      <div class="ask-followups">
        <button class="ask-followup">One more example</button>
        <button class="ask-followup">How do I remember it?</button>
      </div>
    </div>`;
  return `
    <section class="ask ask-${at}" aria-label="Conversation about ${esc(x.headword)}">
      ${thread}
      ${state.askFocus ? `<div class="ask-chips">
        <button type="button" class="ask-chip">${esc(state.askFocus)}${ICON.close}</button>
      </div>` : ""}
      <form class="ask-bar" onsubmit="return false">
        <span class="ask-mark">${ICON.ask}</span>
        <textarea class="ask-input" rows="1" aria-label="Ask about ${esc(x.headword)}"
          placeholder="Ask about ${esc(x.headword)}…"></textarea>
        <button type="submit" class="ask-send" aria-label="Ask">${ICON.send}</button>
      </form>
    </section>`;
}

function renderArticle(x, opts) {
  const meta = !opts || opts.meta !== false;
  const review = meta && state.review ? `
    <div class="review-bar">
      <span class="review-mark">✎</span>
      <span class="label">3 changes<span class="review-long"> proposed</span></span>
      <div class="review-nav">
        <button aria-label="Previous change" disabled>${ICON.chevron}</button>
        <span class="review-at">1/3</span>
        <button aria-label="Next change"><span class="review-down">${ICON.chevron}</span></button>
      </div>
      <span class="spacer"></span>
      <button class="tb-btn" id="discardBtn">Discard</button>
      <button class="tb-btn primary" id="saveProposal">Save<span class="review-long"> changes</span></button>
    </div>` : "";
  const key = (part) => `${x.id}:${part}`;
  const met = looseAttestations(x);

  /* Notes, then where you met it, then the two things you open on purpose. */
  return `
    ${review}
    ${masthead(x)}
    ${x.senses.map((s, i) => senseSection(s, i, x)).join("")}
    ${x.notes.length ? section(key("notes"), false,
      '<span class="num">✎</span><span class="label">Notes</span>', notesList(x)) : ""}
    ${met.length ? section(key("met"), false,
      '<span class="num">✳</span><span class="label">Where you met it</span>', met.map(attestationBlock).join("")) : ""}
    ${meta ? section(key("dict"), true,
      `<span class="num">${ICON.book}</span><span class="label">Other dictionaries</span>`, dictionaryBody(x)) : ""}
    ${meta ? section(key("details"), true,
      `<span class="num">${ICON.info}</span><span class="label">Details</span>`, detailsBody(x)) : ""}`;
}

/* ── Cards ───────────────────────────────────────────────────────────────
   One sense at a time, and inside a sense one sentence at a time. The definition and its gloss stay
   at the top of every card of their sense, because a sentence is only worth reading against the
   meaning it illustrates. The picture is the part that gives way when a card is short of room; if a
   card still cannot fit — a very long sentence — that card alone scrolls, and nothing forbids it. */

function cardExample(e, quoted = false) {
  return `
    <div class="card-ex${isOwn(e) ? " own" : ""}${isClip(e) ? " clip-ex" : ""}">
      <p class="t">${quoted ? '<span class="quote-mark" aria-hidden="true">“</span>' : ""}${spoken(e.text,
        (quoted ? '<span class="quote-mark" aria-hidden="true">”</span>' : "") + say(e.text))}</p>
      ${e.translation ? `<p class="tr">${spoken(e.translation, sayTranslation(e.translation))}</p>` : ""}
      ${isOwn(e) ? '<span class="own-tag">your sentence</span>' : ""}
      ${isClip(e) ? clipLine(e) : ""}
    </div>`;
}

function cardsFor(x) {
  const cards = [];
  x.senses.forEach((s, i) => {
    const items = orderedExamples(s);
    const picture = s.images[0] || null;
    const anchored = picture && Number.isInteger(picture.anchor) ? picture.anchor : null;
    /* A picture goes on the card of the sentence it was drawn from — a clip's included, so a clip
       and its picture share a card. A picture drawn from the sense alone opens the sense. */
    const spotOn = (c) => (anchored === null ? c === 0 : Boolean(items[c]) && items[c].at === anchored);
    /* A card is for reading: the picture if it exists, the page's frame while one is being drawn,
       and otherwise nothing — pictures are asked for on the page. */
    const visualAt = (c) => !spotOn(c) ? ""
      : picture && picture.drawing ? `<div class="card-frame">${pictureFrame(picture)}</div>`
      : picture ? `<div class="card-pic" role="img"><img src="${picture.src}" alt=""></div>`
      : "";
    const glossLines = s.glosses.map((g) =>
      `<p class="card-gloss"><span class="lg">${esc(g.lang)}</span>${g.terms.map(esc).join(" · ")}</p>`).join("");
    const count = Math.max(items.length, 1);
    for (let c = 0; c < count; c++) {
      const item = items[c];
      const visual = visualAt(c);
      /* Only words: an epigraph between two ivy leaves. No sentence either: the leaves alone. */
      const quoted = !visual && Boolean(item);
      const bare = !visual && !item;
      cards.push({
        group: `s${i}`,
        // A domain names a sense well enough alone; otherwise its emoji and its number, as the map shows it.
      chip: s.domain ? esc(senseName(s)) : [s.emoji, String(i + 1)].filter(Boolean).join(" "),
        html: `
          <div class="card-sense">
            <p class="card-def">${spoken(esc(s.definition), say(s.definition))}</p>
            ${glossLines}
          </div>
          <div class="card-main${quoted ? " quoted" : ""}${bare ? " bare" : ""}">
            ${visual}
            ${quoted ? `<span class="card-ornament above" aria-hidden="true">${ICON.hedera}</span>` : ""}
            ${item ? cardExample(item.e, quoted) : ""}
            ${quoted ? `<span class="card-ornament below" aria-hidden="true">${ICON.hedera}</span>` : ""}
            ${bare ? `<span class="card-ornament pair" aria-hidden="true">${ICON.hedera}${ICON.hedera}</span>` : ""}
          </div>
          ${count > 1 ? `<span class="card-pos">${c + 1} / ${count}</span>` : ""}`
      });
    }
  });
  if (x.notes.length) cards.push({ group: "notes", chip: "✎ Notes",
    html: `<h2 class="card-title">Notes</h2><div class="card-main top">${notesList(x)}</div>` });
  const met = looseAttestations(x);
  if (met.length) cards.push({ group: "met", chip: "✳ Met it",
    html: `<h2 class="card-title">Where you met it</h2><div class="card-main top">${met.map(attestationBlock).join("")}</div>` });
  cards.push({ group: "dict", chip: "Dictionaries",
    html: `<h2 class="card-title">Other dictionaries</h2><div class="card-main top">${dictionaryBody(x)}</div>` });
  cards.push({ group: "details", chip: "Details",
    html: `<h2 class="card-title">Details</h2><div class="card-main top">${detailsBody(x)}</div>` });
  return cards;
}

function renderCards(x) {
  const cards = cardsFor(x);
  state.card = Math.max(0, Math.min(state.card, cards.length - 1));
  const groups = [...new Map(cards.map((c, i) => [c.group, { at: cards.findIndex((d) => d.group === c.group), chip: c.chip }])).entries()];
  const current = cards[state.card].group;
  return `
    <div class="cards">
      <header class="cards-head">
        <div class="cards-word">
          <span class="cw-emoji">${x.emoji || "\u{1F4C4}"}</span>
          <div class="cw-line" data-length="${x.headword.length > 24 ? "long" : x.headword.length > 14 ? "mid" : "short"}"><h1 class="cw-headword">${esc(x.headword)}</h1>${say(x.headword, "always head")}</div>
          ${x.reading ? `<span class="reading">${esc(x.reading)}</span>` : ""}
        </div>
        <nav class="cards-nav" aria-label="Senses and sections">
          ${groups.map(([group, g], index) => `${!group.startsWith("s") && index > 0 && groups[index - 1][0].startsWith("s") ? '<span class="cards-sep" aria-hidden="true"></span>' : ""}<button class="cards-chip${group === current ? " on" : ""}${group.startsWith("s") ? "" : " aside"}"
            data-go="${g.at}" data-group="${group}">${g.chip}</button>`).join("")}
        </nav>
      </header>
      <div class="cards-stage">
        <div class="cards-track" id="cardsTrack">
          ${cards.map((c, i) => `<article class="card" data-group="${c.group}" aria-label="Card ${i + 1} of ${cards.length}">${c.html}</article>`).join("")}
        </div>
      </div>
      <div class="cards-edges">
        <button class="cards-edge prev" data-step="-1" aria-label="Previous card">${ICON.back}</button>
        <button class="cards-edge next" data-step="1" aria-label="Next card">${ICON.back}</button>
      </div>
    </div>`;
}

/* Arrows beside the column only where the margin really has room for them, measured against `.main`,
   which clips; otherwise a pair at the foot of the card. */
function placeEdges() {
  const cards = $(".cards"), main = $("#main");
  if (!cards || !main) return;
  const inner = cards.getBoundingClientRect(), outer = main.getBoundingClientRect();
  cards.classList.toggle("edges-beside", inner.left - outer.left >= 100 && outer.right - inner.right >= 100);
}
window.addEventListener("resize", placeEdges);

function wireCards() {
  const track = $("#cardsTrack");
  if (!track) return;
  placeEdges();
  track.scrollLeft = state.card * track.clientWidth;
  let frame = 0;
  track.addEventListener("scroll", () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => syncCard(track));
  });
  syncCard(track);
}

function syncCard(track) {
  const at = Math.round(track.scrollLeft / Math.max(track.clientWidth, 1));
  const card = track.children[at];
  if (!card) return;
  state.card = at;
  const nav = $(".cards-nav");
  nav.querySelectorAll(".cards-chip").forEach((chip) => {
    const on = chip.dataset.group === card.dataset.group;
    chip.classList.toggle("on", on);
    if (on) nav.scrollTo({ left: chip.offsetLeft - (nav.clientWidth - chip.offsetWidth) / 2, behavior: "smooth" });
  });
  $(".cards-edge.prev").disabled = at === 0;
  $(".cards-edge.next").disabled = at === track.children.length - 1;
}

/* A story is the same deck: a snapping track that follows the finger, with the counter and the arrows
   kept in step with it. Everything is redrawn on a reveal, so where the reader was is put back. */
function wireStories() {
  const track = $("#storyTrack");
  if (!track) return;
  placeEdges();
  track.scrollLeft = state.storyAt * track.clientWidth;
  let frame = 0;
  track.addEventListener("scroll", () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => syncStory(track));
  });
  syncStory(track);
}

function syncStory(track) {
  const at = Math.round(track.scrollLeft / Math.max(track.clientWidth, 1));
  state.storyAt = at;
  $(".story-bar-count").textContent = `${at + 1} / ${track.children.length}`;
  $(".cards-edge.prev").disabled = at === 0;
  $(".cards-edge.next").disabled = at === track.children.length - 1;
}

function goStory(at) {
  const track = $("#storyTrack");
  if (!track) return;
  const to = Math.max(0, Math.min(at, track.children.length - 1));
  track.scrollTo({ left: to * track.clientWidth, behavior: "smooth" });
}

/* The words of a story on one line: as many whole words as fit, then `\u00b7 \u2026` — `FitWords` in the
   application. Each word, the separator and the ellipsis are measured once in a hidden copy that
   inherits the line's font, and the line is set again whenever the window changes size. */
function fitStoryWords() {
  document.querySelectorAll(".story-words[data-words]").forEach((line) => {
    const words = line.dataset.words.split("|");
    const text = line.querySelector(".fit-text");
    let ruler = line.querySelector(".fit-ruler");
    if (!ruler) {
      ruler = document.createElement("span");
      ruler.className = "fit-ruler";
      ruler.setAttribute("aria-hidden", "true");
      ruler.innerHTML = [...words, " \u00b7 ", "\u2026"].map((piece) => `<span>${esc(piece)}</span>`).join("");
      line.appendChild(ruler);
    }
    const widths = [...ruler.children].map((one) => one.getBoundingClientRect().width);
    const [separator, ellipsis] = widths.slice(words.length);
    const across = (n) => widths.slice(0, n).reduce((sum, w) => sum + w, 0) + Math.max(n - 1, 0) * separator;
    let shown = words.length;
    if (across(shown) > line.clientWidth) {
      shown = 1;
      for (let n = words.length - 1; n >= 1; n -= 1) {
        if (across(n) + separator + ellipsis <= line.clientWidth) { shown = n; break; }
      }
    }
    text.textContent = words.slice(0, shown).join(" \u00b7 ") + (shown < words.length ? " \u00b7 \u2026" : "");
  });
}
window.addEventListener("resize", fitStoryWords);

function goCard(at) {
  const track = $("#cardsTrack");
  if (!track) return;
  const to = Math.max(0, Math.min(at, track.children.length - 1));
  track.scrollTo({ left: to * track.clientWidth, behavior: "smooth" });
}

/* Cards is the default where a word is glanced at — a phone, a tablet, anything without hover — and
   Page where there is a mouse. Settings will own this; here it follows the preview frame. */
function currentView() {
  if (state.view) return state.view;
  const touch = document.body.classList.contains("phone") || document.body.classList.contains("tablet")
    || window.matchMedia("(hover: none)").matches;
  return touch ? "cards" : "page";
}

/* ── YAML projection ─────────────────────────────────────────────────── */

function yamlFor(x) {
  const q = (v) => {
    if (v === null || v === undefined) return "null";
    const s = String(v);
    return /^[\w .,;:’'ºª/()-]+$/u.test(s) && !/^(true|false|null|yes|no)$/i.test(s) && !/^[\d.]+$/.test(s) && !s.includes(": ")
      ? s : JSON.stringify(s);
  };
  const L = [];
  L.push(`# ${x.headword} — ${langOf(x.language).name}`);
  L.push(`id: ${x.id}`);
  L.push(`language: ${x.language}`);
  L.push(`headword: ${q(x.headword)}`);
  L.push(`lemma: ${q(x.lemma)}`);
  if (x.reading) L.push(`reading: ${q(x.reading)}`);
  L.push(`pos: ${x.pos}`);
  if (x.gender) L.push(`gender: ${x.gender}`);
  L.push(`register: ${x.register || "null"}`);
  if (x.dialect) L.push(`dialect: ${x.dialect}`);
  L.push(`emoji: ${q(x.emoji)}`);
  L.push(`status: ${x.status}`);
  L.push(`topics: [${x.topics.join(", ")}]`);
  L.push(`shortGloss: ${x.shortGloss ? q(x.shortGloss) : "null            # null = derived from sense 1"}`);
  if (x.notes.length) {
    L.push("notes:");
    x.notes.forEach((n) => L.push(`  - ${q(strip(n))}`));
  } else L.push("notes: []");
  L.push("senses:");
  x.senses.forEach((s, i) => {
    L.push(`  - order: ${i}`);
    L.push(`    definition: ${q(s.definition)}`);
    L.push(`    definitionLang: ${s.definitionLang}`);
    if (s.domain) L.push(`    domain: ${s.domain}`);
    if (s.emoji) L.push(`    emoji: ${q(s.emoji)}`);
    L.push("    glosses:");
    s.glosses.forEach((g) => L.push(`      - { lang: ${g.lang}, terms: [${g.terms.map(q).join(", ")}] }`));
    L.push("    examples:");
    s.examples.forEach((e) => {
      L.push(`      - text: ${q(strip(e.text))}`);
      if (e.translation) L.push(`        translation: ${q(strip(e.translation))}`);
      L.push(`        origin: ${e.origin}`);
      if (e.modelId) L.push(`        modelId: ${e.modelId}`);
    });
  });
  if (x.attestations.length) {
    L.push("attestations:");
    x.attestations.forEach((a) => {
      L.push(`  - text: ${q(a.text)}          # verbatim, never rewritten`);
      if (a.translation) L.push(`    translation: ${q(a.translation)}`);
      L.push(`    sourceKind: ${a.sourceKind}`);
      if (a.sourceTitle) L.push(`    sourceTitle: ${q(a.sourceTitle)}`);
      if (a.sourceUrl) L.push(`    sourceUrl: ${a.sourceUrl}`);
      L.push(`    capturedAt: ${q(a.capturedAt)}`);
    });
  }
  return L.join("\n");
}

const YAML_TEMPLATE = `# New entry — fill in what you know, leave the rest.
language: es
headword: ""
lemma: ""
pos: noun            # noun verb adj adv phrase idiom expression
gender: null         # masculine feminine — Spanish nouns only
register: neutral    # neutral formal colloquial slang vulgar
emoji: ""
status: inbox
topics: []           # e.g. [food, travel]
shortGloss: null     # null = derived from the first gloss below
notes: []
senses:
  - order: 0
    definition: ""             # in the target language
    definitionLang: es
    glosses:
      - { lang: en, terms: [""] }
    examples:
      - text: ""
        translation: ""
        origin: manual
attestations: []     # the sentence you actually met it in, verbatim
`;

function highlight(yaml) {
  return esc(yaml)
    .replace(/(#.*)$/gm, '<span class="y-com">$1</span>')
    .replace(/^(\s*)(-?\s*)([A-Za-z_][\w]*)(:)/gm, '$1<span class="y-dash">$2</span><span class="y-key">$3</span>$4')
    .replace(/(:\s)(&quot;[^&]*?&quot;)/g, '$1<span class="y-str">$2</span>')
    .replace(/(:\s)(-?\d+(?:\.\d+)?)$/gm, '$1<span class="y-num">$2</span>');
}


function renderYaml(x) {
  const yaml = yamlFor(x);
  return `
    <div class="code-wrap">
      <div class="code-head">
        <span class="label">${esc(x.headword)}.yaml</span>
        <span class="spacer"></span>
        <span class="label">read-only — press Edit to change</span>
      </div>
      ${editorSurface("view", yaml)}
    </div>`;
}

/* Set in Settings in the application; here they are prototype switches so both looks can be seen.
   Wrapping is the default: these documents are mostly prose, and a definition running off the right
   edge could previously be neither read nor scrolled to. */
let editorWrap = true;
let editorNumbers = false;

/* The application edits with CodeMirror, which needs a bundler this prototype deliberately does not
   have. So this is a *picture* of that editor — the same palette, the same mono measure, the same
   gutter — and not an editable one. Typing is the one thing you cannot try here; everything the
   prototype exists to show, you can. */
function editorSurface(id, text) {
  const lines = text.split("\n");
  return `
    <div class="code-scroll${editorWrap ? " wrap" : ""}${editorNumbers ? " numbered" : ""}" id="${id}Surface">
      <div class="cm-mock">
        ${editorNumbers ? `<div class="cm-mock-gutter">${lines.map((_, i) => `<span>${i + 1}</span>`).join("")}</div>` : ""}
        <div class="cm-mock-content">${lines.map((line) => `<div class="cm-mock-line">${highlight(line) || "&nbsp;"}</div>`).join("")}</div>
      </div>
    </div>`;
}

/* keeps the gutter, the highlight layer and the textarea in lockstep */
/* Nothing to keep in step: the surface is a picture, so it reports its own text and no more. */
function wireSurface(id) {
  const surface = document.getElementById(`${id}Surface`);
  return { get value() { return [...surface.querySelectorAll(".cm-mock-line")].map((n) => n.textContent).join("\n"); } };
}

function renderEdit(x) {
  const yaml = yamlFor(x);
  return `
    <section class="composer" aria-label="Edit ${esc(x.headword)}">
      <div class="composer-head">
        <h2>${esc(x.headword)}</h2>
        <span class="label">${esc(x.headword)}.yaml</span>
        <span class="spacer"></span>
        <button class="icon-btn" id="closeEdit" aria-label="Close">${ICON.close}</button>
      </div>
      <div class="composer-body fill">
        <div class="code-wrap">${editorSurface("edit", yaml)}</div>
      </div>
      <div class="composer-actions">
        <div id="validation"></div>
        <div class="composer-buttons">
          <span class="spacer"></span>
          <button class="tb-btn" id="cancelEdit">Cancel</button>
          <button class="tb-btn primary" id="saveEdit">Save</button>
        </div>
      </div>
    </section>`;
}

/* ── validation stub ─────────────────────────────────────────────────── */

function validate(text) {
  const problems = [];
  const lines = text.split("\n");
  const has = (k) => new RegExp(`^${k}:`, "m").test(text);
  ["language", "headword", "pos", "senses"].forEach((k) => { if (!has(k)) problems.push({ line: null, msg: `required key <code>${k}</code> is missing` }); });
  const hw = text.match(/^headword:\s*(.*)$/m);
  if (hw && /^(""|''|null)?\s*(#.*)?$/.test(hw[1].trim())) problems.push({ line: lines.findIndex((l) => l.startsWith("headword:")) + 1, msg: "<code>headword</code> is empty" });
  const pos = text.match(/^pos:\s*([\w-]+)/m);
  if (pos && !["noun", "verb", "adj", "adv", "phrase", "idiom", "expression"].includes(pos[1]))
    problems.push({ line: lines.findIndex((l) => l.startsWith("pos:")) + 1, msg: `<code>${esc(pos[1])}</code> is not a valid part of speech` });
  lines.forEach((l, i) => { if (/\t/.test(l)) problems.push({ line: i + 1, msg: "tab character — YAML needs spaces" }); });
  const def = text.match(/definition:\s*(.*)$/m);
  if (def && /^(""|''|)\s*(#.*)?$/.test(def[1].trim())) problems.push({ line: lines.findIndex((l) => /definition:/.test(l)) + 1, msg: "the first sense has an empty <code>definition</code>" });
  return problems;
}

function showValidation(target, problems) {
  const box = $(target);
  if (!box) return;
  box.innerHTML = problems.length
    ? `<div class="validation bad"><b>${problems.length} problem${problems.length === 1 ? "" : "s"} — nothing was saved</b>
        <ul>${problems.map((p) => `<li>${p.line ? `line ${p.line}: ` : ""}${p.msg}</li>`).join("")}</ul></div>`
    : '<div class="validation ok"><b>Valid.</b> The entry matches the Acervo schema.</div>';
  return problems.length === 0;
}

/* ── add sheet ───────────────────────────────────────────────────────── */

let addTab = "capture";
/* What the last Process produced. Null until something has been proposed — the Article tab has
   nothing to render before that, and says so rather than showing an empty entry. */
let addDraft = null;

/* The server reports on health what it builds entries with, and whether it can. In the application
   that is a fetch; here it is `?capture=off`, so the refusal can be seen. Off is not a mode anyone
   chooses — it is a provider whose key is missing — and the point of drawing it is that the button
   is dead *with a reason* rather than live and failing when it is finally pressed. */
let captureBlocked = null;

/* Photo capture (docs/features/photo-capture.md), drawn on the one photo the prototype has. Never
   where Add opens: the camera turns on only when asked, and here nothing turns on at all — "Take a
   photo" and "Choose an image" both land on the fixture, already read. `?add=photo&photo=read`
   opens there. */
let photoStage = "idle";
let photoKeep = true;
let photoSource = "book";
/* The camera case: a square photo, exactly as the square viewfinder framed it. */
const PHOTO = {
  src: "img/met-photo-square.jpg",
  sentence: "Esta gigantesca operación, llevada a cabo en el mayor secreto, había sido ordenada por el rey de Francia Felipe IV el Hermoso y dirigida por su consejero Guillermo de Nogaret.",
  headword: "llevar a cabo",
  gloss: "to carry out",
  /* Where "llevada a cabo" and its sentence are on the page, in the photo's own 0–1 coordinates —
     what the server's reading gives the interface to hit-test and draw. */
  words: [[[0.205, 0.267], [0.412, 0.267], [0.412, 0.311], [0.205, 0.311]]],
  bands: [
    [[0.664, 0.217], [0.94, 0.217], [0.94, 0.262], [0.664, 0.262]],
    [[0.069, 0.267], [0.94, 0.267], [0.94, 0.311], [0.069, 0.311]],
    [[0.069, 0.317], [0.94, 0.317], [0.94, 0.362], [0.069, 0.362]],
    [[0.069, 0.366], [0.475, 0.366], [0.475, 0.41], [0.069, 0.41]]
  ],
  uncertain: []
};
/* The chosen-image case: taller than the square, so it fills the width and scrolls inside it. The
   blurred word at its foot is marked as uncertain rather than hidden. */
const SCREEN = {
  ...PHOTO,
  src: "img/met-photo.jpg",
  words: [[[0.205, 0.388], [0.412, 0.388], [0.412, 0.421], [0.205, 0.421]]],
  bands: [
    [[0.664, 0.35], [0.94, 0.35], [0.94, 0.384], [0.664, 0.384]],
    [[0.069, 0.388], [0.94, 0.388], [0.94, 0.421], [0.069, 0.421]],
    [[0.069, 0.425], [0.94, 0.425], [0.94, 0.459], [0.069, 0.459]],
    [[0.069, 0.462], [0.475, 0.462], [0.475, 0.495], [0.069, 0.495]]
  ],
  uncertain: [[[0.62, 0.955], [0.8, 0.955], [0.8, 0.985], [0.62, 0.985]]]
};
const points = (polygon) => polygon.map(([x, y]) => `${x},${y}`).join(" ");

function photoOverlay(regions) {
  return `<svg viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
    ${(regions.uncertain || []).map((p) => `<polygon class="photo-uncertain" points="${points(p)}"/>`).join("")}
    ${regions.bands.map((p) => `<polygon class="photo-sentence" points="${points(p)}"/>`).join("")}
    ${regions.words.map((p) => `<polygon class="photo-word" points="${points(p)}"/>`).join("")}
  </svg>`;
}

function renderPhotoTab() {
  if (photoStage === "idle") return `
      <div class="composer-body">
        <div class="photo-start">
          <div class="photo-start-buttons">
            <button class="tb-btn primary" id="photoTake">Take a photo</button>
            <button class="tb-btn" id="photoChoose">Choose an image</button>
          </div>
          <p class="hint">Or paste or drop a screenshot here. The whole picture is read, and every word on it can be tapped. The camera only turns on when you ask it to.</p>
        </div>
      </div>
      <div class="composer-actions"><div class="composer-buttons"><span class="spacer"></span>
        <button class="tb-btn primary" disabled>Add</button></div></div>`;
  const shown = photoStage === "screenshot" ? SCREEN : PHOTO;
  const chips = [["book", "Book"], ["sign", "Sign"], ["web", "Screen"], ["unknown", "Other"]]
    .map(([kind, label]) => `<button class="cards-chip${photoSource === kind ? " on" : ""}" data-photo-source="${kind}" aria-pressed="${photoSource === kind}">${label}</button>`).join("");
  return `
      <div class="composer-body">
        <div class="photo-window" id="photoWindow"><div class="photo-square" id="photoSquare"><div class="photo-frame">
          <img src="${shown.src}" alt="The photo being read" draggable="false">
          ${photoOverlay({ words: shown.words, bands: shown.bands, uncertain: shown.uncertain })}
        </div></div></div>
        ${photoStage === "screenshot" ? `<p class="hint photo-scroll-hint" id="photoHint">Swipe up or down to see the rest. The square on screen is what is kept.</p>` : ""}
        <div class="photo-sheet">
          <div class="photo-meaning" aria-live="polite"><strong lang="es">${PHOTO.headword}</strong><span> — ${PHOTO.gloss}</span></div>
          <label class="label" for="photoSentence">The sentence, as it will be kept</label>
          <textarea id="photoSentence" class="capture-area photo-sentence-text" lang="es" rows="3">${PHOTO.sentence}</textarea>
          <div class="photo-options">
            <div class="photo-sources" role="group" aria-label="Where you met it">${chips}</div>
            <label class="config-switch">
              <input type="checkbox" id="photoKeep" ${photoKeep ? "checked" : ""}>
              <span><strong>Keep the photo</strong><span>With the sentence, so you can see where on the page you met the word.</span></span>
            </label>
          </div>
        </div>
      </div>
      <div class="composer-actions"><div class="composer-buttons">
        <button class="tb-btn" id="photoAnother">Another photo</button>
        <span class="spacer"></span>
        <button class="tb-btn primary" id="photoAdd">Add</button>
      </div></div>`;
}

function renderSheet() {
  const host = $("#composer");
  host.innerHTML = `
    <section class="composer" aria-label="Add a word">
      <div class="composer-head">
        <h2>Add<span class="head-rest"> a word</span></h2>
        <span class="spacer"></span>
        <div class="seg">
          <button data-tab="capture" class="${addTab === "capture" ? "on" : ""}">Text</button>
          <button data-tab="photo" class="${addTab === "photo" ? "on" : ""}">Photo</button>
          <button data-tab="article" class="${addTab === "article" ? "on" : ""}">Article</button>
          <button data-tab="yaml" class="${addTab === "yaml" ? "on" : ""}">YAML</button>
        </div>
        <button class="icon-btn" id="closeSheet" aria-label="Close">${ICON.close}</button>
      </div>
        ${addTab === "capture" ? `
      <div class="composer-body">
          <label class="label" for="captureText">Paste a word, or the sentence you met it in</label>
          <textarea class="capture-area" id="captureText" style="margin-top:8px" placeholder="Se pican las verduras en dados de un centímetro y se reservan."></textarea>

          <label class="label" for="captureWord" style="margin-top:14px">Which word? <span class="opt">optional</span></label>
          <input class="capture-word" id="captureWord" placeholder="picar">

          <p class="hint">Share the whole sentence — the word is picked out for you unless you name it above, and the sentence is kept as the place you met it. The entry is built for review and lands in <b>Inbox</b>. Nothing is generated in this prototype.</p>

          <details class="fold capture-fold">
            <summary><span class="caret">${ICON.caret}</span><span class="label">Where it came from, and what to ask for</span></summary>
            <div class="fold-body capture-details">
              <label class="label" for="captureUrl">Source link</label>
              <input id="captureUrl" placeholder="https://example.com/receta">
              <label class="label" for="captureTitle">Where it came from</label>
              <input id="captureTitle" placeholder="Receta — pisto manchego">
              <label class="label" for="captureNote">Anything to ask the generator</label>
              <input id="captureNote" placeholder="contrast it with picante">
            </div>
          </details>
      </div>
      <div class="composer-actions">
        ${captureBlocked ? `<div class="validation bad" role="alert">
          <b>This server cannot build entries right now.</b>
          <span>It is set to ${captureBlocked.provider} with the model ${captureBlocked.model},
            and ${captureBlocked.reason}. You can still write the entry yourself.</span>
        </div>` : ""}
        <div class="composer-buttons">
          <span class="spacer"></span>
          <button class="tb-btn" id="switchYaml">Write YAML instead</button>
          <button class="tb-btn primary" id="processBtn" ${captureBlocked ? "disabled" : ""}>Process</button>
        </div>
      </div>`
        : addTab === "photo" ? renderPhotoTab()
        : addTab === "article" ? `
      <div class="composer-body">
        ${addDraft
          ? `<div class="article-preview">${renderArticle(addDraft, { meta: false })}</div>`
          : `<p class="empty">Nothing to preview yet — process a capture, or write the document yourself.</p>`}
      </div>
      <div class="composer-actions">
        <div class="composer-buttons">
          <span class="spacer"></span>
          <button class="tb-btn" id="closeSheet2">Cancel</button>
          <button class="tb-btn" id="switchYaml">Edit YAML</button>
          <button class="tb-btn primary" id="saveDraft" ${addDraft ? "" : "disabled"}>Save</button>
        </div>
      </div>`
        : `
      <div class="composer-body fill">
        <div class="code-wrap">
          <div class="code-head"><span class="label">new-entry.yaml</span></div>
          ${editorSurface("new", YAML_TEMPLATE)}
        </div>
      </div>
      <div class="composer-actions">
        <div id="newValidation"></div>
        <div class="composer-buttons">
          <span class="spacer"></span>
          <button class="tb-btn" id="closeSheet2">Cancel</button>
          <button class="tb-btn primary" id="saveNew">Validate &amp; save</button>
        </div>
      </div>`}
    </section>`;
  wireSheet();
}

/* The photo an attestation kept, opened whole with the word and its sentence drawn again —
   `AttestationPhoto.tsx` `PhotoViewer`. */
function openPhotoViewer(src) {
  document.body.insertAdjacentHTML("beforeend", `<div class="modal-backdrop" id="photoViewerBackdrop">
    <section class="settings photo-viewer" role="dialog" aria-modal="true" aria-labelledby="photo-viewer-title">
      <header><h2 id="photo-viewer-title">Where you met it</h2>
        <button class="close" id="photoViewerClose" aria-label="Close">×</button></header>
      <div class="settings-body"><div class="photo-window"><div class="photo-square"><div class="photo-frame">
        <img src="${esc(src)}" alt="The photo this word was captured from">
        ${src === PHOTO.src ? photoOverlay({ words: PHOTO.words, bands: PHOTO.bands }) : ""}
      </div></div></div></div>
    </section></div>`);
}

function openSheet(tab) { addTab = tab || "capture"; addDraft = null; state.loops = false; state.map = false; state.add = true; render(); }
function closeSheet()   { state.add = false; $("#composer").innerHTML = ""; render(); }

/* ── toast ───────────────────────────────────────────────────────────── */

let toastTimer;
/* One optional action, as the application's toast has: Undo is the only thing that uses it. */
function toast(msg, action) {
  const t = $("#toast");
  t.textContent = msg; t.classList.add("show");
  if (action) {
    const b = el(`<button class="toast-action">${esc(action.label)}</button>`);
    b.onclick = () => { t.classList.remove("show"); action.run(); };
    t.appendChild(b);
  }
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), action ? 7000 : 2200);
}

/* ── loops ────────────────────────────────────────────────────────────────
   A loop is a rendered track over a handful of your words. The surface is an ordinary music
   player — a seekable line with a tick per word, elapsed and total, the three transport buttons,
   and two switches: play it again, and go on to the next one. The words stand where the artwork or
   the lyrics would.

   Where the lyrics would be is every line the loop says, as cards: one per group of lines, as the
   generator grouped them — a word and its translation, an example and what it means, a remark.

   THE ONE RULE THAT IS NOT A MUSIC PLAYER'S: within a card, nothing after its first line is drawn
   before it has been said — a translation, a quiz's answer, an example's meaning. A short bar stands
   where the line will be. The reveal is a pure function of the clock, so dragging backwards
   withholds it again — there is no latch to fall out of step with where the track actually is.

   The controls are a footer of a column that owns its height, never a sticky element inside a
   scroller: the words scroll and the player cannot move, so pause is always where you left it.

   There is no audio here and there will not be: the prototype has no bundler and no files. A fake
   clock stands in for the element, advanced by `requestAnimationFrame`, and everything is driven
   from it exactly as it is driven from `timeupdate` in the application. Which is the point of
   drawing this at all — how the reveal *feels* is not a question a still picture can answer.

   The application's counterparts are `LoopView.tsx`, `LoopPlayer.tsx`, `MadeBar.tsx` and
   `LoopDialog.tsx`, and `loopCards` / `loopMomentAt` in `selectors.ts` are the derivation this
   repeats. */

const player = { loopId: null, at: 0, playing: false, speed: 1, frame: null, last: 0, scrubbing: false,
                 repeat: false, autoplay: false };

function loopsIn(lang) { return LOOPS.filter((l) => l.language === lang).sort((a, b) => a.position - b.position); }
function loopItemsOf(id) { return LOOP_ITEMS.filter((r) => r.loopId === id).sort((a, b) => a.position - b.position); }
function loopCuesOf(id) { return LOOP_CUES.filter((r) => r.loopId === id).sort((a, b) => a.position - b.position); }

/* A format in words, the generator's where it gave them — `selectors.ts` `formatLabel`. */
function formatLabel(id) {
  const named = LOOP_SCHEMA.formats.find((format) => format.id === id);
  if (named) return named.label;
  const words = id.replace(/-/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
const loopIsReady = (loop) => Boolean(loop.audioRef);
const loopOf = (id) => LOOPS.find((l) => l.id === id) || null;

/* A name derived from the words it teaches, because there is no title column: as many as fit, then
   a count of what is left, so two loops over the same words in a different order still read apart. */
function loopTitle(loop, limit = 3) {
  const rows = loopItemsOf(loop.id);
  if (!rows.length) return "Empty loop";
  const named = rows.slice(0, limit).map((r) => r.sourceText);
  const rest = rows.length - named.length;
  return rest > 0 ? `${named.join(", ")} +${rest}` : named.join(", ");
}

const clock = (s) => {
  const whole = Math.max(0, Math.floor(s || 0));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
};

/* A loop's lines as the cards the player draws: one per group, and a line said several times — a
   drill's word — is one row of it. `loopCards` in `selectors.ts`. */
function loopCards(cues) {
  const cards = [];
  cues.forEach((cue) => {
    let card = cards[cards.length - 1];
    if (!card || card.group !== cue.group) {
      card = { group: cue.group, section: cue.section, kind: cue.kind, loopItemId: cue.loopItemId, start: cue.startSeconds, lines: [] };
      cards.push(card);
    }
    const same = card.lines.find((one) => one.text === cue.text && one.language === cue.language);
    if (same) same.starts.push(cue.startSeconds);
    else card.lines.push({ text: cue.text, language: cue.language, role: cue.role, heard: cue.startSeconds, starts: [cue.startSeconds] });
  });
  return cards;
}

/* What the player marks at one instant. The gap after a card belongs to it until the next begins,
   so a card does not go dark while its bed plays on; and `sounding` is the line most recently said
   rather than the one making sound this millisecond, because a word is half a second long every
   few and a mark that blinked for half a second would be unreadable. */
function loopMomentAt(cards, at) {
  let card = -1;
  cards.forEach((one, index) => { if (at >= one.start) card = index; });
  if (card < 0) return { card, sounding: -1 };
  let sounding = -1;
  let latest = -Infinity;
  cards[card].lines.forEach((line, index) => {
    line.starts.forEach((start) => { if (start <= at && start >= latest) { latest = start; sounding = index; } });
  });
  return { card, sounding };
}

/* The word a loop is on, for the bar: the card's, else the last word whose block has begun. */
function loopWordAt(rows, cards, at) {
  const card = cards[loopMomentAt(cards, at).card];
  const own = card && card.loopItemId ? rows.find((row) => row.id === card.loopItemId) : null;
  if (own) return own;
  let latest = null;
  rows.forEach((row) => { if (at >= row.startSeconds) latest = row; });
  return latest;
}

/* ── the fake transport ── */
function loopLoad(id, { play = false, at = 0 } = {}) {
  player.loopId = id;
  player.at = at;
  if (play) loopPlay(); else loopPause();
}

function loopPlay() {
  const loop = loopOf(player.loopId);
  if (!loop || !loopIsReady(loop)) return;
  player.playing = true;
  player.last = performance.now();
  if (!player.frame) player.frame = requestAnimationFrame(loopFrame);
  paintLoops();
}

function loopPause() {
  player.playing = false;
  if (player.frame) { cancelAnimationFrame(player.frame); player.frame = null; }
  paintLoops();
}

function loopFrame(now) {
  const loop = loopOf(player.loopId);
  const total = loop ? loop.durationSeconds : 0;
  if (!player.scrubbing) player.at = Math.min(total, player.at + ((now - player.last) / 1000) * player.speed);
  player.last = now;
  paintLoops();
  if (player.at >= total) { loopEnded(); return; }
  player.frame = requestAnimationFrame(loopFrame);
}

/* What happens at the end, in this order: play it again, else play the next one, else stop. Both
   switches are off by default — a loop that ends is a loop that ends. */
function loopEnded() {
  if (player.repeat) { player.at = 0; player.last = performance.now(); player.frame = requestAnimationFrame(loopFrame); return; }
  if (player.autoplay) {
    const next = loopNeighbour(1);
    if (next) { loopLoad(next.id, { play: true }); render(); return; }
  }
  loopPause();
}

function loopNeighbour(by) {
  const queue = loopsIn(state.lang).filter(loopIsReady);
  const at = queue.findIndex((loop) => loop.id === player.loopId);
  return at < 0 ? null : queue[at + by] || null;
}

function loopSeek(seconds) {
  const loop = loopOf(player.loopId);
  if (!loop) return;
  player.at = Math.max(0, Math.min(loop.durationSeconds, seconds));
  paintLoops();
}

/* Previous behaves the way every player's does: back to the top of this card unless you press it
   just after one started, which means you meant the one before. */
function loopStep(by) {
  const loop = loopOf(player.loopId);
  if (!loop) return;
  const cards = loopCards(loopCuesOf(loop.id));
  const index = loopMomentAt(cards, player.at).card;
  if (by < 0 && index >= 0 && player.at - cards[index].start > 3) { loopSeek(cards[index].start); return; }
  const want = index + by;
  if (want < 0) { loopSeek(0); return; }
  if (want >= cards.length) { loopSeek(loop.durationSeconds); return; }
  loopSeek(cards[want].start);
}

/* ── drawing ── */

function seekBar(loop, rows) {
  const ticks = rows.map((row) => `<span class="seek-tick" style="left:${(row.startSeconds / loop.durationSeconds) * 100}%"></span>`).join("");
  return `
    <div class="seek" id="seek" role="slider" aria-label="Where you are in the loop"
         aria-valuemin="0" aria-valuemax="${Math.round(loop.durationSeconds)}" tabindex="0">
      <span class="seek-track"></span>${ticks}
      <span class="seek-fill"></span><span class="seek-knob"></span>
    </div>
    <div class="seek-times"><span class="at">0:00</span><span>${clock(loop.durationSeconds)}</span></div>`;
}

/* A style in words, the generator's where it gave them — `selectors.ts` `styleLabel`. */
function styleLabel(styleId) {
  if (!styleId) return "No music yet";
  const named = LOOP_SCHEMA.families.find((family) => family.id === styleId);
  if (named) return named.label;
  const words = styleId.replace(/-/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}
const bedOfLoop = (loop) => BEDS.find((bed) => bed.styleId === loop.styleId && bed.seed === loop.seed);
const bedAbout = (bed) => {
  const source = loopOf(bed.sourceLoopId);
  return source ? `kept ${bed.createdAt.slice(5)} · from “${loopTitle(source)}”` : `kept ${bed.createdAt.slice(5)}`;
};

/* The player's menu of other music — `LoopMusic.tsx` `MusicMenu`. Choosing is asking; no Apply. */
function musicMenu(loop) {
  const others = BEDS.filter((bed) => !(bed.styleId === loop.styleId && bed.seed === loop.seed));
  const row = (attrs, name, about, cls = "") => `<button ${attrs}${cls ? ` class="${cls}"` : ""}>
      <span class="music-name">${name}</span><span class="music-about">${esc(about)}</span></button>`;
  return `<div class="menu music-menu${state.musicMenu ? " open" : ""}" role="menu" aria-label="New music for this loop">
    ${row('role="menuitem" data-music=""', "New music in this style", `${styleLabel(loop.styleId)}, with a different bed`)}
    ${others.length ? '<div class="menu-label label">Favourites</div>' : ""}
    ${others.map((bed) => row(`role="menuitem" data-music="${bed.styleId}"`, `${ICON.starOn}${esc(styleLabel(bed.styleId))}`, bedAbout(bed))).join("")}
    <div class="menu-label label">Styles</div>
    ${LOOP_SCHEMA.families.map((family) => row(
      `role="menuitemradio" aria-checked="${family.id === loop.styleId}" data-music="${family.id}"`,
      esc(family.label), family.description, family.id === loop.styleId ? "on" : "")).join("")}
  </div>`;
}

function playerBlock(loop) {
  const rows = loopItemsOf(loop.id);
  const kept = Boolean(bedOfLoop(loop));
  return `<div class="player">
    ${seekBar(loop, rows)}
    <div class="transport">
      <button class="switch${player.repeat ? " on" : ""}" data-switch="repeat"
              aria-pressed="${player.repeat}" aria-label="Play this loop again when it ends">${ICON.repeat}</button>
      <button data-step="-1" aria-label="Previous line">${ICON.prev}</button>
      <button class="big" id="playPause" aria-label="Play">${ICON.play}</button>
      <button data-step="1" aria-label="Next line">${ICON.next}</button>
      <button class="switch${player.autoplay ? " on" : ""}" data-switch="autoplay"
              aria-pressed="${player.autoplay}" aria-label="Go on to the next loop when this one ends">${ICON.continue}</button>
    </div>
    <div class="player-bed">
      ${state.remaking === loop.id ? '<span class="bed-status label">Making new music · 38% · Rendering the music bed</span>'
        : loop.fallbackFrom ? `<span class="bed-status label">${esc(fallbackNote(loop))}</span>` : ""}
      <span class="bed-line">
        <button class="bed-name label" id="bedName" aria-haspopup="menu" aria-expanded="${Boolean(state.musicMenu)}"
                ${state.remaking === loop.id ? "disabled" : ""}>${esc(styleLabel(loop.styleId))}${ICON.down}</button>
        <button class="bed-star${kept ? " on" : ""}" id="bedStar" aria-pressed="${kept}"
                aria-label="${kept ? "No longer keep this music" : "Keep this music as a favourite"}">${kept ? ICON.starOn : ICON.star}</button>
        <span class="label">· ${esc(formatLabel(loop.format))} · ${rows.length} words</span>
        ${musicMenu(loop)}
      </span>
    </div>
  </div>`;
}

/* What a format needs, said as what the owner would set up, and where — `LoopFormat.tsx`. */
const NEEDS = {
  writer: { what: "a writing model", where: "Settings ▸ Providers" },
  multilingual_voice: { what: "a loop voice that can mix languages", where: "Settings ▸ Loops" }
};

function fallbackNote(loop) {
  const asked = LOOP_SCHEMA.formats.find((format) => format.id === loop.fallbackFrom);
  const needs = (asked ? asked.requires : []).map((need) => NEEDS[need].what);
  return `${formatLabel(loop.format)} instead of ${formatLabel(loop.fallbackFrom)}${needs.length ? ` — it needs ${needs.join(" and ")}` : ""}`;
}

const SECTIONS = { quiz: "Quiz", review: "Review" };

/* One card per group of lines. The card being played *is* the big type — there is no second, larger
   copy of it above, so there is one thing to look at and one column to read down. */
function lyricBlock(loop) {
  const cards = loopCards(loopCuesOf(loop.id));
  return `<div class="lyric" id="lyric">${cards.map((card, index) => {
    const entering = SECTIONS[card.section] && (index === 0 || cards[index - 1].section !== card.section);
    return `${entering ? `<div class="lyric-divider label">${SECTIONS[card.section]}</div>` : ""}
    <button class="lyric-row" data-seek="${card.start}" data-card="${index}">${card.lines.map((line, number) => `
      <span class="lyric-line ${line.role === "native" ? "lyric-source" : "lyric-target"}${line.text.length > 28 ? " long" : ""}"
            data-heard="${number === 0 ? -1 : line.heard}" data-text="${esc(line.text)}">
        <span class="lyric-lang" aria-hidden="true">${esc(line.language.split("-")[0].toUpperCase())}</span>${number === 0
          ? `<span class="lyric-said">${esc(line.text)}</span>` : '<span class="lyric-held"></span>'}</span>`).join("")}
    </button>`;
  }).join("")}</div>`;
}

function loopSub(loop) {
  if (!loopIsReady(loop)) return '<span class="doing">Being made…</span>';
  return `${esc(formatLabel(loop.format))} · ${loopItemsOf(loop.id).length} words · ${clock(loop.durationSeconds)}`;
}

/* A loop is a `swipeRow` whose one action is Delete. The row is never `disabled`: a loop that was
   never made is the one you most want rid of, and a disabled button answers no gesture at all. */
function loopRow(loop) {
  const ready = loopIsReady(loop);
  const on = loop.id === player.loopId;
  return swipeRow(`loop:${loop.id}`, `<button class="loop-row${on ? " on" : ""}" data-loop="${loop.id}" aria-disabled="${ready ? "false" : "true"}">
        <span class="loop-go${ready ? "" : " pending"}">${ready ? (on && player.playing ? ICON.pause : ICON.play) : ICON.hourglass}</span>
        <span class="loop-main">
          <span class="loop-title">${esc(loopTitle(loop))}</span>
          <span class="loop-sub">${loopSub(loop)}</span>
        </span>
      </button>`, [{ label: "Delete", menu: "Delete this loop", tone: "danger", attrs: `data-loop-delete="${loop.id}"` }]);
}

/* ── stories ───────────────────────────────────────────────────────────────
   The same shape as loops: a list of made objects, each open, being made, or asked for and never
   made. The reader is a deck rather than a scroller — a part is a picture and a few sentences,
   which is about one screen, so a column of them is a page you scroll to see what a swipe shows
   whole. */
function storiesIn(lang) {
  return STORIES.filter((one) => one.language === lang).sort((a, b) => a.position - b.position);
}
function storyOf(id) { return STORIES.find((one) => one.id === id) || null; }
function partsOf(id) {
  return STORY_PARTS.filter((one) => one.storyId === id).sort((a, b) => a.position - b.position);
}
function wordsOf(id) {
  return STORY_WORDS.filter((one) => one.storyId === id).sort((a, b) => a.position - b.position);
}
function storyTitle(story) {
  if (story.title) return story.title;
  const words = wordsOf(story.id);
  return words.length ? words.map((w) => w.sourceText).join(", ") : "Empty story";
}

/* Marks are **found rather than stored**: the writer reports the forms it wrote, and this locates
   them. A form it cannot find is simply not marked — degraded, never broken. */
function markWords(text, words, field = "forms") {
  const forms = [];
  words.forEach((word) => (word[field] || []).forEach((form) => { if (form.trim()) forms.push(form.trim()); }));
  if (!forms.length) return esc(text);
  forms.sort((a, b) => b.length - a.length);
  /* Each mark says which word it is, so a tap on it is answered from the words you hold. */
  const owner = new Map();
  words.forEach((word) => (word[field] || []).forEach((form) => owner.set(form.trim().toLowerCase(), word.lexemeId)));
  const pattern = new RegExp("(" + forms.map((f) => f.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "gi");
  return esc(text).replace(pattern, (form) => `<b class="story-mark" data-lexeme="${owner.get(form.toLowerCase()) || ""}">${form}</b>`);
}

function storyRow(story) {
  const parts = partsOf(story.id);
  const written = parts.length > 0;
  const drawn = parts.filter((one) => one.imageRef).length;
  const words = wordsOf(story.id);
  const plural = (n, noun) => `${n} ${noun}${n === 1 ? "" : "s"}`;
  const names = words.map((w) => w.sourceText);
  const sub = written
    ? `<span class="story-words" data-words="${esc(names.join("|"))}" title="${esc(names.join(", "))}"><span class="fit-text">${esc(names.join(" \u00b7 "))}</span></span>`
    : '<span class="warn">Never written</span>';
  const meta = written
    ? `<span class="story-meta"><span class="story-counts">${plural(parts.length, "part")} \u00b7 ${plural(words.length, "word")}</span>${
      drawn < parts.length ? `<span class="warn">${drawn} of ${parts.length} drawn</span>` : ""}</span>`
    : "";
  return swipeRow(`story:${story.id}`, `<button class="loop-row" data-story="${story.id}" aria-disabled="${!written}">
        <span class="loop-go story-go${written ? "" : " pending"}">${written ? story.emoji : ICON.hourglass}</span>
        <span class="loop-main">
          <span class="loop-title">${esc(storyTitle(story))}</span>
          <span class="loop-sub">${sub}</span>
        </span>
        ${meta}
      </button>`, [{ label: "Delete", menu: "Delete this story", tone: "danger", attrs: `data-story-delete="${story.id}"` }], "story-shell");
}

function renderStories() {
  const open = state.storyOpen ? storyOf(state.storyOpen) : null;
  if (open) {
    const parts = partsOf(open.id);
    const words = wordsOf(open.id);
    const pages = parts.length + 1;
    const at = Math.min(state.storyAt, pages - 1);
    /* A part read by a directed voice knows where its passages are, and each is a place to start: the
       one that is sounding is tinted, and touching another moves there. The application reads them
       off the recording; this picture cuts the first part at its first sentence and lights it, as if
       it were playing. A clear voice has no passages, so the other parts are plain text. */
    const passages = (part, words, language, playing) => {
      if (!playing) return `<p class="story-text" lang="${language}">${markWords(part.text, words)}</p>`;
      const cut = part.text.search(/[.!?]\s/) + 2;
      const seg = (text, on, index) => `<span class="story-seg${on ? " on" : ""}" data-passage="${index}">${markWords(text, words)}</span>`;
      return `<p class="story-text tappable" lang="${language}">${seg(part.text.slice(0, cut), true, 0)}${seg(part.text.slice(cut), false, 1)}</p>`;
    };
    const partPage = (part, index) => {
      const shown = Boolean(state.storyShown[part.id]);
      return `<article class="card story-card" aria-label="Part ${index + 1}">
        <div class="story-body">
          <div class="story-pic${part.imageRef ? " is-ready" : ""}">${part.imageRef
            ? `<img src="${part.imageRef}" alt="">`
            : `<span class="story-pic-note">${part.failureReason ? "No picture for this part" : "Drawing\u2026"}</span>`}</div>
          <div class="story-copy">
            <span class="card-ornament above" aria-hidden="true">${ICON.hedera}</span>
            <h3 class="story-head"><span class="story-no">${index + 1}</span> \u00b7 ${esc(part.heading)}<button class="say head always story-listen${index === 0 ? " playing" : ""}" data-say="${esc(strip(part.text))}" aria-label="Read this part aloud">${ICON.play}</button></h3>
            ${passages(part, words, open.language, index === 0)}
            <div class="story-tr-slot">${shown
              ? `<p class="story-tr"><span class="story-tr-head">${esc(part.headingTranslation)}. </span>${markWords(part.translation, words, "translationForms")}</p>
                <button class="story-hide" data-hide="${part.id}" aria-label="Hide the translation">Hide</button>`
              : `<button class="story-reveal" data-reveal="${part.id}">Tap to read it in your own language</button>`}</div>
            <span class="card-ornament below" aria-hidden="true">${ICON.hedera}</span>
          </div>
        </div>
      </article>`;
    };
    /* The last page: the words the story was made from, as the word list draws them. A word it could
       not work in is dimmed rather than dropped. */
    const wordsPage = `<article class="card story-card story-words-page" aria-label="Words in this story">
      <div class="story-body"><div class="story-copy">
        <span class="card-ornament above" aria-hidden="true">${ICON.hedera}</span>
        <h3 class="story-head">Words</h3>
        <div class="rows">${words.map((word) => `<div class="row${word.forms.length ? "" : " unused"}">
          <span class="plate" aria-hidden="true">${word.emoji || "\u{1F4C4}"}</span>
          <span><span class="word">${esc(word.sourceText)}</span><span class="gloss">${esc(word.gloss || "")}</span></span>
        </div>`).join("")}</div>
        <span class="card-ornament below" aria-hidden="true">${ICON.hedera}</span>
      </div></div>
    </article>`;
    return `<section class="loops stories reading">
      <div class="cards story-read">
        <div class="loops-back story-bar">
          <span class="story-bar-side">
            <button class="icon-btn" id="storyBack" aria-label="Back to the stories">${ICON.back}</button>
            <span class="label">Stories</span>
          </span>
          <span class="story-bar-title">${esc(storyTitle(open))}</span>
          <span class="story-bar-count">${at + 1} / ${pages}</span>
        </div>
        <div class="cards-stage">
          <div class="cards-track" id="storyTrack">${parts.map(partPage).join("")}${wordsPage}</div>
        </div>
        <div class="cards-edges">
          <button class="cards-edge prev" data-story-step="-1" aria-label="The part before">${ICON.back}</button>
          <button class="cards-edge next" data-story-step="1" aria-label="The next part">${ICON.back}</button>
        </div>
      </div>
    </section>`;
  }
  return `<section class="loops stories">
    <div class="loops-back">
      <button class="icon-btn" id="storiesClose" aria-label="Back to the list">${ICON.back}</button>
      <span class="label">Your words</span><span class="spacer"></span>
    </div>
    <div class="loops-head"><h2>Stories</h2><span class="spacer"></span>
      <button class="tb-btn primary" id="makeStory">${ICON.plus}<span>Make a story</span></button></div>
    <div class="loops-list">${storiesIn(state.lang).map(storyRow).join("")}</div>
  </section>`;
}

function openStories() {
  state.stories = true; state.loops = false; state.map = false;
  state.openId = null; state.openExt = null; state.add = false;
  render();
}

/* ── the map ──────────────────────────────────────────────────────────────
   One language's senses, laid out by meaning (docs/features/meaning-map.md). `map.js` is the
   component and knows nothing of this file; what is here is the host: which data, the header, the
   peek, find, and the way back from an article. The data is the owner's real map when
   `map-data.local.js` has been generated, and the committed sample otherwise (see README). */

const MAP_STYLES = ["atlas", "constellation", "clouds"];
const MAP_LABELS = ["model", "words", "terms"];
let meaningMap = null;
/* Where the map was left, per language: coming back from an article puts it back exactly there. */
const mapCameras = {};
/* Languages whose map has already grown into place this session. It grows once; after that it is
   simply there, which is what "opens straight away" means for the second visit. */
const mapGrown = new Set();

const mapSource = () => (state.mapSample || !window.MAP_LOCAL ? "sample" : "local");
const mapData = () => {
  const all = mapSource() === "sample" ? window.MAP_SAMPLE : window.MAP_LOCAL;
  return (all && all[state.lang]) || null;
};
const fold = (s) => String(s).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
const count = (n) => n.toLocaleString("en-GB");
/* What a shortcut is called on this machine, for the zoom buttons' titles. */
const MOD = /Mac|iPhone|iPad/.test(navigator.platform) ? "\u2318" : "Ctrl+";

function openMap() {
  state.map = true; state.loops = false; state.stories = false;
  state.openId = null; state.openExt = null; state.add = false;
  render();
}
function closeMap() {
  state.map = false; state.mapSel = -1;
  teardownMap();
  render();
}
function teardownMap() {
  const bar = $(".topbar .map-bar");
  if (bar) bar.remove();
  if (!meaningMap) return;
  meaningMap.destroy();
  meaningMap = null;
}

function mapShell(d) {
  const name = langOf(state.lang).name;
  /* `data-map-lang`, not `data-lang`: the document's click handler reads any `[data-lang]` ancestor as
     a pick from the language menu, and every tap on the map chose the language again. */
  return `<section class="map" data-map-lang="${state.lang}" data-src="${mapSource()}" data-state="${state.mapState || ""}">
    <canvas class="map-canvas" role="img" aria-label="A map of your ${esc(name)} words, arranged by meaning"></canvas>
    <div class="map-top">
      <button class="icon-btn" id="mapClose" aria-label="Back to your words">${ICON.back}</button>
      <div class="map-title"><h2>Map</h2>${d ? `<span class="map-count label">${count(d.senses)} meaning${d.senses === 1 ? "" : "s"} · ${count(d.words)} word${d.words === 1 ? "" : "s"}</span>` : ""}</div>
      <div class="map-find">${ICON.search}
        <input id="mapFind" type="search" placeholder="Find a word on the map" autocomplete="off" spellcheck="false" aria-label="Find a word on the map">
        <ol class="map-hits" id="mapHits" hidden></ol>
      </div>
      <!-- The map's own language switcher: the top bar that holds the global one is hidden here, and
           which language a map is of is the one thing that must never be in doubt. Its items are
           ordinary [data-lang] buttons, so the document's handler does exactly what the global menu
           does. -->
      <div class="map-lang">
        <button class="tb-btn lang-btn" id="mapLangBtn" aria-haspopup="menu" aria-label="Vocabulary language">
          <span class="flag">${langOf(state.lang).flag}</span><span class="code">${state.lang.toUpperCase()}</span></button>
        <div class="menu map-lang-menu" id="mapLangMenu">
          <div class="label menu-label">Vocabulary language</div>
          ${LANGUAGES.map((x) => `<button data-lang="${x.code}" class="${x.code === state.lang ? "on" : ""}">
            <span>${x.flag}</span><span>${x.name}</span>
            <span class="cnt">${count(((mapSource() === "sample" ? window.MAP_SAMPLE : window.MAP_LOCAL) || {})[x.code]?.words || 0)}</span>
          </button>`).join("")}
        </div>
      </div>
    </div>
    <div class="map-tools">
      <button class="map-tool" id="mapFit" aria-label="Show the whole map" title="Show the whole map  ${MOD}0">${ICON.fit}</button>
      <button class="map-tool pointer-only" id="mapIn" aria-label="Zoom in" title="Zoom in  ${MOD}+   \u00b7   ${MOD} + scroll">${ICON.plus}</button>
      <button class="map-tool pointer-only" id="mapOut" aria-label="Zoom out" title="Zoom out  ${MOD}\u2212">${ICON.minus}</button>
    </div>
    <aside class="map-peek" id="mapPeek" hidden aria-live="polite"></aside>
    <div class="map-note" id="mapNote" hidden></div>
  </section>`;
}

/* The surface is built once and then kept: re-rendering it would throw away the camera in the middle
   of a pinch. It is rebuilt only when what it shows changes — another language, the other fixture, or
   one of the prototype's states. */
function renderMap() {
  const d = mapData();
  let root = $("#composer .map");
  const stale = !root || root.dataset.mapLang !== state.lang || root.dataset.src !== mapSource() ||
    root.dataset.state !== (state.mapState || "");
  if (stale) {
    teardownMap();
    $("#composer").innerHTML = mapShell(d);
    root = $("#composer .map");
    mountMapBar(root);
    startMap(root, d);
  }
  paintPeek();
}

/* The map's row goes into the top bar itself, so the bar keeps its own box, surface and rule and the
   row is its contents — search, Add and sync are hidden while it is there (`acervo.css`). Its Back and
   language menu are wired here, for every state of the map, the first draw and "no map yet" included. */
function mountMapBar(root) {
  const bar = el('<div class="map-bar"></div>');
  bar.appendChild($(".map-top", root));
  $(".topbar").appendChild(bar);
  bar.addEventListener("click", (ev) => {
    if (ev.target.closest("#mapClose")) { closeMap(); return; }
    if (ev.target.closest("#mapLangBtn")) { $("#mapLangMenu").classList.toggle("open"); return; }
    if (!ev.target.closest(".map-lang")) $("#mapLangMenu").classList.remove("open");
  });
}

function startMap(root, d) {
  const note = $("#mapNote", root);
  // With no map there is nothing to fit, zoom or find in.
  if (state.mapState || !d) { $(".map-tools", root).hidden = true; $(".topbar .map-find").hidden = true; }
  if (state.mapState === "offline" || !d) {
    note.hidden = false;
    note.className = "map-note center";
    note.innerHTML = `<h3>No map yet</h3><p>Your server draws the map, and this device has not reached it
      since you added words in this language. It will appear here the first time it can.</p>`;
    return;
  }
  if (state.mapState === "drawing") {
    note.hidden = false;
    note.className = "map-note center";
    note.innerHTML = `<div class="map-drawing" aria-hidden="true"><span></span><span></span><span></span></div>
      <h3>Drawing your map</h3><p>The first time takes about a minute, while every meaning is read.
      After that the map opens at once.</p>`;
    /* In the application this ends when the artifact arrives; here, after a moment, it grows. */
    setTimeout(() => { if (state.map && state.mapState === "drawing") { state.mapState = null; mapGrown.delete(state.lang); render(); } }, 2600);
    return;
  }
  meaningMap = MeaningMap($(".map-canvas", root), {
    onSelect: (point, i) => { state.mapSel = i; paintPeek(); if (i >= 0) meaningMap.reveal(i); },
    onCamera: (cam) => { mapCameras[state.lang] = cam; },
    onRegion: () => {}
  });
  meaningMap.setStyle(state.mapStyle);
  meaningMap.setLabels(state.mapLabels);
  const returning = mapCameras[state.lang];
  meaningMap.setData(d, returning ? { camera: returning } : { animate: mapGrown.has(state.lang) ? null : "grow" });
  mapGrown.add(state.lang);
  if (state.mapSel >= 0 && d.points[state.mapSel]) meaningMap.select(state.mapSel);
  paintChosen(d);
  if (!d.regions.length) {
    note.hidden = false;
    note.className = "map-note";
    note.textContent = `Regions appear once a language has about 150 meanings. ${langOf(state.lang).name} has ${count(d.senses)}.`;
  }
  wireMap(root, d);
}

function wireMap(root, d) {
  const find = $("#mapFind");
  const hits = $("#mapHits");
  let matches = [];
  const paintHits = () => {
    const q = fold(find.value.trim());
    if (!q) { matches = []; hits.hidden = true; meaningMap.highlight(null); return; }
    const scored = [];
    d.points.forEach((p, i) => {
      const h = fold(p.headword);
      const at = h.indexOf(q);
      const g = fold(p.glossAll || "").indexOf(q);
      if (at < 0 && g < 0) return;
      scored.push({ i, score: (at === 0 ? 0 : at > 0 ? 1 : 2) - p.rank * 0.1 });
    });
    scored.sort((a, b) => a.score - b.score);
    matches = scored.map((x) => x.i);
    meaningMap.highlight(new Set(matches));
    hits.hidden = false;
    hits.innerHTML = matches.length
      ? matches.slice(0, 8).map((i, k) => {
          const p = d.points[i];
          return `<li><button data-map-go="${i}" class="${k === 0 ? "on" : ""}"><span>${p.emoji}</span>
            <span lang="${d.language}">${esc(p.headword)}${p.of > 1 ? ` <span class="label">${p.order + 1}/${p.of}</span>` : ""}</span>
            <span class="hit-gloss">${esc(p.gloss || "")}</span></button></li>`;
        }).join("")
      : `<li class="hit-none">Nothing on this map matches “${esc(find.value.trim())}”.</li>`;
  };
  find.addEventListener("input", paintHits);
  find.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && matches.length) { ev.preventDefault(); goTo(matches[0]); find.blur(); }
    if (ev.key === "Escape") { ev.stopPropagation(); find.value = ""; paintHits(); find.blur(); }
  });
  const onClick = (ev) => {
    const go = ev.target.closest("[data-map-go]");
    if (go) { goTo(Number(go.dataset.mapGo)); return; }
    if (ev.target.closest("#mapFit")) { meaningMap && meaningMap.fit(true); return; }
    if (ev.target.closest("#mapIn")) { meaningMap && meaningMap.zoomBy(1.8); return; }
    if (ev.target.closest("#mapOut")) { meaningMap && meaningMap.zoomBy(1 / 1.8); return; }
    if (ev.target.closest("#peekClose")) { state.mapSel = -1; meaningMap.select(-1); paintPeek(); return; }
    if (ev.target.closest("#peekOpen")) { openFromMap(d.points[state.mapSel]); return; }
    if (ev.target.closest("#peekPick")) { togglePointPick(d.points[state.mapSel]); return; }
    if (!ev.target.closest(".map-find")) hits.hidden = true;
  };
  // The surface and the row in the top bar: Find's hits live in the bar, the peek in the surface.
  root.addEventListener("click", onClick);
  $(".topbar .map-bar").addEventListener("click", onClick);
  find.addEventListener("focus", () => { if (find.value.trim()) hits.hidden = false; });
}

/* The peek is painted first, so the camera knows what it will cover before it decides where the sense
   should land. */
function goTo(i) {
  state.mapSel = i;
  $("#mapHits").hidden = true;
  paintPeek();
  meaningMap.select(i, { fly: true });
}

/* What a tap shows: enough to know the sense, and the way on. The same word's other senses are one
   tap each, and the map flies there along the arc it has drawn, which is the whole reason a map of
   senses beats a map of words. */
function paintPeek() {
  const peek = $("#mapPeek");
  if (!peek) return;
  const d = mapData();
  paintChosen(d);
  const p = d && state.mapSel >= 0 ? d.points[state.mapSel] : null;
  $("#composer .map").classList.toggle("peeking", Boolean(p));
  if (!p) {
    peek.hidden = true; peek.innerHTML = "";
    if (meaningMap) meaningMap.setInsets({ left: 0, bottom: 0 });
    return;
  }
  const siblings = d.points.map((q, i) => [q, i]).filter(([q]) => q.w === p.w);
  const vocab = langOf(state.lang);
  peek.hidden = false;
  peek.innerHTML = `
    <div class="peek-head">
      <span class="peek-plate" aria-hidden="true">${p.emoji || "\u{1F4C4}"}</span>
      <div class="peek-id">
        <div class="peek-word" lang="${d.language}">${esc(p.headword)}</div>
        <div class="peek-meta label">${esc(p.pos)}${p.domain ? ` · ${esc(p.domain)}` : ""}</div>
      </div>
      ${p.pic ? `<img class="peek-pic" src="${p.pic}" alt="">` : ""}
      <button class="icon-btn peek-close" id="peekClose" aria-label="Close">${ICON.close}</button>
    </div>
    ${siblings.length > 1 ? `<div class="peek-senses"><span class="label">Meaning ${p.order + 1} of ${p.of}</span>
      ${siblings.map(([q, i]) => `<button class="peek-sib${i === state.mapSel ? " on" : ""}" data-map-go="${i}"
        aria-label="Meaning ${q.order + 1}">${q.emoji} ${q.order + 1}</button>`).join("")}</div>` : ""}
    <p class="peek-def" lang="${d.definitionLang}">${esc(p.definition)}</p>
    ${p.glossAll ? `<p class="peek-gloss" lang="${(vocab.glossLangs || [])[0] || ""}">${esc(p.glossAll)}</p>` : ""}
    ${p.nb.length ? `<div class="peek-near"><span class="label">Near</span>${p.nb.map((j) => {
      const q = d.points[j];
      return `<button class="peek-chip" data-map-go="${j}" lang="${d.language}">${q.emoji} ${esc(q.headword)}</button>`;
    }).join("")}</div>` : ""}
    <div class="peek-actions">
      <button class="tb-btn peek-pick${isPicked(pointKey(p)) ? " on" : ""}" id="peekPick" aria-pressed="${isPicked(pointKey(p))}"
        title="${isPicked(pointKey(p)) ? "In your selection \u2014 remove it" : "Add to selection"}">${isPicked(pointKey(p)) ? `${ICON.selected}<span>Selected</span>` : `${ICON.select}<span>Select</span>`}</button>
      <button class="tb-btn primary peek-open" id="peekOpen">Open the article ${ICON.forward}</button>
    </div>`;
  /* Tell the camera what the peek covers, so a sense it flies to lands in the part still visible. */
  if (meaningMap) {
    const phone = $("#composer .map").clientWidth <= 720 && peek.offsetWidth >= $("#composer .map").clientWidth - 2;
    meaningMap.setInsets(phone ? { left: 0, bottom: peek.offsetHeight } : { left: peek.offsetWidth + 12, bottom: 0 });
  }
}

/* Every sense of a selected word wears the selection's mark: selection is of words, and a map is
   of senses. Indices, because the map component knows nothing of lexemes. */
function paintChosen(d) {
  if (!meaningMap || !d) return;
  const keys = new Set(picks[state.lang] || []);
  const chosen = new Set();
  if (keys.size) d.points.forEach((p, i) => { if (keys.has(pointKey(p))) chosen.add(i); });
  meaningMap.choose(chosen);
}
function togglePointPick(p) {
  const key = pointKey(p);
  if (key.startsWith("map:")) pickedFromMap[key] = { headword: p.headword, emoji: p.emoji, gloss: p.gloss };
  togglePick(key);
}

/* The article, when the prototype has one for this word; otherwise a note. The way back is remembered
   either way, and the camera is already remembered per language. */
function openFromMap(p) {
  if (!p) return;
  const want = fold(p.headword);
  const hit = LEXEMES.find((x) => x.language === state.lang &&
    (fold(x.headword) === want || fold(x.lemma) === want));
  if (!hit) {
    toast(`In the application this opens “${p.headword}”. The prototype has articles for only a few words.`);
    return;
  }
  state.mapReturn = true;
  state.map = false;
  teardownMap();
  state.openId = hit.id; state.mode = "read";
  render();
}

/* The harness's Update: the layout the device had, then the one that arrived, as the application
   will animate it — the words already on the map glide to where they now belong, and the new ones
   appear after, with a ring. */
function playMapUpdate() {
  const d = mapData();
  if (!meaningMap || !d || !d.before) { toast("This map has no earlier layout to update from"); return; }
  const previous = new Map(d.before.points.map(([i, x, y]) => [d.points[i].id, [x, y]]));
  state.mapSel = -1; paintPeek();
  const arrived = meaningMap.setData(d, { animate: "update", previous, camera: meaningMap.getCamera() });
  paintChosen(d);
  const note = $("#mapNote");
  note.hidden = false;
  note.className = "map-note arrived";
  note.textContent = `${arrived} new meaning${arrived === 1 ? "" : "s"} since you last opened the map`;
  clearTimeout(playMapUpdate.timer);
  playMapUpdate.timer = setTimeout(() => { note.hidden = true; }, 4200);
}

function renderLoops() {
  const loops = loopsIn(state.lang);
  const open = state.loopOpen ? loopOf(state.loopOpen) : null;
  if (open) {
    return `<section class="loops">
      <div class="loops-back">
        <button class="icon-btn" id="loopBack" aria-label="Back to the loops">${ICON.back}</button>
        <span class="label">Loops</span><span class="spacer"></span>
      </div>
      <div class="loop-play">${lyricBlock(open)}${playerBlock(open)}</div>
    </section>`;
  }
  return `<section class="loops">
    <div class="loops-back">
      <button class="icon-btn" id="loopsClose" aria-label="Back to the list">${ICON.back}</button>
      <span class="label">Your words</span><span class="spacer"></span>
    </div>
    <div class="loops-head"><h2>Loops</h2><span class="spacer"></span>
      <button class="tb-btn primary" id="makeLoop">${ICON.plus}<span>Make a loop</span></button></div>
    <div class="loops-list">${loops.map(loopRow).join("")}</div>
  </section>`;
}

/* The bar at the foot for a phone or a tablet, and the chip in the top bar for a desktop. Two skins
   of one thing, so what they say can never disagree; `acervo.css` picks which is drawn. */
function renderLoopBar() {
  const loops = loopsIn(state.lang);
  const loop = player.loopId ? loopOf(player.loopId) : null;
  if (!loop) {
    /* Split in two, and **no `+`**: both surfaces carry their own Make button in their own header,
       and a bar whose job is to be a way in should not also be a way to start something. */
    return `<button class="madebar-half" id="openLoops">
        <span class="madebar-ic">${ICON.note}</span>
        <span class="loopbar-title">Loops</span>
        <span class="loopbar-sub">${loops.length}</span>
      </button>
      <button class="madebar-half" id="openStories">
        <span class="madebar-ic">\u{1F4D6}</span>
        <span class="loopbar-title">Stories</span>
        <span class="loopbar-sub">${storiesIn(state.lang).length}</span>
      </button>
      <button class="madebar-half" id="openMap">
        <span class="madebar-ic">${ICON.map}</span>
        <span class="loopbar-title">Map</span>
        <span class="loopbar-sub">${(() => { const d = mapData(); return d ? count(d.senses) : "\u2014"; })()}</span>
      </button>`;
  }
  return `<span class="loopbar-line" style="width:0"></span>
    <button class="loopbar-play" id="barPlay" aria-label="Play">${ICON.play}</button>
    <button class="loopbar-main" id="openLoops">
      <span class="loopbar-title"></span>
      <span class="loopbar-sub"></span>
    </button>
    <button class="icon-btn loopbar-close" id="barClose" aria-label="Stop and close" title="Stop and close">${ICON.close}</button>`;
}

/* The selection bar. It says how many words are selected and which, as many whole words as fit and
   then "+N", and offers the two things a selection is for today. Its text opens the list of every
   selected word, where one can be taken out without finding it again among a thousand.

   Drawn over the list, the map and an article — reading is when words are gathered — and never over
   Add, the loops or the stories, whose own Make buttons offer the selection. Over an article it is a
   wide window's only: on a phone the word has the whole screen and its foot is the ask dock's, so
   `acervo.css` hides it there, and it steps aside at any width while a conversation is open. */
function selectionShown() {
  return picked().length > 0 && !state.add && !state.loops && !state.stories;
}
/* Whether the bar can be seen over an article — the same width the stylesheet decides it by. */
const selBarOverArticle = () => $(".viewport").clientWidth > 720;
function renderSelBar() {
  const words = picked();
  if (!words.length) return "";
  return `<button class="selbar-what" id="selList" aria-haspopup="menu" aria-expanded="${state.selList}"
      aria-label="Your selection: ${wordsCount(words.length)}. Show them">
      <span class="selbar-badge" aria-hidden="true">${ICON.selected}</span>
      <span class="selbar-text">
        <span class="selbar-title">${wordsCount(words.length)} selected</span>
        <span class="selbar-words" lang="${state.lang}" data-words="${esc(words.map((w) => w.headword).join("|"))}"><span class="fit-text">${esc(words.map((w) => w.headword).join(" · "))}</span></span>
      </span>
    </button>
    <button class="tb-btn selbar-make" id="selLoop" aria-label="Make a loop from these words">${ICON.note}<span>Loop</span></button>
    <button class="tb-btn selbar-make" id="selStory" aria-label="Make a story from these words"><span class="selbar-ic" aria-hidden="true">\u{1F4D6}</span><span>Story</span></button>
    <button class="icon-btn selbar-clear" id="selClear" aria-label="Forget the selection" title="Forget the selection">${ICON.close}</button>
    ${state.selList ? `<div class="menu open sel-menu" role="menu" aria-label="Selected words">
      <div class="label menu-label">Your selection · ${esc(langOf(state.lang).name)}</div>
      <div class="sel-items">${words.map((w) => `<div class="sel-item">
        <button class="sel-open" data-sel-open="${w.key}" role="menuitem">
          <span class="plate" aria-hidden="true">${w.emoji || "\u{1F4C4}"}</span>
          <span class="sel-id"><span class="sel-word" lang="${state.lang}">${esc(w.headword)}</span><span class="sel-gloss">${esc(w.gloss || "")}</span></span>
        </button>
        <button class="sel-drop" data-sel-drop="${w.key}" aria-label="Remove ${esc(w.headword)} from the selection" title="Remove from the selection">${ICON.close}</button>
      </div>`).join("")}</div>
      <div class="menu-sep"></div>
      <button role="menuitem" id="selClear2">Clear the selection</button>
    </div>` : ""}`;
}

/* The words line gives up whole words rather than the end of one, as a story row's does, and says
   how many it left out: "+3" rather than "· …", because here the number is the point. */
function fitSelWords() {
  const line = $(".selbar-words[data-words]");
  if (!line) return;
  const words = line.dataset.words.split("|");
  const text = line.querySelector(".fit-text");
  let ruler = line.querySelector(".fit-ruler");
  if (!ruler) {
    ruler = document.createElement("span");
    ruler.className = "fit-ruler";
    ruler.setAttribute("aria-hidden", "true");
    ruler.innerHTML = [...words, " · ", `  +${words.length}`].map((piece) => `<span>${esc(piece)}</span>`).join("");
    line.appendChild(ruler);
  }
  const widths = [...ruler.children].map((one) => one.getBoundingClientRect().width);
  const [separator, more] = widths.slice(words.length);
  const across = (n) => widths.slice(0, n).reduce((sum, w) => sum + w, 0) + Math.max(n - 1, 0) * separator;
  let shown = words.length;
  if (across(shown) > line.clientWidth) {
    shown = 1;
    for (let n = words.length - 1; n >= 1; n -= 1) {
      if (across(n) + more <= line.clientWidth) { shown = n; break; }
    }
  }
  text.innerHTML = esc(words.slice(0, shown).join(" · ")) +
    (shown < words.length ? ` <span class="fit-more">+${words.length - shown}</span>` : "");
}
window.addEventListener("resize", fitSelWords);

function wireSelBar(root) {
  root.addEventListener("click", (ev) => {
    if (ev.target.closest("#selList")) { state.selList = !state.selList; render(); return; }
    if (ev.target.closest("#selClear") || ev.target.closest("#selClear2")) { clearPicks(); return; }
    if (ev.target.closest("#selLoop")) { state.selList = false; render(); openLoopDialog("selection"); return; }
    if (ev.target.closest("#selStory")) { state.selList = false; render(); openStoryDialog("selection"); return; }
    const drop = ev.target.closest("[data-sel-drop]");
    if (drop) { togglePick(drop.dataset.selDrop); return; }
    const open = ev.target.closest("[data-sel-open]");
    if (open) {
      const entry = pickEntry(open.dataset.selOpen);
      state.selList = false;
      if (!entry || !entry.article) { toast(`In the application this opens “${entry ? entry.headword : "it"}”. The prototype has articles for only a few words.`); render(); return; }
      if (state.map) { state.mapReturn = true; state.map = false; teardownMap(); }
      state.openId = entry.article; state.mode = "read"; state.card = 0;
      render();
    }
  });
}
wireSelBar($("#selbar"));
/* A press anywhere else puts the list away, as the article's menu does. */
document.addEventListener("pointerdown", (ev) => {
  if (state.selList && !ev.target.closest(".selbar")) { state.selList = false; paintSelBar(); }
});

/* Only the bar, so closing its list under a press elsewhere does not rebuild what was pressed. */
function paintSelBar() {
  const shown = selectionShown();
  const bar = $("#selbar");
  bar.innerHTML = shown ? renderSelBar() : "";
  bar.style.display = shown ? "" : "none";
  $(".app").classList.toggle("selecting", shown);
  $(".app").classList.toggle("asking", Boolean(state.openId) && state.ask !== "dock");
  /* On a phone the Made bar gives way to it; a loop that is playing keeps its bar, under this one,
     because hiding what is sounding would be worse than a second row. Over an article, an external
     entry or Add neither is drawn, as in the application (`MadeBar.tsx`): that column's foot is the
     ask dock's. */
  const elsewhere = Boolean(state.openId || state.openExt || state.add);
  $("#loopbar").style.display = elsewhere || (shown && !player.loopId) ? "none" : "";
  /* Split in three only while nothing plays, as `MadeBar.tsx` draws it; the player is one row. */
  $("#loopbar").classList.toggle("madebar", !player.loopId);
  if (shown) fitSelWords();
}

function renderLoopChip() {
  const loops = loopsIn(state.lang);
  const loop = player.loopId ? loopOf(player.loopId) : null;
  if (!loop) return `<button class="tb-btn loop-chip" id="chipOpen" aria-label="Loops" title="Loops">
    ${ICON.note}${loops.length ? `<span class="wide-only">${loops.length}</span>` : ""}</button>`;
  return `<span class="tb-btn loop-chip playing">
    <button class="loop-chip-play" id="chipPlay" aria-label="Play">${ICON.play}</button>
    <button class="loop-chip-what" id="chipOpen">
      <span class="loop-chip-word"></span><span class="loop-chip-at"></span>
    </button></span>`;
}

/* Everything that moves with the clock, and nothing else: re-rendering the surface sixty times a
   second would lose the scroll position, the focus and the animation all at once. Each write is
   guarded by a comparison, so a frame in which nothing changed touches no DOM. */
function paintLoops() {
  const loop = player.loopId ? loopOf(player.loopId) : null;
  const glyph = player.playing ? ICON.pause : ICON.play;
  ["#playPause", "#barPlay", "#chipPlay"].forEach((id) => {
    const button = $(id);
    if (button && button.dataset.glyph !== String(player.playing)) {
      button.dataset.glyph = String(player.playing);
      button.innerHTML = glyph;
      button.setAttribute("aria-label", player.playing ? "Pause" : "Play");
    }
  });
  if (!loop) return;

  const fraction = loop.durationSeconds ? player.at / loop.durationSeconds : 0;
  const percent = `${Math.max(0, Math.min(1, fraction)) * 100}%`;
  const fill = $(".seek-fill"); if (fill) fill.style.width = percent;
  const knob = $(".seek-knob"); if (knob) knob.style.left = percent;
  const at = $(".seek-times .at"); if (at && at.textContent !== clock(player.at)) at.textContent = clock(player.at);
  const line = $(".loopbar-line"); if (line) line.style.width = percent;

  const rows = loopItemsOf(loop.id);
  const cards = loopCards(loopCuesOf(loop.id));
  const moment = loopMomentAt(cards, player.at);
  document.querySelectorAll(".lyric-row").forEach((element, i) => {
    const want = i === moment.card ? "now" : i < moment.card ? "past" : "next";
    if (element.dataset.state !== want) {
      element.dataset.state = want;
      element.classList.toggle("now", want === "now");
      element.classList.toggle("past", want === "past");
      if (want === "now") element.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    element.querySelectorAll(".lyric-line").forEach((line, number) => {
      /* Said or not said, asked of the clock every frame — which is what makes a backwards drag put
         the answer away again rather than leaving it up because it was once shown. */
      const said = player.at >= Number(line.dataset.heard);
      if (line.dataset.said !== String(said)) {
        line.dataset.said = String(said);
        line.lastElementChild.outerHTML = said
          ? `<span class="lyric-said">${esc(line.dataset.text)}</span>`
          : '<span class="lyric-held"></span>';
      }
      /* Which line is sounding: colour, and nothing else. No weight, no size, no offset — so a
         screen left running for four minutes never reflows under the eye that glances at it. */
      line.classList.toggle("saying", i === moment.card && number === moment.sounding);
    });
  });

  const current = loopWordAt(rows, cards, player.at);
  const word = current ? current.sourceText : loopTitle(loop, 2);
  [".loopbar-title", ".loop-chip-word"].forEach((sel) => {
    const node = $(sel); if (node && node.textContent !== word) node.textContent = word;
  });
  const sub = $(".loopbar-sub");
  if (sub) {
    const text = `${clock(player.at)} / ${clock(loop.durationSeconds)}`;
    if (sub.textContent !== text) sub.textContent = text;
  }
  const chipAt = $(".loop-chip-at");
  if (chipAt && chipAt.textContent !== clock(player.at)) chipAt.textContent = clock(player.at);
}

/* ── make a loop ── */
function loopEligible() {
  return LEXEMES.filter((x) => x.language === state.lang && x.status !== "inbox" && x.primaryGloss
    && (state.topic === "all" || x.topics.includes(state.topic))).length;
}

/* The kind of loop — `LoopFormat.tsx` `FormatChoices`: the generator's formats as radio cards, the
   chosen one's switches beneath, and a card that this server cannot make saying why. */
function formatMissing(format) {
  return format.requires.filter((need) =>
    (need === "writer" && !LOOP_SCHEMA.writerAvailable) || (need === "multilingual_voice" && !LOOP_SCHEMA.mixesLanguages));
}

function formatSwitches(format) {
  const entries = Object.entries(format.switches);
  if (!entries.length) return "";
  return `<div class="format-switches">${entries.map(([name, spec]) => spec.choices
    ? `<div class="format-switch"><span>${esc(spec.label)}</span>
        <span class="seg" role="radiogroup" aria-label="${esc(spec.label)}">${spec.choices.map((choice) =>
          `<button type="button" role="radio" aria-checked="${choice === spec.default}" class="${choice === spec.default ? "on" : ""}">${esc(choice)}</button>`).join("")}</span></div>`
    : `<label class="format-switch"><input type="checkbox" name="switch-${name}"${spec.default ? " checked" : ""}><span>${esc(spec.label)}</span></label>`).join("")}</div>`;
}

function formatChoices(chosen = "classic") {
  return `<div class="format-choices">${LOOP_SCHEMA.formats.map((format) => {
    const missing = formatMissing(format);
    const usable = !missing.length || Boolean(format.fallback);
    const needs = missing.map((need) => NEEDS[need].what).join(" and ");
    const where = [...new Set(missing.map((need) => NEEDS[need].where))].join(" and ");
    const note = !missing.length ? "" : format.fallback
      ? `Falls back to ${formatLabel(format.fallback)} here: it needs ${needs} (${where}).`
      : `Needs ${needs} — set one up in ${where}.`;
    return `<label class="config-switch format-card${format.id === chosen ? " on" : ""}${usable ? "" : " off"}">
      <input type="radio" name="loop-format" value="${format.id}"${format.id === chosen ? " checked" : ""}${usable ? "" : " disabled"}>
      <span><strong>${esc(format.label)}</strong><span>${esc(format.description)}</span>${note
        ? `<span class="format-note warn">${esc(note)}</span>` : ""}</span>
    </label>`;
  }).join("")}${formatSwitches(LOOP_SCHEMA.formats.find((format) => format.id === chosen))}</div>`;
}

/* One choice in the dialog's list — `LoopMusic.tsx` `MusicChoices`. */
function musicChoice(value, name, about, on = false, extra = "") {
  return `<div class="music-choice${on ? " on" : ""}">
    <button type="button" role="radio" aria-checked="${on}" data-choice="${esc(value)}">
      <span class="music-name">${name}</span><span class="music-about">${esc(about)}</span></button>${extra}</div>`;
}

/* Where a dialog's words come from: the selection, or a random draw from what is on screen. The
   switch is there only when there is a selection; opened from the selection bar it starts on it, and
   from a surface's own Make button on the random draw, which is what that button always meant.

   In selection mode the words are drawn as chips in the order they were chosen. One the kind cannot
   use is dimmed and says why, and one past the limit is dimmed too — the first ones chosen are the
   ones used — so what will be sent is always exactly what is shown undimmed. */
const MAKE = {
  loop: { max: 24, usable: (w) => w.loopable, why: "no single term to say" },
  story: { max: 8, usable: () => true, why: "" }
};
function madeFrom(kind) {
  const rule = MAKE[kind];
  const words = picked();
  let used = 0;
  return words.map((w) => {
    if (!rule.usable(w)) return { ...w, skip: rule.why };
    used += 1;
    return used > rule.max ? { ...w, skip: `a ${kind} takes at most ${rule.max}` } : { ...w, skip: "" };
  });
}
function sourceBlock(kind, from, scopeHtml) {
  const words = madeFrom(kind);
  if (!words.length) return scopeHtml;
  const sel = from === "selection";
  const usable = words.filter((w) => !w.skip).length;
  const skipped = words.length - usable;
  const where = state.topic === "all" ? langOf(state.lang).name : `${langOf(state.lang).name} · ${topicOf(state.topic)?.name || "Inbox"}`;
  return `<div class="config-field"><span>Words</span>
      <div class="seg make-source" role="radiogroup" aria-label="Which words">
        <button type="button" role="radio" data-source="selection" aria-checked="${sel}" class="${sel ? "on" : ""}">Your selection · ${words.length}</button>
        <button type="button" role="radio" data-source="scope" aria-checked="${!sel}" class="${sel ? "" : "on"}">Random from ${esc(where)}</button>
      </div></div>
    <div data-pane="selection"${sel ? "" : " hidden"}>
      <div class="make-words">${words.map((w) => `<span class="make-chip${w.skip ? " skip" : ""}" lang="${state.lang}"${w.skip ? ` title="Left out: ${esc(w.skip)}"` : ""}>
        <span aria-hidden="true">${w.emoji || "\u{1F4C4}"}</span>${esc(w.headword)}</span>`).join("")}</div>
      ${skipped ? `<p class="config-help make-skip">${[...new Set(words.filter((w) => w.skip).map((w) => w.skip))].map((why) => {
        const names = words.filter((w) => w.skip === why).map((w) => `<i lang="${state.lang}">${esc(w.headword)}</i>`);
        return `Left out, ${esc(why)}: ${names.join(", ")}.`;
      }).join(" ")} ${usable ? `The ${kind} is made from the other ${usable}.` : `There is nothing left to make a ${kind} from.`}</p>` : ""}
    </div>
    <div data-pane="scope"${sel ? " hidden" : ""}>${scopeHtml}</div>`;
}
/* The dialog's own wiring for the switch: which pane shows, and what the button promises. */
function wireSource(node, kind, label) {
  const go = $(".make-go", node);
  const usable = madeFrom(kind).filter((w) => !w.skip).length;
  const paint = (source) => {
    node.querySelectorAll("[data-source]").forEach((b) => {
      const on = b.dataset.source === source;
      b.classList.toggle("on", on); b.setAttribute("aria-checked", String(on));
    });
    node.querySelectorAll("[data-pane]").forEach((pane) => { pane.hidden = pane.dataset.pane !== source; });
    const fromSelection = source === "selection" && node.querySelector("[data-source]");
    go.textContent = fromSelection ? `${label} from ${wordsCount(usable)}` : label;
    go.disabled = Boolean(fromSelection) && !usable;
  };
  node.querySelectorAll("[data-source]").forEach((b) => { b.onclick = () => paint(b.dataset.source); });
  paint(node.querySelector('[data-source].on')?.dataset.source || "scope");
}

function renderLoopDialog(from) {
  const eligible = loopEligible();
  const where = state.topic === "all" ? langOf(state.lang).name : `${langOf(state.lang).name} · ${topicOf(state.topic).name}`;
  const count = Math.min(12, Math.max(1, eligible));
  const scope = `<div class="loop-scope">${ICON.book}<span><b>${esc(where)}</b> · ${eligible} words can be in a loop</span></div>
        <label class="config-field"><span>How many words</span>
          <span class="loop-count">
            <input type="range" id="loopCount" min="4" max="${Math.max(4, Math.min(24, eligible))}" value="${count}">
            <output for="loopCount" id="loopCountOut">${count} words</output>
          </span></label>`;
  return `<div class="modal-backdrop" id="loopBackdrop">
    <section class="settings loop-dialog" role="dialog" aria-modal="true" aria-labelledby="loop-dialog-title">
      <header><h2 id="loop-dialog-title">Make a loop</h2>
        <button class="close" id="loopClose" aria-label="Close">×</button></header>
      <div class="settings-body">
        <p class="config-help">Your words, set to music with their translations.</p>
        ${sourceBlock("loop", from, scope)}
        <div class="config-field"><span>Kind of loop</span>${formatChoices(state.loopFormat || "classic")}</div>
        <div class="config-field"><span>Music</span>
          <div class="music-choices" role="radiogroup" aria-label="Music">
            ${musicChoice("surprise", "Surprise me", "New music, in any style", true)}
            ${BEDS.length ? '<div class="music-group label">Favourites</div>' : ""}
            ${BEDS.map((bed) => musicChoice(`bed:${bed.id}`, `${ICON.starOn}${esc(styleLabel(bed.styleId))}`, bedAbout(bed), false,
              loopOf(bed.sourceLoopId) ? `<button type="button" class="music-preview" aria-label="Hear this music">${ICON.play}</button>` : "")).join("")}
            <div class="music-group label">Styles</div>
            ${LOOP_SCHEMA.families.map((family) => musicChoice(family.id, esc(family.label), family.description)).join("")}
          </div></div>
        <p class="config-help">A word with no single term to say is not eligible: a loop has to
          choose one meaning, and <i>espolvorear</i> has none written down yet.</p>
        <div class="loop-engine">engine ${esc(LOOP_SCHEMA.engineVersion)} · ${
          LOOP_SCHEMA.productionBundle ? "sample pack installed" : "no sample pack — beds will be synthesised"}</div>
        <div class="loop-actions">
          <button class="tb-btn" id="loopCancel">Cancel</button>
          <button class="tb-btn primary make-go" id="loopGo">Make the loop</button>
        </div>
      </div>
    </section>
  </div>`;
}

function openModal(html) {
  const node = el(html);
  document.body.appendChild(node);
  const onKey = (ev) => { if (ev.key === "Escape") shut(); };
  const shut = () => { node.remove(); document.removeEventListener("keydown", onKey); };
  document.addEventListener("keydown", onKey);
  node.onmousedown = (ev) => { if (ev.target === node) shut(); };
  node.querySelectorAll(".close, [data-cancel]").forEach((b) => { b.onclick = shut; });
  return { node, shut };
}

function openLoopDialog(from = "scope") {
  const { node, shut } = openModal(renderLoopDialog(from));
  $("#loopCancel", node).onclick = shut;
  const range = $("#loopCount", node);
  range.oninput = () => { $("#loopCountOut", node).textContent = `${range.value} words`; };
  $(".music-choices", node).onclick = (ev) => {
    const choice = ev.target.closest("[data-choice]");
    if (ev.target.closest(".music-preview")) { toast("Plays the loop this music was kept from — prototype only"); return; }
    if (!choice) return;
    node.querySelectorAll(".music-choice").forEach((one) => {
      const on = one.contains(choice);
      one.classList.toggle("on", on);
      one.querySelector("[data-choice]").setAttribute("aria-checked", String(on));
    });
  };
  const wireFormats = () => {
    $(".format-choices", node).onchange = (ev) => {
      if (ev.target.name !== "loop-format") return;
      state.loopFormat = ev.target.value;
      $(".format-choices", node).outerHTML = formatChoices(state.loopFormat);
      wireFormats();
    };
    $(".format-choices", node).onclick = (ev) => {
      const segment = ev.target.closest(".seg button");
      if (!segment) return;
      segment.parentElement.querySelectorAll("button").forEach((one) => {
        one.classList.toggle("on", one === segment);
        one.setAttribute("aria-checked", String(one === segment));
      });
    };
  };
  wireFormats();
  wireSource(node, "loop", "Make the loop");
  $("#loopGo", node).onclick = () => { shut(); toast("Asked for a loop — prototype only, nothing was made"); };
}

/* Make a story — `StoryDialog.tsx`, which the prototype had not drawn until it had a selection to
   show. The kind and the pictures are the application's two selects; their options here are a
   sample. */
function openStoryDialog(from = "scope") {
  const where = state.topic === "all" ? langOf(state.lang).name : `${langOf(state.lang).name} · ${topicOf(state.topic)?.name || "Inbox"}`;
  const eligible = visible().length;
  const scope = `<div class="loop-scope">${ICON.book}<span><b>${esc(where)}</b> · ${eligible} words can be in a story</span></div>
        <label class="config-field"><span>How many words</span>
          <span class="loop-count">
            <input type="range" id="storyCount" min="1" max="${Math.max(1, Math.min(8, eligible))}" value="3">
            <output for="storyCount" id="storyCountOut">3 words</output>
          </span></label>`;
  const { node, shut } = openModal(`<div class="modal-backdrop">
    <section class="settings loop-dialog" role="dialog" aria-modal="true" aria-labelledby="story-dialog-title">
      <header><h2 id="story-dialog-title">Make a story</h2>
        <button class="close" aria-label="Close">×</button></header>
      <div class="settings-body">
        <p class="config-help">A few of your words, told back to you as a short illustrated story you
          can read in a couple of minutes.</p>
        ${sourceBlock("story", from, scope)}
        <label class="config-field"><span>Kind of story</span>
          <select><option>Surprise me</option><option>\u{1F9ED} An adventure</option><option>\u{1F52C} How it was invented</option></select></label>
        <label class="config-field"><span>Pictures</span>
          <select><option>To suit the story</option><option>Watercolour</option><option>Photograph</option></select></label>
        <label class="config-field"><span>Anything else? <em>(optional)</em></span>
          <textarea rows="3" maxlength="1000" placeholder="Set it on a night train, tell it from the dog’s side, keep it gentle…"></textarea></label>
        <p class="config-help">Every word you choose has to earn its place in the story, so a few work
          better than many. All the pictures are drawn in one style, so the story looks like one thing.</p>
        <div class="loop-actions">
          <button class="tb-btn" data-cancel>Cancel</button>
          <button class="tb-btn primary make-go" id="storyGo">Make the story</button>
        </div>
      </div>
    </section>
  </div>`);
  const range = $("#storyCount", node);
  range.oninput = () => { $("#storyCountOut", node).textContent = wordsCount(Number(range.value)); };
  wireSource(node, "story", "Make the story");
  $("#storyGo", node).onclick = () => { shut(); toast("Asked for a story — prototype only, nothing was made"); };
}

/* ── wiring ──
   Delegated from the pane, the bar and the top bar, so a re-render never leaves a dead handler. */
function wireLoops() {
  const seek = $("#seek");
  if (seek) {
    const to = (ev) => {
      const loop = loopOf(player.loopId);
      const box = seek.getBoundingClientRect();
      const x = (ev.touches ? ev.touches[0].clientX : ev.clientX) - box.left;
      loopSeek((Math.max(0, Math.min(1, x / box.width))) * loop.durationSeconds);
    };
    const move = (ev) => { ev.preventDefault(); to(ev); };
    const up = () => {
      player.scrubbing = false;
      removeEventListener("pointermove", move); removeEventListener("pointerup", up);
    };
    seek.onpointerdown = (ev) => {
      player.scrubbing = true; to(ev);
      addEventListener("pointermove", move); addEventListener("pointerup", up);
    };
    seek.onkeydown = (ev) => {
      if (ev.key === "ArrowRight") loopSeek(player.at + 5);
      else if (ev.key === "ArrowLeft") loopSeek(player.at - 5);
    };
  }
  paintLoops();
}

function openLoops() {
  state.loops = true; state.map = false; state.openId = null; state.openExt = null; state.add = false;
  render();
}

$("#main").addEventListener("click", (ev) => {
  const row = ev.target.closest(".lyric-row");
  if (row) { loopSeek(Number(row.dataset.seek)); if (!player.playing) loopPlay(); return; }
  const step = ev.target.closest("[data-step]");
  if (step) { loopStep(Number(step.dataset.step)); return; }
  const flip = ev.target.closest("[data-switch]");
  if (flip) {
    player[flip.dataset.switch] = !player[flip.dataset.switch];
    flip.classList.toggle("on", player[flip.dataset.switch]);
    flip.setAttribute("aria-pressed", String(player[flip.dataset.switch]));
    return;
  }
  if (ev.target.closest("#playPause")) { player.playing ? loopPause() : loopPlay(); return; }
  if (ev.target.closest("#bedName")) { state.musicMenu = !state.musicMenu; render(); return; }
  if (ev.target.closest("#bedStar")) {
    const loop = loopOf(state.loopOpen);
    const kept = bedOfLoop(loop);
    if (kept) BEDS.splice(BEDS.indexOf(kept), 1);
    else BEDS.unshift({ id: `bd${Date.now()}`, styleId: loop.styleId, seed: loop.seed, sourceLoopId: loop.id, createdAt: "2026-09-23" });
    toast(kept ? "No longer a favourite" : "Kept — offered next time you make a loop");
    render();
    return;
  }
  const music = ev.target.closest("[data-music]");
  if (music) {
    state.musicMenu = false; state.remaking = state.loopOpen;
    toast("Making new music — it takes a few minutes (prototype only)");
    render();
    return;
  }
  const open = ev.target.closest("[data-loop]");
  if (open) {
    state.loopOpen = open.dataset.loop;
    if (open.dataset.loop !== player.loopId) loopLoad(open.dataset.loop, { play: true });
    else if (!player.playing) loopPlay();
    render();
    return;
  }
  const drop = ev.target.closest("[data-loop-delete]");
  if (drop) {
    const id = drop.dataset.loopDelete;
    const items = new Set(LOOP_ITEMS.filter((row) => row.loopId === id).map((row) => row.id));
    LOOPS.splice(LOOPS.findIndex((row) => row.id === id), 1);
    for (let index = LOOP_ITEMS.length - 1; index >= 0; index -= 1) {
      if (items.has(LOOP_ITEMS[index].id)) LOOP_ITEMS.splice(index, 1);
    }
    state.rowMenu = null;
    if (state.loopOpen === id) state.loopOpen = null;
    render();
    return;
  }
  const dropStory = ev.target.closest("[data-story-delete]");
  if (dropStory) {
    const id = dropStory.dataset.storyDelete;
    STORIES.splice(STORIES.findIndex((row) => row.id === id), 1);
    state.rowMenu = null;
    render();
    toast("Deleted everywhere \u2014 the pictures are gone too");
    return;
  }
  /* A word's row actions. Selecting re-renders the list, which also puts a swiped row back where it
     was, so the mark it now wears is the first thing seen. */
  const pick = ev.target.closest("[data-pick]");
  if (pick) { state.rowMenu = null; togglePick(pick.dataset.pick); return; }
  const dropWord = ev.target.closest("[data-word-delete]");
  if (dropWord) {
    const id = dropWord.dataset.wordDelete;
    LEXEMES.splice(LEXEMES.findIndex((row) => row.id === id), 1);
    Object.keys(picks).forEach((lang) => { picks[lang] = picks[lang].filter((key) => key !== id); });
    state.rowMenu = null;
    render();
    toast("Deleted everywhere \u2014 the entry is kept as a tombstone");
    return;
  }
  if (ev.target.closest("#makeLoop")) { openLoopDialog(); return; }
  if (ev.target.closest("#makeStory")) { openStoryDialog(); return; }
  if (ev.target.closest("#loopBack")) { state.loopOpen = null; render(); return; }
  if (ev.target.closest("#loopsClose")) { state.loops = false; state.loopOpen = null; render(); }
  if (ev.target.closest("#storiesClose")) { state.stories = false; state.storyOpen = null; render(); return; }
  if (ev.target.closest("#storyBack")) { state.storyOpen = null; state.storyAt = 0; render(); return; }
  const storyStep = ev.target.closest("[data-story-step]");
  if (storyStep) { goStory(state.storyAt + Number(storyStep.dataset.storyStep)); return; }
  const reveal = ev.target.closest("[data-reveal]");
  if (reveal) { state.storyShown[reveal.dataset.reveal] = true; render(); return; }
  const hide = ev.target.closest("[data-hide]");
  if (hide) { delete state.storyShown[hide.dataset.hide]; render(); return; }
  const storyRowEl = ev.target.closest("[data-story]");
  if (storyRowEl) {
    if (partsOf(storyRowEl.dataset.story).length) {
      state.storyOpen = storyRowEl.dataset.story; state.storyAt = 0; render();
    }
    return;
  }
  if (state.rowMenu) { state.rowMenu = null; render(); }
});

/* A right-click on any row with actions — a word, a loop or a story — opens its menu under the
   pointer. The list is `#pane` and the surfaces are `#composer`; both are inside `#main`. */
$("#main").addEventListener("contextmenu", (ev) => {
  const item = ev.target.closest("[data-row-menu]");
  if (!item) return;
  ev.preventDefault();
  const box = item.getBoundingClientRect();
  state.rowMenu = item.dataset.rowMenu;
  state.rowMenuAt = { x: ev.clientX - box.left, y: ev.clientY - box.top };
  render();
});

function wireLoopControls(root) {
  root.addEventListener("click", (ev) => {
    if (ev.target.closest("#barPlay") || ev.target.closest("#chipPlay")) {
      player.playing ? loopPause() : loopPlay();
      return;
    }
    /* Stops the loop and forgets it as the one playing; the loop itself is untouched. */
    if (ev.target.closest("#barClose")) {
      loopPause();
      player.loopId = null;
      player.at = 0;
      render();
      return;
    }
    if (ev.target.closest("#openStories")) { openStories(); return; }
    if (ev.target.closest("#openMap")) { openMap(); return; }
    if (ev.target.closest("#openLoops") || ev.target.closest("#chipOpen")) {
      state.loopOpen = player.loopId;
      openLoops();
    }
  });
}
wireLoopControls($("#loopbar"));
wireLoopControls($("#loopChip"));

/* ── render ──────────────────────────────────────────────────────────── */

function render() {
  // The sheet belongs to the text it was opened over, and that text is about to be drawn again.
  forgetLook();
  /* Reading a word on a phone or tablet does not need the topic strip, and it cost a whole row. A
     loop does not need it either: a topic files a *word*, and nothing on that surface is filed. */
  $("#main").classList.remove("cards-on");
  renderRail();
  renderLangButton();
  const main = $("#pane");
  const x = state.openId ? LEXEMES.find((y) => y.id === state.openId) : null;

  // A composer owns the height and scrolls itself, so the region around it must not also scroll.
  // The loops surface is one of those: its controls are a footer that must not drift.
  const composing = state.add || state.loops || state.stories || state.map || Boolean(x && state.mode === "edit");
  $("#main").classList.toggle("composing", composing);
  /* The loops bar is a row of `.app`, so `.app` is what carries whether it is wanted: over the list
     and nowhere else. `.main` keeps its own `composing` because it is the thing that stops scrolling. */
  $(".app").classList.toggle("composing", composing);
  // Not `&& !composing`: the loops surface *is* a composing surface — it owns its height so its
  // controls cannot drift — and excluding it here left the rail on screen behind the player.
  $(".app").classList.toggle("loops-open", state.loops || state.stories || state.map);
  $(".app").classList.toggle("adding", Boolean(state.add));
  // The map's own row is the top one: search, Add and sync are one Back away, and on a map the height
  // they took is worth more than they are.
  $(".app").classList.toggle("map-open", state.map);
  $(".app").classList.toggle("article-open", Boolean((state.openId || state.openExt) && !state.add));
  $("#loopbar").innerHTML = renderLoopBar();
  $("#loopChip").innerHTML = renderLoopChip();
  paintSelBar();
  paintLoops();
  $("#paneWrap").style.display = composing ? "none" : "";
  $("#composer").style.display = composing ? "" : "none";
  if (!state.map) teardownMap();
  if (state.map) {
    // A surface of its own, as Loops and Stories are: it replaces the list and owns the height.
    renderMap();
    document.title = "Map — Acervo";
    return;
  }
  if (state.stories) {
    // Its own surface for the reason the loops one is: a thing you go to, needing the whole column.
    $("#composer").innerHTML = renderStories();
    fitStoryWords();
    wireStories();
    document.title = "Stories — Acervo";
    return;
  }
  if (state.loops) {
    // Its own surface rather than a sheet over the list: a player is a place you go to, and the
    // words it shows need the whole column.
    $("#composer").innerHTML = renderLoops();
    wireLoops();
    document.title = "Loops — Acervo";
    return;
  }
  if (state.add) { renderSheet(); document.title = "Add a word — Acervo"; return; }
  if (x && state.mode === "edit") {
    $("#composer").innerHTML = renderEdit(x);
    wireEditor();
    document.title = `${x.headword} — Acervo`;
    return;
  }
  $("#composer").innerHTML = "";

  const ext = state.openExt ? externalOf(state.openExt) : null;
  if (ext) {
    // An external entry replaces the list the way one of yours does, and reads in the same column.
    $("#artBar").style.display = "";
    $("#artBar").innerHTML = `<button class="icon-btn" id="backBtn" aria-label="Back to the list">${ICON.back}</button>`
      + '<span class="label">Other dictionaries</span><span class="spacer"></span>';
    main.innerHTML = renderExternalArticle(ext);
    document.title = `${ext.word} — Acervo`;
    return;
  }

  if (!x) {
    $("#artBar").style.display = "none";
    main.innerHTML = renderList();
  } else {
    // A word still filling in is read on the page, where the reserved slots keep it still.
    const filling = Boolean(fillingOf(x));
    const view = state.mode === "read" ? (filling ? "page" : currentView()) : null;
    const cardsOff = filling ? ' disabled title="Cards open when pictures and clips are ready"' : "";
    $("#artBar").style.display = "";
    $("#artBar").innerHTML = `
      <button class="icon-btn" id="backBtn" aria-label="Back to the list">${ICON.back}</button>
      <span class="label art-where">${esc(state.topic === "all" ? "All words" : state.topic === "inbox" ? "Inbox" : topicOf(state.topic).name)}</span>
      ${view === "cards" ? `<div class="art-title"><span class="art-title-word" data-length="${x.headword.length > 24 ? "long" : x.headword.length > 14 ? "mid" : "short"}">${esc(x.headword)}</span>${say(x.headword, "always head")}</div>` : ""}
      <span class="spacer"></span>
      <div class="seg art-views">
        <button data-view="page" class="${view === "page" ? "on" : ""}">Page</button>
        <button data-view="cards" class="${view === "cards" ? "on" : ""}"${cardsOff}>Cards</button>
        <button data-mode="yaml" class="${state.mode === "yaml" ? "on" : ""}">YAML</button>
      </div>
      ${state.mode === "yaml" ? `<button class="icon-btn" id="editBtn" aria-label="Edit as YAML" title="Edit as YAML">${ICON.pencil}</button>` : ""}
      ${x.status === "inbox" ? `<button class="icon-btn art-file" id="fileBtn" aria-label="File it" title="File it \u2014 out of the Inbox">${ICON.file}</button>` : ""}
      <button class="icon-btn art-pick${isPicked(x.id) ? " on" : ""}" id="pickBtn" aria-pressed="${isPicked(x.id)}"
        aria-label="${isPicked(x.id) ? "Remove from selection" : "Add to selection"}" title="${isPicked(x.id) ? "In your selection \u2014 remove it" : "Add to selection"}">${isPicked(x.id) ? ICON.selected : ICON.select}</button>
      <button class="icon-btn art-delete" id="delBtn" aria-label="Delete" title="Delete">${ICON.trash}</button>
      <div class="art-more">
        <button class="icon-btn" id="moreBtn" aria-label="Article menu">${ICON.more}</button>
        <div class="menu" id="articleMenu">
          <button data-view="page" class="${view === "page" ? "on" : ""}">Page</button>
          <button data-view="cards" class="${view === "cards" ? "on" : ""}"${cardsOff}>Cards</button>
          <button data-mode="yaml" class="${state.mode === "yaml" ? "on" : ""}">YAML</button>
          <div class="menu-sep"></div>
          ${x.status === "inbox" ? '<button id="fileBtn2">File it</button>' : ""}
          <button id="pickBtn2">${isPicked(x.id) ? "Remove from selection" : "Add to selection"}</button>
          <button id="delBtn2" class="danger">Delete this word</button>
        </div>
      </div>`;
    $("#artBar").classList.toggle("carding", view === "cards");
    // Editing is a composer above, so only reading and the read-only projection get here.
    main.innerHTML = view === "cards" ? renderCards(x)
      : view === "page" ? progressStrip(x) + renderArticle(x) : renderYaml(x);
    // The conversation belongs to Page: an edit that reorders senses needs every sense in view.
    $("#askSlot").innerHTML = view === "page" ? renderAsk(x) : "";
    $("#main").classList.toggle("cards-on", view === "cards");
    // At its largest the conversation takes the pane: the article is not drawn, rather than left as
    // a one-line strip above the sheet.
    $("#paneWrap").classList.toggle("ask-only", state.ask === "full" && view === "page");
    if (view === "cards") wireCards();
  }
  document.title = x ? `${x.headword} — Acervo` : "Acervo";
}

/* ── wiring ──────────────────────────────────────────────────────────── */

function wireEditor() {
  const area = wireSurface("edit");
  $("#closeEdit").onclick = () => { state.mode = "read"; render(); };
  $("#cancelEdit").onclick = () => { state.mode = "read"; render(); };
  $("#saveEdit").onclick = () => {
    const ok = showValidation("#validation", validate(area.value));
    if (ok) { toast("Saved — prototype only, nothing was written"); state.mode = "read"; setTimeout(render, 250); }
  };
}

function wireSheet() {
  $("#composer").querySelectorAll("[data-tab]").forEach((b) => { b.onclick = () => { addTab = b.dataset.tab; renderSheet(); }; });
  const close = () => closeSheet();
  const c1 = $("#closeSheet"), c2 = $("#closeSheet2");
  if (c1) c1.onclick = close;
  if (c2) c2.onclick = close;
  const sw = $("#switchYaml"); if (sw) sw.onclick = () => { addTab = "yaml"; renderSheet(); };
  const pb = $("#processBtn");
  // The real app calls the capture route and lands on the rendered proposal. Here there is nothing
  // to call, so a canned entry stands in for one — the point being the surface, not the generation.
  if (pb) pb.onclick = () => {
    addDraft = LEXEMES[0];
    addTab = "article";
    renderSheet();
    toast("Generation is not wired up in this prototype — showing a stand-in entry");
  };
  const sd = $("#saveDraft");
  if (sd) sd.onclick = () => { toast("Saved to Inbox — prototype only"); setTimeout(closeSheet, 500); };
  const read = () => { photoStage = "read"; renderSheet(); };
  if ($("#photoTake")) $("#photoTake").onclick = () => { read(); toast("The camera is not wired up in this prototype — showing a photo"); };
  if ($("#photoChoose")) $("#photoChoose").onclick = () => { photoStage = "screenshot"; renderSheet(); };
  const square = $("#photoSquare");
  if (square) {
    const measure = () => {
      const tall = square.scrollHeight > square.clientHeight + 2;
      $("#photoWindow").classList.toggle("more-above", tall && square.scrollTop > 2);
      $("#photoWindow").classList.toggle("more-below", tall && square.scrollTop + square.clientHeight < square.scrollHeight - 2);
      if (square.scrollTop > 2) $("#photoHint")?.remove();
    };
    square.onscroll = measure;
    square.querySelector("img").onload = measure;
    measure();
  }
  if ($("#photoAnother")) $("#photoAnother").onclick = () => { photoStage = "idle"; renderSheet(); };
  if ($("#photoKeep")) $("#photoKeep").onchange = (event) => { photoKeep = event.target.checked; };
  $("#composer").querySelectorAll("[data-photo-source]").forEach((b) => {
    b.onclick = () => { photoSource = b.dataset.photoSource; renderSheet(); };
  });
  if ($("#photoAdd")) $("#photoAdd").onclick = () => {
    addDraft = LEXEMES[0];
    addTab = "article";
    renderSheet();
    toast("Generation is not wired up in this prototype — showing a stand-in entry");
  };
  if ($("#newArea")) {
    const na = wireSurface("new");
    $("#saveNew").onclick = () => {
      if (showValidation("#newValidation", validate(na.value))) { toast("Saved to Inbox — prototype only"); setTimeout(closeSheet, 500); }
    };
  }
}

document.addEventListener("focusin", (ev) => {
  // Focusing the composer opens the sheet to the half detent, which is where a phone starts.
  if (ev.target.closest(".ask-input") && state.ask === "dock") { state.ask = "open"; render(); }
});

document.addEventListener("click", (ev) => {
  const t = ev.target;
  const hit = (sel) => t.closest(sel);

  const fold = hit(".sec-toggle");
  if (fold) {
    const sec = fold.closest(".sec");
    const shut = !sec.classList.contains("folded");
    sec.classList.toggle("folded", shut);
    fold.setAttribute("aria-expanded", String(!shut));
    folded.set(sec.dataset.fold, shut);
    return;
  }
  const viewBtn = hit("[data-view]");
  if (viewBtn) { state.mode = "read"; state.view = viewBtn.dataset.view; render(); $("#main").scrollTop = 0; return; }
  const goBtn = hit("[data-go]");
  if (goBtn) { goCard(Number(goBtn.dataset.go)); return; }
  const stepBtn = hit("[data-step]");
  if (stepBtn) { goCard(state.card + Number(stepBtn.dataset.step)); return; }
  const kept = hit("[data-photo]");
  if (kept) { openPhotoViewer(kept.dataset.photo); return; }
  if (hit("#photoViewerClose") || (t.id === "photoViewerBackdrop")) { $("#photoViewerBackdrop")?.remove(); return; }
  if (hit("[data-picture]")) { toast("The picture dialog is out of scope for this spike"); return; }

  if (hit("[data-map-open]")) { openMap(); return; }
  const topicBtn = hit("[data-topic]");
  if (topicBtn) { state.map = false; state.mapReturn = false; state.topic = topicBtn.dataset.topic; state.openId = null; state.query = ""; $("#q").value = ""; $("#search").classList.remove("searching"); render(); return; }

  const sortBtn = hit("[data-sort]");
  if (sortBtn) { state.sort = sortBtn.dataset.sort; render(); return; }

  const openBtn = hit("[data-open]");
  if (openBtn) { state.openId = openBtn.dataset.open; state.openExt = null; state.mode = "read"; state.card = 0; render(); $("#main").scrollTop = 0; return; }

  const extBtn = hit("[data-ext]");
  if (extBtn) { state.openExt = extBtn.dataset.ext; state.openId = null; render(); $("#main").scrollTop = 0; return; }

  /* The dock's three detents, so the design can actually be looked at at each of them. Focusing
     the composer opens it, the grabber steps it, and the close button returns it to a bar — the
     same transitions `AskDock.tsx` makes. Nothing here talks to a server. */
  if (hit(".ask-grab")) { state.ask = state.ask === "full" ? "open" : "full"; render(); return; }
  if (hit(".ask .icon-btn")) { state.ask = "dock"; render(); return; }
  if (hit(".ask-send")) { toast("One turn of conversation — not wired up in the prototype"); return; }
  if (hit("#discardBtn")) { state.review = false; render(); return; }
  if (hit("#saveProposal")) { state.review = false; toast("Saved to the server — not wired up in the prototype"); render(); return; }
  // The card's Review button is what puts the article into the marked state.
  if (hit(".ask-card .tb-btn")) { state.review = true; state.ask = "dock"; render(); $("#main").scrollTop = 0; return; }
  if (hit(".ask-chip")) { state.askFocus = null; render(); return; }
  /* Show this meaning on the map: the map opens flown to it and with it selected, as Find would. The
     prototype's articles and its map are separate fixtures, so a word the map does not hold says so. */
  const showOnMap = hit("[data-map-show]");
  if (showOnMap) {
    const d = mapData();
    const want = fold(showOnMap.dataset.mapShow);
    const order = Number(showOnMap.dataset.mapOrder);
    const found = d ? d.points.findIndex((p) => fold(p.headword) === want && p.order === order) : -1;
    const i = found >= 0 ? found : d ? d.points.findIndex((p) => fold(p.headword) === want) : -1;
    if (i < 0) { toast("This word is not on the prototype's map"); return; }
    state.mapSel = i;
    mapGrown.add(state.lang);
    openMap();
    meaningMap && meaningMap.select(i, { fly: true });
    return;
  }
  if (hit(".ask-anchor")) {
    const section = t.closest(".sec");
    const number = section ? section.querySelector(".num")?.textContent?.trim() : null;
    state.askFocus = number ? `sense ${Number(number)}` : "this block";
    state.ask = "open";
    render();
    return;
  }

  const jump = hit("[data-jump]");
  if (jump) { const target = document.getElementById(jump.dataset.jump);
              if (target) target.scrollIntoView({ behavior: "smooth", block: "start" }); return; }

  if (hit("#extAdd")) { toast("Builds the entry from what you are reading — not wired up in the prototype"); return; }
  if (hit("#onlineBtn")) { state.onlineDone = true; render(); return; }

  if (hit("#scopeBtn")) { $("#scopeMenu").classList.toggle("open"); return; }
  const scopeItem = hit("[data-scope]");
  if (scopeItem) {
    state.scope[scopeItem.dataset.scope] = scopeItem.checked;
    scopeItem.closest("label").classList.toggle("on", scopeItem.checked);
    $("#scopeBtn").textContent = `yours +${Object.values(state.scope).filter(Boolean).length}`;
    render(); return;
  }
  if (!hit("#scopeMenu")) $("#scopeMenu").classList.remove("open");

  if (hit("#backBtn")) {
    state.openId = null; state.openExt = null;
    // Opened from the map: Back goes back to it, where it was left, with the peek still open.
    if (state.mapReturn) { state.mapReturn = false; state.map = true; }
    backToReading();
    render(); return;
  }

  const modeBtn = hit("[data-mode]");
  if (modeBtn) { state.mode = modeBtn.dataset.mode; render(); return; }

  if (hit("#editBtn")) { state.mode = "edit"; render(); return; }
  if (hit("#moreBtn")) { $("#articleMenu").classList.toggle("open"); return; }
  if (hit("#delBtn2")) { toast("Delete writes a tombstone — not wired up in the prototype"); return; }
  if (hit("#delBtn"))  { toast("Delete writes a tombstone — not wired up in the prototype"); return; }
  /* Filing is wired up for real, unlike Delete: it is one field, and what it does to the rail and
     the counts is the whole thing worth looking at. */
  if (hit("#fileBtn") || hit("#fileBtn2")) { fileWords([state.openId]); return; }
  if (hit("#pickBtn") || hit("#pickBtn2")) { togglePick(state.openId); return; }
  if (hit("#fileAllBtn")) { fileWords(visible().map((x) => x.id)); return; }

  if (hit("[data-add-picture]")) { toast("Opens the picture dialog — brief, Draw, or your own picture"); return; }
  const say = hit("[data-say]");
  if (say) {
    say.classList.add("playing");
    setTimeout(() => say.classList.remove("playing"), 1100);
    toast(`♪ ${say.dataset.say}`);
    return;
  }
  if (hit("[data-clip]")) { toast("Opens the clip dialog — removing a clip moves there"); return; }

  if (hit("#addBtn")) { openSheet("capture"); return; }

  if (hit("#langBtn")) { $("#langMenu").classList.toggle("open"); return; }
  const langItem = hit("[data-lang]");
  if (langItem) {
    state.lang = langItem.dataset.lang; state.topic = "all"; state.openId = null; state.mapSel = -1;
    $("#langMenu").classList.remove("open"); render(); return;
  }
  $("#langMenu").classList.remove("open");
});

$("#q").addEventListener("input", (ev) => {
  state.loops = false;
  state.map = false;
  state.query = ev.target.value;
  state.openId = null;
  state.openExt = null;
  // ⏎ is the only thing that reaches an online source, so typing always puts that back.
  state.onlineDone = false;
  $("#search").classList.toggle("searching", state.query.trim().length > 0);
  
render();
});

document.addEventListener("keydown", (ev) => {
  if ((ev.metaKey || ev.ctrlKey) && ev.key === "k") {
    ev.preventDefault();
    // Search lives in the bar the map hides, so ⌘K leaves the map for it, as it leaves Loops.
    if (state.map) closeMap();
    $("#q").focus(); $("#q").select();
  }
  const typing = ev.target.closest && ev.target.closest("input, textarea, [contenteditable]");
  const reading = state.openId && !state.add && state.mode === "read";
  /* Select all selects the word, not the application around it: copying an article somewhere else
     is worth keeping, and the top bar, the Add button and the dock are not part of it. */
  if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "a" && reading && !typing) {
    ev.preventDefault();
    const target = currentView() === "cards" ? $("#cardsTrack").children[state.card] : $("#pane");
    const range = document.createRange();
    range.selectNodeContents(target);
    getSelection().removeAllRanges();
    getSelection().addRange(range);
    return;
  }
  if ((ev.key === "ArrowLeft" || ev.key === "ArrowRight") && state.stories && state.storyOpen && !typing) {
    ev.preventDefault();
    goStory(state.storyAt + (ev.key === "ArrowRight" ? 1 : -1));
    return;
  }
  if ((ev.key === "ArrowLeft" || ev.key === "ArrowRight") && reading && !typing && currentView() === "cards") {
    ev.preventDefault();
    goCard(state.card + (ev.key === "ArrowRight" ? 1 : -1));
    return;
  }
  // Innermost first: leave what you are composing before leaving the entry it belongs to.
  if (ev.key === "Escape") {
    if (look) { closeLook(); return; }
    if (state.rowMenu || state.selList) { state.rowMenu = null; state.selList = false; render(); return; }
    if (state.add) closeSheet();
    else if (state.mode === "edit") { state.mode = "read"; render(); }
    else if (state.openExt) { state.openExt = null; render(); }
    else if (state.openId) {
      state.openId = null;
      if (state.mapReturn) { state.mapReturn = false; state.map = true; }
      backToReading();
      render();
    }
    /* Innermost first here too: put the peek away, then leave the map. */
    else if (state.map && !typing) {
      if (state.mapSel >= 0) { state.mapSel = -1; if (meaningMap) meaningMap.select(-1); paintPeek(); }
      else closeMap();
    }
  }
});

/* ── device preview harness (prototype only) ─────────────────────────── */
function setTheme(mode) {
  if (mode === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = mode;
  $("#themeBtn").textContent = mode === "auto" ? "Theme" : mode === "dark" ? "Dark" : "Light";
  $("#themeBtn").classList.toggle("on", mode !== "auto");
}

function paintSwitches() {
  $("#viewBtn").textContent = `View: ${state.view || "auto"}`;
  $("#viewBtn").classList.toggle("on", Boolean(state.view));
  $("#trBtn").classList.toggle("on", state.sayTranslations);
  $("#layoutBtn").classList.toggle("on", state.loops);
  $("#storyBtn").classList.toggle("on", state.stories);
  $("#speedBtn").textContent = `${player.speed}×`;
  $("#mapBtn").classList.toggle("on", state.map);
  $("#mapStyleBtn").textContent = `Style: ${state.mapStyle}`;
  $("#mapLabelsBtn").textContent = `Labels: ${state.mapLabels}`;
  $("#mapSampleBtn").classList.toggle("on", mapSource() === "sample");
  $("#mapSampleBtn").disabled = !window.MAP_LOCAL;
  $("#speedBtn").classList.toggle("on", player.speed !== 1);
}

$("#harness").addEventListener("click", (ev) => {
  const b = ev.target.closest("button"); if (!b) return;
  if (b.id === "themeBtn") {
    const now = document.documentElement.dataset.theme;
    setTheme(now === "dark" ? "light" : now === "light" ? "auto" : "dark");
    return;
  }
  /* Stand-ins for Settings ▸ default article view, and for listening to translations. */
  if (b.id === "viewBtn") { state.view = state.view === null ? "page" : state.view === "page" ? "cards" : null; }
  else if (b.id === "trBtn") { state.sayTranslations = !state.sayTranslations; }
  else if (b.id === "layoutBtn") { if (state.loops) { state.loops = false; state.loopOpen = null; } else openLoops(); }
  else if (b.id === "storyBtn") { if (state.stories) { state.stories = false; state.storyOpen = null; } else openStories(); }
  /* A word takes twenty-two seconds in a real loop. Watching the reveal at that rate is the right
     test of the *rhythm* and a poor test of everything else, so the clock can be wound on. */
  /* The map's open questions, answered by looking: which of the three looks, and which of the three
     ways of naming a region. Update replays a new layout arriving; Sample forces the committed
     fixture when the owner's real one is present. */
  else if (b.id === "mapBtn") { if (state.map) { closeMap(); paintSwitches(); return; } openMap(); }
  else if (b.id === "mapStyleBtn") {
    state.mapStyle = MAP_STYLES[(MAP_STYLES.indexOf(state.mapStyle) + 1) % MAP_STYLES.length];
    if (meaningMap) meaningMap.setStyle(state.mapStyle);
    paintSwitches(); return;
  }
  else if (b.id === "mapLabelsBtn") {
    state.mapLabels = MAP_LABELS[(MAP_LABELS.indexOf(state.mapLabels) + 1) % MAP_LABELS.length];
    if (meaningMap) meaningMap.setLabels(state.mapLabels);
    paintSwitches(); return;
  }
  else if (b.id === "mapUpdateBtn") { if (!state.map) openMap(); playMapUpdate(); paintSwitches(); return; }
  else if (b.id === "mapSampleBtn") { state.mapSample = !state.mapSample; state.mapSel = -1; delete mapCameras[state.lang]; mapGrown.delete(state.lang); }
  else if (b.id === "speedBtn") { player.speed = player.speed === 1 ? 4 : player.speed === 4 ? 12 : 1; }
  else if (b.dataset.frame) {
    document.body.className = b.dataset.frame === "desktop" ? "" : `framed ${b.dataset.frame}`;
    $("#harness").querySelectorAll("button[data-frame]").forEach((x) => x.classList.toggle("on", x === b));
  }
  paintSwitches();
  render();
});

/* ── look a word up ──────────────────────────────────────────────────────
   A tap on a word in the language being learned — in a story, on a loop's card, in an article —
   says what it means in that sentence, in a sheet at the foot of the surface. **The tap moves
   nothing**: a story does not start reading and a loop does not seek, because the owner tapped a
   word to understand it, and whatever the tap used to do is a button on the sheet instead. Anything
   that is not such a word keeps its tap, so a loop's translation line and a card's edge still seek.

   A word you hold is answered from your own words, at once and offline, with the way to its
   article; any other is asked of the server's quick look-up, as a photographed word is, and Add
   files it in the Inbox without leaving what you are reading. Every answer here is a stub. */

/* Where a tap may look up, per surface: text in the language being learned, and nothing else. */
const LOOK_BLOCKS = {
  story: ".story-text",
  loop: ".lyric-source .lyric-said",
  article: "#pane .t, #pane .sense-def"
};

/* What the quick look-up would answer, by the tapped word. The tap is a pointer, not the answer:
   *punto* in "a las ocho en punto" is `en punto`, and *paso* in "con paso firme" is the phrase. */
const LOOK_STUBS = {
  martes: ["el martes", "Tuesday"],
  punto: ["en punto", "sharp, on the dot"],
  perro: ["el perro", "dog"],
  marrón: ["marrón", "brown"],
  pequeña: ["pequeño", "small, little"],
  esquina: ["la esquina", "corner"],
  migajas: ["la migaja", "crumb"],
  buscar: ["buscar", "to look for"],
  calle: ["la calle", "street"],
  paso: ["con paso firme", "with a firm step"],
  firme: ["con paso firme", "with a firm step"],
  "paso firme": ["con paso firme", "with a firm step"],
  espera: ["esperar", "waits"],
  turno: ["el turno", "turn (in a queue)"],
  saca: ["sacar", "takes out"],
  barra: ["la barra de pan", "a loaf, a baguette"],
  horno: ["el horno", "oven"],
  despacio: ["despacio", "slowly"],
  huele: ["oler", "smells"],
  corteza: ["la corteza", "crust"],
  inmediato: ["de inmediato", "at once"],
  cartera: ["la cartera", "wallet"],
  billetes: ["el billete", "banknote"],
  comprendió: ["comprender", "understood"],
  dueño: ["el dueño", "owner"],
  duró: ["durar", "lasted"],
  dormí: ["dormirse", "fell asleep"],
  llevo: ["llevar", "have been (for a time)"],
  torcí: ["torcerse", "twisted (a joint)"],
  bailando: ["bailar", "dancing"],
  nariz: ["la nariz", "nose"],
  estornudar: ["estornudar", "to sneeze"],
  pica: ["picar", "itches", "k3m91xq7d0a2vbe"]
};

/* `?lookup=slow` answers in three seconds, `?lookup=offline` never does. */
const LOOK_MODE = new URLSearchParams(location.search).get("lookup") || "";

let look = null;
let lookTimer = 0;

const ARTICLES = /^(el|la|los|las|un|una|lo)\s+/i;

function lookSurface() {
  if (state.stories && state.storyOpen) return "story";
  if (state.loops && state.loopOpen) return "loop";
  if (state.openId && state.mode === "read" && !state.add) return "article";
  return null;
}

function caretAt(x, y) {
  if (document.caretPositionFromPoint) {
    const at = document.caretPositionFromPoint(x, y);
    return at ? { node: at.offsetNode, offset: at.offset } : null;
  }
  if (document.caretRangeFromPoint) {
    const at = document.caretRangeFromPoint(x, y);
    return at ? { node: at.startContainer, offset: at.startOffset } : null;
  }
  return null;
}

function textNodesOf(block) {
  const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  return nodes;
}

/* The word around a character offset, by the language's own idea of a word — which is also what
   chooses a unit around the tapped character where there are no spaces. */
function wordIn(text, offset, lang) {
  const words = new Intl.Segmenter(lang, { granularity: "word" }).segment(text);
  let before = null;
  for (const piece of words) {
    if (!piece.isWordLike) continue;
    const end = piece.index + piece.segment.length;
    if (piece.index <= offset && offset < end) return { start: piece.index, end };
    if (end === offset) before = { start: piece.index, end };
  }
  return before;
}

/* The sentence a span sits in, and the span measured from the sentence's start — the shape the
   quick look-up takes. */
function sentenceIn(text, start, end, lang) {
  for (const piece of new Intl.Segmenter(lang, { granularity: "sentence" }).segment(text)) {
    const stop = piece.index + piece.segment.length;
    if (piece.index <= start && end <= stop) {
      const lead = piece.segment.length - piece.segment.trimStart().length;
      return { text: piece.segment.trim(), start: start - piece.index - lead, end: end - piece.index - lead };
    }
  }
  return { text, start, end };
}

function rangeOver(nodes, start, end) {
  const range = document.createRange();
  let seen = 0;
  for (const node of nodes) {
    const length = node.data.length;
    if (start >= seen && start <= seen + length) range.setStart(node, start - seen);
    if (end >= seen && end <= seen + length) { range.setEnd(node, end - seen); break; }
    seen += length;
  }
  return range;
}

function offsetIn(nodes, node, offset) {
  let seen = 0;
  for (const one of nodes) {
    if (one === node) return seen + offset;
    seen += one.data.length;
  }
  return -1;
}

/* The word under a tap, or nothing. **A tap near nothing selects nothing**: the caret lands on the
   nearest letter wherever the finger is, so the point must fall on the word itself, give or take a
   fifth of a line — the rule photo capture's tap already keeps. */
function wordAtPoint(ev) {
  const surface = lookSurface();
  if (!surface) return null;
  const caret = caretAt(ev.clientX, ev.clientY);
  if (!caret || caret.node.nodeType !== Node.TEXT_NODE) return null;
  const block = caret.node.parentElement && caret.node.parentElement.closest(LOOK_BLOCKS[surface]);
  if (!block) return null;
  const nodes = textNodesOf(block);
  const text = nodes.map((node) => node.data).join("");
  const offset = offsetIn(nodes, caret.node, caret.offset);
  const word = offset < 0 ? null : wordIn(text, offset, state.lang);
  if (!word) return null;
  const range = rangeOver(nodes, word.start, word.end);
  const onWord = [...range.getClientRects()].some((box) => {
    const give = box.height * 0.2;
    return ev.clientX >= box.left - give && ev.clientX <= box.right + give
      && ev.clientY >= box.top - give && ev.clientY <= box.bottom + give;
  });
  if (!onWord) return null;
  const mark = caret.node.parentElement.closest("[data-lexeme]");
  return { surface, block, text, range, start: word.start, end: word.end, lexemeId: mark ? mark.dataset.lexeme : null };
}

/* A word you hold, from your own words: a story's mark names it, and otherwise the tapped form is
   compared with each headword — with and without its article — and lemma. An inflected form this
   misses is found by the server, which answers with the word you have. */
function heldWord(hit, surface) {
  if (hit.lexemeId) {
    const own = LEXEMES.find((x) => x.id === hit.lexemeId);
    if (own) return { id: own.id, headword: own.headword, gloss: own.shortGloss };
    const told = STORY_WORDS.find((word) => word.lexemeId === hit.lexemeId);
    if (told) return { id: told.lexemeId, headword: told.sourceText, gloss: told.gloss, noArticle: true };
  }
  const want = fold(hit.word);
  const own = LEXEMES.find((x) => x.language === state.lang
    && [x.lemma, x.headword, x.headword.replace(ARTICLES, "")].some((form) => fold(form) === want));
  return own ? { id: own.id, headword: own.headword, gloss: own.shortGloss } : null;
}

/* What the sheet's play button does, per surface: the job the tap used to have. */
function playFor(hit) {
  if (hit.surface === "story") {
    const passage = hit.range.startContainer.parentElement.closest("[data-passage]");
    if (!passage) return null;   // a part read whole has no passages; its ▷ reads it
    const sounding = passage.closest(".story-card") === document.querySelector(".story-card");   // the first part plays
    return { label: sounding ? "From here" : "This passage", run: () => {
      document.querySelectorAll(".story-seg.on").forEach((one) => one.classList.remove("on"));
      passage.classList.add("on");
      toast("♪ Reading on from this passage");
    } };
  }
  if (hit.surface === "loop") {
    const row = hit.block.closest(".lyric-row");
    return { label: "Play from this line", run: () => { loopSeek(Number(row.dataset.seek)); if (!player.playing) loopPlay(); } };
  }
  return null;
}

function openLook(hit) {
  clearTimeout(lookTimer);
  const word = hit.text.slice(hit.start, hit.end);
  const sentence = sentenceIn(hit.text, hit.start, hit.end, state.lang);
  const full = { ...hit, word, sentence };
  const held = heldWord(full, hit.surface);
  look = { ...full, held, play: playFor(full), stage: held ? "done" : "asking", answer: null, added: false };
  if (window.CSS && CSS.highlights && typeof Highlight === "function") CSS.highlights.set("look-up", new Highlight(hit.range));
  if (!held) ask();
  paintLook();
}

function ask() {
  const asked = look;
  asked.stage = "asking";
  if (LOOK_MODE === "offline") {
    lookTimer = setTimeout(() => {
      if (look !== asked) return;
      asked.stage = "failed";
      asked.message = "Looking a word up needs the server, and it can't be reached right now.";
      paintLook();
    }, 700);
    return;
  }
  lookTimer = setTimeout(() => {
    if (look !== asked) return;
    const stub = LOOK_STUBS[asked.word.toLowerCase()] || [asked.word.toLowerCase(), "what it means in this sentence"];
    const own = stub[2] ? LEXEMES.find((x) => x.id === stub[2]) : null;
    asked.answer = { headword: stub[0], gloss: stub[1] };
    if (own) asked.held = { id: own.id, headword: own.headword, gloss: stub[1] };
    asked.stage = "done";
    paintLook();
  }, LOOK_MODE === "slow" ? 3000 : 900);
}

/* Dropped without a trace, for a redraw that takes the text it named with it. */
function forgetLook() {
  clearTimeout(lookTimer);
  look = null;
  if (window.CSS && CSS.highlights) CSS.highlights.delete("look-up");
  const sheet = document.getElementById("lookSheet");
  if (sheet) sheet.remove();
}

function closeLook() { forgetLook(); }

function sheetHtml() {
  const l = look;
  const lang = `lang="${state.lang}"`;
  const self = l.held && l.held.id === state.openId;
  let meaning;
  if (l.held) {
    meaning = `<strong ${lang}>${esc(l.held.headword)}</strong><span> — ${esc(l.held.gloss)}</span>`
      + `<span class="photo-held"> · ${self ? "this word" : "in your words"}</span>`;
  } else if (l.stage === "failed") {
    meaning = `<span class="photo-meaning-failed">${esc(l.message)}</span>`;
  } else if (l.answer) {
    meaning = `<strong ${lang}>${esc(l.answer.headword)}</strong><span> — ${esc(l.answer.gloss)}</span>`;
  } else {
    meaning = `<span class="photo-meaning-pending"><strong ${lang}>${esc(l.word)}</strong> — looking it up…</span>`;
  }
  const s = l.sentence;
  const context = l.held ? "" : `<p class="look-sentence" ${lang}>${esc(s.text.slice(0, s.start))}<mark>${esc(s.text.slice(s.start, s.end))}</mark>${esc(s.text.slice(s.end))}</p>`;
  const actions = [];
  if (l.held && !self) actions.push(`<button class="tb-btn primary" data-look="open">${ICON.open}<span>Open ${esc(l.held.headword)}</span></button>`);
  else if (!l.held && l.added) actions.push(`<span class="look-added">${ICON.check}<span>Added to your Inbox</span></span>`);
  else if (!l.held && l.stage === "failed") actions.push('<button class="tb-btn" data-look="retry">Try again</button>');
  else if (!l.held) actions.push(`<button class="tb-btn primary" data-look="add"${l.stage === "done" ? "" : " disabled"}>${ICON.plus}<span>Add</span></button>`);
  if (l.play) actions.push(`<button class="tb-btn" data-look="play">${ICON.play}<span>${esc(l.play.label)}</span></button>`);
  return `<div class="look-head">
      <div class="photo-meaning look-meaning" aria-live="polite">${meaning}</div>
      <button class="icon-btn look-close" data-look="close" aria-label="Close">${ICON.close}</button>
    </div>
    ${context}
    ${actions.length ? `<div class="look-actions">${actions.join("")}</div>` : ""}`;
}

/* Where the sheet goes. Over the foot of a story's page, or an article's cards; between a loop's
   cards and its controls, which it never covers; and in an article's page on top of the ask dock,
   which already owns the foot of the column and stays there as the page scrolls. */
function paintLook() {
  let sheet = document.getElementById("lookSheet");
  if (!look) { if (sheet) sheet.remove(); return; }
  if (!sheet) {
    sheet = el('<aside class="look-sheet" id="lookSheet" role="dialog" aria-label="Look up a word"></aside>');
    if (look.surface === "story") { sheet.classList.add("over"); $(".story-read").appendChild(sheet); }
    else if (look.surface === "loop") { sheet.classList.add("flow"); $(".loop-play").insertBefore(sheet, $(".loop-play .player")); }
    else if ($(".ask")) { sheet.classList.add("docked"); $(".ask").prepend(sheet); }
    else if ($("#pane .cards")) { sheet.classList.add("over"); $("#pane .cards").appendChild(sheet); }
    else { sheet.classList.add("stuck"); $("#paneWrap").appendChild(sheet); }
    sheet.addEventListener("click", onSheet);
  }
  sheet.innerHTML = sheetHtml();
  if (look.surface === "story") {
    sheet.classList.remove("top");
    const word = look.range.getBoundingClientRect();
    if (word.bottom > sheet.getBoundingClientRect().top - 8) sheet.classList.add("top");
  }
}

function onSheet(ev) {
  const button = ev.target.closest("[data-look]");
  if (!button || !look) return;
  const what = button.dataset.look;
  if (what === "close") { closeLook(); return; }
  if (what === "retry") { ask(); paintLook(); return; }
  if (what === "play") { look.play.run(); return; }
  if (what === "add") { look.added = true; paintLook(); return; }
  if (what === "open") openHeld(look.held);
}

/* Open goes to the article, and Back from it comes back here: the same page of the story, or the
   loop still playing — the way Back from an article opened on the map goes back to the map. */
function openHeld(held) {
  if (!LEXEMES.some((x) => x.id === held.id)) {
    toast(`Opens ${held.headword} — the prototype has no article for it`);
    return;
  }
  if (state.stories) state.readingReturn = { stories: true, storyOpen: state.storyOpen, storyAt: state.storyAt };
  else if (state.loops) state.readingReturn = { loops: true, loopOpen: state.loopOpen };
  else state.readingReturn = null;
  state.stories = false; state.loops = false;
  state.openId = held.id; state.openExt = null; state.mode = "read"; state.card = 0;
  render();
  $("#main").scrollTop = 0;
}

function backToReading() {
  const back = state.readingReturn;
  state.readingReturn = null;
  if (!back) return;
  if (back.stories) { state.stories = true; state.storyOpen = back.storyOpen; state.storyAt = back.storyAt; }
  if (back.loops) { state.loops = true; state.loopOpen = back.loopOpen; }
}

/* Ahead of every other handler on the surfaces, so a word tap on a loop's card never reaches the
   seek. A tap that is not on a word closes the sheet and carries on to do what it always did. */
$("#main").addEventListener("click", (ev) => {
  if (ev.target.closest(".look-sheet")) return;
  // A drag that selected text is a selection, not a tap — the pill answers it.
  if (getSelection() && getSelection().toString()) return;
  const control = ev.target.closest("button, a, input, [data-say]");
  if (control && !control.classList.contains("lyric-row")) return;
  const hit = wordAtPoint(ev);
  if (hit) {
    ev.stopPropagation();
    ev.preventDefault();
    openLook(hit);
    return;
  }
  if (look) closeLook();
}, true);

/* Whatever is selected, in the language the article is in: listen to it, or look it up. A floating
   pill above the selection, because a play button on every phrase would be noise and a selection is
   already the gesture for "this bit" — the way to look up a phrase the tap did not widen to. */
const selectionSay = el(`<div class="sel-say" role="toolbar" aria-label="The selection">
  <button class="sel-act" data-sel="listen" aria-label="Listen to the selection">${ICON.play}<span>Listen</span></button>
  <button class="sel-act" data-sel="look" aria-label="Look the selection up">${ICON.search}<span>Look up</span></button>
</div>`);
selectionSay.hidden = true;
document.body.appendChild(selectionSay);
// Pressing it must not collapse the selection it is about to read.
selectionSay.addEventListener("mousedown", (ev) => ev.preventDefault());
selectionSay.addEventListener("click", (ev) => {
  const act = ev.target.closest("[data-sel]");
  if (!act || act.dataset.sel !== "look") return;
  ev.stopPropagation();
  const selection = getSelection();
  if (!selection || !selection.rangeCount) return;
  const range = selection.getRangeAt(0);
  const surface = lookSurface();
  const start = range.startContainer.nodeType === Node.TEXT_NODE ? range.startContainer.parentElement : range.startContainer;
  const block = surface && start.closest(LOOK_BLOCKS[surface]);
  if (!block) { toast("Look up works on text in the language you are learning"); return; }
  const nodes = textNodesOf(block);
  const text = nodes.map((node) => node.data).join("");
  const from = offsetIn(nodes, range.startContainer, range.startOffset);
  const to = block.contains(range.endContainer) ? offsetIn(nodes, range.endContainer, range.endOffset) : text.length;
  if (from < 0 || to <= from) return;
  const trimmed = text.slice(from, to);
  const lead = trimmed.length - trimmed.trimStart().length;
  const tail = trimmed.length - trimmed.trimEnd().length;
  const hit = { surface, block, text, start: from + lead, end: to - tail, lexemeId: null };
  hit.range = rangeOver(nodes, hit.start, hit.end);
  selection.removeAllRanges();
  selectionSay.hidden = true;
  openLook(hit);
});
document.addEventListener("selectionchange", () => {
  const selection = getSelection();
  const text = selection && !selection.isCollapsed ? selection.toString().trim() : "";
  const surface = lookSurface();
  const root = surface === "article" ? $("#pane") : surface ? $("#composer") : null;
  if (!text || !root || !root.contains(selection.anchorNode)) {
    selectionSay.hidden = true;
    return;
  }
  const box = selection.getRangeAt(0).getBoundingClientRect();
  selectionSay.hidden = false;
  selectionSay.style.left = `${Math.min(Math.max(box.left + box.width / 2, 100), innerWidth - 100)}px`;
  selectionSay.style.top = `${Math.max(box.top, 70)}px`;
  selectionSay.querySelector("[data-sel=listen]").dataset.say = text.length > 160 ? `${text.slice(0, 160)}…` : text;
});

/* `?tap=<word>` taps the first shown occurrence of that word on the surface a deep link opened —
   the story's page, the loop's cards or the article — so every state of the sheet can be shot again. */
function tapByLink(word) {
  const surface = lookSurface();
  if (!surface) return;
  const want = fold(word);
  for (const block of document.querySelectorAll(LOOK_BLOCKS[surface])) {
    const nodes = textNodesOf(block);
    const text = nodes.map((node) => node.data).join("");
    for (const piece of new Intl.Segmenter(state.lang, { granularity: "word" }).segment(text)) {
      if (!piece.isWordLike || fold(piece.segment) !== want) continue;
      const range = rangeOver(nodes, piece.index, piece.index + piece.segment.length);
      const box = range.getBoundingClientRect();
      if (!box.width) continue;
      const mark = range.startContainer.parentElement.closest("[data-lexeme]");
      openLook({ surface, block, text, range, start: piece.index, end: piece.index + piece.segment.length, lexemeId: mark ? mark.dataset.lexeme : null });
      return;
    }
  }
}

/* deep link — ?open=<id|headword>&mode=read|yaml keeps screenshots reproducible */
const params = new URLSearchParams(location.search);
if (params.get("open")) {
  const want = params.get("open").toLowerCase();
  const hit = LEXEMES.find((x) => x.id === want || x.headword.toLowerCase() === want || x.lemma.toLowerCase() === want);
  const mode = params.get("mode");
  if (hit) { state.openId = hit.id; state.lang = hit.language; state.mode = mode === "yaml" || mode === "edit" ? mode : "read"; }
  // `ask=half|full` and `review=1` make the conversation and a proposal under review reachable for
  // a screenshot, the way `mode` already does for the editor.
  const ask = params.get("ask");
  // `half` is the old name for `open`, kept because deep links to it exist in the design notes.
  if (ask === "open" || ask === "half") state.ask = "open";
  if (ask === "full") state.ask = "full";
  if (params.get("focus")) state.askFocus = params.get("focus");
  if (params.get("review") === "1") state.review = true;
}
/* `loops=1` opens the surface, `layout=` picks the shape, `loop=` which one, and `t=` how far in —
   so "mid-word, one translation up and the next still withheld" is a link rather than a description.
   `speed=` is the harness's clock, for a recording that does not want to run four minutes. */
if (params.get("loops") === "1" || params.get("loop") || params.get("t")) {
  state.loops = true;
  const wanted = params.get("loop");
  const picked = wanted ? LOOPS.find((l) => l.id === wanted)
    : (params.get("t") || params.get("play")) ? loopsIn(state.lang).find(loopIsReady) : null;
  if (picked) {
    state.lang = picked.language;
    state.loopOpen = picked.id;
    loopLoad(picked.id, { at: Number(params.get("t")) || 0 });
  }
  if (params.get("speed")) player.speed = Number(params.get("speed")) || 1;
  if (params.get("play") === "1") loopPlay();
}
if (params.get("make") === "1") { state.loops = true; setTimeout(openLoopDialog, 0); }
/* `select=1` puts eight Spanish words in the selection — one of them, espolvorear, with no single term
   to say, so the loop dialog has something to leave out — `sellist=1` opens the bar's list of them,
   and `make=loop-selection` or `make=story-selection` opens a dialog from the bar. */
if (params.get("select") === "1") {
  picks.es = ["k3m91xq7d0a2vbe", "q8v53mrb2e7wl4d", "m5r18kts4b9gy2n", "w9h27fjc5d1qx8v",
    "p2n85gvx7k4rt3c", "f6k39xzb8n2ph7m", "v8j51ctr3x7bn6q", "g3q76mwd9j5fk1z"];
}
if (params.get("sellist") === "1") state.selList = true;
if (params.get("make") === "loop-selection") setTimeout(() => openLoopDialog("selection"), 0);
if (params.get("make") === "story-selection") setTimeout(() => openStoryDialog("selection"), 0);
if (params.get("topic")) state.topic = params.get("topic");
if (params.get("view") === "page" || params.get("view") === "cards") state.view = params.get("view");
if (params.get("card")) state.card = Number(params.get("card")) || 0;
if (params.get("tr") === "on") state.sayTranslations = true;
/* `stories=1` opens the surface, `story=` opens one of the written ones (counting from 1), `part=` is
   the page it opens on (from 0, the last being the words), and `reveal=1` turns every translation over. */
if (params.get("stories") === "1" || params.get("story")) {
  state.stories = true;
  const written = storiesIn(state.lang).filter((one) => partsOf(one.id).length);
  const picked = params.get("story") ? written[Number(params.get("story")) - 1] : null;
  if (picked) {
    state.storyOpen = picked.id;
    state.storyAt = Number(params.get("part")) || 0;
    if (params.get("reveal") === "1") partsOf(picked.id).forEach((one) => { state.storyShown[one.id] = true; });
  }
}
if (params.get("capture") === "off") {
  captureBlocked = { provider: "vertex", model: "gemini-3.7-flash", reason: "VERTEX_API_KEY is not set" };
}
if (params.get("wrap") === "off") editorWrap = false;
if (params.get("numbers") === "on") editorNumbers = true;
if (params.get("theme")) setTheme(params.get("theme"));
if (["read", "screenshot"].includes(params.get("photo"))) photoStage = params.get("photo");
if (params.get("add")) openSheet(params.get("add"));
if (params.get("frame") === "phone" || params.get("frame") === "tablet") {
  const f = params.get("frame");
  document.body.className = `framed ${f}`;
  document.querySelectorAll("#harness button[data-frame]").forEach((b) => b.classList.toggle("on", b.dataset.frame === f));
}
/* `size=375x667` resizes the preview frame, so a small phone can be looked at too. */
const size = (params.get("size") || "").match(/^(\d+)x(\d+)$/);
if (size) Object.assign($(".viewport").style, { width: `${size[1]}px`, height: `${size[2]}px` });

/* The map: `map=1` opens it; `lang=` picks the language; `style=` and `labels=` the two choices;
   `focus=<headword>` peeks at a word and flies to it; `z=` zooms in from the whole map; `sample=1`
   uses the committed fixture; `mapstate=drawing|offline` shows the first draw or a device that has
   never reached the server; `update=1` plays a new layout arriving. */
if (params.get("lang") && langOf(params.get("lang"))) state.lang = params.get("lang");
if (MAP_STYLES.includes(params.get("style"))) state.mapStyle = params.get("style");
if (MAP_LABELS.includes(params.get("labels"))) state.mapLabels = params.get("labels");
if (params.get("sample") === "1") state.mapSample = true;
if (params.get("map") === "1" || params.get("focus") || params.get("mapstate")) {
  state.map = true;
  if (params.get("mapstate") === "drawing" || params.get("mapstate") === "offline") state.mapState = params.get("mapstate");
  const d = mapData();
  const want = params.get("focus") ? fold(params.get("focus")) : null;
  if (d && want) {
    state.mapSel = d.points.findIndex((p) => fold(p.headword) === want);
    if (state.mapSel < 0) state.mapSel = d.points.findIndex((p) => fold(p.headword).startsWith(want));
    mapGrown.add(state.lang);
  }
  if (params.get("z") || params.get("update") === "1") mapGrown.add(state.lang);
}

paintSwitches();
render();
/* `tap=<word>` waits for the story's page to be scrolled to before it taps. */
if (params.get("tap")) setTimeout(() => tapByLink(params.get("tap")), 250);

if (state.map && meaningMap) {
  const d = mapData();
  if (state.mapSel >= 0) meaningMap.select(state.mapSel, { fly: true, zoom: Number(params.get("z")) || 5.5 });
  else if (params.get("z")) meaningMap.zoomTo(Number(params.get("z")));
  if (params.get("update") === "1" && d && d.before) setTimeout(playMapUpdate, 400);
}
