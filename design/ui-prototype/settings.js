/* The Settings window, as a static mock. Every write is a stub; the data is shaped like the routes'
   answers. What is agreed here — the groups, the kit, the words — is what the app's Settings is built
   from, so the port is a move rather than a rewrite. */

const params = new URLSearchParams(location.search);
if (params.get("theme")) document.documentElement.dataset.theme = params.get("theme");
const MAC = params.get("host") === "mac";

const s = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.8",
            "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" };
const svg = (body) => `<svg ${Object.entries(s).map(([k, v]) => `${k}="${v}"`).join(" ")}>${body}</svg>`;
const ICON = {
  general: svg('<circle cx="12" cy="12" r="3"/><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8"/>'),
  reading: svg('<path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H18v14H5.5A1.5 1.5 0 0 0 4 19.5z"/><path d="M4 19.5A1.5 1.5 0 0 1 5.5 18H20v2.5H5.5"/><path d="M8 8h6"/>'),
  dictionaries: svg('<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.2 2.3 3.3 5.2 3.3 8.5S14.2 18.2 12 20.5c-2.2-2.3-3.3-5.2-3.3-8.5S9.8 5.8 12 3.5z"/>'),
  vocabularies: svg('<path d="M5 21V4"/><path d="M5 4h11l-2 4 2 4H5"/>'),
  topics: svg('<path d="M4 12.5V5a1 1 0 0 1 1-1h7.5L20 11.5 12.5 19z"/><circle cx="8.5" cy="8.5" r="1.3"/>'),
  rules: svg('<path d="M4 20h4l10-10-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>'),
  pictures: svg('<rect x="3.5" y="5" width="17" height="14" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M4 16.5l4.5-4 3.5 3 3-2.5 5 4"/>'),
  pronunciation: svg('<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>'),
  clips: svg('<rect x="3.5" y="5" width="17" height="14" rx="2"/><path d="M10 9.5v5l4.5-2.5z"/>'),
  loops: svg('<path d="M6 7h11a3 3 0 0 1 3 3v1"/><path d="M18 17H7a3 3 0 0 1-3-3v-1"/><path d="M8.5 4.5L6 7l2.5 2.5"/><path d="M15.5 19.5L18 17l-2.5-2.5"/>'),
  stories: svg('<path d="M12 6.5C10 5 7.5 4.5 4 4.5v13c3.5 0 6 .5 8 2 2-1.5 4.5-2 8-2v-13c-3.5 0-6 .5-8 2z"/><path d="M12 6.5v13"/>'),
  providers: svg('<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9.5 9.5h5v5h-5z"/><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3"/>'),
  activity: svg('<path d="M3.5 12h4l2.5-6 4 12 2.5-6h4"/>'),
  anki: svg('<rect x="4" y="6.5" width="12" height="14" rx="2"/><path d="M8 3.5h10a2 2 0 0 1 2 2V17"/>'),
  sync: svg('<path d="M20 12a8 8 0 1 1-2.34-5.66"/><path d="M20 4v5h-5"/>'),
  data: svg('<path d="M4 7.5h16v12H4z"/><path d="M3 4h18v3.5H3z"/><path d="M10 11.5h4"/>'),
  chev: svg('<path d="M9 5l7 7-7 7"/>'),
  back: svg('<path d="M15 5l-7 7 7 7"/>'),
  close: svg('<path d="M6 6l12 12M18 6L6 18"/>'),
  up: svg('<path d="M6 15l6-6 6 6"/>'),
  down: svg('<path d="M6 9l6 6 6-6"/>'),
  alert: svg('<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.2v.1"/>'),
  check: svg('<path d="M6 12.5l4 4 8-8.5"/>'),
  play: `<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13l11-6.5z"/></svg>`
};

const GROUPS = [
  { title: "General", pages: [["general", "General"], ["reading", "Reading"], ["dictionaries", "Dictionaries"]] },
  { title: "Vocabulary", pages: [["vocabularies", "Vocabularies"], ["topics", "Topics"], ["rules", "Rules"]] },
  { title: "Media", pages: [["pictures", "Pictures"], ["pronunciation", "Pronunciation"], ["clips", "Clips"], ["loops", "Loops"], ["stories", "Stories"]] },
  { title: "Server", pages: [["providers", "Providers"], ["activity", "Activity"], ["anki", "Anki"]] },
  { title: "Data", pages: [["sync", "Sync"], ["data", "Data"]] }
];
const TITLES = Object.fromEntries(GROUPS.flatMap((group) => group.pages));

const esc = (text) => String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

/* ── the kit ── */
const group = (title, rows, foot = "", count = "", aligned = false) => `<section class="pref-group">
  ${title ? `<h4>${esc(title)}${count ? `<span class="count">${esc(count)}</span>` : ""}</h4>` : ""}
  <div class="pref-card${aligned ? " aligned" : ""}">${rows.join("")}</div>
  ${foot ? `<p class="pref-foot">${foot}</p>` : ""}
</section>`;
const text = (label, hint) => `<span class="pref-text"><span class="pref-label">${esc(label)}</span>${hint ? `<span class="pref-hint">${esc(hint)}</span>` : ""}</span>`;
const toggle = (label, hint, on, disabled = false) => `<label class="pref-row">${text(label, hint)}
  <input type="checkbox" role="switch" class="toggle" ${on ? "checked" : ""} ${disabled ? "disabled" : ""}></label>`;
