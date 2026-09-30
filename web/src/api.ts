import type { Loop, PartOfSpeech, PhotoRegion, Pronunciation, SourceKind, Story, StoryPart, VocabularyGraph } from "./domain";
import { normalizeServerURL, sessionStore, type StoredSession } from "./session";
import type { ArticleDraft } from "./yaml";

type Envelope<T> = { data?: T; error?: { code?: string; message?: string } };
type LoginResponse = { token: string; user: { id: string; email: string } };

/** Shared with the server hook. A mismatch stops synchronisation until the app is updated. */
export const SCHEMA_VERSION = 19;

interface SyncEnvelope {
  schemaVersion: number;
  datasetId: string;
  cursor: number;
  serverTime: string;
}

/**
 * What this server can build entries with.
 *
 * `reason` names an environment variable and never a value, so it is safe to show. It exists so the
 * Capture control can be off *with a reason* rather than live and failing at the moment it is used.
 */
export interface CaptureHealth {
  available: boolean;
  /* The provider that would be asked first, and its model. Null when nothing can be asked: with a
     chain of providers, "unavailable" means no row has its credentials, so there is no model to
     name. `reason` names the first missing environment variable and is the actionable part. */
  provider: string | null;
  model: string | null;
  reason: string | null;
}

/* ── which model builds an entry ──────────────────────────────────────────
   Server state read through a route, not vocabulary: it is owner-scoped, never replicated, and it
   decides what the words are *made of*. It deliberately does not go through `AcervoRepository`,
   which owns the replica and nothing else — the external-dictionary list arrives the same way. */

/** One provider the server knows about, and whether this deployment can actually use it. */
export interface ModelProvider {
  id: string;
  label: string;
  kinds: string[];
  /** The models it offers, per kind. A chain entry is one of these, not a whole provider. */
  models: Record<string, string[]>;
  /** What each speech model does with a direction. Only `instruction` reads the expressive order. */
  styles?: Record<string, "instruction" | "none">;
  available: boolean;
  /** Names an environment variable and never a value, so it is safe to show. */
  reason: string | null;
  /** Where the owner reads their own usage. No provider serves that figure over an API. */
  usageUrl: string | null;
  /**
   * Whose credentials this provider spends, where the credential names one. Null for a provider
   * whose key is just a key, and for a Google login that does not record the account.
   */
  account?: string | null;
  /**
   * Which credential this provider would use, named and abbreviated. `hint` is four characters at
   * each end of the key and never more — enough to tell two keys apart, never enough to use one —
   * and is null for a credential that is a file, which is identified by its `account` instead.
   */
  credential?: ProviderCredential;
  /** The provider's non-secret deployment facts: a project, an account id, a local URL. */
  settings?: { name: string; value: string }[];
  notes: string | null;
}

/* Sense images. Owner-scoped server state and a picture the server draws, so like the provider
   types above these do not go through `AcervoRepository` — but the *rows* they return are ordinary
   `imagePrompts`, and they reach the replica the way everything else does, on the next sync pull. */

/** One image prompt as the image routes answer, which is the stored row plus one derived field. */
export interface ImagePromptRow {
  id: string;
  lexemeId: string;
  senseId: string | null;
  exampleId: string | null;
  prompt: string;
  styleId: string;
  seed: number;
  modelId: string;
  promptVersion: string;
  imageRef: string | null;
  imageModelId: string | null;
  attempts: number;
  failureReason: string | null;
  suppressed: boolean;
  /**
   * The whole prompt the image model is sent — brief, style and frame. Composed on the server and
   * deliberately never stored: the brief, the style id and the version reproduce it exactly, and
   * storing it too would hold the same text twice. Null where there is no brief to compose from.
   */
  composedPrompt: string | null;
}

export interface ImageStyle {
  id: string;
  label: string;
  /** A style with no colour to spend, which the writer avoids where the meaning needs colour. */
  mono: boolean;
  /** A style that renders as a photograph, which `storyContinuity: "artwork"` leaves out. */
  photographic: boolean;
}

/** Whether a story's later pictures are drawn from its earlier pictures of the same people and
 *  places: in every style but the photographic ones, in every style, or never. */
export type StoryContinuity = "artwork" | "all" | "off";

export interface ImageSettings {
  /** Whether a saved word's pictures are drawn on their own, spending money while nobody is watching. */
  drawEnabled: boolean;
  /** The styles switched **off**, never the ones switched on — so a new style arrives on. */
  stylesOff: string[];
  boostVariety: boolean;
  storyContinuity: StoryContinuity;
  /** False means nothing has been chosen and the deployment default is in force. */
  chosen: boolean;
  maxAttempts: number;
  styles: ImageStyle[];
  /** Whether this server is credentialed to draw at all, so a screen can say so plainly. */
  available: boolean;
}

/* Pronunciation. Owner-scoped server state and a clip the server records, so like pictures these do
   not go through `AcervoRepository` — but the rows they return are ordinary `pronunciations`, which
   reach the replica on the next sync pull. */

/** Which fields are recorded when a word is saved, rather than on the first press of play. */
export interface PronunciationPregenerate {
  headword: boolean;
  definitions: boolean;
  examples: boolean;
  /** Whether a story is recorded when it is made. On unless switched off; Settings ▸ Stories. */
  stories: boolean;
}

/** One model in one of the two orders, and the voices it offers per vocabulary language. */
export interface PronunciationModel {
  provider: string;
  providerLabel: string;
  model: string;
  available: boolean;
  /** `instruction` takes an example's emotion; `none` reads everything plainly. */
  style: "instruction" | "none";
  voices: Record<string, string[]>;
}

/** What a voice is asked to read. A selection reads with the `words` order. */
export type PronunciationUse = "words" | "examples" | "loops" | "stories";
/** The two orders, named for their capability: a clear even voice, and one that takes a direction. */
export type PronunciationOrder = "plain" | "expressive";

export interface PronunciationSettings {
  pregenerate: PronunciationPregenerate;
  /**
   * Which order reads each use.
   *
   * It replaces a boolean that only decided whether a *direction was sent*, so switching emotion off
   * still spent the expensive voice on every sentence. Choosing the directed order is what asking
   * for emotion now means — one mechanism where there were two.
   */
  delivery: Record<PronunciationUse, PronunciationOrder>;
  /** {provider: {model: {language: voice}}}. Absent means the model's first voice. */
  voices: Record<string, Record<string, Record<string, string>>>;
  /** Who says a loop's guide lines, in the same shape. Absent means the voice above says them. */
  guideVoices: Record<string, Record<string, Record<string, string>>>;
  chosen: boolean;
  languages: string[];
  /** What a loop's guide speaks: each vocabulary's first gloss language. Each model's `voices`
   *  lists these too, so a guide voice can be chosen. */
  guideLanguages: string[];
  orders: { plain: PronunciationModel[]; expressive: PronunciationModel[] };
}

