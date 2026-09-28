# A standalone macOS application

**Status:** an intention, not a design. It needs one before anything is built
([`../../research/similar-projects.md`](../../research/similar-projects.md), "Heavy to maintain, and hard for
anyone else to run").

**The goal:** download, open, use — the data kept on the machine, and no NAS, Docker or companion
services to run. Only macOS is in scope; other platforms may come later.

**Why it is a design change, not packaging.** Today every write is a round trip to the server, by design
([`../../architecture/sync.md`](../../architecture/sync.md)), and several things are computed on the server
because a phone should not: the meaning map's embeddings and layout, every model call, the job runner,
media. The likeliest shape is that the application **ships the server and starts it with itself**, so
those answers hold on one machine too — the meaning map's design already assumes that. What would need
deciding:

- how the bundled server, its database and its media live inside a macOS application, and how they are
  backed up;
- how providers and keys are configured without a deploy — which is the Settings work in
  [`provider-management.md`](../provider-management.md);
- whether the companion services (the corpus, the loop generator, Anki's sync server) come along, are
  optional downloads, or are left out;
- how a standalone installation later joins a server for sync across devices, if at all.

**Related, and not planned now:** a simpler self-hosted path for anyone who wants sync across devices,
and — only if the project succeeds — a hosted service with downloadable applications.
