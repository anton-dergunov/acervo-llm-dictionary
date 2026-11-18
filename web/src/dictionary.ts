/**
 * Reading a compiled external dictionary.
 *
 * The format is `src/vocabgen/dictionaries/container.py`, described once there and once here; a
 * change to either is a change to both. A lookup is a binary search over the sidecar index and one
 * DEFLATE frame decoded — about 65 KiB transient, which is the number a phone actually cares about.
 *
 * Everything reads through a `ByteSource`, so the same code serves a dictionary stored on this
 * device and one that only the server holds: locally that is `blob.slice`, remotely an HTTP Range
 * request against the artifact the server serves as a static file. That is why there is no
 * server-side lookup route — it would be this file implemented a second time, in another language.
 *
 * What stays resident per open dictionary is the header, the frame table and the restart table:
 * a few hundred KiB even for the whole Spanish Wiktionary. The key bytes and the per-entry payload
 * lengths are deliberately *not* held — together they are megabytes, which does not survive the ten
 * dictionaries per language this is meant to support.
 */

import { inflateSync } from "fflate";

const MAGIC = 0x41435644; // "ACVD"
const FORMAT_VERSION = 1;
/** Frames decoded recently. Small on purpose: the point of framing is not to hold the dictionary. */
const FRAME_CACHE = 4;
/** Restart keys remembered between lookups, so a repeated search does not re-read the same probes. */
const RESTART_KEY_CACHE = 512;

export type DictionaryTier = "fields" | "html";

/** One article. Render-only: `posLabel` is the source's own word and is displayed as it stands. */
export interface DictionaryArticle {
  headword: string;
  lemma?: string;
  language?: string;
  definitionLang?: string;
  ipa?: string;
  /** Every transcription the source gives, `ipa` first, when there is more than one (one per variety). */
  ipas?: string[];
  reading?: string;
  pos?: string;
  posLabel?: string;
  register?: string;
  /** A noun's genders, in Acervo's values; several when homographs differ (French `livre`). */
  genders?: string[];
  senses: { definition: string; definitionLang?: string; domain?: string;
            examples?: { text: string; textLang?: string; translation?: string; translationLang?: string }[] }[];
}

export interface DictionaryEntry {
  dictionaryId: string;
  word: string;
  tier: DictionaryTier;
  /** Present for the `fields` tier. A headword can hold several articles — 行 is háng and xíng. */
  articles?: DictionaryArticle[];
  /** Present for the `html` tier: a display fragment, to be sanitised where it is rendered. */
  html?: string;
}

export interface ByteSource {
  readonly size: number;
  read(offset: number, length: number): Promise<Uint8Array>;
}

export function blobSource(blob: Blob): ByteSource {
  return {
    size: blob.size,
    async read(offset, length) {
      if (length <= 0) return new Uint8Array(0);
      return new Uint8Array(await blob.slice(offset, offset + length).arrayBuffer());
    }
  };
}

/**
 * A dictionary this device does not hold, read over the network from the server that does.
 *
 * This is the one place Acervo reads through the network on purpose. It does not contradict the
 * offline-first rule: an external dictionary is not the replica, so a failure here degrades a
 * reference surface rather than losing anything.
 */
export function rangeSource(url: string, size: number, headers: HeadersInit = {}): ByteSource {
  return {
    size,
    async read(offset, length) {
      if (length <= 0) return new Uint8Array(0);
      const response = await fetch(url, {
        headers: { ...headers, Range: `bytes=${offset}-${offset + length - 1}` },
        cache: "no-store"
      });
      if (!response.ok) throw new Error(`The dictionary could not be read from the server (${response.status}).`);
      return new Uint8Array(await response.arrayBuffer());
    }
  };
}

/* ── varints ─────────────────────────────────────────────────────────────
   LEB128, unsigned, exactly as `container.py` writes them. `cursor` is carried in an object because
   every read advances it and JavaScript has no out-parameters. */

interface Cursor { at: number }

function varint(data: Uint8Array, cursor: Cursor): number {
  let value = 0;
  let shift = 0;
  for (;;) {
    const byte = data[cursor.at++];
    value += (byte & 0x7f) * 2 ** shift;    // not `<<`: shifts are 32-bit and offsets exceed that
    if ((byte & 0x80) === 0) return value;
    shift += 7;
  }
}

