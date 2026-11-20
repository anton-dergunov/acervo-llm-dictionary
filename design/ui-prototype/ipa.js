/* The IPA guide's panel, as a still (`docs/features/ipa-guide.md`): the same markup and classes as
   `web/src/ipa/SoundsPanel.tsx`, for the transcriptions in `data.js`. A popover under the
   transcription; in the phone frame, a sheet over the lower part of the screen. Nothing plays.

   IPA_SAMPLE is the rows of the app's table (`web/src/ipa/symbols.json`) these words use, copied. */

const IPA_SAMPLE = {"letters": {"p": {"name": "voiceless bilabial plosive", "how": "Close both lips, then open them, with no voice.", "like": "\"p\" in \"spin\". At the start of a word English adds a puff of air (pʰ), as in \"pin\".", "heard": null}, "b": {"name": "voiced bilabial plosive", "how": "Like p, but with the voice on: the throat buzzes while you say it.", "like": "\"b\" in \"bed\".", "heard": null}, "t": {"name": "voiceless alveolar plosive", "how": "The tongue tip stops the air at the ridge behind the upper teeth, then lets go, with no voice.", "like": "\"t\" in \"stop\". English \"top\" adds a puff of air (tʰ).", "heard": null}, "d": {"name": "voiced alveolar plosive", "how": "Like t, but with the voice on: the throat buzzes while you say it.", "like": "\"d\" in \"dog\".", "heard": null}, "k": {"name": "voiceless velar plosive", "how": "The back of the tongue stops the air against the soft palate, then lets go, with no voice.", "like": "\"k\" in \"skin\". English \"kin\" adds a puff of air (kʰ).", "heard": null}, "m": {"name": "bilabial nasal", "how": "Lips closed, and the air goes out through the nose: a hum.", "like": "\"m\" in \"man\".", "heard": null}, "n": {"name": "alveolar nasal", "how": "The tongue tip on the ridge behind the upper teeth, air through the nose.", "like": "\"n\" in \"no\".", "heard": null}, "r": {"name": "alveolar trill", "how": "The tongue tip vibrates against the ridge behind the upper teeth, the rolled r.", "like": null, "heard": "Spanish rr, as in perro (dog); Russian р, as in рыба (fish)."}, "ɾ": {"name": "alveolar tap", "how": "The tongue tip taps the ridge behind the upper teeth once, quickly.", "like": "The \"tt\" in American \"butter\".", "heard": "Spanish r between vowels, as in pero (but)."}, "β": {"name": "voiced bilabial fricative", "how": "Like ɸ, with the voice on, a soft b where the lips do not close.", "like": null, "heard": "Spanish b or v between vowels, as in lobo (wolf)."}, "f": {"name": "voiceless labiodental fricative", "how": "The lower lip against the upper teeth, air pushed through.", "like": "\"f\" in \"fan\".", "heard": null}, "θ": {"name": "voiceless dental fricative", "how": "The tongue tip at the upper teeth, air pushed through.", "like": "\"th\" in \"thin\".", "heard": null}, "ð": {"name": "voiced dental fricative", "how": "Like θ, but with the voice on: the throat buzzes while you say it.", "like": "\"th\" in \"this\".", "heard": null}, "s": {"name": "voiceless alveolar fricative", "how": "The tongue tip near the ridge behind the upper teeth, a hiss.", "like": "\"s\" in \"see\".", "heard": null}, "ʂ": {"name": "voiceless retroflex fricative", "how": "Like \"sh\", but with the tongue tip curled back behind the ridge.", "like": "Close to \"sh\" in \"shoe\", with the tongue curled back.", "heard": "Mandarin sh, as in 书 shū (book); Russian ш, as in шар (ball)."}, "x": {"name": "voiceless velar fricative", "how": "Air hissing between the back of the tongue and the soft palate.", "like": "\"ch\" in Scottish \"loch\".", "heard": "German ch, as in Buch (book); Spanish j, as in jamón (ham); Russian х; Mandarin h, as in 好 hǎo (good)."}, "h": {"name": "voiceless glottal fricative", "how": "Air through the open throat, no shape in the mouth.", "like": "\"h\" in \"hat\".", "heard": null}, "j": {"name": "palatal approximant", "how": "The middle of the tongue raised towards the hard palate.", "like": "\"y\" in \"yes\". It is never the English \"j\".", "heard": null}, "l": {"name": "alveolar lateral approximant", "how": "The tongue tip on the ridge behind the upper teeth, air past its sides.", "like": "\"l\" in \"leaf\".", "heard": null}, "i": {"name": "close front unrounded vowel", "how": "The tongue high and forward, lips spread.", "like": "\"ee\" in \"see\", without the slight \"y\" glide English adds at its end.", "heard": null}, "u": {"name": "close back rounded vowel", "how": "The tongue high and back, the lips rounded and pushed forward.", "like": "\"oo\" in \"food\", without the slight \"w\" glide English adds at its end.", "heard": null}, "ɪ": {"name": "near-close near-front unrounded vowel", "how": "A relaxed \"ee\", slightly lower and shorter.", "like": "\"i\" in \"sit\".", "heard": null}, "ʊ": {"name": "near-close near-back rounded vowel", "how": "A relaxed \"oo\", slightly lower, with the lips only lightly rounded.", "like": "\"oo\" in \"foot\".", "heard": null}, "e": {"name": "close-mid front unrounded vowel", "how": "The tongue a little lower than for \"ee\", lips spread.", "like": "The \"a\" in \"say\", without the glide into \"y\".", "heard": "French é, as in été (summer); German ee, as in See (lake)."}, "o": {"name": "close-mid back rounded vowel", "how": "The tongue back, lips rounded, a little lower than \"oo\".", "like": "The \"o\" in \"go\", without the glide into \"w\".", "heard": "French eau (water); German o, as in so."}, "ə": {"name": "mid central vowel", "how": "The tongue at rest in the middle of the mouth, the \"schwa\".", "like": "\"a\" in \"about\".", "heard": null}, "ɜ": {"name": "open-mid central unrounded vowel", "how": "A relaxed vowel in the middle of the mouth, lower than ə.", "like": "The \"ir\" in British \"bird\" (written ɜː, since it is long).", "heard": null}, "ɔ": {"name": "open-mid back rounded vowel", "how": "The tongue low and back, the lips rounded, the mouth fairly open.", "like": "The \"ou\" in British \"thought\" (written ɔː, since it is long).", "heard": "French o, as in porte (door)."}, "a": {"name": "open front unrounded vowel", "how": "The mouth wide open, the tongue low and forward. Many transcriptions use it for the \"ah\" of the middle of the mouth.", "like": "Between the \"a\" in \"cat\" and the \"a\" in \"father\".", "heard": "Spanish a, as in casa (house)."}, "tʰ": {"name": "aspirated voiceless alveolar plosive", "how": "t followed by a puff of air you can feel on your hand.", "like": "\"t\" in \"top\".", "heard": "Mandarin t, as in 他 tā (he)."}}, "marks": {"ʰ": {"name": "aspirated", "how": "Followed by a puff of air. English \"pin\" is pʰ and \"spin\" is p. In Mandarin the puff is what tells Pinyin p (pʰ) from b (p)."}, "̯": {"name": "non-syllabic", "how": "A vowel that does not make a syllable of its own: it glides into or out of its neighbour. The \"i̯\" of ai̯ is the \"y\" at the end of \"eye\", the \"u̯\" of ou̯ the \"w\" at the end of \"go\"."}, "ˈ": {"name": "primary stress", "how": "The syllable after it is stressed. \"about\" is əˈbaʊt."}, "ː": {"name": "long", "how": "The sound before it is held longer. \"see\" is siː."}, ".": {"name": "syllable break", "how": "A new syllable starts here: \"hotel\" is hoʊ.ˈtɛl."}}, "tones": {"˥": {"name": "high level", "how": "The pitch stays high and even, as if singing one note.", "mandarin": "1st tone, as in 妈 mā (mother)."}, "˧˥": {"name": "rising", "how": "The pitch rises from the middle to the top, as in a surprised \"what?\".", "mandarin": "2nd tone, as in 麻 má (hemp)."}, "˨˩˦": {"name": "dipping", "how": "The pitch dips low, then rises. In running speech it often stays low (˨˩).", "mandarin": "3rd tone, as in 马 mǎ (horse)."}}, "pinyin": {"initials": {"t": {"ipa": "tʰ", "how": "\"t\" in \"top\", with a strong puff of air.", "example": "tā"}, "g": {"ipa": "k", "how": "Like \"k\" in \"skin\": no puff of air. To English ears it often sounds like a \"g\", though the voice is not on.", "example": "gē"}, "sh": {"ipa": "ʂ", "how": "Like \"sh\" in \"shoe\", with the tongue tip curled back towards the roof of the mouth, which makes it sound deeper.", "example": "shū"}}, "finals": {"u": {"ipa": "u", "how": "\"oo\" in \"food\". After j, q, x and y it is spelt u but said ü (y).", "example": "bù"}, "uan": {"ipa": "u̯an", "how": "\"wahn\": a short \"oo\" gliding into \"ahn\". After j, q, x and y the same spelling is üan instead. Written wan at the start of a syllable, as in 万 wàn (ten thousand).", "example": "duǎn"}}, "tones": {"1": {"mark": "ā", "ipa": "˥", "how": "High and level, held steady near the top of your voice, as if singing one note."}, "2": {"mark": "á", "ipa": "˧˥", "how": "Rising from the middle to the top, as in a surprised \"what?\"."}, "3": {"mark": "ǎ", "ipa": "˨˩˦", "how": "Low, dipping, then rising; in running speech often just low."}}}};

