import {
  validateChanges, validateGraph, type GraphIndex,
  type Attestation, type AttestationInput, type Bed, type BedInput, type EntityKind, type Example, type ExampleInput,
  type ImagePrompt, type ImagePromptInput, type Lexeme, type LexemeInput, type Loop, type LoopInput,
  type LoopCue, type LoopItem, type LoopItemInput, type Pronunciation, type Sense, type SenseInput,
  type OwnedFields, type Story, type StoryInput, type StoryPart, type StoryPartInput,
  type StoryWord, type StoryWordInput,
  type StudyState, type StudyStateInput, type SyncFields, type Topic, type TopicInput,
  type Vocabulary, type VocabularyInput, type VocabularyGraph
} from "./domain";
import { createLocalDatabase, MemoryDatabase, RECORD_STORES, type LocalDatabase, type ReplicaMeta } from "./localDatabase";
import { newDeviceId, newId, nowInstant } from "./ids";
import { markReplicaRead, markReplicaSetAside, markStartup } from "./startup";
import type { ArticleDraft } from "./yaml";

/**
 * The shape of the records this device stores. **Any change to a replicated record's shape bumps
 * it**, so a copy stored under the old shape is wiped and pulled again rather than refused at every
 * open. 16: a story part's passages became one recording each (`audioRef`, `audioMime`,
 * `durationSeconds`) instead of times into one joined file, and nothing bumped this. 17: `beds`,
 * the loop music the owner keeps. 18: an attestation's `photoRef` and `photoRegion`.
 */
export const LOCAL_SCHEMA_VERSION = 20;

export const EMPTY_GRAPH = (): VocabularyGraph => ({
  vocabularies: [], topics: [], lexemes: [], senses: [], attestations: [], examples: [], imagePrompts: [],
  pronunciations: [], studyStates: [], loops: [], loopItems: [], loopCues: [], stories: [], storyParts: [],
  storyWords: [], beds: []
});

export type Entity = Vocabulary | Topic | Lexeme | Sense | Attestation | Example | ImagePrompt | Pronunciation | StudyState | Loop | LoopItem | LoopCue | Story | StoryPart | StoryWord | Bed;
type EntityInput = VocabularyInput | TopicInput | LexemeInput | SenseInput | AttestationInput | ExampleInput | ImagePromptInput | StudyStateInput | LoopInput | LoopItemInput | StoryInput | StoryPartInput | StoryWordInput | BedInput;

/** What the server returns for a batch of applied records. */
export interface RemoteWrite {
  records: Partial<VocabularyGraph>;
  cursor: number;
  datasetId: string;
}

/**
 * The write half of the server transport. `sync.ts` owns the routes and attaches this; the
 * repository never reaches the network itself, and the interface never reaches past the repository.
 */
/**
 * `enrich: false` asks the server not to queue enrichment for words this write creates. Only a
 * bundle import says so, because it restores the bundle's pictures first and asks afterwards.
 */
export interface WriteOptions {
  enrich?: boolean;
}

export interface ArticleWrite extends RemoteWrite {
  lexemeId: string;
  /** The server job enriching what the save created, or null when it created nothing to enrich. */
  jobId: string | null;
}

export interface RemoteGraph {
  push(changes: Partial<VocabularyGraph>, options?: WriteOptions): Promise<RemoteWrite>;
  saveArticle(
    draft: ArticleDraft, minted: ReadonlySet<string>, base: Record<string, number>, options?: WriteOptions
  ): Promise<ArticleWrite>;
}

export interface ReplicaSnapshot extends VocabularyGraph {
  ready: boolean;
  ownerId: string;
  deviceId: string;
  datasetId: string;
  cursor: number;
  lastPulledAt: string | null;
  lastWroteAt: string | null;
  persistent: boolean;
}

/** The replica's bookkeeping without its records: what a caller reads when it needs no graph. */
export type ReplicaState = Omit<ReplicaSnapshot, keyof VocabularyGraph>;

