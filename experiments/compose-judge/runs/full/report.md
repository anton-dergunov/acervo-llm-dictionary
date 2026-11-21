# Judge run `full`: the failure inventory

10152 articles judged. **2973 (29%) have a severity-3 fault** (a learner would learn something false, or misses an everyday meaning); 8971 (88%) have a listed fault of severity 2 or 3; 9476 (93%) were corrected at all, minor polish included.

## Per vocabulary

| vocabulary | articles | with a 3 | with a 2 or 3 | faults an article |
| --- | ---: | ---: | ---: | ---: |
| ar | 507 | 32% | 90% | 1.58 |
| de-DE | 507 | 22% | 88% | 1.47 |
| el-GR | 503 | 31% | 90% | 1.56 |
| en-US | 511 | 20% | 87% | 1.46 |
| es-ES | 508 | 24% | 83% | 1.34 |
| es-MX | 505 | 26% | 87% | 1.44 |
| fr-FR | 501 | 25% | 85% | 1.40 |
| hi-IN | 494 | 23% | 89% | 1.44 |
| id-ID | 502 | 24% | 87% | 1.45 |
| it-IT | 509 | 25% | 89% | 1.48 |
| ja-JP | 512 | 52% | 88% | 1.62 |
| ko-KR | 510 | 23% | 87% | 1.39 |
| nl-NL | 506 | 31% | 91% | 1.61 |
| pl-PL | 510 | 32% | 89% | 1.56 |
| pt-BR | 507 | 26% | 87% | 1.49 |
| ru | 508 | 30% | 88% | 1.46 |
| th-TH | 509 | 34% | 91% | 1.47 |
| tr-TR | 512 | 37% | 92% | 1.74 |
| vi-VN | 511 | 48% | 93% | 1.72 |
| zh-CN | 520 | 20% | 87% | 1.43 |

## Per composing model

| model | articles | with a 3 | faults an article |
| --- | ---: | ---: | ---: |
| gemini-3.1-flash-lite | 5122 | 28% | 1.50 |
| gemini-3.5-flash-lite | 5030 | 31% | 1.52 |

Which model composed a word depends on the vocabulary, so the table above mixes languages. Within the 16 vocabularies where each model composed at least 100 articles (ar, el-GR, en-US, es-ES, es-MX, hi-IN, id-ID, ko-KR, nl-NL, pl-PL, pt-BR, ru, th-TH, tr-TR, vi-VN, zh-CN), the share of articles with each kind:

| model | articles | with a 3 | `note.filler` | `note.false` | `field.ipa` | `note.missing` | `example.unnatural` | `sense.oversplit` | `shortgloss.mismatch` | `sense.missing` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gemini-3.1-flash-lite | 4052 | 25% | 53.2% | 14.9% | 10.0% | 11.2% | 7.0% | 10.7% | 7.2% | 5.9% |
| gemini-3.5-flash-lite | 4071 | 32% | 51.8% | 10.1% | 17.5% | 9.8% | 11.0% | 9.9% | 7.8% | 3.8% |

## Kinds of fault, by weight (severity summed)