/** What a selection was read by. The audio itself carries no row, because nothing was stored. */
export interface Utterance {
  audio: Blob;
  voice: string | null;
}

export interface ProviderCredential {
  kind: "key" | "file" | "none";
  variable: string | null;
  present: boolean;
  hint: string | null;
}

export interface ModelPair {
  provider: string;
  model: string;
}

export interface ModelChain {
  /** `deployment` means nothing has been chosen and the server's own order is in force. */
  source: "owner" | "deployment";
  /** Why nothing in this chain can be asked, or null. Same producer as the health readout. */
  reason: string | null;
  /** What is *stored*, not what will be walked: an unavailable pair keeps its place. */
  pairs: ModelPair[];
}

export interface ModelCatalogue {
  providers: ModelProvider[];
  chains: Record<string, ModelChain>;
}

export interface ServerHealth {
  name: string;
  version: string;
  build: string;
  schemaVersion: number;
  capture: CaptureHealth;
}

export type PullResponse = SyncEnvelope & { changes: VocabularyGraph };
export type PushResponse = SyncEnvelope & { records: Partial<VocabularyGraph> };
/** A saved article: the records the server wrote, the entry's id, and the job enriching it. */
export type ArticleSaveResponse = PushResponse & { lexemeId: string; jobId: string | null };
export type ResetResponse = SyncEnvelope & { deleted: number };

const API_PATH = "/api/acervo/v1";
// The corpus's own `/api/v1` surface, allow-listed behind Acervo's auth. The packaged typed client
// is pointed here, so this is a *base URL* rather than a route.
const SPEECH_PATH = "/speech";
/** Compiled dictionaries are served as plain files, outside the JSON API and outside `pb_public`. */
const DICTIONARY_PATH = "/api/acervo/dictionaries";
const MEDIA_PATH = "/api/acervo/media";
const REQUEST_TIMEOUT = 15_000;
/* The first map of a language embeds every sense on the server — a minute or more on a small machine,
   once. A device that already holds a map is not waiting on this: it draws what it has. */
const MAP_TIMEOUT = 240_000;
/** Capture is two model calls deep, so the sync timeout would abort a request that is working. */
const CAPTURE_TIMEOUT = 300_000;
// A picture or a clip sent up from this device: a phone photograph over a slow connection.
const UPLOAD_TIMEOUT = 300_000;
/* A spoken word takes under two seconds and an expressive sentence three; a whole chain falling
   through its models is what this has to cover. Somebody is holding a finger over a play button. */
const PRONOUNCE_TIMEOUT = 60_000;
/* A part read aloud by a directed voice is one call to a text model and then one call to the voice
   for every passage, one after another: measured at 5–7 s a passage on the free Gemini voice, so a
   part of eight passages is close to a minute. Long enough not to give up on a recording the server
   is still making, which would then arrive anyway and be found on the next pull. */
const STORY_AUDIO_TIMEOUT = 180_000;
// A photo is ~400 KB up and a page of words down; Vision answers in about a second, and the first
// photo may also wait for the sentence splitter to load.
const PHOTO_TIMEOUT = 45_000;
// The quick look-up: about a second at the median, raced by a second model at 2.5 s on the server.
const QUICK_TIMEOUT = 20_000;

/* ── capture ────────────────────────────────────────────────────────────
   The capture route (`docs/features/capture.md`). What comes back is a *proposal*: a draft the
   interface renders for review and then saves through the repository like any other article.
   Nothing here writes. */

export interface CaptureSentence {
  text: string;
  translation: string | null;
}

export interface CaptureResolution {
  language: string;
  headword: string;
  lemma: string;
  pos: PartOfSpeech;
  sentences: CaptureSentence[];
  note: string | null;
  /** How many leading lines of the submitted text the entry covered. Only meaningful in a stream. */
  consumedLines: number;
  consumedText: string | null;
  /** What the word means in this sentence, in the vocabulary's first gloss language. Only a quick look-up asks. */
  gloss?: string | null;
}

/** An entry this word already has. `foldable` beside it is what a repeat capture can add to it. */
export interface CaptureDuplicate {
  id: string;
  headword: string;
  shortGloss: string | null;
}

/**
 * What a repeat capture carried that the stored entry may not have.
 *
 * `null` when the capture was just the word again. The sentences are the learner's own, already
 * separated from anything a dictionary supplied — which is what makes folding them into the entry
 * they belong to safe.
 */
export interface CaptureFoldable {
  sentences: CaptureSentence[];
  /** Whether a dictionary entry came with it. The text itself stays on the server. */
  reference: boolean;
  note: string | null;
}

/** A provider that was asked before the one that answered, and why it was passed over. */
export interface CapturePassedOver {
  provider: string;
  model: string;
  /** One of the retryable reasons: `rate_limited`, `unavailable`, `unreachable`. */
  reason: string;
}

export interface CaptureResult {
  resolution: CaptureResolution;
  duplicates: CaptureDuplicate[];
  draft: ArticleDraft | null;
  /** Only ever set alongside `duplicates`: what this capture could add to the word already held. */
  foldable?: CaptureFoldable | null;
  /**
   * Empty on the ordinary path. Non-empty means the chain fell through, which is otherwise
   * invisible: the entry names the model that wrote it, but a provider at the head of the order
   * that is quietly broken looks exactly like one that was never chosen.
   */
  passedOver?: CapturePassedOver[];
}

export interface CaptureRequest {
  text: string;
  /**
   * The word the submitter means, when they know it. A hint, not an instruction: the server still
   * corrects spelling and picks the lemma, and still overrides it if the text plainly says otherwise.
   * Absent is the ordinary case — a shared sentence carries no way to point at a word.
   */
  headword?: string | null;
  sourceUrl?: string | null;
  sourceTitle?: string | null;
  /** A free-text request for the generator, sent with the capture. */
  note?: string | null;
  /**
   * An external dictionary's entry for this word, as the reader saw it.
   *
   * Grounding, and only grounding. It is deliberately *not* sent as `text`: the resolver reads that
   * as sentences the learner met, and every one of them would become an attestation — a claim about
   * where this person encountered the word, forged out of a dictionary's own examples. Provenance
   * is modelled here, never flagged, so the two arrive by different doors.
   */
  reference?: string | null;
  /** How closely to follow it. Absent means the `note` says what to do instead. */
  referenceMode?: "faithful" | "expand" | null;
  /**
   * What a quick look-up returned for this same text a moment ago. The server checks it rather than
   * trusting it, and does not pay for resolve a second time.
   */
  resolution?: CaptureResolution | null;
  /** The photo this was read from, as `readPhoto` named it, and where on it the word and sentence are. */
  photoRef?: string | null;
  photoRegion?: PhotoRegion | null;
  sourceKind?: SourceKind | null;
}