export interface AcervoRepository {
  load(ownerId: string): Promise<void>;
  clear(): Promise<void>;
  /**
   * The replica as it stands, **shared rather than copied**: the same object until something
   * changes, so a repaint with nothing new costs nothing and every memo keyed on it survives. It
   * must never be mutated — records are replaced, never edited in place (frozen outside production,
   * so a test catches a caller that tries).
   */
  snapshot(): ReplicaSnapshot;
  /** `snapshot()` without the records, for a caller that wants the cursor or the device id. */
  state(): ReplicaState;
  attachRemote(remote: RemoteGraph | null): void;
  applyRemote(changes: Partial<VocabularyGraph>, cursor: number, datasetId: string): Promise<number>;
  writeGraph(changes: Partial<VocabularyGraph>): Promise<void>;
  saveArticle(draft: ArticleDraft, minted?: ReadonlySet<string>, options?: WriteOptions): Promise<string>;
  saveVocabulary(input: VocabularyInput, id?: string): Promise<Vocabulary>;
  saveTopic(input: TopicInput, id?: string): Promise<Topic>;
  saveLexeme(input: LexemeInput, id?: string): Promise<Lexeme>;
  saveSense(input: SenseInput, id?: string): Promise<Sense>;
  saveAttestation(input: AttestationInput, id?: string): Promise<Attestation>;
  saveExample(input: ExampleInput, id?: string): Promise<Example>;
  saveImagePrompt(input: ImagePromptInput, id?: string): Promise<ImagePrompt>;
  saveStudyState(input: StudyStateInput, id?: string): Promise<StudyState>;
  saveLoop(input: LoopInput, id?: string): Promise<Loop>;
  saveBed(input: BedInput, id?: string): Promise<Bed>;
  /** Takes the named words out of the Inbox in one write, and says how many moved. */
  fileWords(ids: readonly string[]): Promise<number>;
  delete(kind: EntityKind, id: string): Promise<void>;
}

const EMPTY_META = (): ReplicaMeta => ({
  ownerId: "", deviceId: "", schemaVersion: LOCAL_SCHEMA_VERSION,
  datasetId: "", cursor: 0, lastPulledAt: null, lastWroteAt: null
});

/** Why a stored replica cannot be trusted as it is, or null when it can. */
function refusalOf(graph: VocabularyGraph, ownerId: string): string | null {
  try {
    validateGraph(graph);
  } catch (error) {
    return error instanceof Error ? error.message : String(error);
  }
  const foreign = RECORD_STORES.some((kind) => (graph[kind] as Entity[]).some((record) => record.ownerId !== ownerId));
  return foreign ? "Replica records do not belong to the authenticated owner." : null;
}

/** Frozen where a mutation can be caught by a test; production skips the walk. */
const FREEZE = import.meta.env.DEV || import.meta.env.MODE === "test";

function frozen<T>(value: T): T {
  if (!FREEZE || value === null || typeof value !== "object" || Object.isFrozen(value)) return value;
  Object.values(value as object).forEach((inner) => frozen(inner));
  return Object.freeze(value);
}

function frozenGraph(graph: VocabularyGraph): VocabularyGraph {
  if (FREEZE) RECORD_STORES.forEach((kind) => { (graph[kind] as Entity[]).forEach(frozen); Object.freeze(graph[kind]); });
  return graph;
}

export class LocalAcervoRepository implements AcervoRepository {
  /**
   * Replaced, never edited: a merge builds new arrays for the collections it touches and shares the
   * rest. That is what lets `snapshot()` hand the graph out without copying it — a whole-replica
   * `structuredClone` cost 29 ms on a laptop for ten thousand records, and a save or a pull used to
   * take six of them.
   */
  private graph = EMPTY_GRAPH();
  /** Where each record sits in its collection, per kind; built on first use and kept in step. */
  private positions = new Map<EntityKind, Map<string, number>>();
  private cached: ReplicaSnapshot | null = null;
  private meta: ReplicaMeta = EMPTY_META();
  private ready = false;
  private persistent = true;
  private lastInstant = "";
  private remote: RemoteGraph | null = null;
  private queue: Promise<unknown> = Promise.resolve();

  constructor(private database: LocalDatabase = createLocalDatabase()) {}

  async load(ownerId: string): Promise<void> {
    try {
      await this.open(ownerId);
    } catch {
      // Only for a device whose storage cannot be opened, read or written at all — a private
      // window, a refused quota. A stored copy that is merely out of date is wiped in `open`.
      this.database = new MemoryDatabase();
      this.persistent = false;
      await this.open(ownerId);
    }
  }