const IPA_STRESS = new Set(["ˈ", "ˌ"]);
const IPA_TONE_LETTERS = new Set(["˥", "˦", "˧", "˨", "˩"]);
const ipaCircle = (mark) => /\p{M}/u.test(mark) ? `◌${mark}` : IPA_STRESS.has(mark) ? `${mark}◌` : mark;
/* A function, not a value: app.js, which draws the icons, loads after this file. */
const ipaPlay = () => `<button class="say always" aria-label="Listen">${ICON.play}</button>`;

/* Cut as the app's splitter does, for these words: a letter (longest first) keeps the marks after it,
   a run of tone letters is one tone, stress is a row of its own, and each unit is listed once. */
function ipaUnits(ipa) {
  const chars = Array.from(ipa.normalize("NFC")), units = [], seen = new Set();
  for (let at = 0; at < chars.length;) {
    const c = chars[at];
    if ("/[] .".includes(c)) { at += 1; continue; }
    if (IPA_TONE_LETTERS.has(c)) {
      let end = at; while (IPA_TONE_LETTERS.has(chars[end])) end += 1;
      units.push({ kind: "tone", text: chars.slice(at, end).join("") }); at = end; continue;
    }
    if (IPA_STRESS.has(c)) { units.push({ kind: "mark", text: c }); at += 1; continue; }
    const two = chars.slice(at, at + 2).join("");
    const base = IPA_SAMPLE.letters[two] ? two : c;
    at += Array.from(base).length;
    const marks = [];
    while (chars[at] && IPA_SAMPLE.marks[chars[at]] && !IPA_STRESS.has(chars[at])) marks.push(chars[at++]);
    units.push({ kind: "sound", text: base + marks.join(""), base, marks });
  }
  return units.filter((u) => !seen.has(u.kind + u.text) && seen.add(u.kind + u.text));
}