| kind | weight | faults | of them 3 | articles | worst vocabularies (share of their articles) | per composer (share) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `note.filler` | 10993 | 5496 | 1 | 51.5% | hi-IN 61%, ar 60%, tr-TR 59%, el-GR 57% | 3.1-flash-lite 52% / 3.5-flash-lite 51% |
| `note.false` | 3616 | 1332 | 952 | 12.9% | ja-JP 20%, pt-BR 16%, th-TH 15%, el-GR 15% | 3.1-flash-lite 15% / 3.5-flash-lite 10% |
| `field.ipa` | 3498 | 1224 | 1050 | 12.1% | vi-VN 44%, tr-TR 25%, ar 18%, th-TH 17% | 3.1-flash-lite 8% / 3.5-flash-lite 16% |
| `note.missing` | 2322 | 1142 | 38 | 11.2% | de-DE 21%, ru 20%, it-IT 15%, en-US 14% | 3.1-flash-lite 12% / 3.5-flash-lite 10% |
| `example.unnatural` | 2160 | 905 | 350 | 8.7% | nl-NL 13%, ar 13%, tr-TR 13%, pl-PL 12% | 3.1-flash-lite 7% / 3.5-flash-lite 11% |
| `sense.oversplit` | 2083 | 1038 | 7 | 10.2% | id-ID 16%, pl-PL 12%, it-IT 12%, ko-KR 11% | 3.1-flash-lite 10% / 3.5-flash-lite 10% |
| `shortgloss.mismatch` | 1558 | 762 | 34 | 7.5% | en-US 11%, es-ES 10%, de-DE 9%, vi-VN 9% | 3.1-flash-lite 7% / 3.5-flash-lite 8% |
| `sense.missing` | 1211 | 507 | 197 | 5.0% | pt-BR 8%, es-MX 8%, fr-FR 7%, es-ES 6% | 3.1-flash-lite 6% / 3.5-flash-lite 4% |
| `sense.marginal` | 1139 | 563 | 13 | 5.5% | en-US 9%, fr-FR 9%, es-ES 8%, es-MX 8% | 3.1-flash-lite 5% / 3.5-flash-lite 6% |
| `sense.wrong` | 1138 | 395 | 348 | 3.9% | id-ID 6%, nl-NL 6%, vi-VN 5%, th-TH 5% | 3.1-flash-lite 3% / 3.5-flash-lite 4% |
| `field.reading` | 633 | 218 | 197 | 2.1% | ja-JP 37%, zh-CN 6%, nl-NL 0% | 3.1-flash-lite 4% / 3.5-flash-lite 0% |
| `example.translation` | 624 | 302 | 20 | 2.9% | en-US 5%, ar 5%, pt-BR 4%, hi-IN 4% | 3.1-flash-lite 3% / 3.5-flash-lite 3% |
| `definition.form` | 588 | 286 | 16 | 2.6% | pt-BR 5%, zh-CN 4%, en-US 4%, ko-KR 4% | 3.1-flash-lite 4% / 3.5-flash-lite 2% |
| `gloss.wrong` | 523 | 230 | 63 | 2.2% | en-US 5%, id-ID 3%, ru 3%, es-MX 3% | 3.1-flash-lite 2% / 3.5-flash-lite 3% |
| `definition.unclear` | 486 | 229 | 28 | 2.2% | es-MX 3%, nl-NL 3%, pt-BR 3%, es-ES 3% | 3.1-flash-lite 2% / 3.5-flash-lite 2% |
| `example.missing-word` | 424 | 164 | 96 | 1.5% | zh-CN 4%, ja-JP 4%, de-DE 3%, nl-NL 3% | 3.1-flash-lite 2% / 3.5-flash-lite 1% |
| `example.wrong-sense` | 386 | 174 | 38 | 1.7% | tr-TR 4%, en-US 3%, id-ID 2%, fr-FR 2% | 3.1-flash-lite 1% / 3.5-flash-lite 2% |
| `field.pos` | 265 | 114 | 37 | 1.1% | zh-CN 3%, vi-VN 2%, th-TH 2%, ko-KR 2% | 3.1-flash-lite 1% / 3.5-flash-lite 1% |
| `text.corrupt` | 256 | 94 | 68 | 0.9% | el-GR 2%, ar 2%, nl-NL 2%, th-TH 2% | 3.1-flash-lite 0% / 3.5-flash-lite 2% |
| `language.wrong` | 119 | 45 | 29 | 0.4% | en-US 2%, it-IT 1%, th-TH 1%, fr-FR 1% | 3.1-flash-lite 0% / 3.5-flash-lite 1% |
| `field.gender` | 72 | 27 | 18 | 0.3% | ru 1%, hi-IN 1%, pl-PL 1%, de-DE 1% | 3.1-flash-lite 0% / 3.5-flash-lite 0% |
| `field.register` | 31 | 15 | 1 | 0.1% | hi-IN 1%, th-TH 0%, ja-JP 0%, el-GR 0% | 3.1-flash-lite 0% / 3.5-flash-lite 0% |

## Each kind, quoted

