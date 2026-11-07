/* The prototype's icon set, unchanged. Stroke and size come from the stylesheet. */

import type { ReactNode } from "react";

const stroke = { fill: "none", stroke: "currentColor", strokeLinecap: "round" } as const;

export const SearchIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2} aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.6-3.6" /></svg>;
export const ForwardIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2} strokeLinejoin="round" aria-hidden="true"><path d="M9 5l7 7-7 7" /></svg>;
export const BackIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2} strokeLinejoin="round" aria-hidden="true"><path d="M15 5l-7 7 7 7" /></svg>;
export const PlusIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2} aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>;
export const PlayIcon = () => <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13l11-6.5z" /></svg>;
export const CaretIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2.2} strokeLinejoin="round" aria-hidden="true"><path d="M9 5l7 7-7 7" /></svg>;
export const PencilIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M4 20h4l10-10-4-4L4 16z" /><path d="M13.5 6.5l4 4" /></svg>;
export const TrashIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" /></svg>;
export const CloseIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2} aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>;
export const GearIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true">
  <path d="M10.03 5.34 10.44 2.68h3.12l.41 2.66a6.95 6.95 0 0 1 1.35.55l2.17-1.58 2.2 2.2-1.58 2.17a6.95 6.95 0 0 1 .55 1.35l2.66.41v3.12l-2.66.41a6.95 6.95 0 0 1-.55 1.35l1.58 2.17-2.2 2.2-2.17-1.58a6.95 6.95 0 0 1-1.35.55l-.41 2.66h-3.12l-.41-2.66a6.95 6.95 0 0 1-1.35-.55l-2.17 1.58-2.2-2.2 1.58-2.17a6.95 6.95 0 0 1-.55-1.35l-2.66-.41v-3.12l2.66-.41a6.95 6.95 0 0 1 .55-1.35L4.31 6.51l2.2-2.2 2.17 1.58a6.95 6.95 0 0 1 1.35-.55Z" />
  <circle cx="12" cy="12" r="3.1" />
</svg>;
export const CloudIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M7 18h10a4 4 0 0 0 .6-7.96A6 6 0 0 0 6 10.2 3.9 3.9 0 0 0 7 18z" /></svg>;
export const CloudOffIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M7 18h10a4 4 0 0 0 .6-7.96A6 6 0 0 0 6 10.2 3.9 3.9 0 0 0 7 18z" /><path d="M3 3l18 18" /></svg>;
export const SyncIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.9} strokeLinejoin="round" aria-hidden="true"><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v5h-5" /></svg>;
/** A word that came out of a book rather than out of your own reading. */
export const BookIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true"><path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H18v14H5.5A1.5 1.5 0 0 0 4 19.5z" /><path d="M4 19.5A1.5 1.5 0 0 1 5.5 18H20v2.5H5.5" /><path d="M8 8h6" /></svg>;
/** The same, fetched over the network rather than held. */
export const GlobeIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="M3.5 12h17" /><path d="M12 3.5c2.2 2.3 3.3 5.2 3.3 8.5S14.2 18.2 12 20.5c-2.2-2.3-3.3-5.2-3.3-8.5S9.8 5.8 12 3.5z" /></svg>;
/* A picture in a frame: what is being made, rather than a clock, which would read as "late". */
export const PictureIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true"><rect x="3.5" y="5" width="17" height="14" rx="2" /><circle cx="9" cy="10" r="1.6" /><path d="M4 16.5l4.5-4 3.5 3 3-2.5 5 4" /></svg>;
export const AlertIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.9} strokeLinejoin="round" aria-hidden="true"><path d="M12 4l9 16H3z" /><path d="M12 10v4M12 17.2v.1" /></svg>;
/* Asking about a word. A speech bubble with a question in it — deliberately not `✳`, which the
   article already uses for "where you met it", and not a pencil, which is the YAML escape hatch. */
