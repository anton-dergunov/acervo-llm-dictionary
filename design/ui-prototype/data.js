/* Acervo — prototype fixture data.
   Shapes follow web/src/domain.ts so the mock-up can be wired to the real
   repository later without reshaping the view layer. Content is illustrative, except `la obra` and
   `animarse`, which are copied from a real account to judge the article redesign against.

   Three things here are ahead of the schema on purpose, for the article redesign spike:
   - a sense carries an `emoji`, and its `domain` is a one-word label for *every* sense rather than
     only for specialist ones;
   - a picture names the example it was drawn from as `anchor`, an index into `examples` (the
     application's `ImagePrompt.exampleId`); no anchor means it was drawn from the sense alone;
   - an example drawn from an attestation names it as `sourceAttestationId`, so the article can show
     that sentence once instead of twice.
   An example with a `clip` is a subtitle example: the sentence is the corpus's, the clip is where it
   was said. `approved` is gone from the picture because it carried no information. */

const LANGUAGES = [
  { code: "es",      flag: "\u{1F1EA}\u{1F1F8}", name: "Spanish",             definitionLang: "es", glossLangs: ["en"], notesLang: "en" },
  { code: "en",      flag: "\u{1F1EC}\u{1F1E7}", name: "English",             definitionLang: "en", glossLangs: ["ru"], notesLang: "ru" },
  { code: "zh-Hans", flag: "\u{1F1E8}\u{1F1F3}", name: "Chinese (Simplified)", definitionLang: "en", glossLangs: ["ru", "en"], notesLang: "ru" }
];

const TOPICS = [
  { key: "emotions",   name: "Emotions",   icon: "\u{1F4AD}" },
  { key: "actions",    name: "Actions",    icon: "⚡" },
  { key: "nature",     name: "Nature",     icon: "\u{1F33F}" },
  { key: "culture",    name: "Culture",    icon: "\u{1F3AD}" },
  { key: "food",       name: "Food",       icon: "\u{1F37D}️" },
  { key: "health",     name: "Health",     icon: "\u{1FA7A}" },
  { key: "appearance", name: "Appearance", icon: "\u{1F464}" },
  { key: "technology", name: "Technology", icon: "\u{1F4BB}" },
  { key: "travel",     name: "Travel",     icon: "\u{1F9ED}" },
  { key: "slang",      name: "Slang",      icon: "\u{1F4AC}" },
  { key: "social",     name: "Social",     icon: "\u{1F91D}" },
  { key: "places",     name: "Places",     icon: "\u{1F4CD}" },
  { key: "misc",       name: "Misc",       icon: "\u{1F4CC}" }
];

