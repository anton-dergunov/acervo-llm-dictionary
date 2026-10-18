/* The device half of a chat turn, run outside the browser so an answer can be scored by the code
   that ships rather than by a Python copy of it.

   Reads one JSON request per line on stdin and writes one JSON answer per line on stdout:

     {"document": "<yaml>"}                                    -> {"status": "parsed", draft}
     {"document": "<yaml>", "header": true}                    -> {"status": "header", header}
     {"document": "<yaml>", "ops": [...], "modelId": "...",
      "glossLang": "ru"}                                       -> {"status": "applied", draft, yaml, changes}
                                                                | {"status": "refused", sentence}
                                                                | {"status": "threw", sentence}

   "applied" walks the whole path `AddView.applyToDraft` walks — `parseArticle`, `applyOps`,
   `yamlForDraft`, `diffDrafts` — so a throw anywhere on it is caught here exactly where the owner
   would have met the generic "could not be applied" toast. `threw` is that toast, with the error
   the toast throws away. */

import { createInterface } from "node:readline";
import { applyOps, diffDrafts, EditRefused, type EditOp } from "../../web/src/articleEdit";
import { parseArticle, yamlForDraft } from "../../web/src/yaml";

let minted = 0;
const mintId = () => `mint${String(++minted).padStart(11, "0")}`;

function answer(line: string): unknown {
  const request = JSON.parse(line) as {
    document: string; ops?: EditOp[]; modelId?: string; glossLang?: string | null;
  };
  let before;
  try {
    before = parseArticle(request.document);
  } catch (error) {
    return { status: "unparsed", sentence: String((error as Error)?.message ?? error) };
  }
  // The two comment lines `yamlForDraft` would head this document with today. The documents are
  // files written once; an arm on newer code sends the header its own `yaml.ts` writes.
  if ((request as { header?: boolean }).header) {
    return { status: "header", header: yamlForDraft(before).split("\n").slice(0, 2).join("\n") };
  }
  if (!request.ops) return { status: "parsed", draft: before };
  minted = 0;
  try {
    const applied = applyOps(before, request.ops, {
      modelId: request.modelId ?? "experiment", glossLang: request.glossLang ?? null, mintId
    });
    const yaml = yamlForDraft(applied.draft);
    const diff = diffDrafts(before, applied.draft);
    // What the re-derived preview would read back: a proposal that does not survive its own
    // projection is no better than one refused.
    parseArticle(yaml);
    return {
      status: "applied", draft: applied.draft, yaml,
      changes: { count: diff.count, records: [...diff.records.entries()].map(([key, value]) => ({
        key, mark: value.mark, fields: [...value.fields.keys()]
      })), notes: [...diff.notes.entries()].map(([index, value]) => ({ index, mark: value.mark })) }
    };
  } catch (error) {
    if (error instanceof EditRefused) return { status: "refused", sentence: error.message };
    return { status: "threw", sentence: `${(error as Error)?.name}: ${(error as Error)?.message}` };
  }
}

const lines = createInterface({ input: process.stdin });
lines.on("line", (line) => {
  if (!line.trim()) return;
  let out: unknown;
  try {
    out = answer(line);
  } catch (error) {
    out = { status: "bad-request", sentence: String(error) };
  }
  process.stdout.write(JSON.stringify(out) + "\n");
});
