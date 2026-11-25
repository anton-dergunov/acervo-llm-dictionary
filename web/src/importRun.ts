/**
 * An import against the server: the words through the repository, then each picture and clip
 * through the route that stores it, then the word's `enrich`.
 *
 * `transfer.ts` decides what an import does and holds no transport; this module supplies the
 * transport, so Settings ▸ Data ▸ Import and the laptop's installer for the starter vocabularies
 * (`web/scripts/install-bundle.ts`) run one import, not two. It imports nothing that needs a browser:
 * the caller brings the repository and the pull, which in the app are the replica and the sync
 * engine.
 */

import { backendSession, COLLECTIONS } from "./api";
import type { AcervoRepository } from "./repository";
import { importBundle, type BundlePlan, type ImportReport, type ImportSignal } from "./transfer";

/** Pictures and clips restored between pulls. Small enough that a long import fills in visibly,
 *  large enough that two thousand pictures do not cost two thousand extra round trips. */
const RESTORED_PER_PULL = 20;

export interface ImportRun {
  repository: AcervoRepository;
  /** Brings the server's records into the repository: `syncEngine.syncNow` in the app. */
  pull(): Promise<unknown>;
  plan: BundlePlan;
  pictures: Map<string, Uint8Array>;
  recordings: Map<string, Uint8Array>;
  /** Whether the bundle's recordings are put back, or left for the server to record again. */
  restoreClips: boolean;
  /** Whether each new word's `enrich` is queued, as every save queues it. Only the laptop's
   *  installer for testing accounts turns it off, so twenty starters do not open ten thousand jobs. */
  enrich?: boolean;
  onProgress?(done: number, total: number): void;
  signal?: ImportSignal;
}

const audioType = (file: string) =>
  file.endsWith(".wav") ? "audio/wav" : file.endsWith(".ogg") ? "audio/ogg" : "audio/mpeg";

/** Refused with `IMPORT_RUNNING` while another import from this window is still going. */
export async function importThroughServer(run: ImportRun): Promise<ImportReport> {
  const { repository, pull, plan, pictures, recordings } = run;
  const deviceId = repository.state().deviceId;
  let restored = 0;
  /* A word arrives in the replica by itself, because `saveArticle` merges what the server answers.
     A picture or a clip does not: it is written by its own route, so the replica learns of it only
     on a pull — which is why an imported article showed empty frames and a "waiting" count until
     the next sync came round a minute later. Pulling in batches keeps a long import filling in as
     it goes rather than all at the end. */
  const counted = async () => {
    restored += 1;
    if (restored % RESTORED_PER_PULL === 0) await pull();
  };

  const report = await importBundle(
    repository, plan, run.onProgress, run.signal, pictures,
    /* Putting a picture back is the same act, and the same route, as attaching one by hand —
       naming the model that drew it is what makes it a restore rather than a file you chose. */
    async (senseId, bytes, drawnBy) => {
      const blob = new Blob([bytes as unknown as BlobPart], { type: "image/webp" });
      await backendSession.attachImage(senseId, deviceId, blob, drawnBy);
      await counted();
    },
    /* A clip is put back through its own route, naming who recorded it. */
    run.restoreClips && recordings.size ? {
      files: recordings,
      restore: async (target, id, bytes, entry) => {
        const blob = new Blob([bytes as unknown as BlobPart], { type: audioType(entry.file) });
        await backendSession.restorePronunciation(COLLECTIONS[target], id, deviceId, blob, entry);
        await counted();
      }
    } : null,
    run.enrich === false ? null : (lexemeId) => backendSession.enqueueJob({
      kind: "enrich", subject: { kind: "lexeme", id: lexemeId }, trigger: "import"
    })
  );
  // And once at the end, so "import finished" means every picture is here, not merely uploaded.
  if (restored > 0) await pull();
  return report;
}