const LEXEMES = [
  {
    id: "k3m91xq7d0a2vbe", language: "es",
    headword: "picar", lemma: "picar", reading: null,
    pos: "verb", gender: null, register: "neutral", dialect: null,
    emoji: "\u{1F336}️", topics: ["food", "health", "actions"],
    status: "active", shortGloss: "to itch; to sting; to chop; to nibble",
    primaryGloss: "to itch", emotion: "slightly irritated",
    ipa: "/piˈkaɾ/",
    notes: [
      "One of the most overloaded verbs in everyday Spanish — the sense is almost always carried by the object, not the verb.",
      "In Mexico, <b>picar</b> for “to be spicy” is far more common than <i>ser picante</i>.",
      "<b>picar algo</b> before dinner is the standard way to say “have a nibble”; the noun <i>el picoteo</i> follows from it."
    ],
    createdAt: "2026-02-11", editedAt: "2026-08-24", revision: 7,
    senses: [
      {
        definition: "Producir una sensación de comezón o escozor en alguna parte del cuerpo.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to itch", "to feel prickly"] }],
        domain: "itch", emoji: "\u{1F927}",
        examples: [
          { text: "Me <b>pica</b> la nariz, creo que voy a estornudar.", translation: "My nose <b>itches</b>, I think I’m going to sneeze.",
            origin: "attestation", modelId: "gemini-3-flash", approved: true, audio: true },
          { text: "La lana de este jersey <b>pica</b> muchísimo.", translation: "The wool of this jumper <b>is</b> really <b>itchy</b>.",
            origin: "tatoeba", modelId: null, approved: true, audio: true },
          /* Deliberately too long for a phone card, so the one card that has to scroll can be seen
             scrolling on its own. */
          { text: "Cuando era pequeño y pasábamos los veranos en el pueblo de mis abuelos, la hierba seca del campo me <b>picaba</b> tanto en las piernas que volvía a casa rascándome sin parar, y mi abuela, sin decir nada, me ponía un poco de aceite de oliva y me mandaba a la cama.",
            translation: "When I was little and we spent the summers in my grandparents’ village, the dry grass in the fields <b>made</b> my legs <b>itch</b> so much that I came home scratching nonstop, and my grandmother, without a word, would rub a little olive oil on them and send me to bed.",
            origin: "llm", modelId: "gemini-3-flash", approved: true, audio: false }
        ],
        images: [{ src: "img/sense-a.webp", style: "flat-vector", prompt: "A hand hovering near an itchy nose, flat vector, bold shapes, limited palette, no text", anchor: 0 }]
      },
      {
        definition: "Dicho de un alimento: producir una sensación ardiente en la boca.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to be spicy", "to be hot"] }],
        domain: "spicy", emoji: "\u{1F336}️",
        examples: [
          { text: "¿Te <b>pica</b> mucho la salsa?", translation: "Is the sauce very <b>spicy</b> for you?",
            origin: "subtitle", modelId: "gemini-3.1-flash-lite", approved: true, audio: true,
            clip: { title: "Comiendo en un mercado de Ciudad de México 🌮🔥 #mexico #streetfood", channel: "Easy Spanish", at: "7:41" } }
        ],
        images: [{ src: "img/sense-d.webp", style: "storybook", prompt: "A chilli pepper glowing on a spoon of red sauce, soft storybook gouache, warm light, no text", anchor: 0 }]
      },
      {
        definition: "Cortar algo en trozos muy pequeños con un cuchillo.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to chop", "to mince", "to dice"] }],
        domain: "chop", emoji: "\u{1F52A}",
        examples: [
          { text: "<b>Pica</b> la cebolla bien fina antes de sofreírla.", translation: "<b>Chop</b> the onion very finely before frying it.",
            origin: "llm", modelId: "gemini-3-flash", approved: true, audio: false }
        ],
        /* Being drawn right now, so the drawing state can be seen on the page and on a card. */
        images: [{ drawing: true, anchor: 0 }]
      },
      {
        definition: "Comer una cantidad pequeña de algo, generalmente entre horas.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to nibble", "to snack"] }],
        domain: "snack", emoji: "\u{1F968}",
        examples: [
          { text: "Vamos a <b>picar</b> algo antes de cenar.", translation: "Let’s <b>have a nibble</b> before dinner.",
            origin: "llm", modelId: "gemini-3-flash", approved: false, audio: false, note: "Waiting for review — check whether “nibble” reads as too British." }
        ],
        images: []
      },
      {
        definition: "Dicho de un insecto o de un ave: morder o herir con el pico o el aguijón.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to bite", "to sting"] }],
        domain: "bite", emoji: "\u{1F99F}",
        examples: [
          { text: "Me <b>picaron</b> los mosquitos toda la noche.", translation: "The mosquitoes <b>bit</b> me all night.",
            origin: "tatoeba", modelId: null, approved: true, audio: true }
        ],
        images: []
      }
    ],
    attestations: [
      { text: "cuidado que esa salsa pica un monton eh", translation: null,
        sourceKind: "conversation", sourceTitle: "WhatsApp — grupo del curso", sourceUrl: null, capturedAt: "11 Feb 2026" },
      { text: "Se pican las verduras en dados de un centimetro y se reservan.", translation: "The vegetables are diced into one-centimetre cubes and set aside.",
        sourceKind: "web", sourceTitle: "Receta — pisto manchego, El Comidista", sourceUrl: "https://example.com/pisto", capturedAt: "3 Mar 2026",
        /* Photo capture (docs/features/photo-capture.md) keeps the square photo a sentence was read
           from. Drawn here so the section is designed with room for one. */
        photo: "img/met-photo-square.jpg" }
    ],
    study: { system: "anki", reps: 21, lapses: 4, stability: 18.3, difficulty: 8.4, retrievability: 0.71, lastReview: "22 Aug 2026" }
  },

  /* ── copied from a real account, 15 Sep 2026 ── */
  {
    id: "3vu6u4sqccfs6fl", language: "es",
    headword: "la obra", lemma: "obra", reading: null,
    pos: "noun", gender: "feminine", register: "neutral", dialect: null,
    emoji: "\u{1F3AD}", topics: [],
    status: "inbox", shortGloss: "work; play; construction site",
    primaryGloss: "the play", emotion: "plainly",
    ipa: "/la ˈoβɾa/",
    notes: [
      "This word has a very broad meaning depending on the context. It can refer to a 'work of art' (una obra de arte), a 'theatrical play' (una obra de teatro), or physical construction work.",
      "When referring to construction, it often implies the physical site where building is happening, e.g., 'el arquitecto está en la obra'."
    ],
    createdAt: "2026-09-13", editedAt: "2026-09-13", revision: 660,
    imageModelId: "vertex_ai/gemini-3.1-flash-lite-image",
    senses: [
      {
        definition: "Cosa hecha o producida por un agente; especialmente una creación artística o literaria.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["work", "piece"] }],
        domain: "art", emoji: "\u{1F3A8}",
        examples: [
          { text: "A ella solo le queda la satisfacción de que vinieron a admirar su trabajo, sus no horas, no días, no semanas, sus años de trabajo invertidos en esta masiva <b>obra</b> de arte.",
            translation: "She only has the satisfaction that they came to admire her work, not her hours, not her days, not her weeks, but her years of work invested in this massive <b>work</b> of art.",
            origin: "subtitle", modelId: "gemini/gemini-3.1-flash-lite", audio: true,
            clip: { title: "En este pueblo humanos tienen prohibido vivir 🚫", channel: "Luisito Comunica", at: "19:39" } }
        ],
        /* Drawn from the sense alone, although the sense has a clip. */
        images: [{ src: "img/obra-art.webp", style: "oil-painting" }]
      },
      {
        definition: "Representación teatral de un texto dramático.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["play"] }],
        domain: "theater", emoji: "\u{1F3AD}",
        examples: [
          { text: "Nosotros veníamos con una <b>obra</b> que se llamaba Lado del amor, que la había ido muy bien, con una gira muy exitosa.",
            translation: "We were touring a <b>play</b> called Lado del amor, which had gone very well, with a very successful tour.",
            origin: "subtitle", modelId: "gemini/gemini-3.1-flash-lite", audio: true,
            clip: { title: "#ANTESQUENADIE | TERAPIA CON GABRIEL ROLÓN: PONER LÍMITES, AMOR ETERNO Y TOMAR DECISIONES", channel: "LUZU TV", at: "44:55" } }
        ],
        /* Drawn from the clip's sentence: a picture can belong to a clip. */
        images: [{ src: "img/obra-theater.webp", style: "baroque-chiaroscuro", anchor: 0 }]
      },
      {
        definition: "Conjunto de trabajos realizados para construir un edificio o una infraestructura.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["construction", "building site"] }],
        domain: "construction", emoji: "\u{1F3D7}️",
        examples: [],
        images: [{ src: "img/obra-construction.webp", style: "gouache-poster" }]
      }
    ],
    attestations: [],
    study: null
  },

  {
    id: "9tmbiepw0yjey3j", language: "es",
    headword: "animarse", lemma: "animarse", reading: null,
    pos: "verb", gender: null, register: "neutral", dialect: null,
    emoji: "\u{1F9D7}", topics: [],
    status: "inbox", shortGloss: "to dare; to be up for",
    primaryGloss: "to be up for it", emotion: "encouraging",
    ipa: "/a.niˈmaɾ.se/",
    notes: [
      "Used to express having the courage or the willingness to take on an activity, especially when it involves some risk, difficulty, or hesitation.",
      "Commonly followed by 'a' + infinitive."
    ],
    createdAt: "2026-09-13", editedAt: "2026-09-13", revision: 674,
    imageModelId: "vertex_ai/gemini-3.1-flash-lite-image",
    senses: [
      {
        definition: "Tener el valor o la disposición necesaria para hacer algo.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to dare", "to be up for", "to build up the courage"] }],
        /* Stored with no domain: the prompt reserves it for specialist words today. */
        domain: "courage", emoji: "\u{1F4AA}",
        examples: [
          { text: "¿Te <b>animás</b> a comer en una casa de desconocidos?", translation: "Do you <b>dare</b> to eat at a stranger's house?",
            origin: "attestation", sourceAttestationId: "2ct6z7ypkoucc0w", modelId: null, audio: true },
          { text: "y ella te lo supo demostrar acá, que esa motivación y el <b>animarse</b> a supuestamente a esa altura de su vida hizo que hoy esté, no sé, más inspirada y más fuerte.",
            translation: "And she knew how to show you here, that that motivation and <b>daring</b> to do so at that stage of her life meant that today she is, I don't know, more inspired and stronger.",
            origin: "subtitle", modelId: "gemini/gemini-3.1-flash-lite", audio: true,
            clip: { title: "#NADIEDICENADA | CONOCEMOS A MARTA, LA SEÑORA QUE ESTÁ POR CUMPLIR 101 AÑOS", channel: "LUZU TV", at: "27:14" } }
        ],
        images: [{ src: "img/animarse.webp", style: "anime-cel", anchor: 0 }]
      }
    ],
    attestations: [
      { id: "2ct6z7ypkoucc0w", text: "¿Te animás a comer en una casa de desconocidos?", translation: "Do you dare to eat at a stranger's house?",
        sourceKind: "unknown", sourceTitle: null, sourceUrl: null, capturedAt: "13 Sep 2026" }
    ],
    study: null
  },

  {
    id: "b7t42naz9c6uk1p", language: "es",
    headword: "desmayarse", lemma: "desmayarse", reading: null,
    pos: "verb", gender: null, register: "neutral", dialect: null,
    emoji: "\u{1F635}‍\u{1F4AB}", topics: ["health", "actions"],
    status: "active", shortGloss: null,
    primaryGloss: "to faint", emotion: "alarmed",
    ipa: "/desmaˈjaɾse/",
    notes: ["Always pronominal in this meaning. <i>Desmayar</i> without the pronoun is literary and means “to lose heart”."],
    createdAt: "2026-01-14", editedAt: "2026-06-02", revision: 3,
    senses: [
      {
        definition: "Perder el sentido y el conocimiento de forma temporal.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to faint", "to pass out"] }],
        domain: "faint", emoji: "\u{1F635}",
        examples: [
          { text: "Me <b>desmayé</b> cuando vi a la aterradora criatura.", translation: "I <b>fainted</b> when I saw the terrifying creature.",
            origin: "attestation", sourceAttestationId: "att-desmayarse", modelId: null, approved: true, audio: true },
          { text: "Se <b>desmayó</b> en pleno directo, delante de las cámaras.", translation: "She <b>passed out</b> live on air, in front of the cameras.",
            origin: "subtitle", modelId: null, approved: true, audio: true,
            clip: { title: "INFORME SEMANAL | Lo que pasó esta semana 📺", channel: "DW Español", at: "4:12" } }
        ],
        images: [{ src: "img/sense-c.webp", style: "retro-futurist", prompt: "A figure swooning backwards, stars circling, 1970s sci-fi paperback, muted print palette, no text", anchor: 1 }]
      },
      {
        definition: "Quedar sobrecogido por una emoción muy intensa.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["to be overcome", "to swoon"] }],
        domain: "emotion", emoji: "\u{1F60D}",
        examples: [
          { text: "Casi me <b>desmayo</b> de la emoción.", translation: "I almost <b>swooned</b> with excitement.",
            origin: "tatoeba", modelId: null, approved: true, audio: false }
        ],
        images: []
      }
    ],
    attestations: [
      { id: "att-desmayarse", text: "Me desmaye cuando vi a la aterradora criatura", translation: null,
        sourceKind: "book", sourceTitle: "Cuentos de la selva — Horacio Quiroga", sourceUrl: null, capturedAt: "14 Jan 2026" }
    ],
    study: { system: "anki", reps: 14, lapses: 1, stability: 96.4, difficulty: 4.1, retrievability: 0.93, lastReview: "19 Aug 2026" }
  },

  {
    id: "q8v53mrb2e7wl4d", language: "es",
    headword: "la sobremesa", lemma: "sobremesa", reading: null,
    pos: "noun", gender: "feminine", register: "neutral", dialect: null,
    emoji: "☕", topics: ["culture", "food", "social"],
    status: "active", shortGloss: "the talk that keeps everyone at the table after a meal",
    primaryGloss: "the after-dinner talk", emotion: "warm and unhurried",
    ipa: "/soβɾeˈmesa/",
    notes: [
      "No English word covers it — this is the case where the Spanish definition does the work and the gloss cannot.",
      "Common collocations: <i>hacer sobremesa</i>, <i>una sobremesa larga</i>, <i>alargar la sobremesa</i>."
    ],
    createdAt: "2026-03-08", editedAt: "2026-03-08", revision: 1,
    /* Still being filled in on the server, so the strip, the clip slot and the closed Cards switch
       can be seen. `clips` is "searching", "none" or "failed"; `?fill=` overrides it. */
    filling: {
      clips: "searching",
      phases: [["Finding recorded examples", true], ["Recording audio", false]]
    },
    senses: [
      {
        definition: "Tiempo que se está a la mesa después de haber comido, charlando con los demás comensales.",
        definitionLang: "es",
        glosses: [{ lang: "en", terms: ["after-dinner conversation", "lingering at the table"] }],
        domain: null,
        examples: [
          { text: "La comida duró una hora, pero la <b>sobremesa</b> se alargó hasta las seis.", translation: "Lunch lasted an hour, but the <b>sobremesa</b> stretched until six.",
            origin: "llm", modelId: "gemini-3-flash", approved: true, audio: true }
        ],
        images: [{ src: "img/sense-b.webp", style: "storybook", prompt: "Empty coffee cups and crumbs on a sunlit table, chairs pushed back, soft storybook gouache, no text" }]
      }
    ],
    attestations: [],
    study: { system: "anki", reps: 5, lapses: 0, stability: 12.9, difficulty: 5.2, retrievability: 0.88, lastReview: "16 Aug 2026" }
  },

  {
    id: "z1c64pdw8f3hj7s", language: "es",
    headword: "que se mejoren", lemma: "que se mejoren", reading: null,
    pos: "expression", gender: null, register: "neutral", dialect: null,
    emoji: "\u{1F496}", topics: ["health", "social"],
    status: "learned", shortGloss: "get better; feel better soon",
    primaryGloss: "get well soon", emotion: "kindly",
    ipa: "/ke se meˈxoɾen/",
    notes: ["Plural form; use <i>que te mejores</i> to one person you address informally."],
    createdAt: "2026-01-30", editedAt: "2026-05-19", revision: 2,
    senses: [
      {
        definition: "Fórmula para desear a alguien una pronta recuperación.",
        definitionLang: "es",
        glosses: [
          { lang: "en", terms: ["get better", "feel better soon"] },
          { lang: "ru", terms: ["выздоравливайте"] }
        ],
        domain: null,
        examples: [
          { text: "Espero <b>que se mejoren</b> pronto. Un abrazo a toda la familia.", translation: "I hope <b>you get better</b> soon. A hug to the whole family.",
            origin: "attestation", sourceAttestationId: "att-mejoren", modelId: "gemini-3-flash", approved: true, audio: true }
        ],
        images: []
      }
    ],
    attestations: [
      { id: "att-mejoren", text: "espero que se mejoren pronto un abrazo a toda la familia", translation: null,
        sourceKind: "conversation", sourceTitle: "WhatsApp — grupo del curso", sourceUrl: null, capturedAt: "30 Jan 2026" }
    ],
    study: { system: "anki", reps: 26, lapses: 0, stability: 402.7, difficulty: 2.8, retrievability: 0.97, lastReview: "2 Aug 2026" }
  },

  {
    id: "m5r18kts4b9gy2n", language: "es",
    headword: "el atasco", lemma: "atasco", reading: null,
    pos: "noun", gender: "masculine", register: "neutral", dialect: "es-ES",
    emoji: "\u{1F697}", topics: ["travel", "places"],
    status: "active", shortGloss: "traffic jam",
    primaryGloss: "the traffic jam", emotion: "exasperated",
    ipa: "/aˈtasko/",
    notes: ["Peninsular. In Mexico you will hear <i>el embotellamiento</i> or <i>el tráfico</i>."],
    createdAt: "2026-02-02", editedAt: "2026-02-02", revision: 1,
    senses: [{
      definition: "Congestión de vehículos que impide circular con normalidad.",
      definitionLang: "es",
      glosses: [{ lang: "en", terms: ["traffic jam", "gridlock"] }],
      domain: null,
      examples: [{ text: "Ayer hubo un <b>atasco</b> tremendo en la M-30.", translation: "Yesterday there was a terrible <b>traffic jam</b> on the M-30.",
        origin: "manual", modelId: null, approved: true, audio: true }],
      images: []
    }],
    attestations: [],
    study: { system: "anki", reps: 9, lapses: 1, stability: 44.1, difficulty: 4.9, retrievability: 0.9, lastReview: "12 Aug 2026" }
  },

  {
    id: "w9h27fjc5d1qx8v", language: "es",
    headword: "currar", lemma: "currar", reading: null,
    pos: "verb", gender: null, register: "colloquial", dialect: "es-ES",
    emoji: "\u{1F477}", topics: ["slang", "actions"],
    status: "active", shortGloss: "to work; to graft",
    primaryGloss: "to work", emotion: "matter-of-fact",
    ipa: "/kuˈraɾ/",
    notes: ["Noun form <i>el curro</i> = the job. Both are everyday Peninsular colloquial, not rude."],
    createdAt: "2026-04-21", editedAt: "2026-04-21", revision: 1,
    senses: [{
      definition: "Trabajar, especialmente de forma dura o continuada.",
      definitionLang: "es",
      glosses: [{ lang: "en", terms: ["to work", "to graft", "to slog"] }],
      domain: null,
      examples: [{ text: "Lleva <b>currando</b> desde las siete de la mañana.", translation: "He’s been <b>working</b> since seven in the morning.",
        origin: "subtitle", modelId: null, approved: true, audio: true, clip: { title: "Aquí la Tierra - 12/03/2026", channel: "RTVE", at: "12:03" } }],
      images: []
    }],
    attestations: [],
    study: { system: "anki", reps: 3, lapses: 2, stability: 4.2, difficulty: 9.1, retrievability: 0.44, lastReview: "26 Aug 2026" }
  },

  {
    id: "p2n85gvx7k4rt3c", language: "es",
    headword: "espolvorear", lemma: "espolvorear", reading: null,
    pos: "verb", gender: null, register: "neutral", dialect: null,
    emoji: "\u{1F9C2}", topics: ["food", "actions"],
    status: "inbox", shortGloss: "to sprinkle; to dust",
    ipa: "/espolβoɾeˈaɾ/",
    notes: [],
    createdAt: "2026-08-27", editedAt: "2026-08-27", revision: 0,
    senses: [{
      definition: "Esparcir sobre algo una materia hecha polvo.",
      definitionLang: "es",
      glosses: [{ lang: "en", terms: ["to sprinkle", "to dust"] }],
      domain: "cooking",
      examples: [{ text: "<b>Espolvoreé</b> canela sobre el pastel.", translation: "I <b>sprinkled</b> cinnamon on the cake.",
        origin: "attestation", sourceAttestationId: "att-espolvorear", modelId: "gemini-3-flash", approved: false, audio: false }],
      images: []
    }],
    attestations: [{ id: "att-espolvorear", text: "Espolvoree canela sobre el pastel.", translation: "I sprinkled cinnamon on the cake.",
      sourceKind: "unknown", sourceTitle: null, sourceUrl: null, capturedAt: "27 Aug 2026" }],
    study: null
  },

  {
    id: "d4y96wlq1m8sz5b", language: "es",
    headword: "tirarse panza arriba", lemma: "tirarse panza arriba", reading: null,
    pos: "phrase", gender: null, register: "colloquial", dialect: null,
    emoji: "\u{1F3D6}️", topics: ["travel", "actions"],
    status: "active", shortGloss: "to sprawl out on your back",
    primaryGloss: "to sprawl out on your back", emotion: "lazy and content",
    ipa: null,
    notes: [],
    createdAt: "2026-05-05", editedAt: "2026-05-05", revision: 1,
    senses: [{
      definition: "Tumbarse boca arriba de manera relajada, sin hacer nada.",
      definitionLang: "es",
      glosses: [{ lang: "en", terms: ["to lie on one’s back", "to sprawl out"] }],
      domain: null,
      examples: [{ text: "Me gusta <b>tirarme panza arriba</b> en la playa.", translation: "I like to <b>lie on my back</b> at the beach.",
        origin: "manual", modelId: null, approved: true, audio: true }],
      images: []
    }],
    attestations: [],
    study: { system: "anki", reps: 7, lapses: 0, stability: 61.5, difficulty: 3.6, retrievability: 0.94, lastReview: "10 Aug 2026" }
  },

  {
    id: "f6k39xzb8n2ph7m", language: "es",
    headword: "la balsa", lemma: "balsa", reading: null,
    pos: "noun", gender: "feminine", register: "neutral", dialect: null,
    emoji: "\u{1F6F6}", topics: ["travel", "nature"],
    status: "active", shortGloss: "raft",
    primaryGloss: "the raft", emotion: "plainly",
    ipa: "/ˈbalsa/",
    notes: [],
    createdAt: "2026-01-22", editedAt: "2026-01-22", revision: 1,
    senses: [
      { definition: "Embarcación plana formada por maderos unidos entre sí.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["raft"] }], domain: null,
        examples: [{ text: "Cruzaron el río en una <b>balsa</b> improvisada.", translation: "They crossed the river on a makeshift <b>raft</b>.",
          origin: "llm", modelId: "gemini-3-flash", approved: true, audio: true }], images: [] },
      { definition: "Hueco del terreno que se llena de agua, natural o artificialmente.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["pond", "pool"] }], domain: null,
        examples: [{ text: "El agua de la <b>balsa</b> estaba completamente quieta.", translation: "The water of the <b>pond</b> was completely still.",
          origin: "tatoeba", modelId: null, approved: true, audio: false }], images: [] }
    ],
    attestations: [],
    study: { system: "anki", reps: 11, lapses: 0, stability: 74.2, difficulty: 3.9, retrievability: 0.95, lastReview: "8 Aug 2026" }
  },

  {
    id: "n7s24bqk6v9dm3t", language: "es",
    headword: "ponerse malo", lemma: "ponerse malo", reading: null,
    pos: "phrase", gender: null, register: "colloquial", dialect: "es-ES",
    emoji: "\u{1F912}", topics: ["health"],
    status: "active", shortGloss: "to get sick",
    primaryGloss: "to get sick", emotion: "a little sorry for yourself",
    ipa: null, notes: [],
    createdAt: "2026-02-18", editedAt: "2026-02-18", revision: 1,
    senses: [{
      definition: "Empezar a encontrarse mal de salud.",
      definitionLang: "es", glosses: [{ lang: "en", terms: ["to become ill", "to get sick"] }], domain: null,
      examples: [{ text: "Me he <b>puesto muy malo</b> después de cenar.", translation: "I’ve <b>become very ill</b> after dinner.",
        origin: "attestation", modelId: null, approved: true, audio: true }], images: []
    }],
    attestations: [], study: { system: "anki", reps: 12, lapses: 2, stability: 30.8, difficulty: 6.4, retrievability: 0.83, lastReview: "20 Aug 2026" }
  },

  {
    id: "v8j51ctr3x7bn6q", language: "es",
    headword: "el tobillo", lemma: "tobillo", reading: null,
    pos: "noun", gender: "masculine", register: "neutral", dialect: null,
    emoji: "\u{1F9B5}", topics: ["health", "appearance"],
    status: "learned", shortGloss: "ankle",
    primaryGloss: "the ankle", emotion: "plainly",
    ipa: "/toˈβiʊo/", notes: [],
    createdAt: "2026-01-19", editedAt: "2026-01-19", revision: 1,
    senses: [{
      definition: "Parte del cuerpo donde se une el pie con la pierna.",
      definitionLang: "es", glosses: [{ lang: "en", terms: ["ankle"] }], domain: "medicine",
      examples: [{ text: "Me torcí el <b>tobillo</b> bajando las escaleras.", translation: "I twisted my <b>ankle</b> going down the stairs.",
        origin: "llm", modelId: "gemini-3-flash", approved: true, audio: true }], images: []
    }],
    attestations: [], study: { system: "anki", reps: 19, lapses: 0, stability: 388.1, difficulty: 2.4, retrievability: 0.98, lastReview: "1 Jul 2026" }
  },

  {
    id: "g3q76mwd9j5fk1z", language: "es",
    headword: "la azafata", lemma: "azafata", reading: null,
    pos: "noun", gender: "feminine", register: "neutral", dialect: null,
    emoji: "\u{1F469}‍✈️", topics: ["travel", "social"],
    status: "active", shortGloss: "flight attendant",
    primaryGloss: "the flight attendant", emotion: "brisk and polite",
    ipa: "/aθaˈfata/", notes: ["Masculine counterpart: <i>el auxiliar de vuelo</i>."],
    createdAt: "2026-03-30", editedAt: "2026-03-30", revision: 1,
    senses: [{
      definition: "Persona encargada de atender a los pasajeros a bordo de un avión.",
      definitionLang: "es", glosses: [{ lang: "en", terms: ["flight attendant", "stewardess"] }], domain: null,
      examples: [{ text: "La <b>azafata</b> nos pidió abrocharnos el cinturón.", translation: "The <b>flight attendant</b> asked us to fasten our seatbelts.",
        origin: "llm", modelId: "gemini-3-flash", approved: true, audio: true }], images: []
    }],
    attestations: [], study: { system: "anki", reps: 6, lapses: 1, stability: 21.6, difficulty: 5.8, retrievability: 0.86, lastReview: "18 Aug 2026" }
  },

  {
    id: "h2l83nfy7c4vs9r", language: "en",
    headword: "turmoil", lemma: "turmoil", reading: null,
    pos: "noun", gender: null, register: "formal", dialect: null,
    emoji: "\u{1F32A}️", topics: ["emotions", "misc"],
    status: "active", shortGloss: "суматоха; смятение",
    ipa: "/ˈtɜːmɔɪl/",
    notes: ["Mass noun — no plural. Usually <i>in turmoil</i>, rarely <i>a turmoil</i>."],
    createdAt: "2026-02-25", editedAt: "2026-07-14", revision: 4,
    senses: [{
      definition: "A state of great confusion, disturbance or uncertainty.",
      definitionLang: "en",
      glosses: [{ lang: "ru", terms: ["суматоха", "смятение", "потрясения"] }],
      domain: null,
      examples: [
        { text: "The country was in <b>turmoil</b> for weeks after the vote.", translation: "Страна несколько недель находилась в <b>смятении</b> после голосования.",
          origin: "attestation", modelId: "gemini-3-flash", approved: true, audio: true },
        { text: "Her mind was in <b>turmoil</b> and she could not sleep.", translation: "В её голове царила <b>суматоха</b>, и она не могла заснуть.",
          origin: "wiktionary", modelId: null, approved: true, audio: false }
      ],
      images: []
    }],
    attestations: [{ text: "Markets remained in turmoil as the deadline passed without an agreement.", translation: null,
      sourceKind: "web", sourceTitle: "Reuters — markets live blog", sourceUrl: "https://example.com/markets", capturedAt: "25 Feb 2026" }],
    study: { system: "anki", reps: 8, lapses: 1, stability: 33.4, difficulty: 5.5, retrievability: 0.89, lastReview: "21 Aug 2026" }
  },

  {
    id: "c9d47ztk2h6mp8w", language: "en",
    headword: "hoax", lemma: "hoax", reading: null,
    pos: "noun", gender: null, register: "neutral", dialect: null,
    emoji: "\u{1F3AD}", topics: ["culture", "misc"],
    status: "active", shortGloss: "мистификация; розыгрыш",
    ipa: "/həʊks/", notes: [],
    createdAt: "2026-04-02", editedAt: "2026-04-02", revision: 1,
    senses: [{
      definition: "A deliberate deception intended to make people believe something untrue.",
      definitionLang: "en",
      glosses: [{ lang: "ru", terms: ["мистификация", "розыгрыш", "обман"] }],
      domain: null,
      examples: [{ text: "The photograph turned out to be an elaborate <b>hoax</b>.", translation: "Фотография оказалась тщательно подготовленной <b>мистификацией</b>.",
        origin: "llm", modelId: "gemini-3-flash", approved: true, audio: true }], images: []
    }],
    attestations: [], study: { system: "anki", reps: 4, lapses: 0, stability: 17.2, difficulty: 4.4, retrievability: 0.91, lastReview: "23 Aug 2026" }
  },

  {
    id: "t5b62vqj9n3xw7f", language: "zh-Hans",
    headword: "图书馆", lemma: "图书馆", reading: "tú shū guǎn",
    pos: "noun", gender: null, register: "neutral", dialect: null,
    emoji: "\u{1F4DA}", topics: ["places", "culture"],
    status: "active", shortGloss: "библиотека; library",
    ipa: null,
    notes: ["图 (picture) + 书 (book) + 馆 (public building) — the third character recurs in 博物馆 and 体育馆."],
    createdAt: "2026-06-11", editedAt: "2026-06-11", revision: 1,
    senses: [{
      definition: "A building where books are kept and may be borrowed.",
      definitionLang: "en",
      glosses: [
        { lang: "ru", terms: ["библиотека"] },
        { lang: "en", terms: ["library"] }
      ],
      domain: null,
      examples: [{ text: "我在<b>图书馆</b>学习了一下午。", translation: "I studied at the <b>library</b> all afternoon.",
        origin: "llm", modelId: "gemini-3-flash", approved: true, audio: true }], images: []
    }],
    attestations: [], study: null
  }
];

