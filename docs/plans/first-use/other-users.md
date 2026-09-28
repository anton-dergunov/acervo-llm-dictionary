# Other people using Acervo

**Status:** an intention, not scheduled. Acervo has one owner today. This collects what it would take
for someone else to use it — on their own server, or as a second account on the owner's — so the
work can start from a page. The standalone application is its own plan
([`standalone-mac-app.md`](standalone-mac-app.md)); providers and a setup guide for them are
[`../provider-management.md`](../provider-management.md).

## The size to build for

**A handful of accounts per self-hosted server — five to ten**, not a hosted service. Everything in
Acervo assumes one small SQLite file, one job runner and the owner's own provider allowances, and that
is the right shape for a family or a few friends on one machine. A paid, hosted Acervo would be a
different architecture and a different project; it is not planned, and nothing here should be bent
towards it.

## What is shared by a deployment, not owned by an account

Accounts already exist and every record is owner-scoped. Some things are not per owner, and each
needs deciding before there is a second account:

- **The clip corpus.** Schedule settings are per owner and each owner's nightly run updates the
  corpus, but the corpus serves the whole deployment — a second account would update it a second time
  every night. The corpus step belongs to the deployment, or to one owner.
- **Dictionaries** are compiled once per server and read by everyone; building one is a deploy-machine
  command today. **Building a dictionary from the interface** is a job kind and a Settings row — the
  builder already reports progress and raises rather than prints — and is what someone without a
  shell on the server needs.
- **Provider allowances.** Whose keys a second account spends, and whether one account can exhaust
  another's free tier, is a question for [`../provider-management.md`](../provider-management.md).

## Starting with words already there

A new user opens an empty vocabulary, and every word they add costs model calls, pictures and
recordings before it is pleasant to study. **Starter vocabularies** — a few hundred common words per
language and level, with articles, pictures and recordings already made — would let them start the
same day. An export bundle is already the format ([`../../features/export.md`](../../features/export.md)),
so a starter vocabulary is a published bundle, imported like any other.

## Other platforms

The client is a PWA and runs anywhere; the macOS host is the only native shell. A Linux build of the
standalone application may follow the macOS one; Windows comes last, since the owner does not use it.