  private async open(ownerId: string) {
    markStartup("readStart");
    const contents = await this.database.read();
    markReplicaRead(RECORD_STORES.reduce((count, store) => count + (contents[store]?.length ?? 0), 0));
    const deviceId = contents.meta.deviceId || newDeviceId();
    const current = contents.meta.ownerId === ownerId && contents.meta.schemaVersion === LOCAL_SCHEMA_VERSION;
    const graph: VocabularyGraph | null = current ? {
      vocabularies: contents.vocabularies,
      topics: contents.topics,
      lexemes: contents.lexemes,
      senses: contents.senses,
      attestations: contents.attestations,
      examples: contents.examples,
      imagePrompts: contents.imagePrompts,
      pronunciations: contents.pronunciations,
      studyStates: contents.studyStates,
      loops: contents.loops,
      loopItems: contents.loopItems,
      loopCues: contents.loopCues,
      stories: contents.stories,
      storyParts: contents.storyParts,
      storyWords: contents.storyWords,
      beds: contents.beds
    } : null;
    const refusal = graph ? refusalOf(graph, ownerId) : null;
    if (!graph || refusal) {
      // A stored copy the checks refuse is one written under a record shape the code has since
      // moved on from — a change that should have bumped `LOCAL_SCHEMA_VERSION` and did not. It is
      // wiped and pulled again into storage, like one written under another schema. It used to
      // throw here, and `load` then kept the vocabulary in memory instead: the copy on the device
      // was never repaired, so every cold start re-downloaded everything and showed no words
      // while it did.
      if (refusal) markReplicaSetAside(refusal);
      await this.database.wipe();
      this.install(EMPTY_GRAPH());
      this.meta = { ...EMPTY_META(), ownerId, deviceId };
      await this.database.write({ meta: this.meta });
    } else {
      frozenGraph(graph);
      this.install(graph);
      this.meta = {
        ...EMPTY_META(),
        ownerId,
        deviceId,
        datasetId: contents.meta.datasetId ?? "",
        cursor: contents.meta.cursor ?? 0,
        lastPulledAt: contents.meta.lastPulledAt ?? null,
        lastWroteAt: contents.meta.lastWroteAt ?? null
      };
    }
    markStartup("checked");
    this.ready = true;
    this.cached = null;
  }

  async clear(): Promise<void> {
    await this.database.wipe();
    this.install(EMPTY_GRAPH());
    this.meta = EMPTY_META();
    this.ready = false;
    this.cached = null;
  }

  private install(graph: VocabularyGraph): void {
    this.graph = graph;
    this.positions = new Map();
    this.cached = null;
  }

  snapshot(): ReplicaSnapshot {
    this.cached ??= { ...this.graph, ...this.state() };
    return this.cached;
  }

  state(): ReplicaState {
    return {
      ready: this.ready, ownerId: this.meta.ownerId,
      deviceId: this.meta.deviceId, datasetId: this.meta.datasetId, cursor: this.meta.cursor,
      lastPulledAt: this.meta.lastPulledAt, lastWroteAt: this.meta.lastWroteAt,
      persistent: this.persistent
    };
  }

  private positionsOf(kind: EntityKind): Map<string, number> {
    let found = this.positions.get(kind);
    if (!found) {
      found = new Map((this.graph[kind] as Entity[]).map((record, at) => [record.id, at]));
      this.positions.set(kind, found);
    }
    return found;
  }

  private held(kind: EntityKind, id: string): Entity | undefined {
    const at = this.positionsOf(kind).get(id);
    return at === undefined ? undefined : (this.graph[kind] as Entity[])[at];
  }

  /** The graph as `validateChanges` looks things up in it, through the positions already kept. */
  private get index(): GraphIndex {
    return { get: (kind, id) => this.held(kind, id) as never };
  }

  attachRemote(remote: RemoteGraph | null): void {
    this.remote = remote;
  }

  /**
   * Serialises everything that reads and then rewrites the graph. A pull and a write each take a
   * copy on entry and install it on exit, so interleaving them would silently drop whichever
   * finished first. Both round trips are seconds at worst, and neither is on a render path.
   */
  private serialize<T>(work: () => Promise<T>): Promise<T> {
    const result = this.queue.then(work, work);
    this.queue = result.catch(() => undefined);
    return result;
  }

  /**
   * Applies a delta the server sent, newest wins by revision. Only the server mints revisions, so
   * they totally order the versions of a record — there is no timestamp comparison and no merge.
   * Records and the cursor that covers them land in one transaction. Returns how many were applied.
   */
  applyRemote(changes: Partial<VocabularyGraph>, cursor: number, datasetId: string): Promise<number> {
    return this.serialize(() => this.merge(changes, cursor, datasetId));
  }

