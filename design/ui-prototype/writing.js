/* The Write sheet, as a still (`docs/features/writing.md`): the same markup and classes as
   `web/src/WritingDialog.tsx` and `writing/WritingPad.tsx`, for one character in each of its three
   modes. Nothing is checked here — the strokes are placed, not drawn.

   书's strokes are Make Me a Hanzi's, as packaged by hanzi-writer-data 2.0.1 — the dataset the
   server pins — redistributed under the Arphic Public License (see deploy/acervo/strokes/pin.json). */

const WRITING_SHU = {"strokes": ["M 681 421 Q 708 524 748 557 Q 766 576 750 596 Q 674 654 614 629 Q 572 616 534 604 L 483 593 Q 398 578 312 571 Q 294 570 295 560 Q 298 550 318 544 Q 345 531 383 542 Q 431 551 482 559 L 534 568 Q 570 575 607 582 Q 635 588 646 576 Q 658 566 655 543 Q 645 474 629 418 C 621 389 673 392 681 421 Z", "M 531 375 Q 769 399 794 379 Q 801 372 800 357 Q 760 191 741 170 Q 731 154 714 161 Q 683 167 649 174 Q 619 178 640 158 Q 701 103 726 65 Q 733 49 749 56 Q 779 72 807 151 Q 853 319 877 339 Q 896 361 889 370 Q 882 386 826 427 Q 807 445 788 439 Q 754 429 694 423 Q 687 423 681 421 L 629 418 Q 577 415 531 410 L 478 405 Q 375 398 323 385 Q 245 372 188 368 Q 161 367 156 355 Q 153 348 173 335 Q 210 310 246 322 Q 319 346 453 367 Q 463 368 477 369 L 531 375 Z", "M 472 -11 Q 478 -39 485 -49 Q 491 -56 499 -54 Q 514 -45 523 20 Q 535 123 532 224 Q 529 267 531 375 L 531 410 Q 531 480 534 568 L 534 604 Q 534 671 551 757 Q 555 776 539 787 Q 505 811 487 814 Q 474 820 456 810 Q 446 801 454 789 Q 484 741 484 647 Q 483 622 483 593 L 482 559 Q 481 489 478 405 L 477 369 Q 464 71 472 -11 Z", "M 739 695 Q 764 670 790 642 Q 802 629 817 628 Q 827 628 833 641 Q 837 654 831 684 Q 825 711 737 741 Q 722 745 716 743 Q 712 739 712 727 Q 715 717 739 695 Z"], "medians": [[[304, 560], [359, 556], [525, 583], [628, 609], [660, 605], [699, 574], [666, 457], [660, 443], [635, 424]], [[165, 353], [233, 345], [431, 384], [705, 407], [789, 411], [818, 398], [841, 362], [789, 196], [760, 135], [739, 118], [641, 168]], [[465, 799], [499, 773], [511, 756], [512, 738], [495, -44]], [[721, 737], [797, 680], [816, 646]]], "radStrokes": [2]};