/* External dictionaries — what a search finds that is NOT yours (`docs/features/dictionaries.md`).
   Never mixed into LEXEMES: an external entry has no id, no study state and no owner, and the
   whole point of the section below the rule is that the difference is visible. */
const EXTERNAL = [
  {
    word: "picadura", gloss: "Mordedura o herida hecha por un insecto.", origin: "device",
    sources: [{ id: "kaikki-es-es", name: "Wiktionary (es→es)", origin: "device" },
              { id: "wikdict-es-en", name: "WikDict (es→en)", origin: "device" }],
    ipa: "[pikaˈðuɾa]", posLabel: "noun",
    sections: [
      { id: "kaikki-es-es", name: "Wiktionary (es→es)", origin: "device", tier: "fields",
        attribution: "Wiktionary contributors, via kaikki.org. CC BY-SA 4.0.", licence: "CC BY-SA 4.0",
        senses: [
          { definition: "Mordedura o herida hecha por un insecto.",
            examples: [{ text: "Una picadura de mosquito.", translation: "A mosquito bite." }] },
          { definition: "Acción y efecto de picar tabaco." }
        ] },
      { id: "wikdict-es-en", name: "WikDict (es→en)", origin: "device", tier: "html",
        attribution: "WikDict, derived from DBnary/Wiktionary. CC BY-SA 4.0.", licence: "CC BY-SA 4.0",
        html: '<p class="ext-gram">noun</p><ol class="ext-senses">'
            + '<li>Mordedura de un insecto.<p class="ext-tr">bite</p></li>'
            + '<li>Tabaco picado.<p class="ext-tr">shredded tobacco</p></li></ol>' }
    ]
  },
  {
    word: "picante", gloss: "Que pica al paladar.", origin: "device",
    sources: [{ id: "kaikki-es-es", name: "Wiktionary (es→es)", origin: "device" }],
    posLabel: "adjective",
    sections: [
      { id: "kaikki-es-es", name: "Wiktionary (es→es)", origin: "device", tier: "fields",
        attribution: "Wiktionary contributors, via kaikki.org. CC BY-SA 4.0.", licence: "CC BY-SA 4.0",
        senses: [{ definition: "Que pica al paladar." }] }
    ]
  },
  {
    word: "picotear", gloss: "to peck; to nibble", origin: "online",
    sources: [{ id: "freedictionaryapi", name: "Free Dictionary API", origin: "online" }],
    posLabel: "verb", online: true,
    sections: [
      { id: "freedictionaryapi", name: "Free Dictionary API", origin: "online", tier: "fields",
        attribution: "freedictionaryapi.com, Wiktionary-derived. CC BY-SA 4.0.", licence: "CC BY-SA 4.0",
        senses: [{ definition: "to peck (of a bird)" }, { definition: "to nibble; to snack" }] }
    ]
  }
];

