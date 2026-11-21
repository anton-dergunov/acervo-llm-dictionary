# Definition language

**Question.** Compose is told `Define senses in: en` for a vocabulary that defines in English. Does it,
and can compose's check tell when it does not?

**Why it came up.** The starter build (`scripts/starter/build.py`, twelve vocabularies, 9,500 senses)
found `gemini-3.5-flash-lite` writing a large share of its definitions in the word's own language, for
vocabularies that define in English: *la silla* → "Asiento con respaldo para una sola persona."
`gemini-3.1-flash-lite`, asked the same, almost never did. The drafts were labelled
`definitionLang: en` all the same, and nothing checked it: compose's check read the script of glosses
and notes, not of definitions, and script cannot tell Italian from English anyway.

Share of 3.5 Flash-Lite's senses not in English, by script and a stopword count (the first estimate):

| es-MX | es-ES | pt-BR | fr-FR | de-DE | ko-KR | it-IT | ru | zh-CN |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 50% | 45% | 37% | 36% | 35% | 31% | 30% | 9% | 2% |

Two lines of the shipped prompt pointed the other way: a definition is "usually the language of the
word itself", and "a definition is short and formulaic, so it is left in the language being learned".

## Calibration: telling two languages of one script apart (free)

`calibrate.py` reads every stored starter definition as compose's new check does
(`vet.definition_doubt`) and writes `calibration.json`.

- **Script** settles the other cases exactly: 129 starter definitions in another script (ko-KR 70,
  ru 45, zh-CN 10, ar 4) are refused.
- **Within Latin script**, `lingua` (2.2) chooses between the definition language and the word's
  language. Of 5,763 definitions where the two share a script, 1,206 reach 0.7.
