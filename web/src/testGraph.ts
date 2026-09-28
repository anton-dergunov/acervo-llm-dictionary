/* A small representative graph for interface tests: two languages, an inbox word, a clip, an
   attestation with lineage, an image prompt, a study state and one rendered loop.

   `lexemeespolv001` deliberately has no `primaryGloss`, so the loop selectors have a word that is
   not eligible to exclude. */

import type { LoopCue, LoopItem, VocabularyGraph } from "./domain";

const OWNER = "owner0000000001";
const stamp = (day: string) => `2026-${day}T12:00:00.000Z`;
const sync = (created: string, edited = created) => ({
  ownerId: OWNER, deleted: false, createdAt: stamp(created), editedAt: stamp(edited),
  editedBy: "device000000001", revision: 1
});

export const TEST_OWNER = OWNER;

/**
 * A drill's lines for its words, as a render reports them: each word, its translation after the
 * recall gap, then the pair twice more, `spacing` apart. One card per word.
 */
export function drillCues(loopId: string, items: readonly LoopItem[], spacing: number,
  { source = "es", target = "en" }: { source?: string; target?: string } = {}): LoopCue[] {
  const cues: LoopCue[] = [];
  items.forEach((item, group) => {
    const starts = [item.startSeconds, item.targetRevealSeconds!,
      item.targetRevealSeconds! + spacing, item.targetRevealSeconds! + 2 * spacing,
      item.targetRevealSeconds! + 3 * spacing, item.targetRevealSeconds! + 4 * spacing];
    starts.forEach((start, index) => {
      const side = index % 2 === 0 ? "source" : "target";
      cues.push({
        id: `c${loopId.slice(0, 8)}${String(cues.length).padStart(6, "0")}`, loopId,
        position: cues.length, group, kind: "say", section: "words", loopItemId: item.id, side,
        role: side === "source" ? "native" : "guide", language: side === "source" ? source : target,
        text: side === "source" ? item.sourceText : item.targetText, take: Math.floor(index / 2),
        startSeconds: start, endSeconds: starts[index + 1] ?? item.endSeconds,
        ownerId: item.ownerId, deleted: false, createdAt: item.createdAt, editedAt: item.editedAt,
        editedBy: item.editedBy, revision: item.revision
      });
    });
  });
  return cues;
}

export function testGraph(): VocabularyGraph {
  const graph = recorded();
  // The rendered loop's lines, as its render reported them.
  return { ...graph, loopCues: drillCues("loopmorning0001", graph.loopItems, 4.41) };
}

