/**
 * Export and import, as the Data page shows them.
 *
 * The panels own what a bundle needs that `transfer.ts` deliberately does not: the browser's way of
 * handing a file in and out. The zip is read by `bundleZip.ts` and an import is run by
 * `importRun.ts`, both shared with the laptop's installer for the starter vocabularies. Everything
 * about what a bundle *is* stays in `transfer.ts`, so a second transport would add a surface here
 * and nothing else.
 */

import { useMemo, useRef, useState } from "react";
import { strToU8, zipSync } from "fflate";
import { bundleArchive, type BundleArchive } from "../bundleZip";
import { languageOf } from "../languages";
import { repository, type ReplicaSnapshot } from "../repository";
import { syncEngine } from "../sync";
import { languageOptions } from "../selectors";
import { bytesFor } from "../media";
import { clipBytes } from "../pronunciation";
import { importThroughServer } from "../importRun";
import {
  bundleName, exportBundle, picturesIn, pronunciationsIn, readBundle,
  type BundlePlan, type ImportReport
} from "../transfer";
import { Action, Group, Row, Select, Toggle } from "./kit";

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

async function filesIn(file: File): Promise<BundleArchive> {
  return bundleArchive(file.name, new Uint8Array(await file.arrayBuffer()));
}

/** ~110 KiB a picture, which is what makes the size worth warning about before it is asked for. */
const PICTURE_BYTES = 110 * 1024;

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
    const chosen = stage;
    setStage({ at: "running", done: 0, total: 0 });
    const report = await importThroughServer({
      repository, pull: () => syncEngine.syncNow(), plan, pictures, recordings, restoreClips,
      onProgress: (done, total) => setStage({ at: "running", done, total }),
      signal: cancel.current
    }).catch((error: unknown) => {
      // Refused because a run started earlier from this window is still going.
      setStage(chosen);
      setProblem(error instanceof Error ? error.message : String(error));
      return null;
    });
    if (!report) return;
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