### `note.filler` — 5496 faults, 1 of them severity 3

- en-US **secret** (notes[0], 2): “Un 'secret' es algo que no quieres que otras personas sepan.” — Merely repeats the definition instead of giving useful collocations.
- tr-TR **çalışmak** (notes[0], 2): “çalışmak is extremely versatile. Depending on the context, it can mean” — Pure filler restating the glosses.
- de-DE **hassen** (notes, 2): “While 'hassen' is a very strong word in German, it is sometimes” — Notes 0 and 1 repeat the exact same point and partially contradict each other.
- hi-IN **दूध** (notes[0], 2): “It is almost always masculine.” — Restates the gender field (and hedges inaccurately: it is always masculine).
- en-US **cow** (notes[0], 2): “Como verbo, 'to cow' significa intimidar o acobardar a alguien” — Rare C2 verb sense is irrelevant for an A2 noun entry; plural 'cattle' is useful.
- pt-BR **olá** (notes[0], 2): “This is the most common and versatile way to greet someone” — Restates the definition; in Brazil 'oi' is actually the most common casual greeting.

### `note.false` — 1332 faults, 952 of them severity 3

- pl-PL **tańczyć** (notes[0], 3): “Note the consonant cluster 'ńc'. ... before the soft 'ć'” — The word contains 'ńcz' (hard /t͡ʂ/), not 'ńc' or soft 'ć'.
- pt-BR **chegar** (notes[1], 2): “When using 'chegar', use the preposition 'a' to indicate where you arrived” — In everyday Brazilian Portuguese, 'chegar em' is far more common than 'chegar a'.
- ko-KR **열쇠** (notes[0], 3): “Used for physical locks and keys. For figurative meanings, such as” — False claim: 열쇠 is regularly used figuratively in Korean (e.g., 문제 해결의 열쇠, 성공의 열쇠).
- fr-FR **parce que** (senses[0].examples[0], 3): “Note that 'parce que' becomes 'parc'qu'' before a vowel” — Standard mandatory spelling before a vowel is 'parce qu'', not 'parc'qu''.
- el-GR **ο ξένος** (notes[1], 3): “the adjective form which simply means 'foreign' or 'strange'” — As an adjective, 'ξένος' means 'foreign' or 'belonging to someone else', not 'strange' ('παράξενος').
- pt-BR **o sofá** (notes[0], 3): “both 'sofá' and 'canapé' can refer to a couch” — Misleading for A2: in Brazil 'canapé' means a party appetizer; the furniture sense is obsolete.

### `field.ipa` — 1224 faults, 1050 of them severity 3

- ar **وَرَقَة** (ipa, 3): “/waˈra.qa/” — Wrong stress: three light syllables take initial stress /ˈwa.ra.qa/.
- th-TH **โชค** (ipa, 3): “/tɕʰoːk̚/” — Missing falling tone mark on the syllable (/tɕʰôːk/).
- tr-TR **çatı** (ipa, 3): “/tʃɑːtɯ/” — Wrong vowel length and missing stress; the first vowel in 'çatı' is short: /tʃɑˈtɯ/.
- ar **جَائِع** (ipa, 3): “/ˈdʒaː.iʕ/” — Missing the glottal stop /ʔ/ represented by the medial hamza (ئ).
- tr-TR **hayır** (ipa, 3): “/hajɯɾ/” — Missing primary stress mark ('hayır' meaning 'no' is stressed on the first syllable: /ˈhajɯɾ/).
- nl-NL **de woonkamer** (ipa, 3): “/ˈwoːnˌkaː.mər/” — Dutch 'w' is /ʋ/, not /w/.

### `note.missing` — 1142 faults, 38 of them severity 3

