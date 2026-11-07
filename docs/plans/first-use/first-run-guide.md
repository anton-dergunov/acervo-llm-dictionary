# A first-run guide

**Status:** an idea, not designed. It matters once somebody other than the owner installs Acervo,
and nobody does yet. Raised by the owner on 7 Nov 2026.

## The idea

A newly installed Acervo opens with nothing in it: no vocabulary, no topics, no providers. A short
guide would take a new user through the three things that make it work:

1. **A vocabulary**: the language they are learning and the languages to translate into.
2. **Topics**, or the starter set.
3. **Providers**, with exactly two choices:
   - **Google Cloud does everything.** One account, a credentials file, a small bill. The guide asks
     for the file and the project and adds Google Cloud with its usual models. That set already
     exists (`Ready` in `models/families.py`, added by **Add the usual models**), so this step is
     the add form with fewer fields, not new machinery.
   - **I'll choose my own.** A link to [`../../providers.md`](../../providers.md), which leads with
     the free set, then opens Settings ▸ Providers.

The same guide is reachable later from Settings, so it is not lost by closing it once.

## What a design has to answer

- **When it opens.** On the first sign-in to a server with no providers? Only for the account that
  owns the server, since providers belong to the server and a second account cannot add them
  ([`other-users.md`](other-users.md))?
- **Where it lives in Settings,** and whether it is a page of the kit or a window of its own.
- **The credentials file on a tablet.** The file dialog cannot reach a hidden folder on an iPad, so
  the step needs the **Paste…** the Google Cloud page already has, and words for getting the file
  there.
- **What the guide does not do.** It does not create the Google Cloud project, enable APIs or make a
  service account. It links to the guide's steps for those, and checks the file when it arrives.
- **How it ends.** It ends on a first word added, as the proof that it all works.

It is designed in `design/ui-prototype/` first, like every interface change, and screenshotted at
the tablet's size before any code.
