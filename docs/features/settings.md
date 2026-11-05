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

A page may open **sub-pages**: Clips ▸ Channels, a provider's own page, a vocabulary or a topic being
edited. They share the window's back button and title (`useSubPage` in `kit.tsx`), so a page that grows
a detail view does not grow a dialog. A sub-page may name the one it was opened from as its `parent`,
and Back returns there: a vocabulary ▸ Translated into. The window draws each sub-page afresh, so
anything being edited across them is kept outside the page.

## 2 · The window is the screen's size, never the page's

Full screen on a phone, the screen less a 16px margin on a tablet, and with a mouse a generous window
that can be resized and keeps the size it was dragged to on that device. **No page decides the size.**
The window used to be as tall as the page in it, centred, so every switch between pages resized it and
moved its header, and a page that was still loading first shrank it to one line.

A wide window does not stretch the rows: a page is a column at most 760px wide, centred in the pane,
with its title starting where the column does. A switch 1,600 pixels from its label is a row nobody
can read across; a narrow column pinned to the left of a wide window looked unfinished.

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
**notice** is a fact to act on: no provider, a service that does not answer. A voice is chosen by
listening, so its rows carry a **listen** button at their start — a link to its page, a **choice**
among several (a radio row with a check), or a select — and every row of a voice group has one, so
their labels align (`voices.tsx`, shared by Pronunciation and Loops).

A group that is a **form** — fields to type and selects, such as a vocabulary's name, flag and
variety — is `aligned`: every control starts in the same column, whatever its label's length. Left to
flex, each field started where its own label ended and no two lined up.

**A hint is one line of about a dozen words, saying what the setting does for you.** Not how it works
inside — servers, calls, caches, records, which model is asked how many times. The pages carried
paragraphs of that, forty to eighty words each, and the owner read none of it; the reasoning belongs in
the feature's document, which is where it is now. A page has no introduction.

Whether something works is a **state mark**: an icon that carries it, then two or three words — *Works*,
*Key refused*. A key is typed in a **secret** field, hidden and never offered to a password manager.

## 6 · Vocabularies

A language is **found by its name**, in English or in itself — "Spanish", "español" — and shown with
its flag, never as a tag. The tag is how it is stored. The list is CLDR's, from the server
(`GET /languages`, `locales.catalogue`): every language at least a million people speak, most
speakers first, with a script of its own where it is officially written in two (`zh-Hans` and
`zh-Hant`, `sr-Cyrl` and `sr-Latn`). A name matches where one of its words begins — "trad" finds
Chinese (Traditional), "eng" does not find Vietnamese through *Tiếng*. A typed tag is read in its
canonical form, so `eng` finds English rather than a second English; a tag whose language the list
lacks is offered as typed, if the platform can name it, so a smaller language can be kept. The same search chooses the languages a vocabulary is
defined, translated and annotated in.

**Add a language…** finds one and opens its page **unsaved**, filled in: named in English, defined in
itself, translated into what the owner's other vocabularies translate into most (or the browser's
language for the first), notes in the first of those. Nothing is written until *Add vocabulary*;
Cancel leaves nothing behind.

A vocabulary's page has three groups:

- **Name, Flag, Variety.** The **variety** (`region`) is the regional form learned — Argentina's
  Spanish — offered as CLDR's varieties for the language with their flags. *Variety* is the linguist's
  word, and the right one: it now changes the words and grammar the writers prefer, not only how the
  voices sound. The **flag follows the variety**, or the language's main region without one, and is
  derived on the device; a flag pasted in is the owner's own, and choosing another variety returns it
  to automatic.
- **Written in**: the three languages, each a sub-page with the search.
- **You**: a CEFR **level** and **About you**, a paragraph in the owner's own words — goals, what they
  know well and what they don't. Both reach the writers ([`standing-rules.md`](standing-rules.md),
  "The reader"), the level firmly and the paragraph lightly.

## 7 · On the Mac there is one Settings

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

## 8 · Providers

A provider is an account the owner adds — one key, offering models of several kinds — and the page is
where every one of them is added; there is no file to edit and no deploy
([`../architecture/models.md`](../architecture/models.md)). The code is `ModelPanel.tsx` for the page
and `ProviderPages.tsx` for everything under it.

- **The page** lists the providers, each with the kinds it has models for and a state mark, then the
  six orders. A provider whose key was refused is also a notice at the top, with a link to its page:
  nothing is sent to it until the key works, so it must not be missed while scrolling.
- **Add a provider** shows the families this server knows, in the groups the server sends. Choosing one
  opens a short form — a name, the few settings the family asks for, the key — and **Check and add**
  makes one call that spends nothing. A refusal is shown on the form in the provider's own words, and
  nothing is added; a key that works opens the new provider's page, empty.
- **A provider's page** has its key as its first and last four characters with Replace, what the last
  check said with Check again, the family's settings, a group per kind with **Add a model…**, a link to
  the provider's own page for the bill, and Remove. Remove asks for a second press, since the key goes
  with it. Google Cloud signs in with a key or a credentials file; the choice says what each reaches,
  and what only the file reaches is hidden while it signs in with a key. The file is chosen or
  **pasted**: gcloud keeps your own sign-in in a hidden folder a file dialog does not show, and an iPad
  reaches no folder on the Mac at all, while the clipboard crosses devices. What is pasted is checked to
  be whole JSON before it is sent. The line under the field says where the file usually is.
- **Add a model** is one box. It searches what the provider itself says it has, with what is already
  added marked, and once nothing listed matches, what is typed is offered as it is — *Add
  "flux-2-klein-9b"*, under a line saying the provider does not list it — for a model too new for the
  list. Enter adds only a listed name, so a half-typed search never becomes a model. Where a provider
  cannot list a kind at all — Vertex, or Gemini's voices on Cloud Text-to-Speech — the same box takes
  the name. A second "type its name" field beside the search asked for the same name twice.
- **A voice model** has its own page: whether it takes a direction, the languages it speaks (any, or
  some, chosen with the language search), a free allowance, and its voices — listed by the provider, or
  typed with a link to where the provider lists them. The voices are not heard here: a preview needs a
  language and a sample in it, and a WaveNet list spans every language. They are heard on
  Pronunciation, which is where one is chosen.

Every write answers with the whole readout and replaces it, because taking a model or a provider away
also takes it out of the orders. Pronunciation's settings are read again after one, since its voice
choices can change too.