function recorded(): Omit<VocabularyGraph, "loopCues"> {
  return {
    vocabularies: [
      {
        id: "vocabes00000001", language: "es", definitionLang: "es", glossLangs: ["en"], notesLang: "en",
        displayName: null, flag: null, order: 0, ...sync("01-05")
      },
      {
        id: "vocaben00000001", language: "en", definitionLang: "en", glossLangs: ["ru"], notesLang: "ru",
        displayName: null, flag: null, order: 1, ...sync("01-05")
      }
    ],
    topics: [
      { id: "topicfood000001", name: "Food", icon: "🍽️", order: 0, ...sync("01-05") },
      { id: "topictravel0001", name: "Travel", icon: "🧭", order: 1, ...sync("01-05") }
    ],
    lexemes: [
      {
        id: "lexemepicar0001", language: "es", headword: "picar", lemma: "picar", reading: null,
        ipa: "/piˈkaɾ/", pos: "verb", gender: null, register: "neutral", dialect: null, emoji: "🌶️",
        topicIds: ["topicfood000001"], status: "active", shortGloss: "to itch; to chop",
        primaryGloss: "to sting", emotion: "wincing slightly, as if something just bit you",
        notes: ["The sense is carried by the object, not the verb."],
        clipsSearchedAt: stamp("08-24"), ...sync("02-11", "08-24")
      },
      {
        id: "lexemebalsa0001", language: "es", headword: "la balsa", lemma: "balsa", reading: null,
        ipa: null, pos: "noun", gender: "feminine", register: "neutral", dialect: null, emoji: "🛶",
        topicIds: ["topictravel0001"], status: "active", shortGloss: null,
        primaryGloss: "raft", emotion: null, notes: [],
        clipsSearchedAt: null, ...sync("01-22")
      },
      {
        id: "lexemeespolv001", language: "es", headword: "espolvorear", lemma: "espolvorear",
        reading: null, ipa: null, pos: "verb", gender: null, register: "neutral", dialect: null,
        emoji: "🧀", topicIds: ["topicfood000001"], status: "inbox", shortGloss: "to sprinkle",
        primaryGloss: null, emotion: null, notes: [], clipsSearchedAt: null, ...sync("08-27")
      },
      {
        id: "lexemeturmoil01", language: "en", headword: "turmoil", lemma: "turmoil", reading: null,
        ipa: "/ˈtɜːmɔɪl/", pos: "noun", gender: null, register: "formal", dialect: null, emoji: "🌪️",
        topicIds: [], status: "active", shortGloss: null, primaryGloss: "turmoil",
        emotion: "unsettled and churning", notes: [], clipsSearchedAt: null,
        ...sync("02-25")
      }
    ],
    senses: [
      {
        id: "sensepicaritch0", lexemeId: "lexemepicar0001", definition: "Producir comezón.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["to itch"] }], domain: null, emoji: null, order: 0,
        ...sync("02-11")
      },
      {
        id: "sensepicarchop0", lexemeId: "lexemepicar0001", definition: "Cortar en trozos pequeños.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["to chop", "to dice"] }],
        domain: "cooking", emoji: "🔪", order: 1, ...sync("02-11")
      },
      {
        id: "sensebalsaraft0", lexemeId: "lexemebalsa0001", definition: "Embarcación plana.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["raft"] }], domain: null, emoji: null, order: 0,
        ...sync("01-22")
      },
      {
        id: "senseespolvor10", lexemeId: "lexemeespolv001", definition: "Esparcir polvo sobre algo.",
        definitionLang: "es", glosses: [{ lang: "en", terms: ["to sprinkle"] }], domain: "cooking", emoji: null,
        order: 0, ...sync("08-27")
      },
      {
        id: "senseturmoil010", lexemeId: "lexemeturmoil01", definition: "A state of great confusion.",
        definitionLang: "en", glosses: [{ lang: "ru", terms: ["суматоха", "смятение"] }], domain: null, emoji: null,
        order: 0, ...sync("02-25")
      }
    ],
    attestations: [
      {
        id: "attestpicar0010", lexemeId: "lexemepicar0001", text: "cuidado que esa salsa pica un monton",
        translation: null, sourceUrl: null, sourceTitle: "Course chat", sourceKind: "conversation",
        capturedAt: stamp("02-11"), photoRef: null, photoRegion: null, ...sync("02-11")
      }
    ],
    examples: [
      {
        id: "examplepicar010", senseId: "sensepicaritch0", text: "Me pica la nariz.",
        textLang: "es", translation: "My nose itches.", translationLang: "en", origin: "attestation",
        sourceAttestationId: "attestpicar0010", modelId: null, videoRef: null, videoTitle: null,
        videoChannel: null, videoStart: null, videoEnd: null, clipRef: null,
        imageRef: null, emotion: "exasperated, scratching at the collar", note: null,
        matchedForm: "pica", matchedTranslationForm: "itches", ...sync("02-11")
      },
      {
        // A clip, so its id is derived from its sense and the segment it quotes rather than drawn
        // at random — `clipExampleId("sensepicarchop0", "seg_7c3d18e5b04a92f6de27")`.
        id: "osd6ieh00s2hxql", senseId: "sensepicarchop0", text: "Pica la cebolla bien fina.",
        textLang: "es", translation: "Chop the onion very finely.", translationLang: "en",
        origin: "subtitle", modelId: null, sourceAttestationId: null,
        // A real video URL, because that is what the clip pipeline writes: `videoRef` is the
        // corpus's `video.url`, and a fallback link opens it at `videoStart`.
        videoRef: "https://www.youtube.com/watch?v=ebJDiXbeHTY", videoTitle: "Comiendo en un mercado",
        videoChannel: "Easy Spanish", videoStart: 461, videoEnd: 468,
        clipRef: "seg_7c3d18e5b04a92f6de27",
        imageRef: null, emotion: null, note: null, matchedForm: "Pica",
        matchedTranslationForm: "Chop", ...sync("02-11")
      },
      {
        id: "examplebalsa010", senseId: "sensebalsaraft0", text: "Cruzaron el río en una balsa.",
        textLang: "es", translation: "They crossed the river on a raft.", translationLang: "en",
        origin: "llm", sourceAttestationId: null, modelId: "demo-model", videoRef: null,
        videoTitle: null, videoChannel: null, videoStart: null, videoEnd: null, clipRef: null,
        imageRef: null, emotion: null, note: null,
        matchedForm: null, matchedTranslationForm: null, ...sync("01-22")
      }
    ],
    imagePrompts: [
      {
        id: "imagepicar00010", lexemeId: "lexemepicar0001", senseId: "sensepicaritch0",
        prompt: "A hand hovering near an itchy nose, flat vector, no text.", styleId: "flat-vector",
        seed: 184521, modelId: "demo-prompt", promptVersion: "demo-v1",
        imageRef: "images/lexemepicar0001/imagepicar00010.webp", imageModelId: "demo-painter",
        exampleId: "examplepicar010", attempts: 1, failureReason: null, suppressed: false,
        ...sync("02-11")
      }
    ],
    pronunciations: [
      {
        id: "hl08nur0wl9h0n1", lexemeId: "lexemepicar0001", targetKind: "lexeme", targetId: "lexemepicar0001",
        text: "picar", lang: "es", emotion: null, audioRef: "audio/lexemepicar0001/hl08nur0wl9h0n1-1a2b3c4d.mp3",
        audioMime: "audio/mpeg", providerId: "google-tts", modelId: "wavenet", voice: "es-ES-Wavenet-F",
        ...sync("02-11")
      }
    ],
    studyStates: [
      {
        id: "studypicar00010", lexemeId: "lexemepicar0001", senseId: "sensepicaritch0", system: "anki", noteId: 12, cardIds: [1, 2],
        reps: 21, lapses: 4, stability: 18.3, difficulty: 8.4, retrievability: 0.71,
        lastReview: stamp("08-22"), syncedAt: null, ...sync("02-11")
      },
      {
        id: "studybalsa00010", lexemeId: "lexemebalsa0001", senseId: null, system: "anki", noteId: null, cardIds: [],
        reps: 11, lapses: 0, stability: 74.2, difficulty: 3.9, retrievability: 0.95,
        lastReview: stamp("08-08"), syncedAt: null, ...sync("01-22")
      }
    ],
    loops: [
      {
        id: "loopmorning0001", language: "es", styleId: "sunlit-acoustic", seed: 104740,
        engineVersion: "1.4.0", bedFingerprint: "90c6ad267d159b0e", format: "classic", switches: {}, fallbackFrom: null,
        audioRef: "loops/es/90c6ad267d159b0e.mp3", audioMime: "audio/mpeg",
        durationSeconds: 124.5, position: 0, ...sync("09-01")
      },
      {
        // Queued but not rendered: an absent reference is the whole of what says so.
        id: "loopqueued00001", language: "es", styleId: null, seed: 0, engineVersion: null,
        bedFingerprint: null, format: "classic", switches: {}, fallbackFrom: null, audioRef: null, audioMime: null,
        durationSeconds: null, position: 1, ...sync("09-02")
      }
    ],
    loopItems: [
      {
        id: "loopitempicar01", loopId: "loopmorning0001", lexemeId: "lexemepicar0001", position: 0,
        sourceText: "picar", targetText: "to sting",
        emotion: "wincing slightly, as if something just bit you",
        startSeconds: 8.82, sourceRevealSeconds: 8.82, targetRevealSeconds: 17.65,
        endSeconds: 44.12, ...sync("09-01")
      },
      {
        id: "loopitembalsa01", loopId: "loopmorning0001", lexemeId: "lexemebalsa0001", position: 1,
        sourceText: "la balsa", targetText: "raft", emotion: null,
        startSeconds: 44.12, sourceRevealSeconds: 44.12, targetRevealSeconds: 52.94,
        endSeconds: 79.41, ...sync("09-01")
      }
    ],
    stories: [
      {
        id: "storypicada0001", language: "es", typeId: "funny", styleId: "comic-book",
        title: "La balsa que picaba", titleTranslation: "The raft that stung",
        emoji: "\u{1F6F6}", modelId: "gemini/gemini-3.5-flash-lite", position: 0, guidance: null,
        ...sync("09-03")
      },
      {
        // Asked for and never written: having no parts is the whole of what says so.
        id: "storyqueued0001", language: "es", typeId: "mystery", styleId: "film-noir",
        title: null, titleTranslation: null, emoji: "\u{1F575}", modelId: null, guidance: null,
        position: 1, ...sync("09-04")
      }
    ],
    storyParts: [
      {
        id: "storypart000001", storyId: "storypicada0001", position: 0,
        heading: "La balsa", headingTranslation: "The raft",
        text: "Marcos subió a la balsa al amanecer.",
        translation: "Marcos climbed onto the raft at dawn.",
        imagePrompt: "A man climbs onto a wooden raft at dawn.",
        imageRef: "stories/storypicada0001/storypart000001-1f4c8b2e.webp",
        imageModelId: "openai/gpt-image-1", attempts: 1, failureReason: null,
        // Read aloud by a directed voice, in two passages that join back to `text`, one file each.
        audioProviderId: "google-tts", audioModelId: "gemini-3.1-flash-tts-preview", audioVoice: "Kore",
        audioSegments: [
          { text: "Marcos subió a la balsa ", direction: "Calm, like a bedtime story.",
            audioRef: "stories/storypicada0001/storypart000001-00-9a3c1d7e.ogg",
            audioMime: "audio/ogg", durationSeconds: 1.6 },
          { text: "al amanecer.", direction: "Hushed and slow.",
            audioRef: "stories/storypicada0001/storypart000001-01-4b2e8f01.ogg",
            audioMime: "audio/ogg", durationSeconds: 1.18 }
        ],
        ...sync("09-03")
      },
      {
        // Written and briefed, but never drawn — the second state a part can be in.
        id: "storypart000002", storyId: "storypicada0001", position: 1,
        heading: "El picor", headingTranslation: "The sting",
        text: "Algo empezó a picar bajo el agua.",
        translation: "Something began to sting beneath the water.",
        imagePrompt: "Something stirs beneath the water beside the raft.",
        imageRef: null, imageModelId: null, attempts: 2,
        failureReason: "The image model is temporarily rate limited.",
        // Never read aloud — the other state a part can be in.
        audioProviderId: null, audioModelId: null, audioVoice: null, audioSegments: [],
        ...sync("09-03")
      }
    ],
    storyWords: [
      {
        id: "storyword000001", storyId: "storypicada0001", lexemeId: "lexemebalsa0001",
        position: 0, sourceText: "la balsa", forms: ["balsa"], translationForms: ["raft"],
        ...sync("09-03")
      },
      {
        id: "storyword000002", storyId: "storypicada0001", lexemeId: "lexemepicar0001",
        position: 1, sourceText: "picar", forms: ["picar"], translationForms: ["sting"],
        ...sync("09-03")
      },
      {
        // Asked for and never used, which is a fact worth showing rather than hiding.
        id: "storyword000003", storyId: "storyqueued0001", lexemeId: "lexemepicar0001",
        position: 0, sourceText: "picar", forms: [], translationForms: [], ...sync("09-04")
      }
    ],
    // The morning loop's music, kept as a favourite.
    beds: [
      {
        id: "bedmorning00001", styleId: "sunlit-acoustic", seed: 104740, engineVersion: "1.4.0",
        bedFingerprint: "90c6ad267d159b0e", sourceLoopId: "loopmorning0001", ...sync("09-03")
      }
    ]
  };
}