- hi-IN **शाम** (notes, 2): “” — Missing the helpful grammar note on using 'शाम को' for 'in the evening'.
- en-US **cake** (notes, 2): “” — Missing essential A2 countability note (countable for whole cakes, uncountable for portions).
- ko-KR **차갑다** (notes, 2): “” — Missing note on ㅂ-irregular conjugation (차갑다 -> 차가워요, 차가운).
- de-DE **anschauen** (notes, 2): “” — Missing note on separable prefix 'an-' and common reflexive dative usage 'sich etwas anschauen'.
- ar **قَرَأَ** (notes, 2): “” — Needs a note on the irregular hamza seat in the imperfect (يَقْرَأُ) and imperative (اِقْرَأْ).
- ar **بَنَى** (notes[1], 2): “so the final vowel changes depending on the conjugation.” — Says the vowel changes without giving the actual present form (يَبْنِي yabnī).

### `example.unnatural` — 905 faults, 350 of them severity 3

- ru **растительное масло** (senses[0].examples[0].text, 3): “Добавьте немного растительное масло на сковороду.” — Ungrammatical: 'немного' requires the genitive case (растительного масла), not accusative.
- nl-NL **zwemmen** (senses[1].examples[0].text, 3): “De bladeren zwemmen op het water.” — Unnatural Dutch; leaves 'drijven' (float) on water, they do not 'zwemmen'.
- ar **أَحْيَانًا** (senses[0].examples[1].text, 3): “تَمْطُرُ فِي الصَّيْفِ أَحْيَانًا.” — Wrong verb form and vocalization; 'to rain' is Form IV أَمْطَرَ (تُمْطِرُ), not تَمْطُرُ.
- zh-CN **闻** (senses[1].examples[0].text, 3): “此 闻 让 人 惊 讶 。” — Ungrammatical pseudo-classical sentence with spaces between characters, using 闻 as a noun.
- it-IT **la foresta** (senses[0].examples[0].text, 2): “Gli alberi alti coprono la foresta.” — Tautological: a forest is made of trees, so trees do not 'cover' a forest.
- ru **бросать** (senses[1].examples[0].text, 2): “Он решил бросать курить в этом месяце.” — Unnatural aspect: after 'решил' (decided), the perfective 'бросить курить' is strongly required.

### `sense.oversplit` — 1038 faults, 7 of them severity 3

- id-ID **ruangan** (senses[1], 2): “(space) A designated area or zone for a specific purpose.” — Not a distinct sense from sense 0; 'ruangan' is an enclosed room or hall.
- th-TH **เรียน** (senses[1], 2): “To spend a period of time learning or attending classes in a” — Not a separate sense; duration is expressed by มา...แล้ว, not by เรียน itself.
- de-DE **der Onkel** (senses, 2): “The husband or partner of one's aunt.” — Both parent's brother and aunt's husband correspond to the single concept 'uncle' in both languages.
- id-ID **telur** (senses, 2): “” — Bird eggs as food and animal eggs in nature are one core meaning.
- tr-TR **korku** (senses, 2): “” — Fear of danger and fear of a bad outcome are shades of one meaning.
- zh-CN **人** (senses[1], 2): “路上有很多人。 — There are many people on the road.” — Chinese does not inflect for plural; 'person' and 'people' in this example are the exact same sense.

### `shortgloss.mismatch` — 762 faults, 34 of them severity 3

- pt-BR **gentil** (shortGloss, 2): “kind; polite; charming” — 'Charming' is not in the senses and is not a standard meaning of 'gentil'.
- es-MX **fuerte** (shortGloss, 2): “strong; loud; tough” — 'Tough' is in shortGloss, but no sense or gloss covers it.
- id-ID **perawat** (shortGloss, 2): “nurse” — Omits 'caregiver' from sense 1.
- es-MX **el pez** (shortGloss, 3): “fish (living); fish (as food)” — 'Pez' only means a living fish; fish as food is 'pescado'.
- vi-VN **cỏ** (shortGloss, 2): “grass; herb” — 'Herb' is an incorrect translation for 'cỏ'; should be 'grass; weed'.
- es-MX **caer** (shortGloss, 2): “to fall; to drop; to tumble” — Does not cover sense 1 (to make an impression / to be liked).

### `sense.missing` — 507 faults, 197 of them severity 3