function varints(data: Uint8Array): number[] {
  const cursor: Cursor = { at: 0 };
  const values: number[] = [];
  while (cursor.at < data.length) values.push(varint(data, cursor));
  return values;
}

/**
 * Byte-wise comparison, which is the order the index is built in.
 *
 * Deliberately not `String.prototype.localeCompare` and deliberately not `<` on strings: JavaScript
 * compares UTF-16 code units, and above the BMP that disagrees with UTF-8 byte order. A search in
 * the wrong order finds nothing for exactly the rarest characters, which is the kind of bug that
 * survives casual testing.
 */
function compareBytes(left: Uint8Array, right: Uint8Array): number {
  const limit = Math.min(left.length, right.length);
  for (let index = 0; index < limit; index += 1) {
    if (left[index] !== right[index]) return left[index] < right[index] ? -1 : 1;
  }
  return left.length === right.length ? 0 : left.length < right.length ? -1 : 1;
}

function startsWith(key: Uint8Array, prefix: Uint8Array): boolean {
  if (key.length < prefix.length) return false;
  for (let index = 0; index < prefix.length; index += 1) {
    if (key[index] !== prefix[index]) return false;
  }
  return true;
}

const encoder = new TextEncoder();
const decoder = new TextDecoder();

/** The spelling the compiler also stores as an alias, so an accented or capitalised word is found. */
function folded(word: string): string {
  return word.normalize("NFC").toLowerCase();
}

interface Header {
  tier: DictionaryTier;
  frameSize: number;
  restartInterval: number;
  entryCount: number;
  keyCount: number;
  frames: { start: number; length: number };
  frameOffsets: { start: number; length: number };
  payloads: { start: number; length: number };
  restarts: { start: number; length: number };
  keys: { start: number; length: number };
}

function parseHeader(data: Uint8Array): Header {
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  if (view.getUint32(0) !== MAGIC) throw new Error("This is not an Acervo dictionary index.");
  const version = data[4];
  if (version !== FORMAT_VERSION) {
    throw new Error(`This dictionary was built for format ${version}; this version reads ${FORMAT_VERSION}. Install it again.`);
  }
  const tier: DictionaryTier = data[5] === 1 ? "html" : "fields";
  const frameSize = view.getUint16(6, true);
  const restartInterval = view.getUint16(8, true);
  const cursor: Cursor = { at: 10 };
  const entryCount = varint(data, cursor);
  const keyCount = varint(data, cursor);
  const lengths = [varint(data, cursor), varint(data, cursor), varint(data, cursor),
                   varint(data, cursor), varint(data, cursor)];
  let start = cursor.at;
  const [frames, frameOffsets, payloads, restarts, keys] = lengths.map((length) => {
    const section = { start, length };
    start += length;
    return section;
  });
  return { tier, frameSize, restartInterval, entryCount, keyCount,
           frames, frameOffsets, payloads, restarts, keys };
}

/** Where a key's entry sits: which frame, how far into it, and how long. */
interface Location { frame: number; offset: number; length: number }

export class Dictionary {
  private constructor(
    readonly id: string,
    private readonly blob: ByteSource,
    private readonly index: ByteSource,
    private readonly header: Header,
    /** Compressed length of every frame, and where each starts in the blob. */
    private readonly frameLengths: number[],
    private readonly frameStarts: number[],
    /** Byte offset into the payload-length section for each frame's first entry. */
    private readonly payloadOffsets: number[],
    /** Byte offset into the key section of every restart point. */
    private readonly restarts: number[]
  ) {}

  get tier(): DictionaryTier { return this.header.tier; }
  get entryCount(): number { return this.header.entryCount; }
  /** Roughly what this dictionary keeps in memory while it is open, for the Settings pane. */
  get residentBytes(): number {
    return (this.frameLengths.length * 2 + this.payloadOffsets.length + this.restarts.length) * 8;
  }

  private frames = new Map<number, Uint8Array>();

  static async open(id: string, blob: ByteSource, index: ByteSource): Promise<Dictionary> {
    // 64 bytes covers the fixed fields and seven varints with room to spare.
    const header = parseHeader(await index.read(0, Math.min(64, index.size)));
    const [frameBytes, offsetBytes, restartBytes] = await Promise.all([
      index.read(header.frames.start, header.frames.length),
      index.read(header.frameOffsets.start, header.frameOffsets.length),
      index.read(header.restarts.start, header.restarts.length)
    ]);
    const frameLengths = varints(frameBytes);
    const frameStarts: number[] = [];
    let running = 0;
    for (const length of frameLengths) {
      frameStarts.push(running);
      running += length;
    }
    return new Dictionary(id, blob, index, header, frameLengths, frameStarts,
                          varints(offsetBytes), varints(restartBytes));
  }