/* ── photo capture ──────────────────────────────────────────────────────
   A photo goes up and comes back as a page of tappable words (`POST /photo/read`); a tap asks the
   quick look-up (`POST /capture/resolve`) what was meant; Add is `captureText` carrying that
   resolution and the photo. Nothing here writes a record: the photo waits on the server until the
   save that names it, and is removed after a day if none does. */

/** A point, a polygon: normalised to the photo, 0–1 from its top left. */
export type PhotoPoint = [number, number];

export interface PhotoWord {
  id: string;
  text: string;
  /** One outline per printed piece: a word hyphenated across a line break has two. */
  polygons: PhotoPoint[][];
  confidence: number;
  lineId: string;
  /** Offsets into the page's running `text`. */
  start: number;
  end: number;
}

export interface PhotoLine {
  id: string;
  polygon: PhotoPoint[];
  wordIds: string[];
}

export interface PhotoSentence {
  id: string;
  text: string;
  wordIds: string[];
  start: number;
  end: number;
  /** The frame cut it off: its start, or its end, is not in the photo. */
  truncatedStart: boolean;
  truncatedEnd: boolean;
}

export interface PhotoReading {
  /** Where the photo will live once a save keeps it. */
  photoRef: string;
  width: number;
  height: number;
  /** The owner's vocabulary for the detected language, or the detected language itself. */
  language: string | null;
  /** Whether the owner keeps a vocabulary for it. */
  vocabulary: boolean;
  readBy: { provider: string; model: string };
  text: string;
  words: PhotoWord[];
  lines: PhotoLine[];
  sentences: PhotoSentence[];
}

export interface QuickLookUpRequest {
  /** The sentence, as it stands in the sheet. */
  text: string;
  /** The tapped span within it. */
  selection: { start: number; end: number };
  /**
   * Where the sentence was met: read by OCR from a photo, which may repair it, or read in Acervo —
   * a story, a loop, an article — which is finished text and comes back exactly as it was.
   */
  source: "photo" | "reading";
}

/** A word tapped while reading, filed in the Inbox by the headless capture job. */
export interface InboxCapture {
  /** The sentence it was met in, which becomes its attestation. */
  text: string;
  /** What the quick look-up answered for it, so the job writes the word the owner saw. */
  resolution: CaptureResolution;
  /** What the owner was reading: a story, a loop, a word's entry. */
  sourceTitle: string | null;
}

export interface QuickLookUp {
  resolution: CaptureResolution;
  duplicates: CaptureDuplicate[];
  foldable: CaptureFoldable | null;
  passedOver?: CapturePassedOver[];
}

/* ── chat ───────────────────────────────────────────────────────────────
   `docs/features/article-chat.md`: chat lives inside the article, and its output is a proposed
   revision of that record. The route writes nothing. A turn returns prose and, only when the turn
   implies a change, a set of small edit operations — applied to a draft on this device by
   `articleEdit.ts`, reviewed as an ordinary article, and saved through `repository.saveArticle`
   like every other write.

   The document is assembled here rather than on the server on purpose: `yaml.ts` is the only place
   the projection is understood, so a server-side serialiser would be a second implementation of it,
   drifting from the first the moment a field is added. */

export interface ChatTurn {
  role: "you" | "acervo";
  text: string;
}

export type ChatSubject =
  | { kind: "article"; lexemeId: string; document: string; focus: string | null }
  | { kind: "reference"; headword: string; language: string | null };

/** Headword and gloss only. Enough to say "you already have «el traje»", and nothing more. */
export interface ChatNeighbour {
  headword: string;
  shortGloss: string | null;
}

export interface ChatRequest {
  subject: ChatSubject;
  /** External dictionary text on screen. Read-only context for both subject kinds. */
  reference?: string | null;
  referenceSources?: string[];
  neighbours?: ChatNeighbour[];
  /** The transcript, oldest first, including the question being asked as its final `you` turn. */
  turns: ChatTurn[];
}

/**
 * The wire form of an edit. Deliberately loose here: this is the shape the server checked, and
 * whether an id exists or a field may be set is `articleEdit.ts`'s question, against the document.
 */
export interface ChatEditOp {
  op: "set" | "addSense" | "addExample" | "addAttestation" | "remove" | "orderSenses";
  target?: string;
  field?: string;
  value?: unknown;
  after?: string | null;
  senseId?: string;
  fromAttestation?: string | null;
  ref?: string;
  reason?: string;
  ids?: string[];
  sense?: Record<string, unknown>;
  example?: Record<string, unknown>;
  attestation?: Record<string, unknown>;
}

export interface ChatProposal {
  summary: string;
  ops: ChatEditOp[];
}

/** The argument list for the capture the interface already performs from an external article. */
export interface ChatCapture {
  headword: string;
  note: string;
  referenceMode: "faithful" | "expand" | null;
}

export interface ChatResult {
  reply: string;
  followUps: string[];
  /** Article subjects only. A dictionary entry has nothing editable on screen. */
  proposal: ChatProposal | null;
  /** Reference subjects only. */
  capture: ChatCapture | null;
  modelId: string;
}

/** An artifact this server holds, as its metadata sidecar describes it. */
export interface RemoteDictionary {
  id: string;
  name: string;
  sourceLang: string;
  targetLang: string;
  tier: "fields" | "html";
  licence: string;
  attribution: string;
  entryCount: number;
  keyCount: number;
  blobBytes: number;
  indexBytes: number;
  schemaVersion: number;
  sourceDate?: string;
  builtAt?: string;
}

export interface OnlineLookup {
  source: string;
  word: string;
  entries: OnlineArticle[];
}

export interface OnlineArticle {
  headword: string;
  language?: string;
  posLabel?: string;
  ipa?: string;
  senses: { definition: string; examples?: { text: string; translation?: string | null }[] }[];
}

/* ── clips ────────────────────────────────────────────────────────────────
   Server state read through a route, like the model chain and the picture settings: owner-scoped,
   never replicated, and about what the words are *made of* rather than what they are. */

/** What this deployment's corpus holds, so Settings can say more than "on" or "off". */
export interface CorpusReadout {
  configured: boolean;
  reachable: boolean;
  ready?: boolean;
  builtAt?: string | null;
  indexedLanguages?: string[];
  videos?: number;
  segments?: number;
  /**
   * Whether the *player's* target text is configured, and on what.
   *
   * A different surface from the article's translation line, which is Acervo's own and came from
   * the clip-selection call (spoken-clips §2.13). This one is the corpus's, and it is the piece of
   * this deployment that can be switched off with nothing saying so — the player renders one grey
   * sentence whether no provider is credentialed, the chain names rows that container lacks, or a
   * model answered badly. `provider` is the *chain*, deliberately, because that is what the
   * service caches on.
   */
  translation?: { available: boolean; provider: string | null; model: string | null };
  error?: string;
}

