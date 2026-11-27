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
import { flagFor, presentationOf } from "../languages";
import { repository, type ReplicaSnapshot } from "../repository";
import { syncEngine } from "../sync";
import { vocabularyOptions } from "../selectors";
import { bytesFor } from "../media";
import { clipBytes } from "../pronunciation";
import { importThroughServer } from "../importRun";
import {
  bundledName, bundleName, defaultTargets, exportBundle, intoChoices, picturesIn, pronunciationsIn, readBundle,
  targetProblems, type BundlePlan, type BundleVocabulary, type ImportReport, type ImportTarget
} from "../transfer";
import { Action, Group, Notice, Option, OptionField, Options, Row, Select, Toggle } from "./kit";

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
  const [vocabularyId, setVocabularyId] = useState<string>("all");
  const [markdown, setMarkdown] = useState(true);
  const [images, setImages] = useState(false);
  const [pronunciations, setPronunciations] = useState(true);
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState("");
  const choices = vocabularyOptions(snapshot);
  /* Only the vocabulary changes what these find, and they walk every word: memoized, because this
     panel repaints with everything else while an import beside it is running. */
  const pictures = useMemo(
    () => picturesIn(snapshot, { vocabularyId, markdown: false, images: true, pronunciations: false }),
    [snapshot, vocabularyId]
  );
  const clips = useMemo(
    () => pronunciationsIn(snapshot, { vocabularyId, markdown: false, images: false, pronunciations: true }).clips,
    [snapshot, vocabularyId]
  );

  async function run() {
    setBusy("Writing…");
    try {
      const at = new Date().toISOString();
      const files = exportBundle(snapshot, { vocabularyId, markdown, images, pronunciations }, at);
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
      save(bundleName(snapshot, vocabularyId, at), zipSync(archive));
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
      label="Vocabulary" value={vocabularyId}
      options={[{ value: "all", label: "All vocabularies" }, ...choices.map((option) => ({
        value: option.id, label: `${option.name} · ${option.count} ${option.count === 1 ? "entry" : "entries"}`
      }))]}
      onChange={setVocabularyId}
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
  | {
      at: "chosen"; name: string; plan: BundlePlan; pictures: Map<string, Uint8Array>; recordings: Map<string, Uint8Array>;
      /** Where each of the bundle's vocabularies goes, by its directory, as the owner has chosen so far. */
      targets: Map<string, ImportTarget>;
    }
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
      const plan = readBundle(files);
      setStage({ at: "chosen", name: file.name, plan, pictures, recordings, targets: defaultTargets(plan) });
    } catch (error) {
      setStage({ at: "idle" });
      setProblem(error instanceof Error ? error.message : "That file could not be read.");
    }
  }

  async function run(plan: BundlePlan, pictures: Map<string, Uint8Array>, recordings: Map<string, Uint8Array>,
                     targets: Map<string, ImportTarget>) {
    cancel.current = { cancelled: false };
    const chosen = stage;
    setStage({ at: "running", done: 0, total: 0 });
    const report = await importThroughServer({
      repository, pull: () => syncEngine.syncNow(), plan, targets,
      pictures, recordings, restoreClips,
      onProgress: (done, total) => setStage({ at: "running", done, total }),
      signal: cancel.current
    }).catch((error: unknown) => {
      // Refused because a run started earlier from this window is still going, or because what was
      // chosen no longer fits what the account holds.
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

  const snapshot = repository.snapshot();
  const problems = stage.at === "chosen" ? targetProblems(snapshot, stage.plan, stage.targets) : new Map<string, string>();
  const retarget = (directory: string, target: ImportTarget) => {
    if (stage.at === "chosen") setStage({ ...stage, targets: new Map(stage.targets).set(directory, target) });
  };

  return <><Group title="Import" foot={problem
    ? <span className="transfer-problem" role="alert">{problem}</span>
    : "Each vocabulary in the file comes in as a new one, or joins one of yours. Words you already have are left as they are."}>
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
        stage.plan.vocabularies.length ? `${stage.plan.vocabularies.length} ${stage.plan.vocabularies.length === 1 ? "vocabulary" : "vocabularies"}` : "",
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
          stage.report.vocabulariesAdded > 0 ? `${stage.report.vocabulariesAdded} new vocabularies` : ""
        ].filter(Boolean).join(", ")}
      />
      {stage.report.skipped.length > 0 && <div className="pref-row stack"><details className="transfer-report">
        <summary>Already in your vocabulary</summary>
        <ul>{bySkippedVocabulary(stage.report.skipped).map((entry) => <li key={`${entry.vocabulary}/${entry.headword}`}>
          {entry.headword} <span>{entry.vocabulary}</span>
        </li>)}</ul>
      </details></div>}
      {stage.report.failed.length > 0 && <div className="pref-row stack">
        <ProblemList title="Refused" problems={stage.report.failed} open />
      </div>}
      <Action onClick={reset}>Import another file</Action>
    </>}
  </Group>
  {stage.at === "chosen" && <>
    {stage.plan.vocabularies.map((entry) => <TargetChoice
      key={entry.directory} entry={entry} target={stage.targets.get(entry.directory)!}
      into={intoChoices(snapshot, entry)} problem={problems.get(entry.directory) ?? null}
      onChange={(target) => retarget(entry.directory, target)}
    />)}
    <div className="pref-buttons">
      <button type="button" className="tb-btn" onClick={reset}>Cancel</button>
      <button
        type="button" className="tb-btn primary" disabled={stage.plan.articles.length === 0 || problems.size > 0}
        onClick={() => void run(stage.plan, stage.pictures, stage.recordings, stage.targets)}
      >Import {stage.plan.articles.length} {stage.plan.articles.length === 1 ? "entry" : "entries"}</button>
    </div>
  </>}
  </>;
}