  async lookup(word: string): Promise<DictionaryEntry | null> {
    const trimmed = word.trim();
    if (!trimmed) return null;
    let location = await this.locate(encoder.encode(trimmed));
    if (!location) {
      const alternative = folded(trimmed);
      if (alternative !== trimmed) location = await this.locate(encoder.encode(alternative));
    }
    if (!location) return null;
    const frame = await this.frame(location.frame);
    const payload = frame.subarray(location.offset, location.offset + location.length);
    const text = decoder.decode(payload);
    return this.header.tier === "html"
      ? { dictionaryId: this.id, word: trimmed, tier: "html", html: text }
      : { dictionaryId: this.id, word: trimmed, tier: "fields", articles: JSON.parse(text) as DictionaryArticle[] };
  }

  /**
   * Headwords beginning with `prefix`, in order. Touches only the key section — no payload is
   * decoded, so listing candidates costs a fraction of reading one of them.
   */
  async search(prefix: string, limit = 25): Promise<string[]> {
    const typed = prefix.trim().normalize("NFC");
    if (!typed || !this.restarts.length) return [];
    /* Case is not a filter anyone meant to apply. The compiler stores a case-folded alias beside
       every key that needs one, and `lookup` already falls back to it — but a *prefix* scan walks
       the sorted key bytes, so `Mejor` looked for keys beginning `Mejor` and found none, while
       `mejor` found the word. Scanning both spellings is what makes typing `tHiS` work as well as
       typing `this`, and it costs a second binary search only when the two actually differ. */
    const spellings = [typed];
    const lowered = folded(typed);
    if (lowered !== typed) spellings.push(lowered);

    const found: string[] = [];
    const seenWord = new Set<string>();
    // By entry, not only by spelling: a key and its folded alias are one word, and returning both
    // would list it twice.
    const seenEntry = new Set<number>();
    for (const spelling of spellings) {
      // Each spelling gets the full budget rather than a share of one. Letting the first fill the
      // list is how `Casa` came back as `Casa Blanca, Casablanca, Casadevante…` and never `casa` —
      // which is what a phone's autocapitalise turns every first word into.
      await this.scanPrefix(encoder.encode(spelling), limit, found, seenWord, seenEntry);
    }
    if (found.length <= limit) return found;

    /* Trimming the pool, not the scan. Whatever survives, the word that was actually typed has to:
       it is the answer to the question, and the alphabet is no reason to lose it. */
    const wanted = lowered;
    return found
      .map((word, position) => ({ word, position }))
      .sort((left, right) =>
        Number(folded(right.word) === wanted) - Number(folded(left.word) === wanted)
        || left.word.length - right.word.length
        || left.position - right.position)
      .slice(0, limit)
      .map((candidate) => candidate.word);
  }

  /** Walks the sorted keys from `target` while they still begin with it. */
  private async scanPrefix(
    target: Uint8Array, limit: number,
    found: string[], seenWord: Set<string>, seenEntry: Set<number>
  ): Promise<void> {
    if (!target.length) return;
    for (let bucket = await this.floorRestart(target); bucket < this.restarts.length; bucket += 1) {
      for (const { key, entry } of await this.bucket(bucket)) {
        if (!startsWith(key, target)) {
          // The keys are sorted, so once we are past the prefix there is nothing further to find.
          if (compareBytes(key, target) > 0) return;
          continue;
        }
        const word = decoder.decode(key);
        if (!seenWord.has(word) && !seenEntry.has(entry)) {
          seenWord.add(word);
          seenEntry.add(entry);
          found.push(word);
          if (found.length >= limit) return;
        }
      }
    }
  }

  private async locate(target: Uint8Array): Promise<Location | null> {
    if (!this.restarts.length) return null;
    const bucket = await this.floorRestart(target);
    for (const { key, entry } of await this.bucket(bucket)) {
      const order = compareBytes(key, target);
      if (order === 0) return this.locationOf(entry);
      if (order > 0) return null;
    }
    return null;
  }