function ipaRow(symbol, body, play = true) {
  return `<li class="ipa-row"><span class="ipa-sym">${symbol}</span><div class="ipa-text">${body}</div>${play ? ipaPlay() : '<span class="ipa-play-none"></span>'}</li>`;
}
const ipaMarkLine = (mark) => {
  const row = IPA_SAMPLE.marks[mark];
  return `<p class="ipa-mark-line"><span class="ipa-mark-sym">${esc(ipaCircle(mark))}</span> <b>${esc(row.name)}</b>${row.how ? ": " + esc(row.how) : ""}</p>`;
};
const ipaPitch = (letters) => {
  const levels = Array.from(letters, (l) => ({ "˥": 5, "˦": 4, "˧": 3, "˨": 2, "˩": 1 })[l]);
  const y = (l) => 17 - (l - 1) * 3.5, step = levels.length > 1 ? 24 / (levels.length - 1) : 0;
  const points = levels.length > 1 ? levels.map((l, i) => `${2 + i * step},${y(l)}`).join(" ") : `2,${y(levels[0])} 26,${y(levels[0])}`;
  return `<svg class="ipa-pitch" viewBox="0 0 28 20" aria-hidden="true"><line x1="0" y1="19" x2="28" y2="19"/><polyline points="${points}"/></svg>`;
};