/** The skipped words, a vocabulary's together, in the order the vocabularies first appear. */
function bySkippedVocabulary(skipped: ImportReport["skipped"]): ImportReport["skipped"] {
  const order = [...new Set(skipped.map((entry) => entry.vocabulary))];
  return skipped.slice().sort((left, right) => order.indexOf(left.vocabulary) - order.indexOf(right.vocabulary));
}

/**
 * Where one of the file's vocabularies goes: in as a new vocabulary, under the name typed inside that
 * option, or into one of the owner's own of its language, which keeps its own name. Both are always
 * offered when the owner keeps that language; a name already taken holds Import back until it is
 * changed or the other option is chosen.
 */
function TargetChoice({ entry, target, into, problem, onChange }: {
  entry: BundleVocabulary;
  target: ImportTarget;
  into: ReturnType<typeof intoChoices>;
  problem: string | null;
  onChange(target: ImportTarget): void;
}) {
  const named = bundledName(entry);
  const [name, setName] = useState(target.kind === "new" ? target.name : named);
  return <Options title={`${flagFor(entry)} ${named}`} label={`Where ${named} goes`}>
    <Option label="Add as a new vocabulary" checked={target.kind === "new"} onChoose={() => onChange({ kind: "new", name })}>
      <OptionField label="Name" value={name} clash={Boolean(problem)}
        onChange={(typed) => { setName(typed); onChange({ kind: "new", name: typed }); }} />
      {problem && <Notice>{problem}</Notice>}
    </Option>
    {into.map((vocabulary) => {
      const shown = presentationOf(vocabulary);
      const chosen = target.kind === "existing" && target.vocabularyId === vocabulary.id;
      return <Option
        key={vocabulary.id} label={`Add to ${shown.flag} ${shown.name}`} hint="Words you already have are left as they are"
        checked={chosen} onChoose={() => onChange({ kind: "existing", vocabularyId: vocabulary.id })}
      >{chosen && problem ? <Notice>{problem}</Notice> : null}</Option>;
    })}
  </Options>;
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
