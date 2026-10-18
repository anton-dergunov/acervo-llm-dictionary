/* Render the web tests' fixture words through the shipped `yamlFor`, so the experiment's stored-entry
   documents are exactly what the article view would send rather than hand-typed approximations.

     npx --prefix web rolldown experiments/chat-edits/render_fixtures.ts -o <out.mjs> -f esm -p node
     node <out.mjs> experiments/chat-edits/documents */

import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { articleFor } from "../../web/src/selectors";
import { testGraph } from "../../web/src/testGraph";
import { yamlFor } from "../../web/src/yaml";

const WORDS: Record<string, string> = {
  "picar.yaml": "lexemepicar0001",
  "balsa.yaml": "lexemebalsa0001",
  "espolvorear.yaml": "lexemeespolv001",
  "turmoil.yaml": "lexemeturmoil01"
};

const graph = testGraph();
for (const [file, id] of Object.entries(WORDS)) {
  const article = articleFor(graph, id);
  if (!article) throw new Error(`no article ${id} in the fixture graph`);
  writeFileSync(join(process.argv[2], file), yamlFor(article));
}