export const AskIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M20 14.5A2.5 2.5 0 0 1 17.5 17H12l-4.5 3.5V17H6.5A2.5 2.5 0 0 1 4 14.5v-8A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5z" /><path d="M10.2 8.6a1.9 1.9 0 1 1 2.6 1.8c-.5.2-.8.7-.8 1.2v.3" /><path d="M12 14.2v.1" /></svg>;
/** The sheet's grabber: which way it will move, not a decoration. */
export const ChevronIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2.2} strokeLinejoin="round" aria-hidden="true"><path d="M5 15l7-7 7 7" /></svg>;
/** Sending a turn. */
export const SendIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2} strokeLinejoin="round" aria-hidden="true"><path d="M4 12h14" /><path d="M13 6l6 6-6 6" /></svg>;
/** A clip, drawn as a strip of film: a play triangle alone reads as "audio". */
export const FilmIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true"><rect x="3.5" y="5" width="17" height="14" rx="2" /><path d="M3.5 9h17M3.5 15h17M7.5 5v4M12 5v4M16.5 5v4M7.5 15v4M12 15v4M16.5 15v4" /></svg>;
/** The article's details: what is known about the record rather than about the word. */
/* The corner arrow that says a control opens something. Deliberately the plainest possible drawing
   of it: this sits inside a pill that is already carrying a film strip and a line of text, and any
   more ink here would make the clip compete with the sentence above it. */
export const OpenIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2} strokeLinejoin="round" aria-hidden="true"><path d="M7 17L17 7" /><path d="M9 7h8v8" /></svg>;

export const InfoIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5.5" /><path d="M12 7.6v.1" /></svg>;
/**
 * The hedera, the printer's ivy leaf, pointing right (❧); the article mirrors it for ☙.
 *
 * The outline of U+2767 from EB Garamond (Georg Duffner and Octavio Pardo), used under the SIL Open
 * Font License 1.1. Drawn from the glyph rather than typed, because Literata has no such character and
 * every platform's fallback font draws a different one.
 */
export const HederaIcon = () => <svg viewBox="0 0 910 508" aria-hidden="true">
  <path fill="currentColor" d="M135 508Q107 508 86 489Q66 470 51 447Q35 447 18 443Q0 439 0 414Q0 382 16 350Q33 319 58 296Q83 272 107 266Q100 258 98 248Q96 239 96 229Q96 215 110 202Q124 189 146 179Q167 169 190 163Q214 157 232 157Q244 157 256 158Q269 158 281 160Q281 138 272 117Q262 96 248 82Q233 68 218 68Q206 68 200 74Q193 79 187 86Q180 94 171 101Q162 108 144 108Q113 108 92 86Q70 63 70 32Q70 18 80 9Q89 0 102 0Q110 0 114 6Q117 12 120 18Q123 24 126 28Q129 33 134 33Q139 33 142 28Q146 24 150 18Q154 12 158 7Q163 2 170 2Q212 2 246 22Q279 43 298 77Q318 111 318 150Q318 154 318 158Q317 162 317 166Q348 173 371 188Q394 202 410 216Q414 220 419 218Q424 216 420 214Q410 206 398 189Q387 172 387 153Q387 127 400 106Q412 86 433 74Q454 62 480 62Q519 62 547 78Q575 93 598 118Q620 142 640 168Q668 203 696 232Q725 260 766 260Q790 260 813 252Q836 245 851 230Q866 214 866 190Q866 157 844 134Q839 135 834 136Q830 136 826 136Q804 137 794 126Q785 114 785 96Q785 75 802 64Q819 54 840 54Q865 54 880 72Q895 91 902 118Q910 146 910 172Q910 224 886 268Q861 311 819 345Q777 379 726 403Q675 427 622 440Q568 452 520 452Q480 452 438 436Q397 421 370 391Q342 361 342 318Q342 292 358 276Q373 259 396 248Q404 244 404 242Q404 240 396 236Q377 225 356 218Q336 210 312 206Q305 238 290 266Q275 294 254 312Q234 329 208 329Q195 329 184 326Q174 323 165 319Q157 317 149 314Q141 312 133 312Q108 312 93 333Q78 354 78 380Q78 408 92 433Q107 458 130 458Q138 458 144 455Q149 452 153 448Q158 443 164 440Q170 436 178 436Q187 436 192 444Q196 453 196 462Q196 484 178 496Q159 508 135 508ZM190 286Q215 286 238 260Q260 234 272 202H254Q234 202 210 206Q186 211 169 220Q152 230 152 244Q152 260 163 273Q174 286 190 286Z" />
</svg>;
/** More actions: three dots in a row. */
export const MoreIcon = () => <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5.5" cy="12" r="1.7" /><circle cx="12" cy="12" r="1.7" /><circle cx="18.5" cy="12" r="1.7" /></svg>;
/* File it: the Inbox tray with an arrow leaving it — the same tray the rail's 📥 draws, going the
   other way, so the button reads as the opposite of how the word got there. */