- **Every definition between 0.5 and 0.95 was read** (110, in `calibration.json`). English read as
  the other language reached 0.64 ("An adult male person." 0.55, "Frozen water." 0.58, "At no time; on
  no occasion." 0.64). Everything at 0.71 or more was in another language. Hence the threshold, 0.7.
- **A stopword count was worse.** It missed 51 English definitions with no function words ("Costing
  little money; affordable.") and 210 foreign ones lingua caught.
- **Asking lingua among every Latin-script language does not work.** A short English definition
  spreads its confidence over 49 languages ("A male child." gets 0.09 for English), and in
  low-accuracy mode it reads plain English as Latin at 0.94. It would also hold ~230 MB of models in
  the server. So the detector is built per vocabulary, over its own languages only.
- **What it misses:** a definition in a third language. 3.5 Flash-Lite sometimes defined an Italian,
  French or Portuguese word in *Spanish* ("Dispositivo luminoso que regula el tráfico…" for an
  Italian word). Choosing between English and Italian, lingua puts those at 0.54–0.77, so about six of
  them fall under the threshold.
- **False alarms on real words:** the owner's 1,467 Spanish definitions of Spanish words, glossed into
  English, are all passed. The owner's English (defined in English, glossed into Russian) and Mandarin
  (defined in English) are left to the script check, which passes them all. Counts only; no words
  are copied here.

## Prompt arms (run 1, 21 Nov 2026)

**Result: the rewording fixes it, and naming the languages adds nothing.** On the 105 sample words,
3.5 Flash-Lite put a definition in the wrong language in **63 words (60%) with the shipped prompt, 2
(2%) with the reworded one** (62 fixed, 1 broken; exact McNemar p = 1.4e-17). Naming the languages
also gives 2 (61 fixed, 0 broken), so the user message stays as it is. 3.1 Flash-Lite gets 0 of 105
with either. The Spanish control, defined in Spanish, stays in Spanish (0 of 30 with either arm).
585 calls on Vertex, all answered, $1.22.

| Set | Model | Arm | Words | Senses | Wrong senses (certain) | Words with one wrong |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| sample | 3.5 Flash-Lite | before | 105 | 176 | 109 (27) | 63 (60%) |
| sample | 3.5 Flash-Lite | after | 105 | 183 | 5 (0) | 2 (2%) |
| sample | 3.5 Flash-Lite | named | 105 | 177 | 4 (0) | 2 (2%) |
| sample | 3.1 Flash-Lite | after / named | 105 | 172 / 170 | 0 | 0 |
| control | 3.5 Flash-Lite | after / named | 30 | 53 / 49 | 0 | 0 |

- **The baseline re-ran at 60%, not 100%**, though every sample word had failed once: the failure is
  a coin the model tosses per word, which is why one stored draft cannot say whether a prompt fixed it.
- **Before, every vocabulary failed** (de-DE 8/15, es-ES 12, fr-FR 7, it-IT 10, ko-KR 10, pt-BR 12,
  ru 4). **After, only es-ES** (Castilian) still does, on four words in either arm (*la carne*, *la
  estación*, *el huevo*, *joven*), and each is defined wholly in Spanish. None is in another script, so
  compose's check demotes it softly and the next model is asked; 3.1 Flash-Lite never failed.
- **The definitions read as a learner's dictionary should.** Read side by side on a sample: *gratis*
  "Che non costa nulla, che viene dato senza richiedere alcun pagamento." → "Costing nothing; provided
  without payment."; 배우다 "지식이나 기술을 익히다." → "To get knowledge or a skill through study,
  experience, or being taught." None of the dozen pairs read got vaguer.
- Full numbers, per vocabulary and paired: [`runs/1/report.md`](runs/1/report.md).

## Run 2: other definition languages, and the example (21 Nov 2026)

**Question.** The four words still failing in run 1 were all Spanish, and the prompt's one JSON
example is a Spanish word (*el disfraz*) **defined in Spanish** and glossed into English. Does the
example invite them? And is a fix fair to vocabularies that define in some language other than
English, which run 1 never asked about?

**Setups**, the same stored requests with only the vocabulary record changed, so every arm sees the
same words:

| Set | Defined in | Words | Scored by |
| --- | --- | ---: | --- |
| `sample` | English (the starters) | 105, the run 1 words | lingua; script for ko, ru |
| `control` | the word's own language: es-MX | 30 | lingua |
| `own` | the word's own language: fr-FR, de-DE, ja-JP (glossed into English) | 45 | lingua; script for ja |
| `russian` | Russian (glosses and notes too): es-ES, it-IT, de-DE, fr-FR words | 48 | script, exactly |
| `spanish` | Spanish: the en-US starter as it is, and it-IT, fr-FR, pt-BR words | 60 | lingua |

The scorer is compose's check, plus English as a language a definition may slip into even where the
vocabulary does not name it (the model's default), and each reply also goes through compose's whole
check, so an arm that breaks another field shows.

**Arms,** each correct for any definition language except the one built to test the worry:

- `after`: the prompt run 1 shipped;
- `labelled`: `after`, with one line before the example saying what it is: a Spanish word in a
  vocabulary that defines in Spanish and glosses into English, so write each field in the language
  your own lines name;
- `reminder`: `after`, with a closing line in the request made from the vocabulary's definition
  language ("Write every definition in Russian, whatever language the word is in.");
- `shape`: `after`, with the example's definition in English, which should help English-defined
  vocabularies and might hurt the others.

**Result: `labelled` is the only arm with nothing wrong anywhere, and it is shipped.** 1,152 calls on
3.5 Flash-Lite, all answered, $2.73. Totals over the 288 words each arm saw:

| Arm | Words with a definition in the wrong language | Replies not JSON | Other refusals by the check |
| --- | ---: | ---: | ---: |
| `after` | 2 (*la estación*, English setup; *saltar*, Russian setup) | 2 | 0 |
| `labelled` | **0** | **0** | **0** |
| `reminder` | 2 (*la estación*; *amar*, Russian setup) | 3 | 0 |
| `shape` | 0 | 0 | 2 (*bruyant* with no senses; *sitzen*'s notes in Latin script for a Russian setup) |

- **Every slip in both runs was a Spanish word defined in Spanish** (*la carne*, *la estación* twice,
  *el huevo*, *joven*, *saltar*, *amar*), whatever the setup asked: what the example shows. Saying
  what the example is removed them all, and needed no language of its own.
- **The worry about `shape` did not come true where expected:** en-US, defined in Spanish, stayed
  0/30 under every arm. But `shape` cost two other refusals, and it is the one arm that would mislead
  a vocabulary defined in anything but English, so it is not shipped.
- **The reminder line helped nothing** and had the most unreadable replies.
- **The size of the win is small.** 2 words against 0 is no significant difference on its own (exact
  McNemar p = 0.5); `labelled` is shipped because it is never worse on any measure, costs nothing,
  and names the cause the slips share. All demotions in every arm were dictionary notation for a
  transcription (`[ˈtiːnʔɛɪ̯d͡ʒɐ]` against `/ˈtiːnˌʔeːɡɐ/`), unrelated to the language.
- Full numbers: [`runs/2/report.md`](runs/2/report.md).

### Method

`run.py` re-sends the builder's stored requests, rebuilt by `compose_parts` (checked equal to what the
builder sent, system prompt digest included), changing only the prompt or the language lines:

- `before`: the prompt as shipped when the failure was found (`arms/before.md`);
- `after`: the reworded prompt (`arms/after.md`): the two lines
  dropped, the rule stated on the `Define senses in:` line with *la silla* as the example;
- `named`: `after`, with each language line naming its language (`Define senses in: English (en)`).

Words: `sample`, 15 per vocabulary from es-ES, fr-FR, it-IT, pt-BR, de-DE, ko-KR and ru, where 3.5
Flash-Lite's stored draft has a definition the check doubts (105); `control`, 30 es-MX words re-asked
with `definitionLang: es`, which must stay in Spanish.

    .venv/bin/python experiments/definition-language/run.py --providers FILE --row ID
    .venv/bin/python experiments/definition-language/run.py --providers FILE --row ID --set control --arm after --arm named
    .venv/bin/python experiments/definition-language/run.py --providers FILE --row ID --model gemini-3.1-flash-lite --arm after --arm named
    .venv/bin/python experiments/definition-language/report.py

`FILE` is a providers file outside the repository, in `providers.local.json`'s shape, holding the Vertex
row `ID` to bill: 315, 60 and 210 calls, about $1 in all.

## Files

- `calibrate.py`, `calibration.json`: the free calibration above.
- `run.py`, `report.py`, `arms/`: the prompt arms; replies and scores under `runs/<run>/`.