/* Loops — a rendered track over some of your words, the words it teaches, and every line it says
   (design `docs/features/loops.md` §2.9). Three flat arrays, exactly the three collections
   `web/src/domain.ts` declares: there is no title column, no status column and no stored bed, so
   the prototype derives all three the way `selectors.ts` does.

   An empty `audioRef` is the whole of what "not rendered yet" means. One loop here is in that state
   on purpose, so the row that is still being made can be looked at beside the ones that are done. */

/* The times per word, in the proportions a real render produces: the word is spoken as its turn
   opens, the translation a quarter of the way through — that gap is the recall gap, and it is
   deliberately the longest — and then the pair twice more, evenly an eighth of the turn apart, with
   the bed playing out the last quarter. Measured in the step-6 rehearsal (79.1 s of audio for three
   words), stretched slightly for a longer phrase because a longer phrase takes longer to say.

   Eight seconds of bed before the first word, which is what the engine writes: a loop starts as
   music and the first word arrives once you have settled into it. */
function loopTimeline(prefix, loopId, words, from = 8.8) {
  const round = (n) => Math.round(n * 100) / 100;
  let at = from;
  return words.map((word, position) => {
    const span = 20 + Math.min(word.source.length, 26) * 0.22;
    const row = {
      id: `${prefix}${String(position).padStart(15 - prefix.length, "0")}`,
      loopId, lexemeId: word.lexemeId, position,
      sourceText: word.source, targetText: word.target, emotion: word.emotion,
      startSeconds: round(at), sourceRevealSeconds: round(at),
      targetRevealSeconds: round(at + span * 0.25), endSeconds: round(at + span)
    };
    at += span;
    return row;
  });
}