- pt-BR **o e-mail** (senses, 2): “” — Also very commonly refers to an email address (e.g. 'Qual é o seu e-mail?').
- id-ID **hangat** (senses, 2): “” — Missing the common figurative sense 'warm, friendly, cordial' (e.g., sambutan hangat).
- zh-CN **老** (senses, 3): “” — Missing common everyday senses: long-standing (e.g. old friend) and tough/overcooked food.
- es-MX **el menú** (senses, 2): “” — Missing the everyday computing/phone screen sense of 'menú'.
- vi-VN **cam** (senses, 2): “” — Missing the everyday noun/modifier sense of the color orange.
- ar **عِنْدَ** (senses, 2): “” — Missing the common everyday temporal sense ('at, upon, when', e.g., عند الوصول).

### `sense.marginal` — 563 faults, 13 of them severity 3

- pt-BR **parar** (senses[1], 2): “To stay in a place for a period of time” — Staying at a hotel is marginal/regional for A2 compared to 'stop moving' vs 'stop doing'.
- en-US **stone** (senses[1], 2): “Hueso duro que tienen en el centro algunas frutas como el melocotón.” — Chiefly British; in US English 'pit' is the everyday word for a fruit stone.
- es-MX **vender** (senses[1], 2): “To convince someone to accept an idea or plan.” — Figurative persuasive sense is not needed for an A2 beginner.
- it-IT **sorridere** (senses[1], 2): “To be favorable or propitious to someone.” — Figurative literary sense not needed at A2.
- es-ES **el coche** (senses[1], 2): “A carriage or a section of a train used to transport passengers.” — In everyday Spain Spanish, a train carriage is usually 'vagón'; 'coche' is railway jargon.
- ko-KR **그리다** (senses[1], 2): “To feel a deep desire for someone or something that is not present.” — Literary/poetic sense; A2 learners meet 그리워하다 and 보고 싶다 for 'to miss', not 그리다.

### `sense.wrong` — 395 faults, 348 of them severity 3

- vi-VN **người lớn** (senses[1], 3): “(behavior) Behaving in a mature, responsible way appropriate for an adult.” — Entry POS is noun, not adjective, and the example uses 'một người lớn' (a noun).
- vi-VN **gà mái** (senses[1], 3): “A colloquial and sometimes pejorative term for a woman” — Invented English calque ('gossip hens'); 'gà mái' is not used this way in Vietnamese.
- pl-PL **kalendarz** (senses[1], 3): “A page within a planner or diary that displays the structure” — Invented meaning; 'kalendarz' is the whole book, wall chart, or app, not a single page.
- ko-KR **오리** (senses[1], 3): “(distance) A traditional Korean unit of distance equal to about two kilometers.” — '오 리' (five li) is two separate words, not a lexicalized sense of '오리', and archaic for A2.
- pl-PL **kolejka** (senses[1].definition, 2): “A small train, often a toy or one used in a park” — Too narrow; commonly refers to commuter trains, funiculars, or cable cars alongside toy trains.
- tr-TR **kuru** (senses[2], 3): “Having no money or resources; broke.” — 'Kuru' does not mean 'broke/penniless' (that is 'parasız' or 'çulsuz'); the example is unnatural.

### `field.reading` — 218 faults, 197 of them severity 3

- ja-JP **帽子** (reading, 3): “” — Missing hiragana reading (ぼうし) for a word written with kanji.
- ja-JP **砂糖** (reading, 3): “” — Missing hiragana reading (さとう) for a kanji headword.
- ja-JP **同僚** (reading, 3): “” — Kanji headword is missing its hiragana reading (どうりょう).
- ja-JP **疲れる** (reading, 3): “” — Kanji word is missing its hiragana reading (つかれる).
- ja-JP **窓** (reading, 3): “” — Missing hiragana reading まど for a kanji word.
- zh-CN **记得** (reading, 2): “jì de” — Two-syllable word should be written without a space in pinyin.

### `example.translation` — 302 faults, 20 of them severity 3

