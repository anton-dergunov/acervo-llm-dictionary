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

## Prompt arms (run 1, not yet run)

`run.py` re-sends the builder's stored requests, rebuilt by `compose_parts` (checked equal to what the
builder sent, system prompt digest included), changing only the prompt or the language lines:

- `before`: the prompt as shipped when the failure was found (`arms/before.md`);
- `after`: the reworded prompt (`arms/after.md`, now `prompts/acervo_compose.md`): the two lines
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
