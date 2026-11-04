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
const group = (title, rows, foot = "", count = "") => `<section class="pref-group">
  ${title ? `<h4>${esc(title)}${count ? `<span class="count">${esc(count)}</span>` : ""}</h4>` : ""}
  <div class="pref-card">${rows.join("")}</div>
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
const action = (label, kind = "") => `<button class="pref-row pref-action ${kind}">${esc(label)}</button>`;
const select = (label, hint, options, chosen) => `<label class="pref-row">${text(label, hint)}
  <select class="pref-select">${options.map((o) => `<option ${o === chosen ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></label>`;
const segmented = (label, hint, options, chosen) => `<div class="pref-row stack">${text(label, hint)}
  <div class="seg" role="radiogroup" aria-label="${esc(label)}">${options.map((o) =>
    `<button role="radio" aria-checked="${o === chosen}" class="${o === chosen ? "on" : ""}">${esc(o)}</button>`).join("")}</div></div>`;
const button = (label, primary = false) => `<button class="tb-btn ${primary ? "primary" : ""}">${esc(label)}</button>`;
const notice = (message) => `<div class="pref-notice" role="status">${ICON.alert}<span>${message}</span></div>`;
const skeletonRow = () => `<div class="pref-row"><span class="pref-text"><span class="pref-skel"></span><span class="pref-skel"></span></span></div>`;
const reorder = (label, hint, on, badge = "") => `<div class="pref-row">
  <input type="checkbox" role="switch" class="toggle" aria-label="Use ${esc(label)}" ${on ? "checked" : ""}>
  ${text(label, hint)}${badge ? `<span class="badge">${esc(badge)}</span>` : ""}
  <span class="pref-reorder"><button class="icon-btn" aria-label="Move up">${ICON.up}</button><button class="icon-btn" aria-label="Move down">${ICON.down}</button></span></div>`;

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
      link("🇪🇸  Spanish", "", "vocabulary", "es · Argentina · defined in es · translated into en, ru"),
      link("🇨🇳  Chinese", "", "vocabulary", "Defined in English · glossed in English")
    ]),
    group("", [action("Add a vocabulary…")])
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

  providers: () => [
    ...[
      ["Text", [["Gemini · 2.5 Flash Lite", "gemini-free", true, ""], ["Cloudflare · Llama 3.3 70B", "cloudflare", true, ""], ["OpenRouter · Qwen3", "", false, "No key"]]],
      ["Quick look-up", [["Gemini · 2.5 Flash Lite", "gemini-free", true, ""]]],
      ["Pictures", [["Cloudflare · FLUX.1 schnell", "cloudflare", true, ""], ["Vertex · Imagen 4", "vertex", true, ""]]],
      ["Clear voice", [["Gemini · flash-tts", "gemini-free", true, ""]]],
      ["Expressive voice", [["Gemini · flash-tts", "gemini-free", true, ""]]],
      ["Reading photos", [["Gemini · 2.5 Flash", "gemini-free", true, ""]]]
    ].map(([kind, rows]) => group(kind, rows.map(([name, billed, on, badge]) => reorder(name, billed ? `Billed to ${billed}` : "", on, badge)))),
    group("", [link("Credentials", "4 providers", "credentials")])
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
  credentials: { parent: "providers", title: "Credentials", render: () => [
    group("", [
      row("Gemini", "GEMINI_API_KEY", `<span class="pref-value mono">AIza…9xQk</span>`),
      row("Cloudflare", "CLOUDFLARE_API_TOKEN", `<span class="pref-value mono">Xb3d…k2Lm</span>`),
      row("Vertex", "Service account", `<span class="pref-value">Configured</span>`),
      row("OpenRouter", "OPENROUTER_API_KEY", `<span class="badge">Missing</span>`)
    ], "Keys are set on the server with <code>./deploy.sh --configure-llm</code>.")
  ] },
  vocabulary: { parent: "vocabularies", title: "Spanish", render: () => [
    group("", [
      `<label class="pref-row">${text("Name")}<input class="pref-input" value="Spanish" style="max-width:55%"></label>`,
      `<label class="pref-row">${text("Flag")}<input class="pref-input" value="🇪🇸" style="max-width:80px"></label>`,
      select("Senses defined in", "", ["Spanish", "English"], "Spanish"),
      `<label class="pref-row">${text("Glossed in")}<input class="pref-input" value="en, ru" style="max-width:55%"></label>`,
      select("Notes written in", "", ["English", "Spanish", "Russian"], "English")
    ]),
    group("", [select("Accent", "The voices read it as it is spoken there", ["None", "Spain", "Mexico", "Argentina", "Colombia", "Chile", "Latin America"], "Argentina")]),
    `<div style="display:flex;justify-content:flex-end;gap:8px">${button("Cancel")}${button("Save", true)}</div>`,
    group("", [action("Remove this vocabulary", "danger")])
  ] }
};

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
    ? `<button class="prefs-back">${ICON.back}${esc(TITLES[sub.parent])}</button>`
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
  backButton.onclick = () => { if (state.sub) state.sub = null; else state.level = "list"; render(); };
  root.querySelectorAll(".seg button").forEach((b) => b.onclick = () => {
    b.parentElement.querySelectorAll("button").forEach((o) => { o.classList.toggle("on", o === b); o.setAttribute("aria-checked", o === b); });
  });
  root.querySelectorAll(".pref-chip").forEach((b) => b.onclick = () => {
    const on = b.getAttribute("aria-pressed") !== "true";
    b.setAttribute("aria-pressed", on); b.innerHTML = (on ? ICON.check : "") + esc(b.textContent);
  });
}
render();

if (params.get("load") === "slow") setTimeout(() => { corpusArrived = true; if (state.page === "clips" && !state.sub) render(); }, 2500);