const W = {
  picar:      { lexemeId: "k3m91xq7d0a2vbe", source: "picar",                target: "to itch",                    emotion: "slightly irritated" },
  obra:       { lexemeId: "3vu6u4sqccfs6fl", source: "la obra",              target: "the play",                   emotion: "plainly" },
  animarse:   { lexemeId: "9tmbiepw0yjey3j", source: "animarse",             target: "to be up for it",            emotion: "encouraging" },
  desmayarse: { lexemeId: "b7t42naz9c6uk1p", source: "desmayarse",           target: "to faint",                   emotion: "alarmed" },
  sobremesa:  { lexemeId: "q8v53mrb2e7wl4d", source: "la sobremesa",         target: "the after-dinner talk",      emotion: "warm and unhurried" },
  mejoren:    { lexemeId: "z1c64pdw8f3hj7s", source: "que se mejoren",       target: "get well soon",              emotion: "kindly" },
  atasco:     { lexemeId: "m5r18kts4b9gy2n", source: "el atasco",            target: "the traffic jam",            emotion: "exasperated" },
  currar:     { lexemeId: "w9h27fjc5d1qx8v", source: "currar",               target: "to work",                    emotion: "matter-of-fact" },
  panza:      { lexemeId: "d4y96wlq1m8sz5b", source: "tirarse panza arriba", target: "to sprawl out on your back", emotion: "lazy and content" },
  balsa:      { lexemeId: "f6k39xzb8n2ph7m", source: "la balsa",             target: "the raft",                   emotion: "plainly" },
  malo:       { lexemeId: "n7s24bqk6v9dm3t", source: "ponerse malo",         target: "to get sick",                emotion: "a little sorry for yourself" },
  tobillo:    { lexemeId: "v8j51ctr3x7bn6q", source: "el tobillo",           target: "the ankle",                  emotion: "plainly" },
  azafata:    { lexemeId: "g3q76mwd9j5fk1z", source: "la azafata",           target: "the flight attendant",       emotion: "brisk and polite" }
};