export interface ClipSettings {
  searchEnabled: boolean;
  /**
   * Whether the selector rejects a passage whose subject cannot be recovered from the passage.
   *
   * Off by default, deliberately: real speech is messy, and a learner meets it by walking into a
   * conversation already under way. Preserving that is what a clip is for.
   */
  selfContainedOnly: boolean;
  /** False means "following the deployment default", which is a real answer and not a gap. */
  chosen: boolean;
  corpus: CorpusReadout;
}

/**
 * The owner's standing rules for everything a text model writes for them. Stored on the server, so
 * every device reads the same text; empty means none.
 */
export interface PromptRules {
  rules: string;
  chosen: boolean;
  /** The most characters the server will keep. */
  limit: number;
}

/* ── jobs ─────────────────────────────────────────────────────────────────
   Work the server does on the owner's behalf. Server state, never replicated: the interface shows
   it and never does it. A job's results reach the replica the way every record does, on the pull
   that its `revision` event prompts. */

export type JobState = "queued" | "running" | "done" | "failed" | "cancelled";
export type JobStepState = "pending" | "running" | "waiting" | "done" | "skipped" | "failed";

export interface JobStep {
  name: string;
  state: JobStepState;
  done?: number;
  total?: number;
  /** An `llm_*`-style code, and the owner-facing sentence that goes with it. */
  error?: string;
  message?: string;
  /** How many times this step has waited out a busy provider. */
  rests?: number;
  /** While resting: every provider that refused and why, as one phrase the server wrote. */
  waitingOn?: string;
  /** Whatever a step reports beyond progress: `found` clips, `refused` pictures. */
  detail?: Record<string, unknown>;
}

export interface Job {
  id: string;
  ownerId: string;
  parentId: string | null;
  kind: string;
  subject: { kind: string; id: string } | null;
  input: Record<string, unknown>;
  state: JobState;
  trigger: string;
  steps: JobStep[];
  rerun: boolean;
  cancelRequested: boolean;
  dismissed: boolean;
  error: string | null;
  message: string | null;
  notBefore: string | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  children?: Job[];
}

/** Settings ▸ Schedule: when the nightly run happens, and which of its steps are on. */
export interface ScheduleSettings {
  /** 0–23, read in the server's `timezone`. */
  hour: number;
  steps: Record<string, boolean>;
  /** False means nothing has been chosen and the deployment default is in force. */
  chosen: boolean;
  timezone: string;
  nextRunAt: string;
  lastRun: Job | null;
}

/** Settings ▸ Anki: whether Anki is kept up to date by the server, and how it last went. */
export interface AnkiStatus {
  /** False on a server with no Anki sync server behind it; then neither switch can be turned on. */
  configured: boolean;
  /** Push the vocabulary to Anki a minute after it changes. */
  push: boolean;
  /** Read Anki's review state back every hour. */
  pull: boolean;
  lastPush: Job | null;
  lastPull: Job | null;
}

/* ── loops ──
   What the generator can be asked for, as `GET /loops/schema` reports it. Its catalogues are its
   own and are never copied here: a family or a format added in a later version of it appears in
   the dialog with nothing changing on this side. */
/* The meaning map of one language, as the server draws it (docs/features/meaning-map.md).
   Positions, ids and region labels — never vectors and never a sense's text, which the device joins
   from its own replica. */
export interface ServerMapPoint {
  sense: string;
  lexeme: string;
  x: number;
  y: number;
  r: number;
  h: number;
  rank: number;
  nb: number[];
}

export interface ServerMapRegion {
  id: string;
  level: "region" | "hood";
  index: number;
  x: number;
  y: number;
  count: number;
  region?: number;
  labels: { words: string[]; terms: string[]; name?: string };
}

export interface ServerMap {
  language: string;
  fingerprint: string;
  /* What `have` is compared with: the fingerprint and whether the regions are named, since naming
     changes the map without changing its layout. */
  version: string;
  model: string;
  side: number;
  words: number;
  senses: number;
  /* `pending` until the job that names the regions lands; `none` when there is nothing to name. */
  names: "pending" | "ready" | "none";
  points: ServerMapPoint[];
  regions: ServerMapRegion[];
  contours: [number, number[]][];
}

export type MapAnswer = ServerMap | { current: true; version: string };

/** One kind of music, with the generator's own words to choose it by. */
export interface LoopFamily {
  id: string;
  label: string;
  description: string;
}

/** A choice a format offers: on or off, or one of its named `choices`. */
export interface LoopSwitch {
  label: string;
  default: boolean | string;
  choices?: string[];
}

/** One kind of loop — a drill, a radio lesson, a story — in the generator's own words. */
export interface LoopFormat {
  id: string;
  label: string;
  description: string;
  switches: Record<string, LoopSwitch>;
  /** `writer` (a model that writes its lines) and `multilingual_voice` (a voice that can say two
   *  languages in one line). */
  requires: string[];
  /** What is made instead when a requirement is missing, or null when it is then refused. */
  fallback: string | null;
}

export interface LoopSchema {
  apiVersion: string;
  engineVersion: string;
  /** False means the pinned sample bundle is not installed, or not all of it: no loop can be made. */
  productionBundle: boolean;
  formats: LoopFormat[];
  /** Whether this server has a text model to write a format's lines with. */
  writerAvailable: boolean;
  /** Whether the voice chosen for loops can say two languages in one line. */
  mixesLanguages: boolean;
  /** Every kind of music there is. "Surprise me" is not one of them — it is asking for none. */
  families: LoopFamily[];
  maxItems: number;
}

/** A change of music: another style, the same style afresh (nothing given), or a kept bed (both). */
export interface LoopMusic {
  family?: string;
  seed?: number;
}

export interface LoopRequest {
  deviceId: string;
  language: string;
  /** Word ids, sampled from the scope on screen. The server never re-derives that scope. */
  lexemeIds: string[];
  format?: string;
  switches?: Record<string, boolean | string>;
  family?: string;
  /** A kept bed's seed, given only with its family: the pair is what replays it. */
  seed?: number;
}

/* ── stories ──
   The kinds of story and the styles they can be drawn in, as `GET /stories/types` reports them.
   Both are tracked config the server ships, never enums copied here: a kind added to
   `config/story-types.yaml` appears in the dialog with nothing changing on this side. */
export interface StoryTypeOption {
  id: string;
  label: string;
  emoji: string;
  /** The styles this kind suggests. "Surprise me" picks from these; the dialog offers them all. */
  styles: string[];
}

export interface StoryTypes {
  types: StoryTypeOption[];
  /** Every style the owner has left switched on, so one may be picked that no kind suggests. */
  styles: { id: string; label: string }[];
  minWords: number;
  maxWords: number;
  minParts: number;
  maxParts: number;
  defaultParts: number;
}