- tr-TR **giysi** (senses[0].examples[0].translation, 2): “There is too much clothing in the wardrobe.” — Unnatural English; 'too many clothes' is the natural translation.
- pl-PL **pamiętać** (senses[1].examples[0].translation, 2): “You must keep the keys in mind.” — Unnatural translation; in English one says 'remember to take the keys'.
- zh-CN **打电话** (senses[0].examples[0].translation, 2): “I want to make a phone call to her.” — Stilted translation; 'I want to call her' is natural.
- ar **بَكَى** (senses[0].examples[0].translation, 2): “The baby cried because he is hungry.” — Unnatural tense sequence in English; should be 'because he was hungry'.
- th-TH **ข้าว** (senses[1].examples[0].translation, 2): “Let's go eat a meal.” — Unnatural English calque; 'Let's go eat' or 'Let's go have a meal' is natural.
- id-ID **bersemangat** (senses[0].examples[0].translation, 2): “He is very enthusiastic to go on vacation tomorrow.” — 'Enthusiastic to go' is unidiomatic in English; 'excited to go' is natural.

### `definition.form` — 286 faults, 16 of them severity 3

- pt-BR **mal-educado** (senses[0].definition, 2): “Not polite; someone who lacks good manners” — Defines an adjective as a noun ('someone who lacks...').
- pt-BR **preto** (senses[1].definition, 3): “Something that is very dark, lacking light or brightness.” — Defines an adjective as a thing ('Something that is...').
- es-MX **viejo** (senses[1].definition, 2): “Something that has been used for a long time” — An adjective must be defined as a quality, not as 'something' (a noun).
- pl-PL **niebieski** (senses[0].definition, 2): “The colour of a clear daytime sky.” — Defined as a noun ('The colour...') instead of an adjective ('Having the colour...').
- zh-CN **感冒** (senses[1], 2): “To become sick with a cold.” — Entry POS is noun, so including a verb sense here mismatches the POS.
- pt-BR **amanhã** (senses[0].definition, 2): “The day after today.” — Noun definition for an adverb; should be 'On the day after today.'

### `gloss.wrong` — 230 faults, 63 of them severity 3

- el-GR **βαρύς** (senses[1].glosses, 2): “serious, severe, dull” — 'dull' is not a translation of βαρύς in this sense.
- id-ID **laut** (senses[0].glosses, 2): “sea, ocean” — 'Laut' is 'sea'; 'ocean' is 'samudra' or 'lautan'.
- pt-BR **colocar** (senses[1].glosses, 3): “put on, wear” — 'Colocar' denotes the action of putting clothes on, not the state of wearing them.
- it-IT **la pasta** (senses[1].glosses, 2): “dough, batter” — Contradicts note[1]; liquid batter is 'pastella', whereas 'pasta' is firmer dough.
- el-GR **το φάρμακο** (senses[0].glosses, 2): “medicine, pill, remedy” — 'Pill' is specifically 'χάπι'; 'φάρμακο' means medicine or medication in general.
- th-TH **ถึง** (senses[1].glosses, 2): “up to, until” — Entry POS is verb, but sense 1 is glossed with prepositions ('up to, until').

### `definition.unclear` — 229 faults, 28 of them severity 3

- en-US **luck** (senses[0].definition, 2): “Circunstancias o eventos buenos que ocurren por azar” — 'Luck' can be good or bad (as note 0 itself says), though unmodified it often means good luck.
- ko-KR **시간** (senses[0].definition, 2): “The indefinite continued progress of existence and events.” — Philosophical dictionary definition, not plain A2 learner language; misses 'free time' and 'point in time'.
- vi-VN **tòa nhà** (senses[0].definition, 2): “A structure with walls and a roof, such as a house or” — Contradicts the note and Vietnamese usage: 'tòa nhà' is a large/multi-story building, not a house.
- id-ID **kotor** (senses[1].definition, 2): “Not clean morally, or used to describe earnings before taxes are deducted.” — Conflates two distinct meanings ('foul/corrupt' and 'gross before deductions') into one sense.
- hi-IN **उँगली** (senses[0].definition, 2): “One of the five distinct parts at the end of the hand” — In Hindi, उँगली usually refers to the four fingers excluding the thumb (अँगूठा).
- ko-KR **슬프다** (senses[0].definition, 2): “Feeling disappointed and displeased at heart.” — 'Disappointed and displeased' describes annoyance/disappointment, not sadness or grief; also omits sad things.

