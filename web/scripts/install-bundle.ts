/**
 * Import bundles into an account from the laptop, with the app's own import:
 *
 *   printf '%s\n' "$PASSWORD" | npx tsx scripts/install-bundle.ts --server URL --email EMAIL \
 *     [--fresh] [--name NAME | --into NAME] ZIP...
 *
 * (run from `web/`; the password is read from stdin, never an argument.) A laptop tool for filling
 * the owner's testing accounts with the starter vocabularies (`scripts/starter/test_accounts.sh`),
 * not part of the app. It signs in, keeps a replica in memory (`MemoryDatabase`, the one the tests
 * use), and runs `importThroughServer` — the code Settings ▸ Data ▸ Import runs — so filling an
 * account is also a test of what a person installing a starter gets.
 *
 * Each vocabulary in a bundle comes in as a new vocabulary under the bundle's name, as Settings ▸ Data
 * ▸ Import does until told otherwise; a name the account already shows is refused, naming it, and
 * nothing of that bundle is imported. `--name NAME` gives the new vocabulary another name, and
 * `--into NAME` adds the words to the account's vocabulary of that name instead, skipping the ones it
 * already holds. Both are for a bundle of one vocabulary, such as a starter.
 *
 * `--fresh` deletes every word in the account first (`POST /graph/reset`, which keeps languages and
 * topics): an import skips words already held, so a corrected word would otherwise never replace the
 * one installed before it.
 *
 * An import never queues a job or spends a provider by itself, in any account. `--testing` also makes
 * the account one where nothing else runs by itself, set before the first word arrives: no pictures
 * drawn on their own for words added there later, no Anki push or pull, no nightly steps.
 */

import { readFileSync } from "node:fs";
import { basename } from "node:path";

/* What the app's modules expect of a browser, and only that: a `window` with no Mac host on it, and
   the `localStorage` the session is kept in. Set before the modules load, so they are imported
   dynamically below. */
const stored = new Map<string, string>();
Object.assign(globalThis, {
  window: globalThis,
  localStorage: {
    getItem: (key: string) => stored.get(key) ?? null,
    setItem: (key: string, value: string) => { stored.set(key, value); },
    removeItem: (key: string) => { stored.delete(key); }
  }
});

const { backendSession } = await import("../src/api");
const { bundleArchive } = await import("../src/bundleZip");
const { importThroughServer } = await import("../src/importRun");
const { MemoryDatabase } = await import("../src/localDatabase");
const { LocalAcervoRepository } = await import("../src/repository");
const { defaultTargets, readBundle, targetProblems } = await import("../src/transfer");
const { presentationOf } = await import("../src/languages");
const { vocabularies } = await import("../src/selectors");
type ImportTarget = import("../src/transfer").ImportTarget;
type BundlePlan = import("../src/transfer").BundlePlan;
type VocabularyGraph = import("../src/domain").VocabularyGraph;
type RemoteGraph = import("../src/repository").RemoteGraph;

function options(argv: string[]) {
  const value = (flag: string) => {
    const at = argv.indexOf(flag);
    if (at < 0 || !argv[at + 1]) throw new Error(`${flag} is required`);
    return argv[at + 1];
  };
  const given = (flag: string) => argv.includes(flag) ? value(flag) : null;
  const flags = new Set(["--server", "--email", "--name", "--into"]);
  const zips = argv.filter((arg, index) => !arg.startsWith("--") && !flags.has(argv[index - 1] ?? ""));
  if (!zips.length) throw new Error("name at least one bundle zip");
  const name = given("--name");
  const into = given("--into");
  if (name && into) throw new Error("--name and --into are two different answers; give one");
  return {
    server: value("--server"), email: value("--email"), fresh: argv.includes("--fresh"),
    testing: argv.includes("--testing"), name, into, zips
  };
}

/**
 * Where each of the bundle's vocabularies goes: in as a new one under the bundle's name, unless the
 * command line said another name, or the account's vocabulary to add it to.
 */
function targetsFor(graph: VocabularyGraph, plan: BundlePlan, name: string | null, into: string | null): Map<string, ImportTarget> {
  const targets = defaultTargets(plan);
  if (!name && !into) return targets;
  if (plan.vocabularies.length !== 1) {
    throw new Error(`this bundle holds ${plan.vocabularies.length} vocabularies; --name and --into are for a bundle of one`);
  }
  const [{ directory }] = plan.vocabularies;
  if (name) return targets.set(directory, { kind: "new", name });
  const held = vocabularies(graph).find((one) => presentationOf(one).name.toLocaleLowerCase() === into!.trim().toLocaleLowerCase());
  if (!held) {
    const names = vocabularies(graph).map((one) => presentationOf(one).name).join(", ") || "none";
    throw new Error(`the account has no vocabulary called ${into} (it has: ${names})`);
  }
  return targets.set(directory, { kind: "existing", vocabularyId: held.id });
}