function writingSheet(word, mode) {
  const MARGIN = 40, BOX = 1024, SPAN = BOX + 2 * MARGIN, FLIP = "translate(0 900) scale(1 -1)";
  const shu = WRITING_SHU;
  const chars = Array.from(word.headword);
  const at = Math.max(0, chars.indexOf("书"));
  const syllables = (word.reading || "").split(/\s+/);
  const written = mode === "watch" ? shu.strokes.length : 2;
  const toPage = ([x, y]) => [x, 900 - y];
  const outline = mode !== "write"
    ? `<g class="writing-outline">${shu.strokes.map((d) => `<path d="${d}"/>`).join("")}</g>` : "";
  const solid = `<g class="writing-strokes">${shu.strokes.slice(0, written).map((d, i) =>
    `<path d="${d}"${mode === "watch" && (shu.radStrokes || []).includes(i) ? ' class="radical"' : ""}/>`).join("")}</g>`;
  const numbers = mode === "watch" ? shu.medians.map((m, i) => {
    const [x, y] = toPage(m[0]);
    return `<g class="writing-number" transform="translate(${x} ${y})"><circle r="34"/><text dy="12">${i + 1}</text></g>`;
  }).join("") : "";
  const tones = { "ā": 1, "ē": 1, "ī": 1, "ō": 1, "ū": 1, "á": 2, "é": 2, "í": 2, "ó": 2, "ú": 2, "ǎ": 3, "ě": 3, "ǐ": 3, "ǒ": 3, "ǔ": 3, "à": 4, "è": 4, "ì": 4, "ò": 4, "ù": 4 };
  const toneOf = (s) => tones[[...s].find((c) => tones[c])] || 5;
  const hidden = mode === "write";
  const dots = mode === "watch" ? "" : `<ol class="writing-dots">${shu.strokes.map((_, i) =>
    `<li class="${i < written ? (i === 1 ? "helped" : "clean") : i === written ? "next" : "ahead"}"></li>`).join("")}</ol>`;
  const said = mode === "watch" ? "" : mode === "trace" ? "That's stroke 4 — stroke 3 comes first." : `Stroke ${written + 1} of ${shu.strokes.length}`;
  const controls = mode === "watch"
    ? `<button class="icon-btn" aria-label="Previous stroke"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5l-7 7 7 7"/></svg></button>
       <button class="tb-btn primary">Play</button>
       <button class="icon-btn" aria-label="Next stroke" disabled><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5l7 7-7 7"/></svg></button>
       <span class="writing-count">Stroke 4 of 4</span><button class="tb-btn">Again</button><button class="tb-btn">Next character</button>`
    : `<button class="tb-btn">Show the next stroke</button>${hidden ? '<button class="tb-btn">Peek</button>' : ""}<button class="tb-btn">Start over</button>`;
  return `<div class="modal-backdrop" id="writingBackdrop"><section class="settings writing-dialog" role="dialog" aria-modal="true">
    <header><h2>${hidden ? "Write from memory" : `Write ${word.headword}`}</h2><button class="close" data-writing-close aria-label="Close">×</button></header>
    <div class="settings-body writing-body">
      <div class="writing-top">
        <div class="writing-prompt"><span class="writing-reading">${syllables.map((s, i) =>
          `<span class="tone-${toneOf(s)}${i === at ? " now" : ""}">${s}</span>`).join("")}</span>
          <button class="say always head" aria-label="Listen"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg></button>
          <span class="writing-gloss">${word.shortGloss || "library"}</span></div>
        <div class="seg writing-modes">${["watch", "trace", "write"].map((m) =>
          `<button data-writing-mode="${m}" class="${m === mode ? "on" : ""}">${m[0].toUpperCase() + m.slice(1)}</button>`).join("")}</div>
      </div>
      <div class="writing-chars">${chars.map((c, i) =>
        `<button class="writing-char${i === at ? " on" : ""}${i < at ? " done" : ""}"><span class="glyph">${hidden && i >= at ? "?" : c}</span>${i < at ? '<span class="score">86</span>' : ""}</button>`).join("")}</div>
      <div class="writing-stage"><svg class="writing-pad${mode === "watch" ? "" : " drawing"}" viewBox="${-MARGIN} ${-MARGIN} ${SPAN} ${SPAN}">
        <g class="writing-grid"><rect x="0" y="0" width="${BOX}" height="${BOX}"/><path class="guide" d="M 512 0 V 1024 M 0 512 H 1024 M 0 0 L 1024 1024 M 1024 0 L 0 1024"/></g>
        <g transform="${FLIP}">${outline}${solid}</g>${numbers}
      </svg></div>
      ${dots}
      <p class="writing-said">${said}</p>
      <div class="writing-controls">${controls}</div>
    </div></section></div>`;
}

function openWriting(word, mode = "trace") {
  document.getElementById("writingBackdrop")?.remove();
  document.body.insertAdjacentHTML("beforeend", writingSheet(word, mode));
  const node = document.getElementById("writingBackdrop");
  node.addEventListener("click", (event) => {
    const chosen = event.target.closest("[data-writing-mode]");
    if (chosen) { openWriting(word, chosen.dataset.writingMode); return; }
    if (event.target === node || event.target.closest("[data-writing-close]")) node.remove();
  });
}