function ipaPanel(word, phone) {
  const units = ipaUnits(word.ipa);
  const rows = units.map((u) => {
    if (u.kind === "tone") {
      const t = IPA_SAMPLE.tones[u.text] || { name: "contour", how: "" };
      return ipaRow(`<span class="ipa-tone"><span>${esc(u.text)}</span>${ipaPitch(u.text)}</span>`,
        `<p class="ipa-how"><b>${esc(t.name[0].toUpperCase() + t.name.slice(1))}.</b> ${esc(t.how)}</p>${t.mandarin ? `<p class="ipa-like">Mandarin ${esc(t.mandarin)}</p>` : ""}`);
    }
    if (u.kind === "mark") {
      const m = IPA_SAMPLE.marks[u.text];
      return ipaRow(esc(ipaCircle(u.text)), `<p class="ipa-how"><b>${esc(m.name[0].toUpperCase() + m.name.slice(1))}.</b> ${esc(m.how)}</p>`, false);
    }
    if (u.kind !== "sound") return "";
    const r = IPA_SAMPLE.letters[u.base];
    if (!r) return ipaRow(esc(u.text), `<p class="ipa-how">Not a symbol this guide explains.</p>`);
    const like = r.like ? `<p class="ipa-like">${esc(r.like.startsWith('"') ? "Like " + r.like : r.like)}</p>` : "";
    const heard = r.heard ? `<p class="ipa-like">Heard in ${esc(r.heard)}</p>` : "";
    return ipaRow(esc(u.text), `<p class="ipa-how">${esc(r.how)}</p>${like}${heard}<p class="ipa-name">${esc(r.name)}</p>${u.marks.map(ipaMarkLine).join("")}`);
  }).join("");
  const p = IPA_SAMPLE.pinyin;
  const tonesMark = { 1: "◌̄", 2: "◌́", 3: "◌̌" };
  const syllable = (text, tone, initial, final) => `<div class="ipa-syllable"><p class="ipa-syllable-name tone-${tone}">${text}</p><ul class="ipa-rows">
    ${[["initials", initial], ["finals", final]].map(([part, letters]) => { const r = p[part][letters]; return ipaRow(`<span class="ipa-pinyin-letters">${letters}</span>`,
      `<p class="ipa-how"><span class="ipa-said">/${esc(r.ipa)}/</span> ${esc(r.how)}</p><p class="ipa-says">The recording says <span class="ipa-said-word">${esc(r.example)}</span>.</p>`); }).join("")}
    ${ipaRow(`<span class="ipa-tone-mark tone-${tone}">${tonesMark[tone]}</span>`, `<p class="ipa-how"><b>Tone ${tone}</b> <span class="ipa-said">${p.tones[tone].ipa}</span>. ${esc(p.tones[tone].how)}</p>`)}
  </ul></div>`;
  const pinyin = word.language === "zh-Hans" ? `<section class="ipa-pinyin" aria-label="Pinyin"><h3>Pinyin</h3>
    ${syllable("tú", 2, "t", "u")}${syllable("shū", 1, "sh", "u")}${syllable("guǎn", 3, "g", "uan")}</section>` : "";
  const heading = Array.from(word.ipa).map((c) => IPA_STRESS.has(c) ? `<span class="ipa-stress">${c}</span>` : esc(c)).join("");
  return `<section class="ipa-panel ${phone ? "sheet" : "pop"}" id="ipaPanel" role="dialog" aria-label="Sounds in ${esc(word.ipa)}">
    <header class="ipa-head"><span class="ipa-heading">${heading}</span>
      <button class="icon-btn ipa-close" data-ipa-close aria-label="Close">${ICON.close}</button></header>
    <ul class="ipa-rows">${rows}</ul>${pinyin}</section>`;
}

/* In the phone frame the sheet goes to the frame (the `.viewport` contains it), as the app's goes to
   the document; elsewhere the popover goes under the transcription. */
function openIpa(word) {
  closeIpa();
  const phone = document.body.classList.contains("phone");
  const html = ipaPanel(word, phone);
  if (phone) document.querySelector(".viewport").insertAdjacentHTML("beforeend", `<div class="ipa-backdrop" data-ipa-close></div>${html}`);
  else document.querySelector(".ipa-open")?.insertAdjacentHTML("afterend", html);
  document.querySelector(".ipa-open")?.setAttribute("aria-expanded", "true");
}
function closeIpa() {
  document.querySelectorAll("#ipaPanel, .ipa-backdrop").forEach((node) => node.remove());
  document.querySelector(".ipa-open")?.setAttribute("aria-expanded", "false");
}