export const FileIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true">
  <path d="M3 13h4l1.5 3h7l1.5-3h4" /><path d="M3 13l3-7h12l3 7v5H3z" /><path d="M12 10V2M9 5l3-3 3 3" />
</svg>;

/* ── the loop player ──
   Transport glyphs drawn solid rather than stroked: at 22 px a stroked triangle reads as the
   outline of a play button, and every player on the device draws a filled one. */
export const PauseIcon = () => <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="7" y="5.5" width="3.6" height="13" rx="1.1" /><rect x="13.4" y="5.5" width="3.6" height="13" rx="1.1" /></svg>;
export const PreviousIcon = () => <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="5.5" y="6.5" width="2.4" height="11" rx="1" /><path d="M16.5 6.5v11L8 12z" /></svg>;
export const NextIcon = () => <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7.5 6.5v11L16 12z" /><rect x="16.1" y="6.5" width="2.4" height="11" rx="1" /></svg>;
/* Play it again: the two arrows every player uses, so it needs no label to be understood. */
export const RepeatIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.9} strokeLinejoin="round" aria-hidden="true"><path d="M6 7h11a3 3 0 0 1 3 3v1" /><path d="M18 17H7a3 3 0 0 1-3-3v-1" /><path d="M8.5 4.5L6 7l2.5 2.5" /><path d="M15.5 19.5L18 17l-2.5-2.5" /></svg>;
/* And on to the next one: a queue with a play mark, which is how a player says continuous play. */
export const ContinueIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.9} strokeLinejoin="round" aria-hidden="true"><path d="M4 7h11M4 12h8M4 17h8" /><path d="M16 11.5v7l5.5-3.5z" fill="currentColor" strokeWidth={1} /></svg>;
/* Keeping a loop's music: a star, filled once it is kept. The only mark in the app that means
   "favourite", so it is not borrowed for anything else. */
export const StarIcon = ({ filled = false }: { filled?: boolean }) => <svg viewBox="0 0 24 24" {...stroke} fill={filled ? "currentColor" : "none"} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M12 3.8l2.5 5.2 5.7.8-4.1 4 1 5.7-5.1-2.7-5.1 2.7 1-5.7-4.1-4 5.7-.8z" /></svg>;
/* Opens a menu below or above: the caret turned down. */
export const DownIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2.2} strokeLinejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>;
/* Selecting a word: a circle with a plus, and the same circle with a check once it is selected. */
export const SelectIcon = ({ on = false }: { on?: boolean }) => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true">
  <circle cx="12" cy="12" r="8.5" />{on ? <path d="M8.3 12.3l2.5 2.5 5-5.2" /> : <path d="M12 8.5v7M8.5 12h7" />}
</svg>;
/* The badge a selected word wears, in the list and — drawn on the canvas — on the map. */
export const CheckIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={3.2} strokeLinejoin="round" aria-hidden="true"><path d="M6 12.5l4 4 8-8.5" /></svg>;
/* A loop's own mark: a beamed pair, which says music without saying "audio file". */
export const NoteIcon = () => <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M19 4.2L9.2 6.4v9.05a2.9 2.9 0 1 0 1.5 2.55V9.1l6.8-1.5v5.6a2.9 2.9 0 1 0 1.5 2.55z" /></svg>;
/* The map: a folded sheet; and the four corners of "show all of it". */
export const MapIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M9 4.5L3.5 6.5v13L9 17.5l6 2 5.5-2v-13L15 6.5z" /><path d="M9 4.5v13M15 6.5v13" /></svg>;
export const FitIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.9} strokeLinejoin="round" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>;
export const MinusIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={2} aria-hidden="true"><path d="M5 12h14" /></svg>;
export const HourglassIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true"><path d="M7 4h10M7 20h10" /><path d="M8 4c0 4 4 5 4 8s-4 4-4 8" /><path d="M16 4c0 4-4 5-4 8s4 4 4 8" /></svg>;

/* The pages of Settings, drawn alike so the list reads as one set. The prototype's
   `design/ui-prototype/settings.js` draws the same paths. */