const LOOP_WORDS = {
  lp7k2md90xqv4b1: [W.picar, W.balsa, W.sobremesa, W.atasco, W.currar, W.tobillo,
                    W.animarse, W.azafata, W.malo, W.mejoren, W.desmayarse, W.panza],
  lp3f81nzc6yh5t2: [W.obra, W.sobremesa, W.currar, W.atasco, W.azafata,
                    W.tobillo, W.malo, W.desmayarse, W.animarse, W.picar],
  lp9w45bqj2mk7d3: [W.balsa, W.tobillo, W.azafata, W.picar, W.currar, W.obra, W.atasco, W.animarse],
  lp2h63vxr8ns1g4: [W.sobremesa, W.mejoren, W.panza, W.balsa, W.malo, W.atasco]
};

/* A drill's lines, as its render reports them: each word, its translation after the recall gap,
   then the pair twice more, an eighth of the turn apart. One card per word. */
function drillLines(prefix, rows) {
  const round = (n) => Math.round(n * 100) / 100;
  const lines = [];
  rows.forEach((row, group) => {
    const spacing = (row.endSeconds - row.startSeconds) * 0.125;
    const starts = [row.startSeconds, ...[0, 1, 2, 3, 4].map((n) => round(row.targetRevealSeconds + n * spacing))];
    starts.forEach((start, index) => {
      const source = index % 2 === 0;
      lines.push({
        id: `${prefix}${String(lines.length).padStart(15 - prefix.length, "0")}`, loopId: row.loopId,
        position: lines.length, group, kind: "say", section: "words", loopItemId: row.id,
        side: source ? "source" : "target", role: source ? "native" : "guide", language: source ? "es" : "en",
        text: source ? row.sourceText : row.targetText, take: Math.floor(index / 2),
        startSeconds: start, endSeconds: starts[index + 1] ?? row.endSeconds
      });
    });
  });
  return lines;
}