export interface StoryRequest {
  deviceId: string;
  language: string;
  /** Word ids, sampled from the scope on screen. The server never re-derives that scope. */
  lexemeIds: string[];
  typeId?: string;
  styleId?: string;
  /** The owner's own note to the writer — a setting, a narrator, a tone. Optional. */
  guidance?: string;
}

export interface JobRequest {
  kind: string;
  subject: { kind: string; id: string };
  /** What the job needs beyond its subject: an edited brief and style, for edit-and-draw. */
  input?: Record<string, string>;
  trigger?: "manual" | "import";
}

export class AcervoApiError extends Error {
  constructor(message: string, readonly status: number, readonly code: string) { super(message); }
}

function timeoutSignal(milliseconds: number): AbortSignal | undefined {
  return typeof AbortSignal !== "undefined" && "timeout" in AbortSignal ? AbortSignal.timeout(milliseconds) : undefined;
}

/** The caller's own signal, if it gave one, and the timeout: whichever fires first. */
function withTimeout(signal: AbortSignal | null | undefined, milliseconds: number): AbortSignal | undefined {
  const timeout = timeoutSignal(milliseconds);
  if (!signal) return timeout;
  if (!timeout) return signal;
  return "any" in AbortSignal ? AbortSignal.any([signal, timeout]) : signal;
}

class ApiClient {
  private session: StoredSession | null = null;
  private onUnauthorized: (() => void) | null = null;

  configure(session: StoredSession | null) { this.session = session; }
  current() { return this.session; }

  /** Where a file lives, for the direct reads that do not go through the JSON envelope. */
  fileUrl(root: string, path: string): string {
    const baseUrl = this.session?.baseUrl;
    if (!baseUrl) throw new AcervoApiError("Configure the Acervo server first.", 0, "not_configured");
    return `${baseUrl}${root}${path}`;
  }

  authHeaders(): Record<string, string> {
    return this.session?.token ? { Authorization: `Bearer ${this.session.token}` } : {};
  }
  /** Called when the server rejects the stored token. The replica is deliberately kept. */
  handleUnauthorized(handler: (() => void) | null) { this.onUnauthorized = handler; }

  async call<T>(path: string, options: RequestInit = {}, anonymous = false, timeout = REQUEST_TIMEOUT): Promise<T> {
    if (!anonymous && !this.session?.token) throw new AcervoApiError("Sign in to continue.", 401, "unauthenticated");
    const baseUrl = this.session?.baseUrl;
    if (!baseUrl) throw new AcervoApiError("Configure the Acervo server first.", 0, "not_configured");
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    // Only where the caller has not said otherwise: a picture is sent as a raw body with its own
    // type, and overwriting that would hand the server a WebP labelled as JSON.
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (!anonymous && this.session?.token) headers.set("Authorization", `Bearer ${this.session.token}`);
    let response: Response;
    try { response = await fetch(`${baseUrl}${API_PATH}${path}`, { ...options, headers, cache: "no-store", signal: withTimeout(options.signal, timeout) }); }
    catch (error) {
      // The caller changed its mind, which is not the server being unreachable.
      if (options.signal?.aborted) throw error;
      throw new AcervoApiError("The Acervo server could not be reached. Local vocabulary remains available.", 0, "offline");
    }
    let envelope: Envelope<T> = {};
    try { envelope = await response.json() as Envelope<T>; } catch { /* diagnosed below */ }
    if (!response.ok || envelope.error || envelope.data === undefined) {
      if (response.status === 401 && !anonymous) this.onUnauthorized?.();
      throw new AcervoApiError(envelope.error?.message || "The Acervo server returned an invalid response.", response.status, envelope.error?.code || "request_failed");
    }
    return envelope.data;
  }

  /**
   * A response that is meant never to end, so it gets no timeout: the caller aborts it. Failures
   * still arrive as the envelope's error.
   */
  async stream(path: string, signal: AbortSignal): Promise<Response> {
    if (!this.session?.token) throw new AcervoApiError("Sign in to continue.", 401, "unauthenticated");
    const baseUrl = this.session.baseUrl;
    let response: Response;
    try {
      response = await fetch(`${baseUrl}${API_PATH}${path}`, {
        headers: { Accept: "text/event-stream", Authorization: `Bearer ${this.session.token}` },
        cache: "no-store",
        signal
      });
    } catch {
      throw new AcervoApiError("The Acervo server could not be reached.", 0, "offline");
    }
    if (!response.ok || !response.body) {
      if (response.status === 401) this.onUnauthorized?.();
      let envelope: Envelope<unknown> = {};
      try { envelope = await response.json() as Envelope<unknown>; } catch { /* no body to read */ }
      throw new AcervoApiError(envelope.error?.message || "The Acervo server returned an invalid response.", response.status, envelope.error?.code || "request_failed");
    }
    return response;
  }

  /** A route that answers with bytes rather than an envelope, whose failures still arrive as one. */
  async bytes(path: string, options: RequestInit = {}, timeout = REQUEST_TIMEOUT): Promise<Response> {
    if (!this.session?.token) throw new AcervoApiError("Sign in to continue.", 401, "unauthenticated");
    const baseUrl = this.session.baseUrl;
    if (!baseUrl) throw new AcervoApiError("Configure the Acervo server first.", 0, "not_configured");
    const headers = new Headers(options.headers);
    if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    headers.set("Authorization", `Bearer ${this.session.token}`);
    let response: Response;
    try { response = await fetch(`${baseUrl}${API_PATH}${path}`, { ...options, headers, cache: "no-store", signal: timeoutSignal(timeout) }); }
    catch { throw new AcervoApiError("The Acervo server could not be reached.", 0, "offline"); }
    if (!response.ok) {
      if (response.status === 401) this.onUnauthorized?.();
      let envelope: Envelope<unknown> = {};
      try { envelope = await response.json() as Envelope<unknown>; } catch { /* no body to read */ }
      throw new AcervoApiError(envelope.error?.message || "The Acervo server returned an invalid response.", response.status, envelope.error?.code || "request_failed");
    }
    return response;
  }
}

const client = new ApiClient();

