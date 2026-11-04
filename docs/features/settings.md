# Settings

One window, the same on every device, holding every setting Acervo has — the vocabulary's, this
device's, the server's, and on the Mac the application's own. The code is `web/src/settings/`; the
design is `design/ui-prototype/settings.html`, whose stylesheet is shared with the app's.

## 1 · Sixteen pages in five groups

| Group | Pages |
|---|---|
| General | General · Reading · Dictionaries |
| Vocabulary | Vocabularies · Topics · Rules |
| Media | Pictures · Pronunciation · Clips · Loops · Stories |
| Server | Providers · Activity · Anki |
| Data | Sync · Data |

The pages were seventeen tabs in one row that scrolled sideways, with nothing to say which belonged
together; the owner could not find things. A group is what a page is *about*, so a new setting goes on
the page of the thing it changes — a voice for loops on Loops, not on Pronunciation — and a new page
goes in the group it belongs to. The nightly run is on Activity, beside the record of what it did,
rather than on a page of its own. Docs and the interface name a page as **Settings ▸ Page**, so a page
is not renamed lightly.

A page may open **sub-pages**: Clips ▸ Channels, Providers ▸ Credentials, a vocabulary or a topic being
edited. They share the window's back button and title (`useSubPage` in `kit.tsx`), so a page that grows
a detail view does not grow a dialog.

## 2 · The window is the screen's size, never the page's

Full screen on a phone, the screen less a 16px margin on a tablet, and with a mouse a generous window
that can be resized and keeps the size it was dragged to on that device. **No page decides the size.**
The window used to be as tall as the page in it, centred, so every switch between pages resized it and
moved its header, and a page that was still loading first shrank it to one line.

## 3 · One DOM at every width

Where the window is at least 640px wide the list of pages is a sidebar beside the page. Narrower, the
list is a page of its own and a page drills in from it, with a back button — the way a phone's own
settings work, so nothing scrolls sideways and nothing is two rows of chips. Which of the two shows is a
container query on the window and a `data-level` attribute, so the component renders the same markup
everywhere and only the stylesheet knows the width; jsdom tests see both levels at once.

## 4 · A page shows what it last knew

A server-backed page reads through `cache.ts`: the last answer at once, asked for again behind it, and
replaced when the reply lands. Opening Settings reads the cheap ones in the background. A page used to
fetch every time it was shown and render "Reading your settings…" first — that, with §2, was the blink
on every page switch.

It is a cache of route answers and nothing else. A write still goes to the server and fails loudly;
what a save shows is the server's reply; signing out empties it. The replica and its rules are untouched.

The one setting another service holds — what the clip corpus contains — is its own route and is never
read in the background ([`spoken-clips.md`](spoken-clips.md) §10).

## 5 · The kit, and how a setting is written

Every page is built from `kit.tsx`: a **group** is a titled card of rows; a **row** is a label with at
most one hint under it and its control on the right — a switch, a select, a segmented choice of two or
three, a link to a sub-page, or a whole-row action (in the warning colour when it destroys). A
**notice** is a fact to act on: no provider, a service that does not answer.

**A hint is one line of about a dozen words, saying what the setting does for you.** Not how it works
inside — servers, calls, caches, records, which model is asked how many times. The pages carried
paragraphs of that, forty to eighty words each, and the owner read none of it; the reasoning belongs in
the feature's document, which is where it is now. A page has no introduction.

The kit is also what the provider work in [`../plans/provider-management.md`](../plans/provider-management.md)
builds on: an ordered list with switches, a sub-page per provider, a key field.

## 6 · On the Mac there is one Settings

The application's own settings — opening at login, showing the window at login, checking for and
installing updates, the server — are on General, read and changed through the bridge
(`macos/Sources/HostSettings.swift`), which tells the page when they change. Acervo ▸ Settings… (⌘,)
opens this window. There used to be a second, native Settings window for them; two windows called
Settings was the confusion.

The application still owns them: the page stores none of them, a login item reads the system's own
answer, and a refusal comes back as a sentence. The server is shown and not edited, because changing it
is signing in again — a session's token belongs to the server that issued it — so **Change server…**
signs out to the sign-in screen, which asks for the address. Checking for updates still runs natively,
so an interface that fails to load cannot strand the Mac on a broken build.