/* A radio lesson: the drill, and between the words what a writer wrote for them — an intro, a remark
   where one helps, an example with its meaning, a quick quiz halfway (the translation first, the word
   as its answer), and a goodbye. Laid out line by line, each taking the time it needs, which is what
   a render does with written lines. */
function radioLesson(prefix, loopId, words, written) {
  const round = (n) => Math.round(n * 100) / 100;
  const items = [];
  const lines = [];
  let at = 6.4;
  let group = 0;
  const line = (kind, section, item, side, role, text, seconds) => {
    lines.push({
      id: `${prefix}c${String(lines.length).padStart(14 - prefix.length, "0")}`, loopId, position: lines.length,
      group, kind, section, loopItemId: item ? item.id : null, side, role, language: role === "native" ? "es" : "en",
      text, take: 0, startSeconds: round(at), endSeconds: round(at + seconds * 0.7)
    });
    at += seconds;
  };
  line("intro", "intro", null, null, "guide", written.intro, 5.6); group += 1;
  const half = Math.ceil(words.length / 2);
  words.forEach((word, position) => {
    const item = {
      id: `${prefix}i${String(position).padStart(14 - prefix.length, "0")}`, loopId, lexemeId: word.lexemeId,
      position, sourceText: word.source, targetText: word.target, emotion: word.emotion,
      startSeconds: round(at), sourceRevealSeconds: round(at)
    };
    items.push(item);
    for (let take = 0; take < 3; take += 1) {
      line("say", "words", item, "source", "native", word.source, take ? 3.2 : 6.4);
      if (!take) item.targetRevealSeconds = round(at);
      line("say", "words", item, "target", "guide", word.target, 3.2);
    }
    lines.slice(-6).forEach((one, index) => { one.take = Math.floor(index / 2); });
    item.endSeconds = round(at);
    group += 1;
    const remark = written.remarks[word.source];
    if (remark) { line("remark", "words", item, null, "guide", remark, 7.2); group += 1; }
    const example = written.examples[word.source];
    if (example) {
      line("example", "words", item, null, "native", example[0], 4.4);
      line("translation", "words", item, null, "guide", example[1], 4);
      group += 1;
    }
    if (position + 1 === half) {
      words.slice(0, half).forEach((one, index) => {
        line("say", "quiz", items[index], "target", "guide", one.target, 3.2);
        line("say", "quiz", items[index], "source", "native", one.source, 3.2);
        group += 1;
      });
    }
  });
  line("outro", "outro", null, null, "guide", written.outro, 4.8);
  return { items, lines, duration: round(at + 6) };
}

const RADIO = radioLesson("lr2", "lp3f81nzc6yh5t2", LOOP_WORDS.lp3f81nzc6yh5t2, {
  intro: "Ten words today, from a long lunch to a traffic jam — and one word for the moment you faint.",
  outro: "That's the lot. Next time you're stuck in el atasco, say them all again.",
  remarks: {
    "la sobremesa": "English has no word for la sobremesa: the talk that goes on at the table long after the plates are cleared.",
    "currar": "Currar is what you say to friends. Trabajar is what you write on a form."
  },
  examples: {
    "la obra": ["La obra duró tres horas y me dormí.", "The play lasted three hours and I fell asleep."],
    "el atasco": ["Llevo una hora en este atasco.", "I've been in this traffic jam for an hour."],
    "el tobillo": ["Me torcí el tobillo bailando.", "I twisted my ankle dancing."]
  }
});

const LOOP_ITEMS = [
  ...loopTimeline("li1", "lp7k2md90xqv4b1", LOOP_WORDS.lp7k2md90xqv4b1),
  ...RADIO.items,
  ...loopTimeline("li3", "lp9w45bqj2mk7d3", LOOP_WORDS.lp9w45bqj2mk7d3),
  ...loopTimeline("li4", "lp2h63vxr8ns1g4", LOOP_WORDS.lp2h63vxr8ns1g4)
];

/* The lines of every rendered loop. The one being made has none yet: they arrive with its track. */
const LOOP_CUES = [
  ...drillLines("lc1", LOOP_ITEMS.filter((row) => row.loopId === "lp7k2md90xqv4b1")),
  ...RADIO.lines,
  ...drillLines("lc4", LOOP_ITEMS.filter((row) => row.loopId === "lp2h63vxr8ns1g4"))
];

const endOf = (loopId) => {
  const rows = LOOP_ITEMS.filter((row) => row.loopId === loopId);
  return Math.round((rows[rows.length - 1].endSeconds + 6) * 10) / 10;   // the bed plays out
};

const LOOPS = [
  {
    id: "lp7k2md90xqv4b1", language: "es", position: 1,
    styleId: "gentle-game", seed: 104740, engineVersion: "0.7.0", bedFingerprint: "f35282aaf3c40245",
    format: "classic", switches: {}, fallbackFrom: null, audioRef: "loops/es/lp7k2md90xqv4b1-6ad2f019.mp3", audioMime: "audio/mpeg",
    durationSeconds: endOf("lp7k2md90xqv4b1"), createdAt: "2026-09-16", editedAt: "2026-09-16"
  },
  {
    id: "lp3f81nzc6yh5t2", language: "es", position: 2,
    styleId: "acoustic-flow", seed: 88213, engineVersion: "0.7.0", bedFingerprint: "b1d9042ce7f3aa88",
    format: "radio-lesson", switches: { repetitions: "3", remarks: true, quiz: true, review: false }, fallbackFrom: null,
    audioRef: "loops/es/lp3f81nzc6yh5t2-91c47b3e.mp3", audioMime: "audio/mpeg",
    durationSeconds: RADIO.duration, createdAt: "2026-09-12", editedAt: "2026-09-12"
  },
  /* Asked for and not made: no reference, so no duration and no bed either — all three arrive
     together when the render lands. The job is what says how far along it is. */
  {
    id: "lp9w45bqj2mk7d3", language: "es", position: 3,
    styleId: null, seed: 41207, engineVersion: null, bedFingerprint: null,
    format: "story", switches: {}, fallbackFrom: null, audioRef: null, audioMime: null,
    durationSeconds: null, createdAt: "2026-09-18", editedAt: "2026-09-18"
  },
  {
    id: "lp2h63vxr8ns1g4", language: "es", position: 4,
    styleId: "bright-pastoral", seed: 22910, engineVersion: "0.7.0", bedFingerprint: "44aa1c0b9e21f7d6",
    // Asked for as a radio lesson on a day the loop voice was the clear, even one: made as a drill.
    format: "classic", switches: {}, fallbackFrom: "radio-lesson", audioRef: "loops/es/lp2h63vxr8ns1g4-2f70d4aa.mp3", audioMime: "audio/mpeg",
    durationSeconds: endOf("lp2h63vxr8ns1g4"), createdAt: "2026-08-30", editedAt: "2026-08-30"
  }
];

/* What `GET /loops/schema` reports: the generator's own catalogues, never copied into Acervo.
   `productionBundle: false` would mean every bed is the synthesised palette. */