### `example.missing-word` — 164 faults, 96 of them severity 3

- de-DE **der Kalender** (senses[1].examples[0].text, 3): “Das Kalenderblatt für den neuen Monat ist sehr bunt.” — Uses the compound 'Kalenderblatt' instead of the headword 'Kalender'.
- th-TH **แต่** (senses[1].examples[0].text, 3): “ฉันรอเขาตั้งแต่เช้า” — Uses the compound word 'ตั้งแต่' instead of the standalone lemma 'แต่'.
- de-DE **der Zug** (senses[1].examples[0].text, 3): “Mach bitte das Fenster zu, hier zieht es.” — Uses the verb 'ziehen' instead of the noun 'Zug'.
- nl-NL **de citroen** (senses[1].examples[0].text, 3): “Ze draagt een jas in een frisse citroenkleur.” — Uses the compound 'citroenkleur' instead of the headword 'citroen'.
- zh-CN **在** (senses[1].examples[0].text, 2): “他正在吃饭。” — Uses the compound word 正在 instead of standalone 在 as the progressive marker.
- zh-CN **家庭** (senses[0], 2): “” — An everyday abstract noun with usage distinctions needs an example sentence.

### `example.wrong-sense` — 174 faults, 38 of them severity 3

- tr-TR **tuvalet** (senses[0].examples[0].text, 2): “Tuvalet nerede?” — Asking where the toilet is asks for the room (sense 1), not the bowl.
- ko-KR **오늘** (senses[0].examples[1].text, 2): “오늘 무슨 요일이에요?” — Here 오늘 is used as a noun (subject with omitted particle), not an adverb.
- zh-CN **对** (senses[1].examples[0].text, 2): “我们面对面坐着。” — Uses the set phrase 面对面, not 对 as an adjective.
- fr-FR **attendre** (senses[2].examples[0].text, 3): “Je m'attends à une réponse positive.” — Uses the reflexive 's'attendre à' instead of transitive 'attendre', contradicting note[0].
- th-TH **ชื่อ** (senses[0].examples[0].text, 2): “คุณชื่ออะไร” — Uses ชื่อ as a verb ('to be named') inside a noun-only entry without explanation.
- hi-IN **छत** (senses[0].examples[0].text, 2): “बारिश में घर की छत से पानी टपक रहा है।” — Water dripping indoors comes from the ceiling (sense 1) as much as the roof.

### `field.pos` — 114 faults, 37 of them severity 3

- ar **بِدُون** (pos, 2): “expression” — Should be classified as a preposition.
- vi-VN **tách** (senses[1], 3): “To divide or separate something into smaller parts or pieces.” — Verb sense included in a noun entry.
- es-ES **sin** (pos, 3): “expression” — 'sin' is a preposition, not an expression.
- pt-BR **amanhã** (senses[1], 2): “Precisamos pensar no amanhã.” — Sense 1 ('o amanhã') is a masculine noun, contradicting the adverb POS and already covered in note 0.
- zh-CN **和** (pos, 2): “expression” — 和 is a conjunction and preposition, not an expression.
- pt-BR **com** (pos, 2): “expression” — 'com' is a basic preposition, not an expression.

### `text.corrupt` — 94 faults, 68 of them severity 3

- en-US **hear** (senses[1].glosses, 2): “oir hablar” — Missing accent mark on 'oír'.
- ja-JP **会う** (notes[0], 3): “會 (meeting) is often confused with 合う” — Uses non-standard traditional character 會 instead of the headword 会う.
- pl-PL **taksówka** (senses[0].examples[0].text, 3): “żeby nie spóższyć się na pociąg.” — Non-existent spelling 'spóższyć'; the correct verb is 'spóźnić'.
- id-ID **lucu** (senses[0].glosses, 2): “funny, amusing, hilarous” — Typo in gloss: 'hilarous' instead of 'hilarious'.
- th-TH **รูปถ่าย** (notes[1], 3): “It refers specifically to a photograph taken with a camera, as requested.” — Leaked AI prompt meta-commentary ('as requested') and restates the definition.
- it-IT **economico** (notes[0], 3): “it is often preferred over the word 'economico' by some” — Self-contradictory gibberish comparing the word to itself.