  private async merge(
    changes: Partial<VocabularyGraph>, cursor: number, datasetId: string, wroteAt?: string
  ): Promise<number> {
    if (!this.ready) throw new Error("Load the Acervo repository before applying remote records.");
    const write: Partial<VocabularyGraph> = {};
    let applied = 0;
    RECORD_STORES.forEach((kind) => {
      const incoming = changes[kind] as Entity[] | undefined;
      if (!incoming?.length) return;
      const accepted = new Map<string, Entity>();
      incoming.forEach((record) => {
        if (record.ownerId !== this.meta.ownerId) throw new Error("Cannot apply a record owned by another account.");
        const current = accepted.get(record.id) ?? this.held(kind, record.id);
        // A reply that lost a race with a newer version of the same record must not undo it.
        if (current && record.revision <= current.revision) return;
        accepted.set(record.id, frozen(structuredClone(record)));
      });
      if (!accepted.size) return;
      write[kind] = [...accepted.values()] as never;
      applied += accepted.size;
    });
    validateChanges(this.graph, write, this.index);
    // A push is not a pull: only a pull moves the "last received" stamp.
    const meta: Partial<ReplicaMeta> = wroteAt
      ? { cursor, datasetId, lastWroteAt: wroteAt }
      : { cursor, datasetId, lastPulledAt: this.instant() };
    await this.database.write({ ...write, meta });
    this.lay(write);
    this.meta = { ...this.meta, ...meta } as ReplicaMeta;
    this.cached = null;
    return applied;
  }

  /** Replace or append each record, copying only the collections that change. */
  private lay(records: Partial<VocabularyGraph>): void {
    const next = { ...this.graph };
    (Object.keys(records) as EntityKind[]).forEach((kind) => {
      const list = (this.graph[kind] as Entity[]).slice();
      const positions = this.positionsOf(kind);
      (records[kind] as Entity[]).forEach((record) => {
        const at = positions.get(record.id);
        if (at === undefined) { positions.set(record.id, list.length); list.push(record); } else list[at] = record;
      });
      (next as Record<string, unknown>)[kind] = FREEZE ? Object.freeze(list) : list;
    });
    this.graph = next;
  }

  private instant(): string {
    const current = nowInstant();
    const next = current > this.lastInstant ? current : new Date(Date.parse(this.lastInstant) + 1).toISOString();
    this.lastInstant = next;
    return next;
  }

  private stamp(existing?: Entity): SyncFields & OwnedFields {
    const editedAt = this.instant();
    return {
      ownerId: this.meta.ownerId,
      deleted: false,
      createdAt: existing?.createdAt ?? editedAt,
      editedAt,
      editedBy: this.meta.deviceId,
      // The revision the edit is based on. The server refuses the write if it has moved on, and
      // replaces this with the one it allocates.
      revision: existing?.revision ?? 0
    };
  }

  /**
   * Sends a change set to the server and stores what comes back. Nothing local moves until the
   * server has accepted it: offline, this throws and the replica is exactly as it was.
   */
  private commit(changes: Partial<VocabularyGraph>, options?: WriteOptions): Promise<void> {
    return this.serialize(() => this.send(changes, options));
  }

  private async send(changes: Partial<VocabularyGraph>, options?: WriteOptions): Promise<void> {
    if (!this.ready) throw new Error("Load the Acervo repository before writing.");
    (Object.values(changes) as Entity[][]).forEach((records) => records?.forEach((record) => {
      if (record.ownerId !== this.meta.ownerId) throw new Error("Cannot write a record owned by another account.");
    }));
    validateChanges(this.graph, changes, this.index);
    if (!this.remote) {
      throw new Error("Acervo is not connected to the server, so this change was not saved.");
    }
    const result = await this.remote.push(changes, options);
    // One transaction for the records the server blessed and the stamp that says we wrote.
    await this.merge(result.records, result.cursor, result.datasetId, this.instant());
  }

  writeGraph(changes: Partial<VocabularyGraph>): Promise<void> {
    return this.commit(changes);
  }

  private async save(kind: EntityKind, input: EntityInput, requestedId?: string): Promise<Entity> {
    if (!this.ready) throw new Error("Load the Acervo repository before writing.");
    const existing = requestedId ? this.held(kind, requestedId) : undefined;
    const record = { ...input, id: existing?.id ?? requestedId ?? newId(), ...this.stamp(existing) } as Entity;
    await this.commit({ [kind]: [record] });
    return this.held(kind, record.id) ?? record;
  }

