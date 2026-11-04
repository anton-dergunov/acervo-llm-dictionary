/**
 * Export and import, as the Data page shows them.
 *
 * The panels own the two things a bundle needs that `transfer.ts` deliberately does not: the zip,
 * and the browser's way of handing a file in and out. Everything about what a bundle *is* stays in
 * `transfer.ts`, so a second transport would add a surface here and nothing else.
 */

import { useMemo, useRef, useState } from "react";
import { strFromU8, strToU8, unzipSync, zipSync } from "fflate";
import { languageOf } from "../languages";
import { repository, type ReplicaSnapshot } from "../repository";
import { syncEngine } from "../sync";
import { languageOptions } from "../selectors";
import { backendSession } from "../api";
import { bytesFor } from "../media";
import { clipBytes, COLLECTIONS } from "../pronunciation";
import {
  AUDIO_DIRECTORY, bundleName, exportBundle, importBundle, MEDIA_DIRECTORY, picturesIn, pronunciationsIn, readBundle,
  type BundleFile, type BundlePlan, type ImportReport
} from "../transfer";
import { Action, Group, Row, Select, Toggle } from "./kit";

/** Whatever the archiver on the other machine felt like adding. None of it is vocabulary. */
const NOISE = /(^|\/)(__MACOSX\/|\.DS_Store$|\._)/;