const LOOP_SCHEMA = {
  apiVersion: "2.0.0", engineVersion: "0.7.0", productionBundle: true, maxItems: 40,
  /* Each kind of loop, with the generator's own words for it, its switches, what it needs and what it
     becomes without it. Whether this server has a writing model, and a loop voice that can mix
     languages, is Acervo's to say. */
  formats: [
    { id: "classic", label: "Classic drill", description: "Each word, a pause to recall it, its translation, and the pair twice more.",
      switches: {}, requires: [], fallback: null },
    { id: "alternating", label: "Alternating", description: "Word and translation back to back, with no pause to recall.",
      switches: {}, requires: [], fallback: null },
    { id: "echo", label: "Say it back", description: "Each word, then a moment for you to say it before the translation.",
      switches: {}, requires: [], fallback: null },
    { id: "radio-lesson", label: "Radio lesson", description: "The drill with a presenter: examples, a remark where one helps, a quiz halfway.",
      switches: {
        repetitions: { label: "Times each word is said", default: "3", choices: ["2", "3", "4"] },
        remarks: { label: "Remarks about words", default: true },
        quiz: { label: "Quiz halfway", default: true },
        review: { label: "Final review", default: true }
      }, requires: ["writer", "multilingual_voice"], fallback: "classic" },
    { id: "story", label: "Story", description: "A very short story told a line at a time between the words.",
      switches: {}, requires: ["writer"], fallback: null }
  ],
  writerAvailable: true, mixesLanguages: true,
  /* Each kind of music with the generator's own words for it. "Surprise me" is not among them: it
     is the absence of a choice, and the dialog's to name. */
  families: [
    { id: "meditative", label: "Meditative", description: "Slow and spacious: long held chords, little or no percussion." },
    { id: "organic", label: "Organic", description: "Earthy mid-tempo pulse: marimba or piano over soft hand percussion." },
    { id: "acoustic-flow", label: "Acoustic flow", description: "Calm and flowing: sustained piano and strings, a light pulse." },
    { id: "gentle-game", label: "Gentle game", description: "Quick, cheerful arpeggios, like a calm game menu." },
    { id: "sunlit-acoustic", label: "Sunlit acoustic", description: "Guitar, harp or plucked strings; bright and unhurried." },
    { id: "playful-plucked", label: "Playful plucked", description: "Kalimba, mbira, strumstick and guitar: plucked and bouncy." },
    { id: "bright-pastoral", label: "Bright pastoral", description: "Ocarina and pizzicato strings; open, countryside feel." }
  ]
};

/* Beds the owner kept (`web/src/domain.ts` `Bed`): the music of one loop, offered again when a loop
   is made. Style and seed replay it; the loop it came from is what the dialog plays to preview it. */
const BEDS = [
  { id: "bd4m81xq0zv2c7n", styleId: "gentle-game", seed: 104740, sourceLoopId: "lp7k2md90xqv4b1", createdAt: "2026-09-17" }
];

/* ── stories ──
   A story is a handful of words told back as a short illustrated tale. Its state is derived, like a
   loop's: having no parts is the whole of what "never written" means, and a part with no `imageRef`
   has not been drawn. There is no status column on either. */
const STORIES = [
  {
    id: "st4m19pqb7wzx2c", language: "es", position: 1, typeId: "funny", styleId: "comic-book",
    title: "El perro de la panadería", titleTranslation: "The bakery dog", emoji: "\u{1F415}",
    modelId: "gemini/gemini-3.5-flash-lite", createdAt: "2026-09-19", editedAt: "2026-09-19"
  },
  {
    id: "st8c50fkd3vnr6h", language: "es", position: 2, typeId: "everyday", styleId: "golden-hour",
    title: "El café de las siete", titleTranslation: "The seven o'clock coffee", emoji: "☕",
    modelId: "gemini/gemini-3.5-flash-lite", createdAt: "2026-09-19", editedAt: "2026-09-19"
  },
  /* Asked for and never written: no parts at all, which is the whole of what says so. */
  {
    id: "st2v77hjs9blm4k", language: "es", position: 3, typeId: "mystery", styleId: "film-noir",
    title: null, titleTranslation: null, emoji: "\u{1F575}", modelId: null,
    createdAt: "2026-09-19", editedAt: "2026-09-19"
  }
];

const STORY_PARTS = [
  {
    id: "sp01", storyId: "st4m19pqb7wzx2c", position: 0,
    heading: "La panadería a las ocho", headingTranslation: "The bakery at eight",
    text: "Cada martes a las ocho en punto, un perro marrón entra en la pequeña panadería de la esquina. No viene a buscar migajas como los demás animales de la calle. Camina con paso firme hacia el mostrador y espera su turno.",
    translation: "Every Tuesday at eight sharp, a brown dog walks into the little bakery on the corner. He does not come looking for crumbs like the other animals on the street. He walks firmly up to the counter and waits his turn.",
    imageRef: "img/sense-a.webp", imageModelId: "openai/gpt-image-1", attempts: 1, failureReason: null
  },
  {
    id: "sp02", storyId: "st4m19pqb7wzx2c", position: 1,
    heading: "El pan perfecto", headingTranslation: "The perfect loaf",
    text: "Don Mateo saca una barra caliente del horno y la coloca sobre la madera limpia. El perro se acerca despacio y huele la corteza con atención. Si algo no está bien, empieza a ladrar de inmediato.",
    translation: "Don Mateo takes a warm loaf from the oven and sets it on the clean wood. The dog comes closer slowly and smells the crust carefully. If something is not right, he starts barking at once.",
    imageRef: null, imageModelId: null, attempts: 2,
    failureReason: "The image model is temporarily rate limited."
  },
  {
    id: "sp03", storyId: "st4m19pqb7wzx2c", position: 2,
    heading: "El verdadero dueño", headingTranslation: "The real owner",
    text: "Al final del mes, el perro regresa con una cartera llena de billetes en la boca. Don Mateo comprendió demasiado tarde que su mejor cliente tenía un restaurante propio.",
    translation: "At the end of the month, the dog comes back with a wallet full of notes in his mouth. Don Mateo understood too late that his best customer had a restaurant of his own.",
    imageRef: null, imageModelId: null, attempts: 0, failureReason: null
  }
];

/* One row per word the story was asked to teach. **An empty `forms` means the story did not manage
   to use it**, which is a fact worth showing rather than hiding — and the forms are what the reader
   searches the text for, so a mark is found rather than stored. */
const STORY_WORDS = [
  { id: "sw01", storyId: "st4m19pqb7wzx2c", lexemeId: "wd1", position: 0, sourceText: "la panadería", forms: ["panadería"], translationForms: ["bakery"], emoji: "\u{1F35E}", gloss: "bakery" },
  { id: "sw02", storyId: "st4m19pqb7wzx2c", lexemeId: "wd2", position: 1, sourceText: "ladrar", forms: ["ladrar"], translationForms: ["barking"], emoji: "\u{1F415}", gloss: "to bark" },
  { id: "sw03", storyId: "st4m19pqb7wzx2c", lexemeId: "wd3", position: 2, sourceText: "el mostrador", forms: ["mostrador"], translationForms: ["counter"], emoji: "\u{1F6D2}", gloss: "counter" },
  { id: "sw04", storyId: "st2v77hjs9blm4k", lexemeId: "wd2", position: 0, sourceText: "ladrar", forms: [], translationForms: [], emoji: "\u{1F415}", gloss: "to bark" }
];