### `language.wrong` — 45 faults, 29 of them severity 3

- nl-NL **het restaurant** (senses[0].examples[0].text, 3): “We gaan tonight naar een Italiaans restaurant in het centrum.” — Contains the English word 'tonight' instead of Dutch 'vanavond'.
- fr-FR **la campagne** (notes[0], 3): “as in 'vivir à la campagne'.” — 'vivir' is Spanish; the French verb is 'vivre'.
- zh-CN **孤独** (notes[1], 3): “It differs from 单纯 being alone physically (独自)” — Untranslated Chinese word 单纯 ('merely/simple') leaked into an English sentence.
- th-TH **อากาศ** (senses[1].examples[0].text, 3): “เปิดหน้าต่างเพื่อให้มีอากาศ fresh เข้ามา” — Untranslated English word 'fresh' mixed into the Thai example sentence.
- tr-TR **tamir etmek** (senses[0].examples[0].text, 3): “Ustalar kırılan sandalyeyi tamir etmek için workshopa götürdü.” — Uses untranslated English word 'workshopa' instead of Turkish 'atölyeye' or 'tamirhaneye'.
- el-GR **η αδερφή** (notes[0], 2): “αδεφλή or ακόμα the older spelling” — Greek word «ακόμα» leaked into an English note.

### `field.gender` — 27 faults, 18 of them severity 3

- nl-NL **de kalender** (gender, 2): “” — Missing grammatical gender ('common' / de-word).
- ru **родители** (gender, 2): “masculine” — Headword 'родители' is a plural form; labeling it masculine is misleading for learners.
- ru **наличные** (gender, 3): “neuter” — наличные is a pluralia tantum noun and has no singular grammatical gender.
- pl-PL **schody** (gender, 2): “common” — Polish has no 'common' gender; plurale tantum nouns have no singular gender (non-virile plural).
- es-MX **la naranja** (senses[1], 3): “A bright color made by mixing red and yellow.” — As a color noun ('el naranja'), it is masculine, conflicting with headword 'la naranja'.
- ru **часы** (gender, 3): “masculine” — Pluralia tantum nouns ('часы') have no grammatical gender in Russian.

### `field.register` — 15 faults, 1 of them severity 3

- th-TH **ทารก** (register, 2): “neutral” — Should be 'formal', as the entry's own notes state.
- ja-JP **ありがとうございます** (register, 2): “neutral” — Uses polite 'ございます' form; register should be 'polite', as Note 0 itself states.
- hi-IN **ईर्ष्यालु** (register, 3): “neutral” — Formal Sanskritized word; everyday spoken Hindi uses 'जलन' (jalan) constructions.
- hi-IN **उपहार** (register, 2): “neutral” — As the note itself states, उपहार is formal; everyday speech prefers तोहफ़ा or गिफ़्ट.
- el-GR **τα λεφτά** (register, 2): “neutral” — 'λεφτά' is colloquial/informal compared to neutral 'χρήματα'.
- hi-IN **व्यक्ति** (register, 2): “neutral” — The notes correctly explain that व्यक्ति is formal, so register should be 'formal'.

## Kinds the judge named itself

Not in the closed set. Similar names are the same kind under different words; merge them by reading.

| name | faults | of them 3 | first instance |
| --- | ---: | ---: | ---: |
| `new:example.missing` | 18 | 1 | ar **قَابَلَ** (senses, 2): “” — A polysemous verb with three distinct senses needs examples to illustrate usage. |
| `new:homograph-conflation` | 1 | 0 | ja-JP **辛い** (senses, 2): “” — Conflates two distinct Japanese words (からい 'spicy/salty' and つらい 'painful') that share kanji. |
| `new:definition.incomplete` | 1 | 0 | pt-BR **aqui** (senses[0].definition, 2): “In or at the place where the speaker is.” — Also means 'to this place' with verbs of motion (e.g., 'Venha aqui'). |