function save(name: string, bytes: Uint8Array): void {
  const url = URL.createObjectURL(new Blob([bytes as unknown as BlobPart], { type: "application/zip" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Late enough for the click to have been handled, early enough not to hold the bundle in memory.
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

/**
 * The bundle's text files, and its pictures and clips kept as bytes.
 *
 * Split because `strFromU8` on a WebP or an MP3 produces mojibake — everything under `media/`, and
 * every recording under `audio/`, has to stay binary all the way to the route that stores it. A
 * clip's `clips.yaml` is text like any other.
 */
async function filesIn(file: File): Promise<{ files: BundleFile[]; pictures: Map<string, Uint8Array>; recordings: Map<string, Uint8Array> }> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (!/\.zip$/i.test(file.name)) {
    return { files: [{ path: file.name, text: strFromU8(bytes) }], pictures: new Map(), recordings: new Map() };
  }
  const files: BundleFile[] = [];
  const pictures = new Map<string, Uint8Array>();
  const recordings = new Map<string, Uint8Array>();
  Object.entries(unzipSync(bytes))
    .filter(([path, content]) => !path.endsWith("/") && !NOISE.test(path) && content.length > 0)
    .forEach(([path, content]) => {
      if (path.startsWith(`${MEDIA_DIRECTORY}/`)) pictures.set(path, content);
      else if (path.includes(`${AUDIO_DIRECTORY}/`) && !/\.ya?ml$/i.test(path)) recordings.set(path, content);
      else files.push({ path, text: strFromU8(content) });
    });
  return { files, pictures, recordings };
}

/** ~110 KiB a picture, which is what makes the size worth warning about before it is asked for. */
const PICTURE_BYTES = 110 * 1024;
/** Pictures restored between pulls. Small enough that a long import fills in visibly, large enough
 *  that two thousand pictures do not cost two thousand extra round trips. */
const RESTORED_PER_PULL = 20;

export function ExportPanel({ snapshot }: { snapshot: ReplicaSnapshot }) {
  const [language, setLanguage] = useState<string>("all");
  const [markdown, setMarkdown] = useState(true);
  const [images, setImages] = useState(false);
  const [pronunciations, setPronunciations] = useState(true);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState("");
  const languages = languageOptions(snapshot);
  /* Only the language changes what these find, and they walk every word: memoized, because this
     panel repaints with everything else while an import beside it is running. */
  const pictures = useMemo(
    () => picturesIn(snapshot, { language, markdown: false, images: true, pronunciations: false }),
    [snapshot, language]
  );
  const clips = useMemo(
    () => pronunciationsIn(snapshot, { language, markdown: false, images: false, pronunciations: true }).clips,
    [snapshot, language]
  );

  async function run() {
    setBusy("Writing…");
    try {
      const at = new Date().toISOString();
      const files = exportBundle(snapshot, { language, markdown, images, pronunciations }, at);
      const archive: Record<string, Uint8Array> = {};
      files.forEach((file) => { archive[file.path] = strToU8(file.text); });

      let missing = 0;
      if (images) {
        // Sequential and counted, because this is the one export that is not offline-capable: the
        // bytes come from this device's cache where it has them and from the server where it does
        // not. A picture that cannot be read is skipped with a count rather than failing the whole
        // archive — the words are the part you cannot regenerate.
        for (const [index, picture] of pictures.entries()) {
          setBusy(`Fetching pictures… ${index + 1} of ${pictures.length}`);
          try {
            archive[picture.path] = await bytesFor(picture.reference);
          } catch {
            missing += 1;
          }
        }
      }

      let silent = 0;
      if (pronunciations) {
        for (const [index, clip] of clips.entries()) {
          setBusy(`Fetching pronunciations… ${index + 1} of ${clips.length}`);
          try {
            archive[clip.path] = await clipBytes(clip.reference);
          } catch {
            silent += 1;
          }
        }
      }

      setBusy("Writing…");
      save(bundleName(language, at), zipSync(archive));
      setProblem([
        missing ? `${missing} picture(s) could not be read and were left out.` : "",
        silent ? `${silent} pronunciation(s) could not be read and were left out.` : ""
      ].filter(Boolean).join(" "));
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "The export could not be written.");
    } finally {
      setBusy("");
    }
  }

  const megabytes = Math.max(1, Math.round(pictures.length * PICTURE_BYTES / 1024 / 1024));
  return <Group title="Export" foot={problem
    ? <span className="transfer-problem" role="alert">{problem}</span>
    : "A zip of YAML files, one per word, made from this device’s copy."}>
    <Select
      label="Vocabulary" value={language}
      options={[{ value: "all", label: "All languages" }, ...languages.map((option) => ({
        value: option.code, label: `${option.name} · ${option.count} ${option.count === 1 ? "entry" : "entries"}`
      }))]}
      onChange={setLanguage}
    />
    <Toggle
      label="Include Obsidian markdown" hint="A readable file per topic, for a vault"
      checked={markdown} onChange={setMarkdown}
    />
    <Toggle
      label="Include pictures"
      hint={pictures.length ? `${pictures.length} pictures, about ${megabytes} MB, read from the server` : "No pictures drawn yet"}
      checked={images} onChange={setImages}
    />
    <Toggle
      label="Include pronunciations"
      hint={clips.length ? `${clips.length} recordings, a few kilobytes each` : "Nothing recorded yet"}
      checked={pronunciations} onChange={setPronunciations}
    />
    <Action onClick={() => void run()} disabled={busy !== ""}>{busy || "Export…"}</Action>
  </Group>;
}

type Stage =
  | { at: "idle" }
  | { at: "chosen"; name: string; plan: BundlePlan; pictures: Map<string, Uint8Array>; recordings: Map<string, Uint8Array> }
  | { at: "running"; done: number; total: number }
  | { at: "done"; report: ImportReport };

export function ImportPanel({ onChanged }: { onChanged(): void }) {
  const [stage, setStage] = useState<Stage>({ at: "idle" });
  const [problem, setProblem] = useState("");
  const picker = useRef<HTMLInputElement>(null);
  const cancel = useRef({ cancelled: false });
  const [restoreClips, setRestoreClips] = useState(true);

  async function choose(file: File | undefined) {
    if (!file) return;
    setProblem("");
    try {
      const { files, pictures, recordings } = await filesIn(file);
      setStage({ at: "chosen", name: file.name, plan: readBundle(files), pictures, recordings });
    } catch (error) {
      setStage({ at: "idle" });
      setProblem(error instanceof Error ? error.message : "That file could not be read.");
    }
  }

  async function run(plan: BundlePlan, pictures: Map<string, Uint8Array>, recordings: Map<string, Uint8Array>) {
    cancel.current = { cancelled: false };
    setStage({ at: "running", done: 0, total: 0 });
    const deviceId = repository.state().deviceId;
    let restored = 0;

    const report = await importBundle(
      repository, plan,
      (done, total) => setStage({ at: "running", done, total }),
      cancel.current,
      pictures,
      /* Putting a picture back is the same act, and the same route, as attaching one by hand —
         naming the model that drew it is what makes it a restore rather than a file you chose. */
      async (senseId, bytes, drawnBy) => {
        const blob = new Blob([bytes as unknown as BlobPart], { type: "image/webp" });
        await backendSession.attachImage(senseId, deviceId, blob, drawnBy);
        restored += 1;
        /* A word arrives in the replica by itself, because `saveArticle` merges what the server
           answers. A *picture* does not: it is written by the image route, so the replica learns of
           it only on a pull — which is why an imported article showed empty frames and a "waiting"
           count until the next sync came round a minute later. Pulling in batches keeps a long
           import filling in as it goes rather than all at the end. */
        if (restored % RESTORED_PER_PULL === 0) await syncEngine.syncNow();
      },
      /* A clip is put back through its own route, naming who recorded it, and reaches the replica
         on a pull exactly as a restored picture does. */
      restoreClips && recordings.size ? {
        files: recordings,
        restore: async (target, id, bytes, entry) => {
          const type = entry.file.endsWith(".wav") ? "audio/wav" : entry.file.endsWith(".ogg") ? "audio/ogg" : "audio/mpeg";
          await backendSession.restorePronunciation(
            COLLECTIONS[target], id, deviceId, new Blob([bytes as unknown as BlobPart], { type }), entry
          );
          restored += 1;
          if (restored % RESTORED_PER_PULL === 0) await syncEngine.syncNow();
        }
      } : null,
      (lexemeId) => backendSession.enqueueJob({
        kind: "enrich", subject: { kind: "lexeme", id: lexemeId }, trigger: "import"
      })
    );

    // And once at the end, so "import finished" means every picture is here, not merely uploaded.
    if (restored > 0) await syncEngine.syncNow();
    onChanged();
    setStage({ at: "done", report });
  }

  function reset() {
    setStage({ at: "idle" });
    setProblem("");
    if (picker.current) picker.current.value = "";
  }

  return <Group title="Import" foot={problem
    ? <span className="transfer-problem" role="alert">{problem}</span>
    : "Adds the words in a bundle. A word you already have is left as it is."}>
    {stage.at === "idle" && <label className="pref-row stack">
      <span className="pref-text">
        <span className="pref-label">Choose a bundle</span>
        <span className="pref-hint">A zip exported from Acervo, or one YAML file</span>
      </span>
      <input
        ref={picker} type="file" accept=".zip,.yaml,.yml" className="transfer-file" aria-label="Bundle to import"
        onChange={(event) => void choose(event.target.files?.[0])}
      />
    </label>}

    {stage.at === "chosen" && <>
      <Row label={stage.name} hint={[
        `${stage.plan.articles.length} ${stage.plan.articles.length === 1 ? "entry" : "entries"}`,
        stage.plan.topics.length ? `${stage.plan.topics.length} topics` : "",
        stage.plan.vocabularies.length ? `${stage.plan.vocabularies.length} languages` : "",
        stage.pictures.size ? `${stage.pictures.size} pictures` : "",
        stage.recordings.size ? `${stage.recordings.size} pronunciations` : ""
      ].filter(Boolean).join(", ")} />
      {stage.recordings.size > 0 && <Toggle
        label="Restore pronunciations" hint="Off, they are recorded again on the first press"
        checked={restoreClips} onChange={setRestoreClips}
      />}
      {stage.plan.problems.length > 0 && <div className="pref-row stack"><ProblemList
        title={`${stage.plan.problems.length} ${stage.plan.problems.length === 1 ? "file" : "files"} could not be read and will be left out`}
        problems={stage.plan.problems}
      /></div>}
      <div className="pref-row pref-buttons">
        <button type="button" className="tb-btn" onClick={reset}>Cancel</button>
        <button
          type="button" className="tb-btn primary" disabled={stage.plan.articles.length === 0}
          onClick={() => void run(stage.plan, stage.pictures, stage.recordings)}
        >Import {stage.plan.articles.length} {stage.plan.articles.length === 1 ? "entry" : "entries"}</button>
      </div>
    </>}

    {stage.at === "running" && <Row
      label={`Importing ${stage.done} of ${stage.total}…`} hint="Each entry is saved to the server before the next"
    >
      <button type="button" className="tb-btn" onClick={() => { cancel.current.cancelled = true; }}>Stop</button>
    </Row>}

    {stage.at === "done" && <>
      <Row
        label={stage.report.aborted ? "Import stopped early" : "Import finished"}
        hint={[
          `${stage.report.added} added`,
          stage.report.picturesRestored > 0 ? `${stage.report.picturesRestored} pictures put back` : "",
          stage.report.pronunciationsRestored > 0 ? `${stage.report.pronunciationsRestored} pronunciations put back` : "",
          stage.report.skipped.length > 0 ? `${stage.report.skipped.length} already present` : "",
          stage.report.failed.length > 0 ? `${stage.report.failed.length} refused` : "",
          stage.report.topicsAdded > 0 ? `${stage.report.topicsAdded} new topics` : "",
          stage.report.vocabulariesAdded > 0 ? `${stage.report.vocabulariesAdded} new languages` : ""
        ].filter(Boolean).join(", ")}
      />
      {stage.report.skipped.length > 0 && <div className="pref-row stack"><details className="transfer-report">
        <summary>Already in your vocabulary</summary>
        <ul>{stage.report.skipped.map((entry) => <li key={`${entry.language}/${entry.headword}`}>
          {entry.headword} <span>{languageOf(entry.language).name}</span>
        </li>)}</ul>
      </details></div>}
      {stage.report.failed.length > 0 && <div className="pref-row stack">
        <ProblemList title="Refused" problems={stage.report.failed} open />
      </div>}
      <Action onClick={reset}>Import another file</Action>
    </>}
  </Group>;
}

function ProblemList({ title, problems, open = false }: {
  title: string;
  problems: { path: string; message: string }[];
  open?: boolean;
}) {
  return <details className="transfer-report" open={open}>
    <summary>{title}</summary>
    <ul>{problems.map((entry, index) => <li key={`${entry.path}:${index}`}>
      {entry.path} <span>{entry.message}</span>
    </li>)}</ul>
  </details>;
}