/** A testing account: nothing draws, syncs to Anki or runs at night by itself. */
async function quiet(email: string): Promise<void> {
  await backendSession.saveImageSettings({ drawEnabled: false });
  const anki = await backendSession.ankiStatus();
  if (anki.configured && (anki.push || anki.pull)) await backendSession.saveAnkiSettings({ push: false, pull: false });
  const schedule = await backendSession.scheduleSettings();
  await backendSession.saveScheduleSettings({ steps: Object.fromEntries(Object.keys(schedule.steps).map((step) => [step, false])) });
  console.log(`${email}: pictures not drawn by themselves, Anki off, no nightly steps`);
}

async function main(): Promise<number> {
  const { server, email, fresh, testing, name, into, zips } = options(process.argv.slice(2));
  const password = readFileSync(0, "utf8").split("\n")[0];
  const session = await backendSession.login(server, email, password);

  const repository = new LocalAcervoRepository(new MemoryDatabase());
  await repository.load(session.userId);
  /* What the sync engine is to the app, without its timers and window events. */
  const pull = async () => {
    const before = repository.state();
    const response = await backendSession.pullGraph(before.cursor);
    await repository.applyRemote(response.changes, response.cursor, response.datasetId);
  };
  const remote: RemoteGraph = {
    async push(changes) {
      const response = await backendSession.pushGraph(repository.state().deviceId, changes);
      return { records: response.records, cursor: repository.state().cursor, datasetId: response.datasetId };
    },
    async saveArticle(draft, minted, base, writeOptions) {
      const response = await backendSession.saveArticle(repository.state().deviceId, draft, [...minted], base, writeOptions);
      return {
        records: response.records, cursor: repository.state().cursor, datasetId: response.datasetId,
        lexemeId: response.lexemeId, jobId: response.jobId
      };
    }
  };
  repository.attachRemote(remote);
  await pull();
  if (testing) await quiet(email);

  if (fresh) {
    await backendSession.resetGraph(repository.state().deviceId);
    await pull();
    console.log(`${email}: every word deleted`);
  }

  let failures = 0;
  for (const zip of zips) {
    const archive = bundleArchive(basename(zip), new Uint8Array(readFileSync(zip)));
    const plan = readBundle(archive.files);
    if (plan.problems.length) {
      failures += 1;
      console.error(`${basename(zip)}: ${plan.problems.length} files do not read; nothing imported`);
      plan.problems.slice(0, 5).forEach((problem) => console.error(`  ${problem.path}: ${problem.message}`));
      continue;
    }
    let targets: Map<string, ImportTarget>;
    try {
      targets = targetsFor(repository.snapshot(), plan, name, into);
    } catch (error) {
      failures += 1;
      console.error(`${basename(zip)}: ${error instanceof Error ? error.message : String(error)}; nothing imported`);
      continue;
    }
    const refused = [...targetProblems(repository.snapshot(), plan, targets).values()];
    if (refused.length) {
      failures += 1;
      console.error(`${basename(zip)}: nothing imported`);
      refused.forEach((problem) => console.error(`  ${problem} (--name gives it another, --into adds it to yours)`));
      continue;
    }
    const started = Date.now();
    let shown = 0;
    const report = await importThroughServer({
      repository, pull, plan, targets,
      pictures: archive.pictures, recordings: archive.recordings, restoreClips: true,
      onProgress: (done, total) => {
        if (done - shown >= 100 || done === total) {
          shown = done;
          process.stdout.write(`\r${basename(zip)}: ${done} of ${total}`);
        }
      }
    });
    process.stdout.write("\n");
    const seconds = Math.round((Date.now() - started) / 1000);
    console.log(`${basename(zip)}: ${report.added} words added, ${report.skipped.length} already held, `
      + `${report.picturesRestored} pictures, ${report.pronunciationsRestored} recordings, `
      + `${report.failed.length} failed, ${seconds} s${report.aborted ? " — stopped early" : ""}`);
    report.failed.slice(0, 10).forEach((problem) => console.error(`  ${problem.path}: ${problem.message}`));
    if (report.failed.length || report.aborted) failures += 1;
  }
  return failures ? 1 : 0;
}

process.exitCode = await main().catch((error: unknown) => {
  console.error(error instanceof Error ? error.message : String(error));
  return 2;
});