const row = (label, hint, trailing = "") => `<div class="pref-row">${text(label, hint)}${trailing}</div>`;
const link = (label, value, to, hint = "") => `<button class="pref-row" data-sub="${to}">${text(label, hint)}${value ? `<span class="pref-value">${esc(value)}</span>` : ""}${ICON.chev.replace("<svg", '<svg class="chev"')}</button>`;
/* A voice: its ▶ at the start of the row, and the rest of the row the way to its page or the choice of it. */
const listen = (name) => `<button class="icon-btn listen" aria-label="Hear ${esc(name)}">${ICON.play}</button>`;
const voiceLink = (label, value, to, hint = "") => `<div class="pref-row split">${listen(value)}<button class="pref-open" data-sub="${to}">${text(label, hint)}<span class="pref-value">${esc(value)}</span>${ICON.chev.replace("<svg", '<svg class="chev"')}</button></div>`;
const choice = (label, hint, checked = false) => `<div class="pref-row split">${listen(label)}<button class="pref-open" role="radio" aria-checked="${checked}">${text(label, hint)}${checked ? `<span class="pref-check">${ICON.check}</span>` : ""}</button></div>`;
const voiceSelect = (label, hint, options, chosen) => `<div class="pref-row split">${listen(label)}${text(label, hint)}
  <select class="pref-select">${options.map((o) => `<option ${o === chosen ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></div>`;
const field = (label, value, placeholder = "") => `<label class="pref-row">${text(label)}<input class="pref-input" value="${esc(value)}" placeholder="${esc(placeholder)}"></label>`;
const area = (label, value, placeholder, limit) => `<div class="pref-row stack">${text(label)}
  <textarea class="pref-text-area short" placeholder="${esc(placeholder)}">${esc(value)}</textarea>
  <span class="pref-hint pref-count">${value.trim().length} / ${limit}</span></div>`;
/* A language to choose: its flag, its English name, its own name under it, and why not, if not. */
const language = (flag, name, autonym, why = "") => `<button class="pref-row pref-language" ${why ? "disabled" : ""}>
  <span class="pref-flag" aria-hidden="true">${flag}</span>${text(name, autonym === name ? "" : autonym)}${why ? `<span class="pref-value">${esc(why)}</span>` : ""}</button>`;
const search = (placeholder, value = "") => group("", [`<label class="pref-row"><input class="pref-input" type="search" value="${esc(value)}" placeholder="${esc(placeholder)}"></label>`]);
const action = (label, kind = "") => `<button class="pref-row pref-action ${kind}">${esc(label)}</button>`;
const select = (label, hint, options, chosen) => `<label class="pref-row">${text(label, hint)}
  <select class="pref-select">${options.map((o) => `<option ${o === chosen ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></label>`;
const segmented = (label, hint, options, chosen) => `<div class="pref-row stack">${label ? text(label, hint) : ""}
  <div class="seg" role="radiogroup" aria-label="${esc(label)}">${options.map((o) =>
    `<button role="radio" aria-checked="${o === chosen}" class="${o === chosen ? "on" : ""}">${esc(o)}</button>`).join("")}</div></div>`;
const button = (label, primary = false) => `<button class="tb-btn ${primary ? "primary" : ""}">${esc(label)}</button>`;
const notice = (message) => `<div class="pref-notice" role="status">${ICON.alert}<span>${message}</span></div>`;
const skeletonRow = () => `<div class="pref-row"><span class="pref-text"><span class="pref-skel"></span><span class="pref-skel"></span></span></div>`;
const reorder = (label, hint, on, badge = "") => `<div class="pref-row">
  <input type="checkbox" role="switch" class="toggle" aria-label="Use ${esc(label)}" ${on ? "checked" : ""}>
  ${text(label, hint)}${badge ? `<span class="badge">${esc(badge)}</span>` : ""}
  <span class="pref-reorder"><button class="icon-btn" aria-label="Move up">${ICON.up}</button><button class="icon-btn" aria-label="Move down">${ICON.down}</button></span></div>`;

/* ── providers and usage ──
   The mock of docs/plans/provider-management.md: a provider is an account with one key, offering
   models of several kinds; Usage counts every call per model, against a free allowance if one is set. */
const PROVIDERS = {
  "provider-gemini": { label: "Gemini API", kinds: "Text · Voices", state: ["ok", "Works"] },
  "provider-google": { label: "Google Cloud", kinds: "Voices · Reading photos", state: ["ok", "Works"] },
  "provider-cloudflare": { label: "Cloudflare", kinds: "Text · Pictures", state: ["ok", "Works"] },
  "provider-elevenlabs": { label: "ElevenLabs", kinds: "Voices", state: ["ok", "Works"] },
  "provider-groq": { label: "Groq", kinds: "Text", state: ["ok", "Works"] },
  "provider-openrouter": { label: "OpenRouter", kinds: "Text", state: ["bad", "Key rejected"] }
};
const stateMark = ([tone, words]) => `<span class="pref-state ${tone}">${tone === "ok" ? ICON.check : ICON.alert}${esc(words)}</span>`;
const providerLink = (id, p) => `<button class="pref-row" data-sub="${id}">${text(p.label, p.kinds)}${stateMark(p.state)}${ICON.chev.replace("<svg", '<svg class="chev"')}</button>`;
const subAction = (label, to, kind = "") => `<button class="pref-row pref-action ${kind}" data-sub="${to}">${esc(label)}</button>`;
/* A pair in an order: the provider, its model in the provider's own spelling, and how much is spent. */
const pair = (provider, model, used, on, badge) => `<div class="pref-row${on ? "" : " unavailable"}">
  <input type="checkbox" role="switch" class="toggle" aria-label="Use ${esc(provider)} ${esc(model)}" ${on ? "checked" : ""}>
  <span class="pref-text"><span class="pref-label">${esc(provider)} · <span class="model-id">${esc(model)}</span></span>${used ? `<span class="pref-hint">${esc(used)}</span>` : ""}</span>
  ${badge ? `<span class="badge">${esc(badge)}</span>` : ""}
  <span class="pref-reorder"><button class="icon-btn" aria-label="Move up">${ICON.up}</button><button class="icon-btn" aria-label="Move down">${ICON.down}</button></span></div>`;
const modelLabel = (id, hint) => `<span class="pref-text"><span class="pref-label mono">${esc(id)}</span>${hint ? `<span class="pref-hint">${esc(hint)}</span>` : ""}</span>`;
const modelRow = (id, hint) => `<div class="pref-row">${modelLabel(id, hint)}<button class="icon-btn" aria-label="Remove ${esc(id)}">${ICON.close}</button></div>`;
const modelLink = (id, hint, to) => `<button class="pref-row" data-sub="${to}">${modelLabel(id, hint)}${ICON.chev.replace("<svg", '<svg class="chev"')}</button>`;
const keyField = (label, placeholder) => `<label class="pref-row">${text(label)}<input class="pref-input mono" type="password" autocomplete="off" placeholder="${esc(placeholder)}"></label>`;
const keyRow = (label, hint, shown) => row(label, hint, `<span class="pref-value mono">${esc(shown)}</span>${button("Replace")}`);
const checkRow = (state, hint, again = "Check again") => `<div class="pref-row"><span class="pref-text">${stateMark(state)}<span class="pref-hint">${esc(hint)}</span></span>${again ? button(again) : ""}</div>`;
/* How much of an allowance is gone: the figure, then a thin bar, warning-coloured from 90%. */
const gauge = (used, of, words) => {
  const share = Math.min(1, used / of);
  return `<span class="pref-gauge${share >= .9 ? " near" : ""}"><span class="pref-gauge-words">${esc(words)}</span>
    <span class="pref-gauge-track" role="meter" aria-valuemin="0" aria-valuemax="${of}" aria-valuenow="${used}" aria-label="${esc(words)}"><span style="width:${(share * 100).toFixed(1)}%"></span></span></span>`;
};
const usageRow = (id, hint, meter = "", to = "usage-model") => `<button class="pref-row usage" data-sub="${to}">${modelLabel(id, hint)}${meter}${ICON.chev.replace("<svg", '<svg class="chev"')}</button>`;
const figures = (items) => `<section class="pref-group"><div class="pref-card"><div class="pref-figures">${items.map(([n, l]) =>
  `<div class="pref-figure"><span class="pref-figure-n">${esc(n)}</span><span class="pref-figure-l">${esc(l)}</span></div>`).join("")}</div></div></section>`;

/* Thirty days of one model, oldest first: calls that answered, and calls that failed. The last
   eight days run into the free allowance of ten a day, which is what a rate limit looks like here. */
const DAYS = [6, 4, 8, 3, 0, 5, 7, 9, 2, 6, 10, 8, 4, 0, 3, 7, 9, 10, 6, 5, 8, 10, 10, 9, 10, 10, 7, 10, 10, 9]
  .map((ok, i) => ({ ok, failed: [0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,2,0,0,0,3,2,0,4,3,0,2,0,2][i] }));
function dayLabel(index) {
  const date = new Date(Date.UTC(2026, 10, 5 - (DAYS.length - 1 - index)));
  return index === DAYS.length - 1 ? "Today" : date.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}
function chart() {
  const top = 15;
  const bars = DAYS.map((d, i) => {
    const tip = `${dayLabel(i)}: ${d.ok} answered${d.failed ? `, ${d.failed} failed` : ""}`;
    const ok = d.ok ? `<span class="seg-ok${d.failed ? "" : " end"}" style="height:${(d.ok / top) * 100}%"></span>` : "";
    const failed = d.failed ? `<span class="seg-failed end" style="height:${(d.failed / top) * 100}%"></span>` : "";
    return `<span class="pref-bar" tabindex="0" data-tip="${esc(tip)}" aria-label="${esc(tip)}">${ok}${failed}</span>`;
  }).join("");
  return `<div class="pref-chart">
    <div class="pref-legend"><span><i class="seg-ok"></i>Answered</span><span><i class="seg-failed"></i>Failed</span></div>
    <div class="pref-plot"><span class="pref-tick" style="bottom:${(10 / top) * 100}%">10</span><span class="pref-grid" style="bottom:${(10 / top) * 100}%"></span>
      <div class="pref-bars">${bars}</div><span class="pref-tip" hidden></span></div>
    <div class="pref-axis"><span>${dayLabel(0)}</span><span>${dayLabel(15)}</span><span>Today</span></div>
  </div>`;
}

/* ── the pages ── */
const PAGES = {
  general: () => [
    `<section class="pref-group"><div class="pref-card"><div class="pref-row">
      <span class="pref-avatar">L</span>${text("learner@account.example.com", "1,728 entries across 13 topics on this device")}</div></div></section>`,
    MAC
      ? group("Updates", [
          row("Build 53 is available", "This Mac runs build 52", button("Update and Restart", true)),
          toggle("Check for updates automatically", "", true),
          toggle("Install updates automatically", "They start the next time Acervo opens", false)
        ], "Version 0.4.0 (52)")
      : group("Updates", [
          row("Acervo is up to date", "Version 0.1.0 (202610181718)"),
          row("Acervo for macOS", "Version 0.4.0, build 52", button("Download"))
        ]),
    MAC ? group("This Mac", [
      row("Server", "", `<span class="pref-value mono">acervo.example.com</span>`),
      toggle("Open Acervo at login", "", true),
      toggle("Show the window at login", "Off, Acervo starts in the menu bar", false, false)
    ]) : "",
    group("", MAC ? [action("Change server…"), action("Sign out", "danger")] : [action("Sign out", "danger")])
  ],

  reading: () => [
    group("Articles", [segmented("Open words as", "Cards on a touch screen, Page with a mouse", ["Automatic", "Page", "Cards"], "Automatic")]),
    group("YAML editor", [
      toggle("Wrap long lines", "", true),
      toggle("Show line numbers", "Errors name the line they are on", false)
    ], "These apply to this device only.")
  ],

  dictionaries: () => [
    group("", [row("Stored on this device", "", `<span class="pref-value">412 MB of 6.1 GB</span>`)]),
    group("Spanish", [
      dictionary("Wiktionary (Spanish)", "Stored · 38 MB", true, "Remove"),
      dictionary("Wiktionary (English)", "Not stored · 96 MB", true, "Store"),
      dictionary("RAE — Diccionario", "Opens in the browser", true, "Open")
    ]),
    group("Chinese", [
      dictionary("CC-CEDICT", "Stored · 21 MB", true, "Remove"),
      dictionary("Wiktionary (Chinese)", "Not compiled on the server", false, "")
    ], "Each dictionary downloads from its publisher.")
  ],

  vocabularies: () => [
    group("", [
      link("🇦🇷  Spanish", "1,412 words", "vocabulary", "Argentina · B1 · translated into English, Russian"),
      link("🇨🇳  Chinese (Simplified)", "316 words", "vocabulary", "translated into Russian, English")
    ]),
    `<section class="pref-group"><div class="pref-card"><button class="pref-row pref-action" data-sub="addLanguage">Add a language…</button></div></section>`
  ],

  topics: () => [
    group("Spanish", ["📥 Inbox · 3", "💬 Emotions · 120", "🍳 Kitchen · 84", "⚖️ Law · 45", "🌿 Nature · 210"].map((topic) => {
      const [name, count] = topic.split(" · ");
      return `<div class="pref-row">${text(name, `${count} words`)}<span class="pref-reorder">
        <button class="icon-btn" aria-label="Move up">${ICON.up}</button><button class="icon-btn" aria-label="Move down">${ICON.down}</button></span>
        ${button("Edit")}</div>`;
    })),
    group("", [action("Add a topic…")])
  ],

  rules: () => [
    group("Rules for everything written for you", [`<div class="pref-row stack">
      <textarea class="pref-text-area" aria-label="Rules for generated content">Prefer Peninsular Spanish. Keep examples under fifteen words.
Never use the word "literally" in a gloss.</textarea>
      <span style="display:flex;align-items:center;gap:12px"><span class="pref-hint" style="flex:1">96 of 4,000 characters</span>${button("Save", true)}</span></div>`],
      "Applies to new entries, examples, chat, pictures, stories and clip choices. Ask again to rewrite what exists.")
  ],

  pictures: () => [
    group("", [
      toggle("Draw pictures", "New words get their pictures on their own", true),
      toggle("Push for stylistic variety", "Less predictable, more varied styles", false)
    ]),
    `<section class="pref-group"><h4>Styles<span class="count">18 of 23 on</span></h4><div class="pref-card">
      <div class="pref-chips">${["Ink sketch", "Watercolour", "Gouache", "Linocut", "Risograph", "Pixel art", "Claymation", "Paper cut-out",
        "Comic panel", "Children's book", "Ukiyo-e", "Art nouveau", "Blueprint", "Stained glass", "Photograph", "Film still",
        "Isometric", "Flat vector", "Chalkboard", "Embroidery", "Mosaic", "Charcoal", "Pop art"].map((name, index) =>
        `<button class="pref-chip" aria-pressed="${index % 5 !== 3}">${index % 5 !== 3 ? ICON.check : ""}${esc(name)}</button>`).join("")}</div>
      <div class="pref-row" style="justify-content:flex-end;gap:8px">${button("All on")}${button("All off")}</div></div>
      <p class="pref-foot">The writer picks the style that suits each meaning. One always stays on.</p></section>`
  ],

  pronunciation: () => [
    group("Record in advance", [
      toggle("The word itself", "", true),
      toggle("Definitions", "When they are in the language you learn", false),
      toggle("Example sentences", "", true)
    ]),
    group("Which voice reads", [
      select("Words and definitions", "", ["Clear voice", "Expressive voice"], "Clear voice"),
      select("Example sentences", "", ["Clear voice", "Expressive voice"], "Expressive voice")
    ], "The expressive voice reads with emotion; the clear one is cheaper and faster."),
    group("🇪🇸 Spanish · Argentina", [
      voiceLink("Clear voice", "Wavenet-A · United States", "voice", "wavenet · 1 backup"),
      voiceLink("Expressive voice", "Kore · Argentina", "voice-expressive", "gemini-3.1-flash-tts-preview · 1 backup")
    ], "No clear voice has an accent from Argentina yet; the nearest reads."),
    group("🇬🇧 English · United Kingdom", [
      voiceLink("Clear voice", "Wavenet-A · United Kingdom", "voice", "wavenet · 1 backup"),
      voiceLink("Expressive voice", "Puck · United Kingdom", "voice-expressive", "gemini-3.1-flash-tts-preview · 1 backup")
    ]),
    group("🇷🇺 Russian · Russia", [
      voiceLink("Clear voice", "Wavenet-B · Russia", "voice", "wavenet · 1 backup"),
      voiceLink("Expressive voice", "Charon · Russia", "voice-expressive", "gemini-3.1-flash-tts-preview · 1 backup")
    ]),
    group("On this device", [
      toggle("Keep pronunciations", "Play offline · 12 MB kept", true),
      action("Forget pronunciations on this device", "danger")
    ])
  ],

  clips: () => [
    params.get("corpus") === "down"
      ? notice("The clip corpus is not answering. Clips already saved still play.")
      : group("", [corpusRow()]),
    group("", [
      toggle("Look for clips", "New words get short spoken examples", true),
      toggle("Only passages that stand on their own", "Skip clips that need their video to make sense", true)
    ]),
    group("", [link("Channels", "64 of 80 on", "channels")])
  ],

  loops: () => [
    group("Voice", [segmented("Repetitions are", "", ["Read again each time", "Recorded once, varied"], "Read again each time")],
      "Read again sounds the emotion you wrote; recorded once is cheaper."),
    group("Guide’s voice", [voiceLink("English", "Puck · United Kingdom", "voice-expressive", "gemini-3.1-flash-tts-preview")],
      "Who says the lines in your own language. Unchosen, the same voice says every line."),
    group("Generator", [row("LexiBeat 2.3", "", `<span class="pref-value">Sample pack installed</span>`)]),
    group("On this device", [toggle("Keep loops", "Play offline · 220 MB kept", true), action("Forget loops on this device", "danger")])
  ],

  stories: () => [
    group("Voice", [segmented("Narration", "", ["Expressive", "Clear"], "Expressive")],
      "Expressive reads each passage in its own manner; clear reads a part in one go."),
    group("", [toggle("Record narration when a story is made", "Off, a part records the first time it plays", true)]),
    group("Pictures", [segmented("Keep characters and places consistent", "", ["Every style", "Drawn only", "Off"], "Drawn only")])
  ],

  /* Providers are added here, each with its own key; the orders below choose among their models.
     The hint under a pair is how much of its free allowance is gone, the same figure Usage shows. */
  providers: () => [
    notice(`OpenRouter refused its key, so nothing is sent to it. <button class="pref-link-inline" data-sub="provider-openrouter">Replace the key</button>`),
    group("Providers", [
      ...Object.entries(PROVIDERS).map(([id, p]) => providerLink(id, p)),
      subAction("Add a provider…", "addProvider")
    ]),
    group("", [link("Usage", "Today: 142 calls · 3 failed", "usage")]),
    ...[
      ["Text", [["Gemini API", "gemini-3.5-flash-lite", "96 of 500 today", true], ["Groq", "llama-3.3-70b-versatile", "", true],
                ["Cloudflare", "gpt-oss-20b", "", true], ["OpenRouter", "qwen3-235b:free", "", false, "Key rejected"]]],
      ["Quick look-up", [["Gemini API", "gemini-3.1-flash-lite", "21 of 500 today", true]]],
      ["Pictures", [["Cloudflare", "flux-2-klein-4b", "18 of 95 today", true], ["Cloudflare", "flux-1-schnell", "", true]]],
      ["Clear voice", [["Google Cloud", "Chirp 3 HD", "212k of 1M characters this month", true], ["Google Cloud", "WaveNet", "", true]]],
      ["Expressive voice", [["Gemini API", "gemini-3.8-flash-tts", "9 of 10 today", true], ["ElevenLabs", "eleven_v4", "3.1k of 10k characters this month", true]]],
      ["Reading photos", [["Google Cloud", "document-text-detection", "41 of 1,000 this month", true]]]
    ].map(([kind, rows]) => group(kind, rows.map(([provider, model, used, on, badge = ""]) => pair(provider, model, used, on, badge))))
  ],

  activity: () => [
    group("Nightly run", [
      select("Run at", "Europe/Madrid · next tonight", ["01:00", "02:00", "03:00", "04:00"], "03:00"),
      toggle("Update recorded speech", "New videos from your channels", true),
      row("Last run", "", `<span class="pref-value">3 Nov, 03:00 · done</span>`)
    ]),
    `<div class="pref-divider" role="separator">Recent activity</div>`,
    group("In progress", [row("Drawing pictures for “la chispa”", "2 of 3 senses", button("Cancel"))]),
    group("Could not finish", [row("Recording “apretar”", "Gemini refused: quota exhausted for today", `${button("Try again")}${button("Dismiss")}`)]),
    group("Finished recently", [row("Enriched “tierno”", "14:31"), row("Made a loop: Emotions", "13:02")])
  ],

  anki: () => [
    group("", [
      toggle("Send changes to Anki", "Last push 14:02", true),
      `<div class="pref-row" style="justify-content:flex-end">${button("Push now")}</div>`
    ]),
    group("", [
      toggle("Read your reviews every hour", "Last read 14:00", true),
      `<div class="pref-row" style="justify-content:flex-end">${button("Read now")}</div>`
    ])
  ],

  sync: () => [
    group("", [row("Up to date", "Last synced 14:49 · 1,728 entries"), action("Sync now")]),
    group("", [action("Replace this device’s copy…", "danger")], "Downloads everything again from the server.")
  ],

  data: () => [
    group("Export", [
      select("Vocabulary", "", ["All vocabularies", "Spanish", "Chinese"], "All vocabularies"),
      toggle("Obsidian notes", "", false),
      toggle("Pictures", "", true),
      toggle("Pronunciations", "", false),
      action("Export…")
    ]),
    group("Import", [action("Choose a file…")], "Words already here are updated, not duplicated."),
    group("", [action("Delete all words…", "danger")])
  ]
};

const SUBPAGES = {
  voice: { parent: "pronunciation", title: "Spanish · Clear voice", render: () => [
    group("United States", [
      choice("Wavenet-A · female", "Google Cloud Text-to-Speech · wavenet", true),
      choice("Wavenet-B · male", "Google Cloud Text-to-Speech · wavenet"),
      choice("Standard-A · female", "Google Cloud Text-to-Speech · standard")
    ], "None of these voices has an accent from Argentina; the nearest reads. The accent is set in Vocabularies."),
    group("Spain", [
      choice("Wavenet-F · female", "Google Cloud Text-to-Speech · wavenet"),
      choice("Wavenet-E · male", "Google Cloud Text-to-Speech · wavenet"),
      choice("Standard-F · female", "Google Cloud Text-to-Speech · standard")
    ]),
    group("If it can’t answer", [
      voiceSelect("Google Cloud Text-to-Speech · standard", "United States", ["Automatic · Standard-A", "Standard-A · female", "Standard-B · male"], "Automatic · Standard-A")
    ], "Each is asked in turn, in the order Providers gives."),
    group("", [action("Use the default voice")])
  ] },
  "voice-expressive": { parent: "pronunciation", title: "Spanish · Expressive voice", render: () => [
    group("Speaks any accent", [
      choice("Kore · female · firm", "Google Cloud Text-to-Speech · gemini-3.1-flash-tts-preview", true),
      choice("Puck · male · upbeat", "Google Cloud Text-to-Speech · gemini-3.1-flash-tts-preview"),
      choice("Charon · male · informative", "Google Cloud Text-to-Speech · gemini-3.1-flash-tts-preview"),
      choice("Aoede · female · breezy", "Google Cloud Text-to-Speech · gemini-3.1-flash-tts-preview")
    ], "Told to speak as in Argentina."),
    group("If it can’t answer", [
      voiceSelect("Google Cloud Text-to-Speech · gemini-2.5-flash-tts", "Argentina", ["Automatic · Kore", "Kore · female · firm", "Puck · male · upbeat"], "Automatic · Kore")
    ], "Each is asked in turn, in the order Providers gives.")
  ] },
  channels: { parent: "clips", title: "Channels", render: () => [
    group("", [row("Update now", "Last updated 3 Nov, 03:00", button("Update"))]),
    group("Spanish", [
      toggle("Dot CSV", "Science", true), toggle("La Resistencia", "Talk shows", true),
      toggle("Pantomima Full", "Comedy", false), toggle("El Orden Mundial", "News", true)
    ], "", "3 of 4 on"),
    group("Chinese", [toggle("小Lin说", "Economics", true), toggle("Mandarin Corner", "Learning", true)], "", "2 of 2 on"),
    group("", [action("Add a channel…")], "Changes take effect at the next update.")
  ] },
  addProvider: { parent: "providers", title: "Add a provider", render: () => [
    group("Free to start", [
      link("Gemini API", "", "provider-new", "Text, and voices that take a direction"),
      link("Cloudflare", "", "provider-new", "Text, pictures and voices, a daily allowance"),
      link("Groq", "", "provider-new", "Fast text"),
      link("OpenRouter", "", "provider-new", "Text from many models, some free")
    ]),
    group("Popular", [
      link("OpenAI", "", "provider-new", "Text and pictures"),
      link("Anthropic", "", "provider-new", "Text"),
      link("Google Cloud", "", "provider-new", "Voices and reading photos; text and pictures too"),
      link("ElevenLabs", "", "provider-new", "Voices that take a direction"),
      link("Azure Speech", "", "provider-new", "Voices in over a hundred languages · not yet tried with Acervo")
    ]),
    group("On your own machines", [
      link("Ollama", "", "provider-new", "Text from a model on your computer"),
      link("Speech server", "", "provider-new", "Kokoro or Piper voices on your computer"),
      link("Draw Things or Forge", "", "provider-new", "Pictures drawn on your computer")
    ]),
    group("", [link("Any compatible service", "", "provider-new", "Give its address and key")])
  ] },
  /* Choosing a provider opens its page empty: the few fields it needs, then one check. */
  "provider-new": { parent: "addProvider", title: "Cloudflare", render: () => [
    group("", [
      field("Name", "Cloudflare"),
      field("Account ID", "", "On the Workers AI page")
    ], "", "", true),
    group("Key", [keyField("API token", "Paste the token")],
      `Create a Workers AI token at <a href="#">dash.cloudflare.com</a>. It is kept on your server.`, "", true),
    `<div class="pref-buttons">${button("Cancel")}${button("Check and add", true)}</div>`
  ] },
  "provider-gemini": { parent: "providers", title: "Gemini API", render: () => [
    group("Key", [
      keyRow("API key", "From Google AI Studio", "AIza…k3Fq"),
      checkRow(["ok", "Works · 52 models"], "Checked today, 14:02")
    ]),
    group("Text", [
      modelRow("gemini-3.5-flash-lite", "500 a day free"),
      modelRow("gemini-3.1-flash-lite", "500 a day free"),
      subAction("Add a model…", "addModel")
    ]),
    group("Voices", [
      modelLink("gemini-3.8-flash-tts", "Takes a direction · any language · 10 a day free", "model-tts"),
      modelLink("gemini-3.8-flash-lite-tts", "Takes a direction · any language", "model-tts"),
      subAction("Add a model…", "addModel")
    ]),
    group("Pictures", [subAction("Add a model…", "addModel")], "Gemini has no free pictures."),
    group("", [
      link("Usage", "Today: 126 calls · 2 failed", "usage"),
      row("Google AI Studio", "Your limits and the bill", button("Open"))
    ]),
    group("", [action("Remove this provider", "danger")])
  ] },
  /* Google Cloud signs in two ways; the choice says what each one unlocks. */
  "provider-google": { parent: "providers", title: "Google Cloud", render: () => googleCloud("key") },
  "provider-google-file": { parent: "providers", title: "Google Cloud", render: () => googleCloud("file") },
  "provider-cloudflare": { parent: "providers", title: "Cloudflare", render: () => simpleProvider("Cloudflare", "API token", "Xb3d…k2Lm", "Works · account a1b2…9f0e",
    [["Text", [["gpt-oss-20b", ""]]], ["Pictures", [["flux-2-klein-4b", "About 95 a day free"], ["flux-1-schnell", "About 170 a day free"]]]]) },
  "provider-elevenlabs": { parent: "providers", title: "ElevenLabs", render: () => simpleProvider("ElevenLabs", "API key", "sk_4f…e81a", "Works · free plan",
    [["Voices", [["eleven_v4", "Takes a direction · 10k characters a month free"]]]]) },
  "provider-groq": { parent: "providers", title: "Groq", render: () => simpleProvider("Groq", "API key", "gsk_…Q2vd", "Works · 21 models",
    [["Text", [["llama-3.3-70b-versatile", "1,000 a day free"]]]]) },
  "provider-openrouter": { parent: "providers", title: "OpenRouter", render: () => [
    group("Key", [
      keyRow("API key", "From openrouter.ai", "sk-or…77Hc"),
      checkRow(["bad", "OpenRouter refused this key"], "Checked today, 09:15 · nothing is sent to it until it works", "Check again")
    ]),
    group("Text", [modelRow("qwen3-235b:free", "50 a day free")]),
    group("", [action("Remove this provider", "danger")])
  ] },
  /* One box: it searches the provider's own list, and once nothing listed matches, what is typed can
     be added as it is — a model too new for the list. A second "type its name" field asked twice. */
  addModel: { parent: "provider-gemini", title: "Add a text model", render: () => [
    search("Search Gemini’s models", "flash"),
    group("Gemini offers", [
      row("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", `<span class="pref-value">Added</span>`).replace('class="pref-label"', 'class="pref-label mono"'),
      `<button class="pref-row">${modelLabel("gemini-3.8-flash", "Gemini 3.8 Flash")}</button>`,
      `<button class="pref-row">${modelLabel("gemini-3.6-flash", "Gemini 3.6 Flash")}</button>`,
      `<button class="pref-row">${modelLabel("gemini-3.8-pro", "Gemini 3.8 Pro")}</button>`
    ], "", "52")
  ] },
  "addModel-unlisted": { parent: "provider-gemini", title: "Add a text model", render: () => [
    search("Search Gemini’s models", "gemini-3.9-flash"),
    group("Gemini offers", [action("Add “gemini-3.9-flash”")],
      "Gemini does not list it, so add it only as its own page spells it.", "52")
  ] },
  "model-tts": { parent: "provider-gemini", title: "gemini-3.8-flash-tts", render: () => [
    group("", [
      toggle("Takes a direction", "Reads as asked: warmly, slowly, as in Argentina", true),
      select("Languages", "", ["Any language", "Only some…"], "Any language")
    ]),
    group("Free allowance", [
      field("Amount", "10"),
      select("Counted in", "", ["Characters", "Calls"], "Calls"),
      select("Each", "", ["Day", "Month"], "Day")
    ], `Your own limit is on <a href="#">aistudio.google.com</a>. Usage measures against it.`, "", true),
    `<section class="pref-group"><h4>Voices<span class="count">30 listed by Gemini</span></h4><div class="pref-card">${[
      ["Kore", "female · firm"], ["Puck", "male · upbeat"], ["Charon", "male · informative"], ["Aoede", "female · breezy"]
    ].map(([name, hint]) => `<div class="pref-row split">${listen(name)}${text(name, hint)}</div>`).join("")}
      <button class="pref-row pref-action">Show all 30</button></div>
      <p class="pref-foot">Who reads each language is chosen in Pronunciation.</p></section>`,
    group("", [action("Remove this model", "danger")])
  ] },
  /* Usage: what this server has spent, per provider and model, against the allowances you set. */
  usage: { parent: "providers", title: "Usage", render: () => [
    group("", [segmented("", "", ["Today", "This month", "All time"], "Today")]),
    figures([["142", "calls"], ["3", "failed"], ["1.2M", "tokens"], ["18", "pictures"], ["24k", "characters"], ["4", "photos"]]),
    group("Gemini API", [
      usageRow("gemini-3.5-flash-lite", "96 calls · 980k tokens", gauge(96, 500, "96 of 500 today"), "usage-model-text"),
      usageRow("gemini-3.1-flash-lite", "21 calls · 230k tokens", gauge(21, 500, "21 of 500 today")),
      usageRow("gemini-3.8-flash-tts", "9 calls · 2 failed · 1.4k characters", gauge(9, 10, "9 of 10 today"))
    ]),
    group("Cloudflare", [
      usageRow("flux-2-klein-4b", "18 pictures · 1 failed", gauge(18, 95, "18 of 95 today")),
      usageRow("gpt-oss-20b", "3 calls · 12k tokens")
    ]),
    group("Google Cloud", [
      usageRow("Chirp 3 HD", "38 calls · 2.1k characters", gauge(212000, 1000000, "212k of 1M this month")),
      usageRow("document-text-detection", "4 photos", gauge(41, 1000, "41 of 1,000 this month"))
    ]),
    group("ElevenLabs", [usageRow("eleven_v4", "6 calls · 640 characters", gauge(3100, 10000, "3.1k of 10k this month"))],
      "Counted by Acervo. Your provider’s own page has the bill.")
  ] },
  /* A voice's Change opens its own page, where its allowance already is; any other model has no
     page, so its Change opens the allowance alone. */
  "usage-model": { parent: "usage", title: "gemini-3.8-flash-tts", render: () => [
    group("", [row("Gemini API · Voices", "Free allowance 10 a day · answers in 2.4 s on average",
      `<button class="tb-btn" data-sub="model-tts">Change</button>`)]),
    figures([["214", "calls, 30 days"], ["19", "failed · 9%"], ["31k", "characters"]]),
    `<section class="pref-group"><h4>Last 30 days</h4><div class="pref-card">${chart()}</div></section>`,
    group("Why calls failed", [
      row("Allowance spent", "Gemini said no more today", `<span class="pref-value">17</span>`),
      row("Too slow", "No answer in 30 seconds", `<span class="pref-value">2</span>`)
    ], "A failed call passes to the next voice in the order."),
    group("Last failure", [row("Quota exceeded for today, retry after 00:00 UTC", "Today, 11:42")])
  ] },
  "usage-model-text": { parent: "usage", title: "gemini-3.5-flash-lite", render: () => [
    group("", [row("Gemini API · Text", "Free allowance 500 a day · answers in 1.1 s on average",
      `<button class="tb-btn" data-sub="allowance">Change</button>`)]),
    figures([["2,870", "calls, 30 days"], ["0", "failed · 0%"], ["29M", "tokens"]]),
    `<section class="pref-group"><h4>Last 30 days</h4><div class="pref-card">${chart()}</div></section>`
  ] },
  allowance: { parent: "usage-model-text", title: "Free allowance", render: () => [
    group("Free allowance", [
      field("Amount", "500"),
      select("Counted in", "", ["Calls", "Tokens"], "Calls"),
      select("Each", "", ["Day", "Month"], "Day")
    ], `Your own limit is on <a href="#">aistudio.google.com</a>. Usage measures against it.`, "", true),
    `<div class="pref-buttons">${button("Cancel")}${button("Save", true)}</div>`
  ] },
  vocabulary: { parent: "vocabularies", title: "Spanish", render: () => [
    group("", [
      field("Name", "Spanish"),
      field("Flag", "", "🇦🇷"),
      select("Variety", "", ["None", "🇲🇽 Mexico", "🇦🇷 Argentina", "🇪🇸 Spain", "🇨🇴 Colombia", "🇺🇸 United States", "🌐 Latin America"], "🇦🇷 Argentina")
    ], "", "", true),
    group("Written in", [
      link("Senses defined in", "🇪🇸 Spanish", "definitionLanguage"),
      link("Translated into", "🇬🇧 English, 🇷🇺 Russian", "glossLanguages"),
      link("Notes written in", "🇬🇧 English", "definitionLanguage")
    ]),
    group("You", [
      select("Level", "", ["Not set", "A1 · Beginner", "A2 · Elementary", "B1 · Intermediate", "B2 · Upper intermediate", "C1 · Advanced", "C2 · Proficient"], "B1 · Intermediate"),
      area("About you", "Preparing for a trip to Argentina in March. I learned Spanish from Spain, so peninsular forms are familiar; the subjunctive is my weak spot.",
        "Your goals, what you know well and what you don't.", 1000)
    ], "", "", true),
    `<div class="pref-buttons">${button("Cancel")}${button("Save", true)}</div>`,
    group("", [action("Remove this vocabulary", "danger")])
  ] },
  addLanguage: { parent: "vocabularies", title: "Add a language", render: () => [
    search("Search by name, such as Spanish or español", "fr"),
    group("", [
      language("🇫🇷", "French", "français"),
      language("🇮🇷", "Persian", "فارسی"),
      language("🇿🇦", "Afrikaans", "Afrikaans"),
      language("🇫🇮", "Finnish", "suomi"),
      language("🇳🇱", "Western Frisian", "Frysk")
    ])
  ] },
  glossLanguages: { parent: "vocabulary", title: "Translated into", render: () => [
    group("", [
      row("🇬🇧 English", "", `<span class="pref-reorder"><button class="icon-btn" aria-label="Move up" disabled>${ICON.up}</button><button class="icon-btn" aria-label="Move down">${ICON.down}</button></span><button class="icon-btn" aria-label="Remove English">${ICON.close}</button>`),
      row("🇷🇺 Russian", "", `<span class="pref-reorder"><button class="icon-btn" aria-label="Move up">${ICON.up}</button><button class="icon-btn" aria-label="Move down" disabled>${ICON.down}</button></span><button class="icon-btn" aria-label="Remove Russian">${ICON.close}</button>`)
    ], "The first is the one a word's one-line gloss is written in."),
    search("Search by name, such as Spanish or español", "ger"),
    group("", [language("🇩🇪", "German", "Deutsch"), language("🇩🇿", "Algerian Arabic", "Algerian Arabic")])
  ] },
  definitionLanguage: { parent: "vocabulary", title: "Senses defined in", render: () => [
    search("Search by name, such as Spanish or español"),
    group("", [
      language("🇺🇸", "English", "English"), language("🇨🇳", "Chinese (Simplified)", "中文 (简体)"),
      language("🇮🇳", "Hindi", "हिन्दी"), language("🇪🇸", "Spanish", "español"), language("🇪🇬", "Arabic", "العربية")
    ])
  ] }
};

/* A provider with one key and a few models: the shape most of them have. */
function simpleProvider(name, keyLabel, shown, works, kinds) {
  return [
    group("Key", [keyRow(keyLabel, `From ${name}`, shown), checkRow(["ok", works], "Checked today, 14:02")]),
    ...kinds.map(([kind, models]) => group(kind, [...models.map(([id, hint]) => modelRow(id, hint)), subAction("Add a model…", "addModel")])),
    group("", [link("Usage", "", "usage")]),
    group("", [action("Remove this provider", "danger")])
  ];
}

/* Google Cloud: a key reaches voices and photos; a credentials file adds Vertex text and pictures. */
function googleCloud(mode) {
  const key = mode === "key";
  const signIn = `<div class="pref-row stack">${text("Sign in with", key ? "Reaches voices and reading photos" : "Reaches everything, Vertex text and pictures too")}
    <div class="seg" role="radiogroup" aria-label="Sign in with">${[["API key", "provider-google"], ["Credentials file", "provider-google-file"]].map(([label, to]) =>
      `<button role="radio" data-sub="${to}" aria-checked="${(to === "provider-google") === key}" class="${(to === "provider-google") === key ? "on" : ""}">${label}</button>`).join("")}</div></div>`;
  return [
    group("", [signIn]),
    key
      ? group("Key", [keyRow("API key", "Allowed to use Text-to-Speech and Vision", "AIza…7tPe"), checkRow(["ok", "Works · Text-to-Speech and Vision answer"], "Checked today, 14:02")])
      : group("Credentials", [
          row("Credentials file", "A service account, or your own sign-in", `${button("Paste…")}${button("Replace…")}`),
          ...(params.get("paste") ? [`<div class="pref-row stack">
            <textarea class="pref-text-area short" placeholder='{ "type": "authorized_user", … }'>{ "type": "authorized_user", "client_id": "…</textarea>
            <div class="pref-buttons"><span class="pref-hint warn">That is not the whole file: it should start with { and end with }.</span>${button("Cancel")}${button("Use it", true)}</div></div>`] : []),
          checkRow(["ok", "Works as acervo-tts@project.example.com"], "Checked today, 14:02")
        ], `Your own sign-in is usually at <code>~/.config/gcloud/application_default_credentials.json</code>. It is kept on your server.`),
    key ? "" : group("", [
      field("Project", "example-project"),
      select("Location", "", ["global", "europe-west1", "us-central1"], "global")
    ], "", "", true),
    key ? "" : group("Text", [modelRow("gemini-3.8-flash", ""), subAction("Add a model…", "addModel")]),
    key ? "" : group("Pictures", [modelRow("gemini-3.1-flash-lite-image", "Keeps a story’s characters the same"), subAction("Add a model…", "addModel")]),
    group("Voices", [
      modelLink("Chirp 3 HD", "1M characters a month free", "model-tts"),
      modelLink("WaveNet", "4M characters a month free", "model-tts"),
      modelLink("gemini-2.5-flash-tts", "Takes a direction", "model-tts"),
      subAction("Add a model…", "addModel")
    ]),
    group("Reading photos", [modelRow("document-text-detection", "1,000 a month free")]),
    group("", [link("Usage", "", "usage"), row("Google Cloud console", "Your quotas and the bill", button("Open"))]),
    group("", [action("Remove this provider", "danger")])
  ];
}

function dictionary(name, state, on, act) {
  return `<label class="pref-row">${text(name, state)}${act ? button(act) : ""}<input type="checkbox" role="switch" class="toggle" ${on ? "checked" : ""}></label>`;
}

function corpusRow() {
  if (params.get("load") === "slow" && !corpusArrived) return skeletonRow();
  return row("Clip corpus", "Updated 3 Nov", `<span class="pref-value">12,340 videos · 5 languages</span>`);
}
let corpusArrived = false;

/* ── the window ── */
const state = {
  page: params.get("page") || "general",
  sub: params.get("sub") || null,
  level: params.get("level") || (params.get("page") ? "page" : "list")
};

const root = document.createElement("div");
root.className = "modal-backdrop";
document.body.appendChild(root);

function render() {
  const sub = state.sub && SUBPAGES[state.sub];
  const title = sub ? sub.title : TITLES[state.page];
  const back = sub
    ? `<button class="prefs-back">${ICON.back}${esc(SUBPAGES[sub.parent]?.title ?? TITLES[sub.parent])}</button>`
    : `<button class="prefs-back to-list">${ICON.back}Settings</button>`;
  const body = (sub ? sub.render() : PAGES[state.page]()).filter(Boolean).join("");
  root.innerHTML = `<section class="settings-window" role="dialog" aria-modal="true" aria-labelledby="settings-title" data-level="${state.level}">
    <button class="close" aria-label="Close settings">${ICON.close}</button>
    <div class="prefs-frame">
      <aside class="prefs-side">
        <header class="prefs-head"><h2 id="settings-title">Settings</h2></header>
        <div class="prefs-scroll"><nav class="prefs-nav" aria-label="Settings sections">${GROUPS.map((g) => `<div>
          <h4>${esc(g.title)}</h4><ul>${g.pages.map(([id, label]) => `<li><button data-page="${id}" ${id === state.page ? 'aria-current="page"' : ""}>
            <span class="prefs-icon">${ICON[id]}</span><span>${esc(label)}</span>${ICON.chev.replace("<svg", '<svg class="chev"')}</button></li>`).join("")}</ul></div>`).join("")}
        </nav></div>
      </aside>
      <div class="prefs-main" role="region" aria-labelledby="prefs-page-title">
        <header class="prefs-head">${back}<h3 id="prefs-page-title">${esc(title)}</h3></header>
        <div class="prefs-scroll"><div class="prefs-page">
          ${body}
        </div></div>
      </div>
    </div>
  </section>`;
  root.querySelectorAll("[data-page]").forEach((b) => b.onclick = () => {
    Object.assign(state, { page: b.dataset.page, sub: null, level: "page" }); render();
  });
  root.querySelectorAll("[data-sub]").forEach((b) => b.onclick = () => { state.sub = b.dataset.sub; render(); });
  const backButton = root.querySelector(".prefs-back");
  backButton.onclick = () => {
    if (state.sub) state.sub = SUBPAGES[SUBPAGES[state.sub].parent] ? SUBPAGES[state.sub].parent : null;
    else state.level = "list";
    render();
  };
  root.querySelectorAll(".seg button").forEach((b) => b.onclick = () => {
    b.parentElement.querySelectorAll("button").forEach((o) => { o.classList.toggle("on", o === b); o.setAttribute("aria-checked", o === b); });
  });
  /* The chart's tooltip: the day under the pointer or the focus, said in words. */
  root.querySelectorAll(".pref-plot").forEach((plot) => {
    const tip = plot.querySelector(".pref-tip");
    const show = (bar) => {
      tip.textContent = bar.dataset.tip; tip.hidden = false;
      const left = bar.offsetLeft + bar.offsetWidth / 2;
      tip.style.left = `${Math.max(tip.offsetWidth / 2, Math.min(plot.clientWidth - tip.offsetWidth / 2, left))}px`;
      plot.querySelectorAll(".pref-bar").forEach((b) => b.classList.toggle("hot", b === bar));
    };
    plot.querySelectorAll(".pref-bar").forEach((bar) => { bar.onpointerenter = () => show(bar); bar.onfocus = () => show(bar); bar.onclick = () => show(bar); });
    plot.onpointerleave = () => { tip.hidden = true; plot.querySelectorAll(".pref-bar").forEach((b) => b.classList.remove("hot")); };
  });
  root.querySelectorAll(".pref-chip").forEach((b) => b.onclick = () => {
    const on = b.getAttribute("aria-pressed") !== "true";
    b.setAttribute("aria-pressed", on); b.innerHTML = (on ? ICON.check : "") + esc(b.textContent);
  });
}
render();

if (params.get("load") === "slow") setTimeout(() => { corpusArrived = true; if (state.page === "clips" && !state.sub) render(); }, 2500);