  /**
   * The last restart point whose key is not greater than `target`.
   *
   * A binary search over *reads*: the restart keys are on disk, so each probe fetches one. That is
   * about 17 reads of a few hundred bytes for the largest dictionary — far cheaper than holding
   * megabytes of keys resident to avoid them.
   */
  private async floorRestart(target: Uint8Array): Promise<number> {
    let low = 0;
    let high = this.restarts.length - 1;
    while (low < high) {
      const middle = Math.ceil((low + high) / 2);
      if (compareBytes(await this.restartKey(middle), target) <= 0) low = middle;
      else high = middle - 1;
    }
    return low;
  }

  /** The whole key stored at a restart point. Front-coding is why every 16th one is stored whole. */
  private async restartKey(index: number): Promise<Uint8Array> {
    const cached = this.restartKeyCache.get(index);
    if (cached) return cached;
    const start = this.header.keys.start + this.restarts[index];
    const available = (index + 1 < this.restarts.length
      ? this.restarts[index + 1] : this.header.keys.length) - this.restarts[index];
    let data = await this.index.read(start, Math.min(available, 256));
    let cursor: Cursor = { at: 0 };
    varint(data, cursor);                                // shared prefix: always zero here
    let length = varint(data, cursor);
    if (cursor.at + length > data.length) {
      // A long headword — multi-word entries are ordinary — so read the record exactly.
      data = await this.index.read(start, Math.min(available, cursor.at + length));
      cursor = { at: 0 };
      varint(data, cursor);
      length = varint(data, cursor);
    }
    const key = data.slice(cursor.at, cursor.at + length);
    this.restartKeyCache.set(index, key);
    // Bounded: a search path differs per word, so this would otherwise grow towards the whole key
    // section, which is the thing this reader exists not to hold.
    while (this.restartKeyCache.size > RESTART_KEY_CACHE) {
      this.restartKeyCache.delete(this.restartKeyCache.keys().next().value as number);
    }
    return key;
  }

  private restartKeyCache = new Map<number, Uint8Array>();

  /** Every key in one restart bucket, decoded from its front-coded form. */
  private async bucket(index: number): Promise<{ key: Uint8Array; entry: number }[]> {
    const start = this.restarts[index];
    const end = index + 1 < this.restarts.length ? this.restarts[index + 1] : this.header.keys.length;
    const data = await this.index.read(this.header.keys.start + start, end - start);
    const cursor: Cursor = { at: 0 };
    const keys: { key: Uint8Array; entry: number }[] = [];
    let previous = new Uint8Array(0);
    while (cursor.at < data.length) {
      const shared = varint(data, cursor);
      const length = varint(data, cursor);
      const key = new Uint8Array(shared + length);
      key.set(previous.subarray(0, shared));
      key.set(data.subarray(cursor.at, cursor.at + length), shared);
      cursor.at += length;
      keys.push({ key, entry: varint(data, cursor) });
      previous = key;
    }
    return keys;
  }

  /**
   * Where entry `index` sits inside its frame.
   *
   * Only its own frame's payload lengths are read — at most 256 varints — which is what the
   * per-frame offset table in the index exists for. Holding every entry's length instead would be
   * about 2 MiB for the largest dictionary and would not survive ten of them being installed.
   */
  private async locationOf(index: number): Promise<Location> {
    const frame = Math.floor(index / this.header.frameSize);
    const start = this.payloadOffsets[frame];
    const end = frame + 1 < this.payloadOffsets.length
      ? this.payloadOffsets[frame + 1]
      : this.header.payloads.length;
    const data = await this.index.read(this.header.payloads.start + start, end - start);
    const cursor: Cursor = { at: 0 };
    let offset = 0;
    for (let position = frame * this.header.frameSize; ; position += 1) {
      const length = varint(data, cursor);
      if (position === index) return { frame, offset, length };
      offset += length;
    }
  }

  private async frame(number: number): Promise<Uint8Array> {
    const cached = this.frames.get(number);
    if (cached) return cached;
    const compressed = await this.blob.read(this.frameStarts[number], this.frameLengths[number]);
    const decoded = inflateSync(compressed);
    this.frames.set(number, decoded);
    // Insertion order is iteration order, so the oldest frame is the first key.
    while (this.frames.size > FRAME_CACHE) {
      this.frames.delete(this.frames.keys().next().value as number);
    }
    return decoded;
  }
}
