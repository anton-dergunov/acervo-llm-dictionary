/* Stands in for the server in repository tests: numbers every record it is handed, exactly as the
   server does, keeps what it stored, and answers an article save the way `POST /articles` would. */

import type { VocabularyGraph } from "./domain";
import {
  EMPTY_GRAPH, type ArticleWrite, type Entity, type RemoteGraph, type RemoteWrite, type WriteOptions
} from "./repository";
import { articleChanges } from "./testArticles";

export interface FakeRemote extends RemoteGraph {
  calls: number;
  /** Set to make the next write fail, the way an unreachable or refusing server would. */
  fail: Error | null;
  sent: Partial<VocabularyGraph>[];
  /** What each write asked of the server beyond its records, in order. */
  options: (WriteOptions | undefined)[];
  /** What the server holds. */
  stored: VocabularyGraph;
}

export function fakeRemote(datasetId = "dataset00000001", ownerId = "owner0000000001"): FakeRemote {
  let sequence = 0;

  const store = (changes: Partial<VocabularyGraph>): Partial<VocabularyGraph> => {
    const records: Partial<VocabularyGraph> = {};
    (Object.keys(changes) as (keyof VocabularyGraph)[]).forEach((kind) => {
      const incoming = changes[kind] as Entity[] | undefined;
      if (!incoming) return;
      const numbered = incoming.map((record) => ({ ...record, revision: ++sequence }));
      records[kind] = numbered as never;
      const held = remote.stored[kind] as Entity[];
      numbered.forEach((record) => {
        const at = held.findIndex((one) => one.id === record.id);
        if (at < 0) held.push(record); else held[at] = record;
      });
    });
    return records;
  };

  /* A clock that only moves forward, as the server's does: records are ordered by when they were
     made, and two saves in the same millisecond must still come out in the order they happened. */
  let last = 0;
  const later = () => {
    const held = Object.values(remote.stored).flat() as Entity[];
    const newest = Math.max(last, ...held.map((record) => Date.parse(record.editedAt) || 0));
    last = Math.max(Date.now(), newest + 1);
    return new Date(last).toISOString();
  };

  const remote: FakeRemote = {
    calls: 0,
    fail: null,
    sent: [],
    options: [],
    stored: EMPTY_GRAPH(),
    async push(changes) {
      remote.calls += 1;
      remote.sent.push(structuredClone(changes));
      remote.options.push(undefined);
      if (remote.fail) throw remote.fail;
      // The cursor is deliberately not advanced by a write: the engine leaves it alone so the
      // next pull re-delivers these rows rather than skipping anything written in between.
      return { records: store(changes), cursor: 0, datasetId } satisfies RemoteWrite;
    },
    async saveArticle(draft, minted, _base, options) {
      remote.calls += 1;
      if (remote.fail) throw remote.fail;
      const { lexemeId, changes } = articleChanges(
        remote.stored, draft, minted, { ownerId, deviceId: "device000000001" }, later()
      );
      remote.sent.push(structuredClone(changes));
      remote.options.push(options);
      return { records: store(changes), cursor: 0, datasetId, lexemeId, jobId: null } satisfies ArticleWrite;
    }
  };
  return remote;
}