  saveVocabulary(input: VocabularyInput, id?: string) { return this.save("vocabularies", input, id) as Promise<Vocabulary>; }
  saveTopic(input: TopicInput, id?: string) { return this.save("topics", input, id) as Promise<Topic>; }
  saveLexeme(input: LexemeInput, id?: string) { return this.save("lexemes", input, id) as Promise<Lexeme>; }
  saveSense(input: SenseInput, id?: string) { return this.save("senses", input, id) as Promise<Sense>; }
  saveAttestation(input: AttestationInput, id?: string) { return this.save("attestations", input, id) as Promise<Attestation>; }
  saveExample(input: ExampleInput, id?: string) { return this.save("examples", input, id) as Promise<Example>; }
  saveImagePrompt(input: ImagePromptInput, id?: string) { return this.save("imagePrompts", input, id) as Promise<ImagePrompt>; }
  saveStudyState(input: StudyStateInput, id?: string) { return this.save("studyStates", input, id) as Promise<StudyState>; }
  /**
   * A loop is *rendered* by the server, so this writes the row rather than the track: the position
   * a reorder gave it, and — from the job — the reference and the bed that produced it. Online-only
   * and loud when it fails, like every other write.
   */
  saveLoop(input: LoopInput, id?: string) { return this.save("loops", input, id) as Promise<Loop>; }
  /** Keep a loop's music as a favourite. Unkeeping it is `delete("beds", id)`, a tombstone. */
  saveBed(input: BedInput, id?: string) { return this.save("beds", input, id) as Promise<Bed>; }

  /**
   * Takes words out of the Inbox, as one write.
   *
   * One change set rather than a `saveLexeme` each, because the case this exists for is emptying an
   * Inbox a whole imported vocabulary landed in: a few hundred round trips is minutes on a tablet,
   * and half of them landing is a state nothing else here can produce.
   *
   * A word that is not in the Inbox is left out rather than rewritten, so filing twice costs one
   * empty call and never a revision. The count is what was actually changed.
   */
  async fileWords(ids: readonly string[]): Promise<number> {
    if (!this.ready) throw new Error("Load the Acervo repository before writing.");
    const wanted = new Set(ids);
    const filing = this.graph.lexemes
      .filter((lexeme) => wanted.has(lexeme.id) && !lexeme.deleted && lexeme.status === "inbox")
      .map((lexeme) => ({ ...lexeme, status: "active", ...this.stamp(lexeme) } as Lexeme));
    if (!filing.length) return 0;
    await this.commit({ lexemes: filing });
    return filing.length;
  }

  /**
   * Saves a whole article, edited as YAML, in one write — on the server.
   *
   * The document goes as the draft `parseArticle` produced, and `POST /articles` works out what it
   * means for the stored entry: a record carrying an id is the one it names, a record without one is
   * new, and a stored record the document no longer mentions is tombstoned. Nothing is recreated, so
   * the Anki note join, the image seed and `createdAt` survive a fixed typo. One round trip, all or
   * nothing, and nothing local moves until the server has accepted it.
   *
   * `base` is what this replica holds of the entry, at the revisions it holds them: the server states
   * those revisions, so an edit made from a stale copy is refused, and it tombstones only records
   * this device could have seen.
   *
   * `minted` names ids this save is *creating* rather than naming, and is empty for every caller but
   * one: a chat proposal that adds an example drawn from a sentence you just supplied needs both
   * records in one save. The exception is an **argument**, not a field in the document, so a
   * hand-typed document cannot claim it.
   */
  async saveArticle(
    draft: ArticleDraft, minted: ReadonlySet<string> = new Set(), options?: WriteOptions
  ): Promise<string> {
    return this.serialize(async () => {
      if (!this.ready) throw new Error("Load the Acervo repository before writing.");
      if (!this.remote) {
        throw new Error("Acervo is not connected to the server, so this change was not saved.");
      }
      const result = await this.remote.saveArticle(draft, minted, this.baseOf(draft.id), options);
      await this.merge(result.records, result.cursor, result.datasetId, this.instant());
      return result.lexemeId;
    });
  }

