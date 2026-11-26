/**
 * Import bundles into an account from the laptop, with the app's own import:
 *
 *   printf '%s\n' "$PASSWORD" | npx tsx scripts/install-bundle.ts --server URL --email EMAIL [--fresh] ZIP...
 *
 * (run from `web/`; the password is read from stdin, never an argument.) A laptop tool for filling
 * the owner's testing accounts with the starter vocabularies (`scripts/starter/test_accounts.sh`),
 * not part of the app. It signs in, keeps a replica in memory (`MemoryDatabase`, the one the tests
 * use), and runs `importThroughServer` — the code Settings ▸ Data ▸ Import runs — so filling an
 * account is also a test of what a person installing a starter gets.
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
const { readBundle } = await import("../src/transfer");
type RemoteGraph = import("../src/repository").RemoteGraph;

function options(argv: string[]) {
  const value = (flag: string) => {
    const at = argv.indexOf(flag);
    if (at < 0 || !argv[at + 1]) throw new Error(`${flag} is required`);
    return argv[at + 1];
  };
  const flags = new Set(["--server", "--email"]);
  const zips = argv.filter((arg, index) => !arg.startsWith("--") && !flags.has(argv[index - 1] ?? ""));
  if (!zips.length) throw new Error("name at least one bundle zip");
  return {
    server: value("--server"), email: value("--email"), fresh: argv.includes("--fresh"),
    testing: argv.includes("--testing"), zips
  };
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
  const { server, email, fresh, testing, zips } = options(process.argv.slice(2));
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
    const started = Date.now();
    let shown = 0;
    const report = await importThroughServer({
      repository, pull, plan, pictures: archive.pictures, recordings: archive.recordings, restoreClips: true,
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