export const backendSession = {
  current: () => client.current(),
  async restore(): Promise<StoredSession | null> {
    const session = await sessionStore.load();
    client.configure(session);
    return session;
  },
  async login(rawUrl: string, email: string, password: string): Promise<StoredSession> {
    const baseUrl = normalizeServerURL(rawUrl);
    client.configure({ baseUrl, email: email.trim(), token: "", userId: "" });
    try {
      const result = await client.call<LoginResponse>("/session", {
        method: "POST", body: JSON.stringify({ email: email.trim(), password })
      }, true);
      const session = { baseUrl, email: result.user.email, token: result.token, userId: result.user.id };
      await sessionStore.save(session);
      client.configure(session);
      return session;
    } catch (error) { client.configure(null); throw error; }
  },
  async refresh(): Promise<StoredSession | null> {
    const current = client.current();
    if (!current?.token) return current;
    try {
      const result = await client.call<LoginResponse>("/session/refresh", { method: "POST" });
      const session = { ...current, email: result.user.email, token: result.token, userId: result.user.id };
      await sessionStore.save(session);
      client.configure(session);
      return session;
    } catch (error) {
      if (error instanceof AcervoApiError && error.status === 401) {
        client.configure(null);
        await sessionStore.clear();
        return null;
      }
      return current;
    }
  },
  async logout() { client.configure(null); await sessionStore.clear(); },
  /** Drops the token but keeps the replica: the vocabulary is still the owner's. */
  async reject() { const current = client.current(); client.configure(null); if (current) await sessionStore.clear(); },
  onUnauthorized(handler: (() => void) | null) { client.handleUnauthorized(handler); },

  /**
   * A server fact, read once. Unauthenticated on the server, and asked for anonymously here so it
   * still answers while a session is being restored — but it goes through `client.call` like every
   * other route, because on the native host the server is not the page's origin.
   */
  health(): Promise<ServerHealth> {
    return client.call<ServerHealth>("/health", {}, true);
  },

  /** When the nightly run happens, and how the last one went. */
  scheduleSettings(): Promise<ScheduleSettings> {
    return client.call<ScheduleSettings>("/schedule/settings");
  },
  saveScheduleSettings(changes: { hour?: number; steps?: Record<string, boolean> }): Promise<ScheduleSettings> {
    return client.call<ScheduleSettings>("/schedule/settings", {
      method: "PUT", body: JSON.stringify(changes)
    });
  },

  /** Whether the server keeps Anki up to date, and how the last push and read went. */
  ankiStatus(): Promise<AnkiStatus> {
    return client.call<AnkiStatus>("/anki");
  },
  saveAnkiSettings(changes: { push?: boolean; pull?: boolean }): Promise<AnkiStatus> {
    return client.call<AnkiStatus>("/anki/settings", { method: "PUT", body: JSON.stringify(changes) });
  },
  /** Push now, or Read now: due at once, even if a push was waiting for edits to stop. */
  ankiNow(what: "push" | "pull"): Promise<Job> {
    return client.call<Job>(`/anki/${what}`, { method: "POST", body: "{}" });
  },

  /** The server's open jobs — what a client rebuilds its map from — or its recent ones. */
  async jobs(open: boolean): Promise<Job[]> {
    return (await client.call<{ jobs: Job[] }>(open ? "/jobs?open=true" : "/jobs")).jobs;
  },
  job(id: string): Promise<Job> {
    return client.call<Job>(`/jobs/${encodeURIComponent(id)}`);
  },
  /** Try again, and an import's request for enrichment. A save never needs this. */
  loopSchema(): Promise<LoopSchema> { return client.call<LoopSchema>("/loops/schema"); },
  /* `have` is the version this device already holds; a map still current answers `current`. */
  readMap(language: string, have?: string | null): Promise<MapAnswer> {
    const query = have ? `?have=${encodeURIComponent(have)}` : "";
    return client.call<MapAnswer>(`/map/${encodeURIComponent(language)}${query}`, {}, false, MAP_TIMEOUT);
  },
  /* Answers 202 with the row and the job that will render it. The row exists either way: a loop
     that was asked for and not made is one with no `audioRef`, which is all "not ready" means. */
  makeLoop(request: LoopRequest): Promise<{ loop: Loop; job: Job }> {
    return client.call<{ loop: Loop; job: Job }>("/loops", { method: "POST", body: JSON.stringify(request) });
  },
  /* Renders the loop again with other music. The row is left alone until the new track lands, so the
     loop goes on playing — and describing — the music it has; 409 `loop_busy` while one is under way. */
  changeLoopMusic(loopId: string, music: LoopMusic): Promise<{ job: Job }> {
    return client.call<{ job: Job }>(
      `/loops/${encodeURIComponent(loopId)}/music`, { method: "POST", body: JSON.stringify(music) }
    );
  },
  /* A route rather than an ordinary tombstone, because the track goes with the rows: it is megabytes
     and nothing else would ever remove it, so the row and the file are written by the same party —
     the shape `removeImage` already has. */
  deleteLoop(loopId: string, deviceId: string): Promise<Loop> {
    return client.call<Loop>(
      `/loops/${encodeURIComponent(loopId)}`,
      { method: "DELETE", headers: { "X-Acervo-Device": deviceId } }
    );
  },
  storyTypes(): Promise<StoryTypes> { return client.call<StoryTypes>("/stories/types"); },
  /* Answers 202 with the row and the job that will write it. The row exists either way: a story
     that was asked for and never written is one with no parts, which is all "not written" means. */
  makeStory(request: StoryRequest): Promise<{ story: Story; job: Job }> {
    return client.call<{ story: Story; job: Job }>("/stories", { method: "POST", body: JSON.stringify(request) });
  },
  /* A route rather than an ordinary tombstone, for `deleteLoop`'s reason: the pictures go with the
     rows, and only the party that writes the rows can unlink them. */
  deleteStory(storyId: string, deviceId: string): Promise<Story> {
    return client.call<Story>(
      `/stories/${encodeURIComponent(storyId)}`,
      { method: "DELETE", headers: { "X-Acervo-Device": deviceId } }
    );
  },
  /* One part read aloud now, in the voice the story is already read in. The same function the
     `story.audio` step runs, so a part recorded either way is indistinguishable; the row it returns
     reaches the replica on the next pull, like a clip's. One or more model calls, with a model
     call's timeout. */
  recordStoryPart(storyId: string, partId: string, deviceId: string): Promise<StoryPart> {
    return client.call<StoryPart>(
      `/stories/${encodeURIComponent(storyId)}/parts/${encodeURIComponent(partId)}/audio`,
      { method: "POST", body: JSON.stringify({ deviceId }) },
      false,
      STORY_AUDIO_TIMEOUT
    );
  },
  enqueueJob(request: JobRequest): Promise<Job> {
    return client.call<Job>("/jobs", { method: "POST", body: JSON.stringify(request) });
  },
  cancelJob(id: string): Promise<Job> {
    return client.call<Job>(`/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST", body: "{}" });
  },
  dismissJob(id: string): Promise<Job> {
    return client.call<Job>(`/jobs/${encodeURIComponent(id)}/dismiss`, { method: "POST", body: "{}" });
  },
  /** The event stream, read with `fetch` because `EventSource` cannot send the bearer header. */
  events(signal: AbortSignal): Promise<Response> {
    return client.stream("/events", signal);
  },

  pullGraph(since: number): Promise<PullResponse> {
    return client.call<PullResponse>(`/graph?schemaVersion=${SCHEMA_VERSION}&since=${since}`);
  },
  pushGraph(deviceId: string, changes: Partial<VocabularyGraph>, options: { enrich?: boolean } = {}): Promise<PushResponse> {
    return client.call<PushResponse>("/graph", {
      method: "POST",
      body: JSON.stringify({
        schemaVersion: SCHEMA_VERSION, deviceId, changes,
        ...(options.enrich === false ? { enrich: false } : {})
      })
    });
  },
  /**
   * One article, as the document the device parsed. The server works out what it means for the
   * stored entry and writes it in one transaction; `base` is the revision this replica holds of
   * each of the entry's records, so an edit made from a stale copy is refused rather than laid over
   * a newer one.
   */
  saveArticle(deviceId: string, draft: ArticleDraft, minted: string[], base: Record<string, number>,
              options: { enrich?: boolean } = {}): Promise<ArticleSaveResponse> {
    return client.call<ArticleSaveResponse>("/articles", {
      method: "POST",
      body: JSON.stringify({
        schemaVersion: SCHEMA_VERSION, deviceId, draft, minted, base,
        ...(options.enrich === false ? { enrich: false } : {})
      })
    });
  },
  /**
   * One turn of conversation. Writes nothing — a proposal is applied to a draft on this device and
   * only a second press, through the repository, ever reaches the store.
   *
   * On `CAPTURE_TIMEOUT` rather than the ordinary read timeout: this is one model call, but a slow
   * one, and the sync timeout would abort a request that is working.
   */
  chat(deviceId: string, request: ChatRequest): Promise<ChatResult> {
    return client.call<ChatResult>("/chat", {
      method: "POST",
      body: JSON.stringify({
        schemaVersion: SCHEMA_VERSION,
        deviceId,
        subject: request.subject,
        reference: request.reference?.trim() || null,
        referenceSources: request.referenceSources ?? [],
        neighbours: request.neighbours ?? [],
        turns: request.turns
      })
    }, false, CAPTURE_TIMEOUT);
  },

  /**
   * Submits text to the capture route and returns what it made of it. The route writes nothing: the
   * interface reviews the draft and saves it like any other article. Headless transports submit to
   * `POST /captures` instead, and the server files what it makes in the Inbox.
   */
  captureText(deviceId: string, request: CaptureRequest): Promise<CaptureResult> {
    return client.call<CaptureResult>("/capture", {
      method: "POST",
      body: JSON.stringify({
        schemaVersion: SCHEMA_VERSION,
        deviceId,
        mode: "single",
        text: request.text,
        headword: request.headword?.trim() || null,
        sourceUrl: request.sourceUrl ?? null,
        sourceTitle: request.sourceTitle ?? null,
        note: request.note ?? null,
        reference: request.reference?.trim() || null,
        referenceMode: request.referenceMode ?? null,
        resolution: request.resolution ?? null,
        photoRef: request.photoRef ?? null,
        photoRegion: request.photoRegion ?? null,
        sourceKind: request.sourceKind ?? null
      })
    }, false, CAPTURE_TIMEOUT);
  },

  /** Reads a photo into a page of tappable words. The photo is sent as it is — `photoText.encodePhoto` prepares it. */
  readPhoto(photo: Blob): Promise<PhotoReading> {
    return client.call<PhotoReading>("/photo/read", {
      method: "POST",
      headers: { "Content-Type": photo.type || "image/jpeg" },
      body: photo
    }, false, PHOTO_TIMEOUT);
  },
  /** Keeps a photo pending without reading it — the square of a screenshot that was on screen. */
  storePhoto(photo: Blob): Promise<{ photoRef: string; width: number; height: number }> {
    return client.call("/photo/store", {
      method: "POST",
      headers: { "Content-Type": photo.type || "image/jpeg" },
      body: photo
    }, false, PHOTO_TIMEOUT);
  },
  /** The Photo tab opened: the server loads its sentence splitter now rather than on the first photo. */
  warmPhoto(): Promise<unknown> {
    return client.call("/photo/warm", { method: "POST", body: "{}" });
  },
  /** The quick look-up a tap makes. Aborted by `signal` when the selection moves on. */
  resolveCapture(deviceId: string, request: QuickLookUpRequest, signal?: AbortSignal): Promise<QuickLookUp> {
    return client.call<QuickLookUp>("/capture/resolve", {
      method: "POST",
      signal,
      body: JSON.stringify({
        schemaVersion: SCHEMA_VERSION,
        deviceId,
        mode: "single",
        source: request.source,
        text: request.text,
        selection: request.selection
      })
    }, false, QUICK_TIMEOUT);
  },
  /**
   * Add, for a word tapped while reading: the headless capture job (`POST /captures`), which files
   * the word in the Inbox while the owner goes on reading. Online-only and loud when it fails.
   */
  queueCapture(deviceId: string, request: InboxCapture): Promise<Job> {
    return client.call<Job>("/captures", {
      method: "POST",
      body: JSON.stringify({
        schemaVersion: SCHEMA_VERSION,
        deviceId,
        mode: "single",
        text: request.text,
        headword: request.resolution.headword,
        language: request.resolution.language,
        resolution: request.resolution,
        sourceTitle: request.sourceTitle
      })
    });
  },
  /* ── external dictionaries ────────────────────────────────────────────
     Two calls and two addresses. The list and an online lookup are ordinary JSON; the artifact
     itself is a static file read with byte ranges, so the reader can treat a dictionary the server
     holds exactly like one this device stored. */

  /** The catalogue as this owner sees it, and their chains. Owner-scoped, so it needs a session. */
  fetchModels(): Promise<ModelCatalogue> {
    return client.call<ModelCatalogue>("/models");
  },
  /**
   * Changes the chains named and returns the whole readout.
   *
   * `null` for a kind forgets the choice and returns it to the server's own order — without it, one
   * saved chain would be a one-way door, since unchecking everything is refused as an empty chain.
   * The answer is the server's, not this client's optimism, and it carries fresh availability.
   */
  saveModelSelection(chains: Record<string, ModelPair[] | null>): Promise<ModelCatalogue> {
    return client.call<ModelCatalogue>("/models/selection", {
      method: "PUT", body: JSON.stringify({ chains })
    });
  },

  imageSettings(): Promise<ImageSettings> {
    return client.call<ImageSettings>("/images/settings");
  },
  saveImageSettings(changes: Partial<Pick<ImageSettings, "drawEnabled" | "stylesOff" | "boostVariety" | "storyContinuity">>): Promise<ImageSettings> {
    return client.call<ImageSettings>("/images/settings", {
      method: "PUT", body: JSON.stringify(changes)
    });
  },

  /** One text call covering every sense of the word. Its own timeout — a model call, not a read. */
  /** One picture's row and the whole prompt it composes to, which is never stored. */
  imagePrompt(promptId: string): Promise<ImagePromptRow> {
    return client.call<ImagePromptRow>(`/images/prompts/${encodeURIComponent(promptId)}`);
  },

  /**
   * The owner's own file, as a raw body — one part, so no multipart and no dependency for it.
   *
   * Keyed by the sense rather than by a prompt: a picture you supply may be the first thing that
   * sense ever gets, and the prompt id is derived from the sense, so the server finds or mints the
   * row at the id it was always going to have.
   */
  async attachImage(
    senseId: string, deviceId: string, file: Blob, drawnBy: string | null = null
  ): Promise<ImagePromptRow> {
    return client.call<ImagePromptRow>(
      `/images/senses/${encodeURIComponent(senseId)}/picture`,
      {
        method: "PUT",
        body: file,
        headers: {
          "Content-Type": file.type || "application/octet-stream",
          "X-Acervo-Device": deviceId,
          /* Naming the model that drew it makes this a *restore* rather than a picture you chose:
             the row keeps its provenance and stays replaceable. Absent, it is your own file, which
             carries no model and is left alone by anything that draws. */
          ...(drawnBy ? { "X-Acervo-Drawn-By": drawnBy } : {})
        }
      },
      false,
      UPLOAD_TIMEOUT
    );
  },

  /** Remove the picture and rule the sense out. Not a tombstone — see `services/images.py`. */
  removeImage(promptId: string, deviceId: string): Promise<ImagePromptRow> {
    return client.call<ImagePromptRow>(
      `/images/prompts/${encodeURIComponent(promptId)}`,
      { method: "DELETE", headers: { "X-Acervo-Device": deviceId } }
    );
  },

  pronunciationSettings(): Promise<PronunciationSettings> {
    return client.call<PronunciationSettings>("/pronunciations/settings");
  },
  savePronunciationSettings(
    changes: Partial<{
      pregenerate: Partial<PronunciationPregenerate>;
      delivery: Partial<Record<PronunciationUse, PronunciationOrder>>;
      voices: PronunciationSettings["voices"];
      guideVoices: PronunciationSettings["guideVoices"];
    }>
  ): Promise<PronunciationSettings> {
    return client.call<PronunciationSettings>("/pronunciations/settings", {
      method: "PUT", body: JSON.stringify(changes)
    });
  },

  /**
   * The clip for one spoken field: the stored one while it is current, otherwise a new recording.
   * `again` records it anew, which is "Record again". One model call, with a model call's timeout.
   */
  pronounce(collection: string, id: string, deviceId: string, again = false): Promise<Pronunciation> {
    return client.call<Pronunciation>(
      `/pronunciations/${encodeURIComponent(collection)}/${encodeURIComponent(id)}`,
      { method: "POST", body: JSON.stringify({ deviceId, again }) },
      false,
      PRONOUNCE_TIMEOUT
    );
  },

  /** Read a selection aloud. Nothing is stored anywhere, the server included. */
  async utterance(text: string, language: string): Promise<Utterance> {
    const response = await client.bytes(
      "/pronunciations/utterance",
      { method: "POST", body: JSON.stringify({ text, language }) },
      PRONOUNCE_TIMEOUT
    );
    return { audio: await response.blob(), voice: response.headers.get("X-Acervo-Voice") || null };
  },

  /** Put back a clip a bundle carried, naming who recorded it. Refused if the words have changed. */
  restorePronunciation(
    collection: string, id: string, deviceId: string, audio: Blob,
    spoken: { text: string; providerId: string; modelId: string; voice: string | null; emotion: string | null }
  ): Promise<Pronunciation> {
    const query = new URLSearchParams({
      text: spoken.text, providerId: spoken.providerId, modelId: spoken.modelId,
      voice: spoken.voice ?? "", emotion: spoken.emotion ?? ""
    });
    return client.call<Pronunciation>(
      `/pronunciations/${encodeURIComponent(collection)}/${encodeURIComponent(id)}/audio?${query}`,
      {
        method: "PUT", body: audio,
        headers: { "Content-Type": audio.type || "application/octet-stream", "X-Acervo-Device": deviceId }
      },
      false,
      UPLOAD_TIMEOUT
    );
  },

  listDictionaries(): Promise<{ dictionaries: RemoteDictionary[] }> {
    return client.call<{ dictionaries: RemoteDictionary[] }>("/dictionaries");
  },
  lookupOnlineDictionary(source: string, word: string, language?: string): Promise<OnlineLookup> {
    const query = new URLSearchParams({ word });
    if (language) query.set("language", language);
    return client.call<OnlineLookup>(`/dictionaries/online/${encodeURIComponent(source)}?${query}`);
  },
  dictionaryFileUrl(id: string, extension: "dict" | "idx" | "json"): string {
    return client.fileUrl(DICTIONARY_PATH, `/${encodeURIComponent(id)}.${extension}`);
  },
  dictionaryHeaders(): Record<string, string> {
    return client.authHeaders();
  },

  /**
   * Where a picture lives. The route is behind bearer auth, so this URL cannot go in an `<img src>`
   * — `media.ts` fetches it with the token and hands the element a blob URL instead.
   */
  mediaFileUrl(reference: string): string {
    return client.fileUrl(MEDIA_PATH, `/${reference.split("/").map(encodeURIComponent).join("/")}`);
  },
  mediaHeaders(): Record<string, string> {
    return client.authHeaders();
  },

  /**
   * Where the corpus answers, through Acervo's own allow-listed proxy.
   *
   * A base URL and a header set rather than a method per route, because `clips.ts` hands both to
   * the *packaged* typed client — the one the retrieval repository ships and tests. Reimplementing
   * its fifteen methods here to gain Acervo's envelope would mean keeping a second copy of its
   * response types in two languages, and the proxy forwards the body verbatim so that it does not
   * have to.
   */
  speechBaseUrl(): string {
    return client.fileUrl(API_PATH, SPEECH_PATH);
  },
  speechHeaders(): Record<string, string> {
    return client.authHeaders();
  },

  clipSettings(): Promise<ClipSettings> {
    return client.call<ClipSettings>("/clips/settings");
  },
  saveClipSettings(
    changes: Partial<Pick<ClipSettings, "searchEnabled" | "selfContainedOnly">>
  ): Promise<ClipSettings> {
    return client.call<ClipSettings>("/clips/settings", {
      method: "PUT", body: JSON.stringify(changes)
    });
  },

  promptRules(): Promise<PromptRules> {
    return client.call<PromptRules>("/rules");
  },
  savePromptRules(rules: string): Promise<PromptRules> {
    return client.call<PromptRules>("/rules", { method: "PUT", body: JSON.stringify({ rules }) });
  },

  resetGraph(deviceId: string): Promise<ResetResponse> {
    return client.call<ResetResponse>("/graph/reset", {
      method: "POST",
      body: JSON.stringify({ schemaVersion: SCHEMA_VERSION, deviceId, confirm: "delete-all-words" })
    });
  }
};