  /** Every record of one entry this replica holds, at the revision it holds it. */
  private baseOf(lexemeId: string | null): Record<string, number> {
    if (!lexemeId) return {};
    const graph = this.graph;
    const senses = new Set(graph.senses.filter((one) => one.lexemeId === lexemeId).map((one) => one.id));
    const records: Entity[] = [
      ...graph.lexemes.filter((one) => one.id === lexemeId),
      ...graph.senses.filter((one) => one.lexemeId === lexemeId),
      ...graph.examples.filter((one) => senses.has(one.senseId)),
      ...graph.attestations.filter((one) => one.lexemeId === lexemeId),
      ...graph.imagePrompts.filter((one) => one.lexemeId === lexemeId),
      ...graph.pronunciations.filter((one) => one.lexemeId === lexemeId)
    ];
    return Object.fromEntries(records.map((record) => [record.id, record.revision]));
  }

  async delete(kind: EntityKind, id: string): Promise<void> {
    if (!this.ready) throw new Error("Load the Acervo repository before writing.");
    const changed: Partial<VocabularyGraph> = {};
    const change = <T extends Entity>(store: EntityKind, value: T) => {
      const list = (changed[store] ?? []) as T[];
      list.push(value);
      changed[store] = list as never;
    };
    const tombstone = <T extends Entity>(store: EntityKind, record: T) => {
      change(store, { ...record, ...this.stamp(record), deleted: true } as T);
    };
    const target = this.held(kind, id);
    if (!target || target.deleted) return;
    tombstone(kind, target);
    if (kind === "topics") {
      this.graph.lexemes
        .filter((record) => record.topicIds.includes(id) && !record.deleted)
        .forEach((record) => change("lexemes", {
          ...record, ...this.stamp(record), topicIds: record.topicIds.filter((topicId) => topicId !== id)
        }));
    } else if (kind === "lexemes") {
      const senseIds = new Set(this.graph.senses.filter((record) => record.lexemeId === id).map((record) => record.id));
      this.graph.senses.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("senses", record));
      this.graph.attestations.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("attestations", record));
      this.graph.examples.filter((record) => senseIds.has(record.senseId) && !record.deleted).forEach((record) => tombstone("examples", record));
      this.graph.imagePrompts.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("imagePrompts", record));
      this.graph.pronunciations.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("pronunciations", record));
      this.graph.studyStates.filter((record) => record.lexemeId === id && !record.deleted).forEach((record) => tombstone("studyStates", record));
      // `loopItems` and `storyWords` are deliberately absent. A loop is a recording and a story is
      // written: both stay truthful about what they said, and their rows simply point at a
      // tombstone from here on.
    } else if (kind === "loops") {
      // A loop's items and lines go with it, and nothing else does: the words it named are untouched.
      //
      // The interface deletes a loop through `DELETE /loops/{id}` rather than here, because the
      // track has to go with the rows and only the server can unlink it. This branch stays so the
      // cascade is the same wherever it is written from — but a deletion that comes through it
      // leaves megabytes on the server naming nothing.
      this.graph.loopItems.filter((record) => record.loopId === id && !record.deleted).forEach((record) => tombstone("loopItems", record));
      this.graph.loopCues.filter((record) => record.loopId === id && !record.deleted).forEach((record) => tombstone("loopCues", record));
    } else if (kind === "stories") {
      // A story's parts and words go with it, and nothing else does: the words it taught are
      // untouched. Deleted through `DELETE /stories/{id}` rather than here for the reason a loop
      // is — the pictures have to go with the rows, and only the server can unlink them.
      this.graph.storyParts.filter((record) => record.storyId === id && !record.deleted).forEach((record) => tombstone("storyParts", record));
      this.graph.storyWords.filter((record) => record.storyId === id && !record.deleted).forEach((record) => tombstone("storyWords", record));
    } else if (kind === "senses") {
      this.graph.examples.filter((record) => record.senseId === id && !record.deleted).forEach((record) => tombstone("examples", record));
      this.graph.imagePrompts.filter((record) => record.senseId === id && !record.deleted).forEach((record) => tombstone("imagePrompts", record));
      const examples = new Set(this.graph.examples.filter((record) => record.senseId === id).map((record) => record.id));
      this.graph.pronunciations
        .filter((record) => !record.deleted && ((record.targetKind === "sense" && record.targetId === id)
          || (record.targetKind === "example" && examples.has(record.targetId))))
        .forEach((record) => tombstone("pronunciations", record));
    }
    await this.commit(changed);
  }
}

export const repository: AcervoRepository = new LocalAcervoRepository();