const page = (body: ReactNode) => () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true">{body}</svg>;
export const SunIcon = page(<><circle cx="12" cy="12" r="3" /><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8" /></>);
export const FlagIcon = page(<><path d="M5 21V4" /><path d="M5 4h11l-2 4 2 4H5" /></>);
export const TagIcon = page(<><path d="M4 12.5V5a1 1 0 0 1 1-1h7.5L20 11.5 12.5 19z" /><circle cx="8.5" cy="8.5" r="1.3" /></>);
export const SpeakerIcon = page(<><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" /><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11" /></>);
export const VideoIcon = page(<><rect x="3.5" y="5" width="17" height="14" rx="2" /><path d="M10 9.5v5l4.5-2.5z" /></>);
export const OpenBookIcon = page(<><path d="M12 6.5C10 5 7.5 4.5 4 4.5v13c3.5 0 6 .5 8 2 2-1.5 4.5-2 8-2v-13c-3.5 0-6 .5-8 2z" /><path d="M12 6.5v13" /></>);
export const ChipIcon = page(<><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9.5 9.5h5v5h-5z" /><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3" /></>);
export const PulseIcon = page(<path d="M3.5 12h4l2.5-6 4 12 2.5-6h4" />);
export const CardsIcon = page(<><rect x="4" y="6.5" width="12" height="14" rx="2" /><path d="M8 3.5h10a2 2 0 0 1 2 2V17" /></>);
export const ArchiveIcon = page(<><path d="M4 7.5h16v12H4z" /><path d="M3 4h18v3.5H3z" /><path d="M10 11.5h4" /></>);

/* ── the make dialogs ──
   How words are drawn, the three kinds of loop, and the strip's own controls. */
/** Surprise me: a die, because the choice is left to chance and says so. */
export const DiceIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true">
  <rect x="4" y="4" width="16" height="16" rx="3.5" />
  <g fill="currentColor" stroke="none"><circle cx="8.6" cy="8.6" r="1.35" /><circle cx="15.4" cy="8.6" r="1.35" /><circle cx="12" cy="12" r="1.35" /><circle cx="8.6" cy="15.4" r="1.35" /><circle cx="15.4" cy="15.4" r="1.35" /></g>
</svg>;
export const ShuffleIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M4 7h3c2.2 0 3.3 1.2 4.5 3.4l1 1.8c1.2 2.2 2.3 3.8 4.5 3.8H20" /><path d="M4 17h3c1.3 0 2.2-.5 3-1.4M14 8.4c.8-.9 1.7-1.4 3-1.4h3" /><path d="M17.5 4.5L20 7l-2.5 2.5M17.5 14.5L20 17l-2.5 2.5" /></svg>;
/** Hard: a summit, the climb Anki says a word still is. */
export const PeakIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M3 19.5l6.5-11.5 3.6 6.2 2.4-3.7 5.5 9z" /><path d="M7.4 11.7l2.1 1.3 1.6-1.2" /></svg>;
/** Rare: a gem, met seldom. */
export const GemIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true"><path d="M6.5 4.5h11l3.5 5L12 20 3 9.5z" /><path d="M3 9.5h18M9.5 4.5 8 9.5l4 10.5 4-10.5-1.5-5" /></svg>;
/** Newest: freshly added. */
export const SparkleIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true"><path d="M11 3.5l1.9 5.1 5.1 1.9-5.1 1.9L11 17.5l-1.9-5.1L4 10.5l5.1-1.9z" /><path d="M18 14.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z" /></svg>;
/** Every choice at once, as a grid. */
export const GridIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true"><rect x="4" y="4" width="6.5" height="6.5" rx="1.5" /><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5" /><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5" /><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" /></svg>;
/** A drill: a word and its translation, turned over and over. */
/** A drill: the same words round and round, as a loop of two arrows. */
export const DrillIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.8} strokeLinejoin="round" aria-hidden="true"><path d="M4 11.5V10a4 4 0 0 1 4-4h11.5M16.5 3l3 3-3 3M20 12.5V14a4 4 0 0 1-4 4H4.5M7.5 21l-3-3 3-3" /></svg>;
/** A radio lesson: someone presenting the words. */
export const MicIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.7} strokeLinejoin="round" aria-hidden="true"><rect x="9" y="3.5" width="6" height="10.5" rx="3" /><path d="M5.5 11.5a6.5 6.5 0 0 0 13 0" /><path d="M12 18v2.5M8.5 20.5h7" /></svg>;
/** A story told between the words. */
export const TaleIcon = () => <svg viewBox="0 0 24 24" {...stroke} strokeWidth={1.6} strokeLinejoin="round" aria-hidden="true"><path d="M12 7C10 5.5 7.5 5 4 5v12.5c3.5 0 6 .5 8 2 2-1.5 4.5-2 8-2V5c-3.5 0-6 .5-8 2z" /><path d="M12 7v12.5" /><path d="M6.5 9h3M6.5 12h3M14.5 9h3M14.5 12h3" /></svg>;
