# Judge run `full`: the failure inventory

10172 articles judged. **2982 (29%) have a severity-3 fault** (a learner would learn something false, or misses an everyday meaning); 8990 (88%) have a listed fault of severity 2 or 3; 9495 (93%) were corrected at all, minor polish included.

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
| hi-IN | 499 | 23% | 89% | 1.44 |
| id-ID | 502 | 24% | 87% | 1.45 |
| it-IT | 509 | 25% | 89% | 1.48 |
| ja-JP | 517 | 52% | 88% | 1.62 |
| ko-KR | 510 | 23% | 87% | 1.39 |
| nl-NL | 506 | 31% | 91% | 1.61 |
| pl-PL | 510 | 32% | 89% | 1.56 |
| pt-BR | 512 | 27% | 87% | 1.49 |
| ru | 508 | 30% | 88% | 1.46 |
| th-TH | 514 | 34% | 91% | 1.47 |
| tr-TR | 512 | 37% | 92% | 1.74 |
| vi-VN | 511 | 48% | 93% | 1.72 |
| zh-CN | 520 | 20% | 87% | 1.43 |

## Per composing model

| model | articles | with a 3 | faults an article |
| --- | ---: | ---: | ---: |
| gemini-3.1-flash-lite | 5139 | 28% | 1.50 |
| gemini-3.5-flash-lite | 5033 | 31% | 1.52 |

Which model composed a word depends on the vocabulary, so the table above mixes languages. Within the 16 vocabularies where each model composed at least 100 articles (ar, el-GR, en-US, es-ES, es-MX, hi-IN, id-ID, ko-KR, nl-NL, pl-PL, pt-BR, ru, th-TH, tr-TR, vi-VN, zh-CN), the share of articles with each kind:

| model | articles | with a 3 | `note.filler` | `note.false` | `field.ipa` | `note.missing` | `example.unnatural` | `sense.oversplit` | `shortgloss.mismatch` | `sense.missing` |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gemini-3.1-flash-lite | 4064 | 25% | 53.2% | 14.9% | 10.0% | 11.1% | 7.0% | 10.7% | 7.2% | 5.9% |
| gemini-3.5-flash-lite | 4074 | 32% | 51.8% | 10.1% | 17.5% | 9.7% | 11.0% | 9.9% | 7.8% | 3.8% |

## Kinds of fault, by weight (severity summed)

| kind | weight | faults | of them 3 | articles | worst vocabularies (share of their articles) | per composer (share) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `note.filler` | 11015 | 5507 | 1 | 51.5% | hi-IN 61%, ar 60%, tr-TR 59%, el-GR 57% | 3.1-flash-lite 52% / 3.5-flash-lite 51% |
| `note.false` | 3627 | 1336 | 955 | 12.9% | ja-JP 20%, pt-BR 16%, th-TH 15%, el-GR 15% | 3.1-flash-lite 15% / 3.5-flash-lite 10% |
| `field.ipa` | 3500 | 1225 | 1050 | 12.0% | vi-VN 44%, tr-TR 25%, ar 18%, th-TH 17% | 3.1-flash-lite 8% / 3.5-flash-lite 16% |
| `note.missing` | 2324 | 1143 | 38 | 11.2% | de-DE 21%, ru 20%, it-IT 15%, en-US 14% | 3.1-flash-lite 12% / 3.5-flash-lite 10% |
| `example.unnatural` | 2165 | 907 | 351 | 8.7% | nl-NL 13%, ar 13%, tr-TR 13%, pl-PL 12% | 3.1-flash-lite 7% / 3.5-flash-lite 11% |
| `sense.oversplit` | 2091 | 1042 | 7 | 10.2% | id-ID 16%, pl-PL 12%, it-IT 12%, ko-KR 11% | 3.1-flash-lite 10% / 3.5-flash-lite 10% |
| `shortgloss.mismatch` | 1560 | 763 | 34 | 7.5% | en-US 11%, es-ES 10%, de-DE 9%, vi-VN 9% | 3.1-flash-lite 7% / 3.5-flash-lite 8% |
| `sense.missing` | 1214 | 508 | 198 | 5.0% | pt-BR 8%, es-MX 8%, fr-FR 7%, es-ES 6% | 3.1-flash-lite 6% / 3.5-flash-lite 4% |
| `sense.wrong` | 1144 | 397 | 350 | 3.9% | id-ID 6%, nl-NL 6%, vi-VN 5%, th-TH 5% | 3.1-flash-lite 3% / 3.5-flash-lite 4% |
| `sense.marginal` | 1139 | 563 | 13 | 5.5% | en-US 9%, fr-FR 9%, es-ES 8%, es-MX 8% | 3.1-flash-lite 5% / 3.5-flash-lite 6% |
| `field.reading` | 639 | 220 | 199 | 2.2% | ja-JP 37%, zh-CN 6%, nl-NL 0% | 3.1-flash-lite 4% / 3.5-flash-lite 0% |
| `example.translation` | 626 | 303 | 20 | 2.9% | en-US 5%, ar 5%, pt-BR 4%, hi-IN 4% | 3.1-flash-lite 3% / 3.5-flash-lite 3% |
| `definition.form` | 588 | 286 | 16 | 2.6% | pt-BR 5%, zh-CN 4%, en-US 4%, ko-KR 4% | 3.1-flash-lite 4% / 3.5-flash-lite 2% |
| `gloss.wrong` | 523 | 230 | 63 | 2.2% | en-US 5%, id-ID 3%, ru 3%, es-MX 3% | 3.1-flash-lite 2% / 3.5-flash-lite 3% |
| `definition.unclear` | 488 | 230 | 28 | 2.2% | es-MX 3%, nl-NL 3%, pt-BR 3%, es-ES 3% | 3.1-flash-lite 2% / 3.5-flash-lite 2% |
| `example.missing-word` | 427 | 165 | 97 | 1.6% | zh-CN 4%, ja-JP 4%, de-DE 3%, nl-NL 3% | 3.1-flash-lite 2% / 3.5-flash-lite 1% |
| `example.wrong-sense` | 389 | 175 | 39 | 1.7% | tr-TR 4%, en-US 3%, id-ID 2%, fr-FR 2% | 3.1-flash-lite 1% / 3.5-flash-lite 2% |
| `field.pos` | 267 | 115 | 37 | 1.1% | zh-CN 3%, vi-VN 2%, ko-KR 2%, en-US 2% | 3.1-flash-lite 1% / 3.5-flash-lite 1% |
| `text.corrupt` | 256 | 94 | 68 | 0.9% | el-GR 2%, ar 2%, nl-NL 2%, tr-TR 2% | 3.1-flash-lite 0% / 3.5-flash-lite 2% |
| `language.wrong` | 119 | 45 | 29 | 0.4% | en-US 2%, it-IT 1%, th-TH 1%, fr-FR 1% | 3.1-flash-lite 0% / 3.5-flash-lite 1% |
| `field.gender` | 72 | 27 | 18 | 0.3% | ru 1%, hi-IN 1%, pl-PL 1%, de-DE 1% | 3.1-flash-lite 0% / 3.5-flash-lite 0% |
| `field.register` | 31 | 15 | 1 | 0.1% | hi-IN 1%, th-TH 0%, ja-JP 0%, el-GR 0% | 3.1-flash-lite 0% / 3.5-flash-lite 0% |

## Each kind, quoted

### `note.filler` — 5507 faults, 1 of them severity 3

- en-US **secret** (notes[0], 2): “Un 'secret' es algo que no quieres que otras personas sepan.” — Merely repeats the definition instead of giving useful collocations.
- tr-TR **bira** (notes[0], 2): “Used as a general term for all types of beer, both domestic and imported.” — Pure filler; should be empty or note the initial stress.
- de-DE **hassen** (notes, 2): “While 'hassen' is a very strong word in German, it is sometimes” — Notes 0 and 1 repeat the exact same point and partially contradict each other.
- hi-IN **दूध** (notes[0], 2): “It is almost always masculine.” — Restates the gender field (and hedges inaccurately: it is always masculine).
- en-US **cow** (notes[0], 2): “Como verbo, 'to cow' significa intimidar o acobardar a alguien” — Rare C2 verb sense is irrelevant for an A2 noun entry; plural 'cattle' is useful.
- pt-BR **o vestido** (notes[0], 2): “In Portuguese, 'vestido' strictly means a dress.” — Restates the gloss; English speakers have no reason to confuse 'vestido' with 'roupa'.

### `note.false` — 1336 faults, 955 of them severity 3

- pl-PL **stopa** (senses[1].examples[0], 3): “undergoes a consonant shift (t -> ci) in the locative case, becoming 'stopie'.” — False grammar claim in example note: 'p' softens to 'pi' in 'stopie', not 't' to 'ci'.
- pt-BR **cair** (notes[0], 3): “the rest of the conjugation follows regular -ir patterns.” — False grammar claim: 'cair' has hiatus irregularities across tenses (cai, caímos, caem, caía, caiu).
- zh-CN **见面** (notes[0], 3): “This is an inseparable verb-object compound, meaning it cannot take a direct” — Contradiction in terms: 见面 is a separable verb (离合词), e.g., 见过面, 见一面.
- ko-KR **등** (notes[1], 3): “When using '등' as a suffix for lists, always leave a space” — Contradictory grammar: suffixes do not take a space; 등 is a bound noun (의존 명사).
- fr-FR **parce que** (senses[0].examples[0], 3): “Note that 'parce que' becomes 'parc'qu'' before a vowel” — Standard mandatory spelling before a vowel is 'parce qu'', not 'parc'qu''.
- el-GR **ο ξένος** (notes[1], 3): “the adjective form which simply means 'foreign' or 'strange'” — As an adjective, 'ξένος' means 'foreign' or 'belonging to someone else', not 'strange' ('παράξενος').

### `field.ipa` — 1225 faults, 1050 of them severity 3

- vi-VN **bài học** (ipa, 3): “/1baːj˨˩ 1hɔwk͡p̚˧˥/” — Contains stray digits '1' and gives wrong tone (sắc instead of nặng) for 'học'.
- ar **وَرَقَة** (ipa, 3): “/waˈra.qa/” — Wrong stress: three light syllables take initial stress /ˈwa.ra.qa/.
- th-TH **สนามบิน** (ipa, 2): “” — Missing IPA transcription.
- tr-TR **çalışma masası** (ipa, 3): “/tʃaɫɯˈma maˈsasɯ/” — Missing /ʃ/ sound in 'çalışma' and wrong stress placement.
- ar **جَائِع** (ipa, 3): “/ˈdʒaː.iʕ/” — Missing the glottal stop /ʔ/ represented by the medial hamza (ئ).
- tr-TR **havalimanı** (ipa, 2): “/ha.va.li.ma.nɯ/” — Missing stress mark in IPA (/ha.va.li.maˈnɯ/).

### `note.missing` — 1143 faults, 38 of them severity 3

- it-IT **il cugino** (notes, 2): “” — Should note that the definite article is dropped with singular possessive adjectives ('mio cugino').
- hi-IN **शाम** (notes, 2): “” — Missing the helpful grammar note on using 'शाम को' for 'in the evening'.
- en-US **cake** (notes, 2): “” — Missing essential A2 countability note (countable for whole cakes, uncountable for portions).
- ko-KR **바쁘다** (notes, 2): “” — Missing essential grammar note that 바쁘다 drops ㅡ before -아/어 (바빠요).
- de-DE **anschauen** (notes, 2): “” — Missing note on separable prefix 'an-' and common reflexive dative usage 'sich etwas anschauen'.
- ar **قَرَأَ** (notes, 2): “” — Needs a note on the irregular hamza seat in the imperfect (يَقْرَأُ) and imperative (اِقْرَأْ).

### `example.unnatural` — 907 faults, 351 of them severity 3

- ar **عِيد مِيلَاد** (senses[0].examples[0].text, 2): “يَوْمُ عِيدِ مِيلَادِي غَدًا.” — يَوْمُ is redundant before عِيدِ مِيلَادِي; native speakers say عِيدُ مِيلَادِي غَدًا.
- ru **кольцо** (senses[1].examples[0].text, 2): “Дым поднялся в воздух кольцо за кольцом.” — Awkward aspect and phrasing; Russian naturally says 'выпускать кольца дыма' or 'сесть в кольцо'.
- nl-NL **zijn** (senses[1].examples[0].text, 2): “De sleutels zijn op tafel.” — Dutch uses positional verbs ('De sleutels liggen op tafel'), not 'zijn', for objects on surfaces.
- ar **أَحْيَانًا** (senses[0].examples[1].text, 3): “تَمْطُرُ فِي الصَّيْفِ أَحْيَانًا.” — Wrong verb form and vocalization; 'to rain' is Form IV أَمْطَرَ (تُمْطِرُ), not تَمْطُرُ.
- zh-CN **想念** (senses[1].examples[0].text, 2): “老师一直在想念着他毕业的学生们。” — 想念 is rarely used with 着, and 学生们 after a modifier is unnatural.
- it-IT **la farmacia** (senses[0].examples[0].text, 2): “Devo andare alla farmacia a comprare la medicina.” — Italian normally uses 'andare in farmacia' for going to the pharmacy in general.

### `sense.oversplit` — 1042 faults, 7 of them severity 3

- id-ID **rahasia** (senses, 2): “” — Senses 0 and 1 are both just the noun 'secret'; merge them.
- th-TH **เรียนรู้** (senses, 2): “To gain understanding or insight through observation or practice.” — Senses 0 and 1 are shades of the same meaning (to learn/acquire knowledge).
- de-DE **der Onkel** (senses, 2): “The husband or partner of one's aunt.” — Both parent's brother and aunt's husband correspond to the single concept 'uncle' in both languages.
- id-ID **tahu** (senses[1], 2): “(skill) To understand how to do something or to have a skill.” — In the example 'tahu cara', 'cara' means 'how to'; 'tahu' itself still just means 'to know'.
- tr-TR **hatırlamak** (senses, 2): “(mind) To keep something in your mind and not forget it.” — Oversplit; 'keep in mind' in Turkish is usually 'aklında tutmak' or 'unutmamak', not a distinct sense.
- zh-CN **路** (senses, 2): “” — Sense 0 mixes physical roads with 'on the way', while sense 1 also includes 'route'.

### `shortgloss.mismatch` — 763 faults, 34 of them severity 3

- pt-BR **gentil** (shortGloss, 2): “kind; polite; charming” — 'Charming' is not in the senses and is not a standard meaning of 'gentil'.
- es-MX **fuerte** (shortGloss, 2): “strong; loud; tough” — 'Tough' is in shortGloss, but no sense or gloss covers it.
- id-ID **perawat** (shortGloss, 2): “nurse” — Omits 'caregiver' from sense 1.
- es-MX **el pez** (shortGloss, 3): “fish (living); fish (as food)” — 'Pez' only means a living fish; fish as food is 'pescado'.
- vi-VN **chuột** (shortGloss, 2): “mouse; rat” — Does not clearly reflect the second sense (computer mouse).
- es-MX **caer** (shortGloss, 2): “to fall; to drop; to tumble” — Does not cover sense 1 (to make an impression / to be liked).

### `sense.missing` — 508 faults, 198 of them severity 3

- pt-BR **o chefe** (senses, 2): “” — Missing the everyday sense of 'chef' / head cook in a restaurant.
- id-ID **hangat** (senses, 2): “” — Missing the common figurative sense 'warm, friendly, cordial' (e.g., sambutan hangat).
- zh-CN **长** (senses, 3): “” — Missing the everyday temporal sense 'long (in time)'.
- es-MX **el menú** (senses, 2): “” — Missing the everyday computing/phone screen sense of 'menú'.
- vi-VN **bắt** (senses, 3): “” — Missing the very common everyday sense 'to force / make someone do something'.
- ar **عِنْدَ** (senses, 2): “” — Missing the common everyday temporal sense ('at, upon, when', e.g., عند الوصول).

### `sense.wrong` — 397 faults, 350 of them severity 3

- ko-KR **원피스** (senses[1], 3): “(garment) A swimsuit or garment in which the top and bottom are” — Contradicts note [0]; alone, 원피스 means a dress, not a swimsuit or jumpsuit.
- pt-BR **com ciúme** (senses[1], 3): “(envy) Feeling unhappy or bitter because someone else has something you want.” — As Note 1 states, 'com ciúme' is not used for envy ('com inveja'); contradictions.
- th-TH **น้ำ** (senses[1].definition, 2): “The liquid extract or juice of fruits or vegetables.” — น้ำ alone means any liquid or fluid; 'juice' is only in compounds like น้ำส้ม.
- el-GR **γελώ** (senses[1], 3): “To smile or look happy without making sound.” — 'γελώ' means to laugh; 'to smile' without sound is 'χαμογελώ'.
- es-MX **la boda** (senses[1], 3): “(status) The legal union between two people.” — 'Boda' means the wedding event, not the legal state of marriage ('matrimonio').
- th-TH **ไอ** (senses[0], 2): “(symptom) The act of pushing air out of the throat” — As a noun, ไอ means 'vapor/steam'. 'Cough' is a verb (or อาการไอ as noun).

### `sense.marginal` — 563 faults, 13 of them severity 3

- it-IT **sorridere** (senses[1], 2): “To be favorable or propitious to someone.” — Figurative literary sense not needed at A2.
- es-ES **el coche** (senses[1], 2): “A carriage or a section of a train used to transport passengers.” — In everyday Spain Spanish, a train carriage is usually 'vagón'; 'coche' is railway jargon.
- ko-KR **그리다** (senses[1], 2): “To feel a deep desire for someone or something that is not present.” — Literary/poetic sense; A2 learners meet 그리워하다 and 보고 싶다 for 'to miss', not 그리다.
- vi-VN **ảnh** (senses[1], 2): “(reflection) An optical image reflected in a mirror or on a surface.” — Standalone 'ảnh' rarely means reflection in everyday Vietnamese; it belongs to compounds like 'phản ảnh'.
- ru **сухой** (senses[2], 2): “(person) Lean and thin in build.” — Literary/dated sense; 'сухощавый' or 'худой' is standard at A2.
- vi-VN **cơn đau** (senses[1], 2): “(emotion) A strong feeling of emotional sadness or suffering.” — Emotional pain is normally 'nỗi đau'; 'cơn đau' is for physical bouts/pangs of pain.

### `field.reading` — 220 faults, 199 of them severity 3

- zh-CN **T恤衫** (reading, 2): “T xù shān” — Should give full pinyin pronunciation (tī xù shān) for the Latin letter T.
- ja-JP **払う** (reading, 3): “” — Missing hiragana reading for a Japanese word with kanji.
- ja-JP **帽子** (reading, 3): “” — Missing hiragana reading (ぼうし) for a word written with kanji.
- ja-JP **砂糖** (reading, 3): “” — Missing hiragana reading (さとう) for a kanji headword.
- ja-JP **同僚** (reading, 3): “” — Kanji headword is missing its hiragana reading (どうりょう).
- ja-JP **疲れる** (reading, 3): “” — Kanji word is missing its hiragana reading (つかれる).

### `example.translation` — 303 faults, 20 of them severity 3

- tr-TR **akşam** (senses[1].examples[0].translation, 2): “It is dusk, the air is getting dark.” — 'Hava kararıyor' means 'it is getting dark', not literally 'the air is getting dark'.
- tr-TR **çorba** (senses[0].examples[0].translation, 2): “We drank a hot lentil soup before dinner in the evening.” — Calqued 'drank soup' and redundant 'before dinner in the evening'.
- pl-PL **nosić** (senses[0].examples[0], 2): “Ona nosi czerwoną sukienkę. — She is wearing a red dress.” — 'nosi' means wears habitually; 'mieć na sobie' is used for wearing right now.
- zh-CN **掉** (senses[0].examples[0].translation, 2): “My phone dropped on the ground.” — Unnatural English; 'fell on the ground' or 'dropped to the ground' is natural.
- ar **بَكَى** (senses[0].examples[0].translation, 2): “The baby cried because he is hungry.” — Unnatural tense sequence in English; should be 'because he was hungry'.
- th-TH **เนื้อปลา** (senses[0].examples[0].translation, 2): “This fish meat is very fresh.” — Omits จานนี้ ('this dish/plate of') from the translation.

### `definition.form` — 286 faults, 16 of them severity 3

- it-IT **economico** (senses[1].definition, 2): “Something designed to save money or resources during use.” — Defines an adjective as a noun ('Something designed...').
- pt-BR **mal-educado** (senses[0].definition, 2): “Not polite; someone who lacks good manners” — Defines an adjective as a noun ('someone who lacks...').
- pt-BR **preto** (senses[1].definition, 3): “Something that is very dark, lacking light or brightness.” — Defines an adjective as a thing ('Something that is...').
- es-MX **viejo** (senses[1].definition, 2): “Something that has been used for a long time” — An adjective must be defined as a quality, not as 'something' (a noun).
- pl-PL **niebieski** (senses[0].definition, 2): “The colour of a clear daytime sky.” — Defined as a noun ('The colour...') instead of an adjective ('Having the colour...').
- zh-CN **感冒** (senses[1], 2): “To become sick with a cold.” — Entry POS is noun, so including a verb sense here mismatches the POS.

### `gloss.wrong` — 230 faults, 63 of them severity 3

- zh-CN **傍晚** (senses[0].glosses, 2): “evening, dusk, nightfall” — 'Evening' is too broad and overlaps with 晚上; 'dusk' or 'late afternoon' is primary.
- ru **пустой** (senses[0].glosses, 2): “empty, vacant, hollow” — 'Hollow' is 'полый' in Russian; 'пустой' means empty inside, not hollow by structure.
- th-TH **ฟัง** (senses[0].glosses, 3): “listen, hear” — 'Hear' translates ได้ยิน, not ฟัง.
- pt-BR **o deserto** (senses[1].glosses, 2): “wasteland, deserted place” — 'Wasteland' implies ruined or barren land, not a temporarily empty street; 'ghost town' fits better.
- ru **ждать** (senses[0].glosses, 3): “to wait, to stay” — 'ждать' does not mean 'to stay' (that is 'оставаться'); omits 'to wait for'.
- hi-IN **स्वस्थ** (senses[1].glosses, 2): “wholesome, healthful” — Lacks the most natural everyday translation 'healthy'.

### `definition.unclear` — 230 faults, 28 of them severity 3

- el-GR **ο ξάδερφος** (senses[0].definition, 2): “The child of one's uncle or aunt.” — Defines any cousin, but the masculine noun ο ξάδερφος refers specifically to a male cousin.
- it-IT **il panino** (senses[0].definition, 2): “consisting of two slices of bread or a split roll” — Contradicts the note; a sandwich made with sliced loaf bread is a 'tramezzino' or 'toast'.
- pt-BR **machucar** (senses[1].definition, 3): “To feel emotional pain or be saddened by someone's words or actions.” — Defines the transitive verb as 'to feel pain' instead of 'to cause pain'.
- ko-KR **샤워** (senses[0].definition, 2): “A stream of water sprayed on a person to wash themselves.” — Defines the water spray rather than the act of washing, which the example shows.
- el-GR **το αεροπλάνο** (senses[0].definition, 2): “and a weight greater than that of the air it displaces.” — Overly technical physics phrasing for an A2 learner's dictionary.
- tr-TR **ile** (senses[2].definition, 3): “Connecting words or clauses in the sense of 'and'.” — 'İle' as a conjunction only connects nouns/pronouns, never clauses.

### `example.missing-word` — 165 faults, 97 of them severity 3

- id-ID **telur** (senses[1].examples[0].text, 2): “Kura-kura bertelur di pasir pantai.” — Uses the derived verb 'bertelur' instead of the noun 'telur'.
- tr-TR **olmak** (senses[3].examples[0].text, 3): “Ben evdeyim.” — Example uses the copula suffix (-yim), not the verb 'olmak'.
- pl-PL **próbować** (senses[0].examples[0].text, 2): “Muszę spróbować tej zupy, bo pachnie wyśmienicie.” — Uses the perfective verb 'spróbować' instead of the headword 'próbować'.
- pl-PL **dom** (senses, 2): “” — Senses lack examples, though 'dom' has important prepositional idioms ('w domu' vs 'do domu').
- th-TH **ถือ** (senses[1].examples[0].text, 3): “เขานับถือศาสนาพุทธ” — Uses the distinct compound verb นับถือ instead of the headword ถือ.
- de-DE **der Kalender** (senses[1].examples[0].text, 3): “Das Kalenderblatt für den neuen Monat ist sehr bunt.” — Uses the compound 'Kalenderblatt' instead of the headword 'Kalender'.

### `example.wrong-sense` — 175 faults, 39 of them severity 3

- pt-BR **a luz** (senses[0].examples[0].text, 2): “Apague a luz antes de sair do quarto.” — Turning off a room light illustrates sense 1 (electric light/lamp), not sense 0 (general brightness).
- el-GR **το ζώο** (senses[1].examples[0].text, 2): “Μη συμπεριφέρεσαι σαν ζώο!” — This uses a simile with the literal 'animal' sense, not the person/insult sense.
- it-IT **dimenticare** (senses[0].examples[0].text, 2): “Ho dimenticato le chiavi sul tavolo.” — Example under sense 0 (memory) actually shows sense 1 (leaving belongings behind).
- vi-VN **cà phê** (senses[1].examples[0].text, 2): “Chúng ta gặp nhau ở quán cà phê nhé?” — Uses 'quán cà phê' (shop of coffee) instead of 'cà phê' alone meaning a café.
- tr-TR **yabancı** (senses[1].examples[0].text, 2): “Bu şehirde çok fazla yabancı turist var.” — Uses 'yabancı' as an attributive adjective ('foreign tourists'), not a noun ('foreigner').
- tr-TR **soğuk** (senses[2].examples[0].text, 2): “Yeni komşumuz bana biraz soğuk davrandı.” — 'soğuk davrandı' uses 'soğuk' adverbially (acted coldly), not as an adjective.

### `field.pos` — 115 faults, 37 of them severity 3

- ja-JP **ここ** (pos, 3): “adv” — ここ is a demonstrative pronoun (or noun), not an adverb, as notes[2] itself says.
- th-TH **พยาบาล** (senses[1], 3): “(care) To look after, nurse, or tend to someone” — Entry POS is noun, but sense 1 is a verb (and rare in everyday A2 Thai).
- es-ES **blanco** (senses[1], 3): “A target or objective in a shooting game or sport.” — Noun sense included in an adjective entry.
- nl-NL **zonder** (pos, 2): “expression” — 'zonder' is a preposition (or conjunction with 'te'/'dat'), not a general expression.
- es-MX **pero** (pos, 2): “expression” — 'Pero' is a coordinating conjunction ('conj'), as its own definition states.
- ar **بِدُون** (pos, 2): “expression” — Should be classified as a preposition.

### `text.corrupt` — 94 faults, 68 of them severity 3

- en-US **check** (senses[2].glosses, 2): “control, revision” — Missing accent mark on Spanish word 'revisión'.
- ru **писать** (notes[0], 2): “писа́ть карт́ину” — Misplaced stress mark on consonant т instead of vowel и.
- th-TH **ตลก** (senses[0].examples[0].text, 3): “หนังเรื่องนี้ตลกมากจนฉันหัว” — Truncated word at end: 'หัว' (head) instead of 'หัวเราะ' (laugh).
- en-US **hear** (senses[1].glosses, 2): “oir hablar” — Missing accent mark on 'oír'.
- ja-JP **会う** (notes[0], 3): “會 (meeting) is often confused with 合う” — Uses non-standard traditional character 會 instead of the headword 会う.
- pl-PL **taksówka** (senses[0].examples[0].text, 3): “żeby nie spóższyć się na pociąg.” — Non-existent spelling 'spóższyć'; the correct verb is 'spóźnić'.

### `language.wrong` — 45 faults, 29 of them severity 3

- it-IT **giusto** (senses[0].definition, 3): “Conforme a la verdad o a la razón; exacto.” — Definition is written in Spanish instead of English.
- th-TH **บริษัท** (senses[0].examples[0].text, 3): “ฉันทำงานอยู่ที่บริษัทนี้มาห้า years แล้ว” — Contains the English word 'years' instead of Thai ปี.
- zh-CN **花** (senses[0].examples[0].text, 3): “春天到了， park 里开满了花。” — Contains the English word 'park' instead of Chinese 公园.
- nl-NL **het restaurant** (senses[0].examples[0].text, 3): “We gaan tonight naar een Italiaans restaurant in het centrum.” — Contains the English word 'tonight' instead of Dutch 'vanavond'.
- fr-FR **la campagne** (notes[0], 3): “as in 'vivir à la campagne'.” — 'vivir' is Spanish; the French verb is 'vivre'.
- th-TH **อากาศ** (senses[1].examples[0].text, 3): “เปิดหน้าต่างเพื่อให้มีอากาศ fresh เข้ามา” — Untranslated English word 'fresh' mixed into the Thai example sentence.

### `field.gender` — 27 faults, 18 of them severity 3

- pt-BR **o chefe** (gender, 3): “masculine” — 'chefe' is a common-gender noun ('o/a chefe'), as the note itself says.
- ru **наличные** (gender, 3): “neuter” — наличные is a pluralia tantum noun and has no singular grammatical gender.
- ar **بَعْدَ الظُّهْر** (gender, 2): “masculine” — Adverbial prepositional phrase, not an inflecting masculine noun.
- nl-NL **de kalender** (gender, 2): “” — Missing grammatical gender ('common' / de-word).
- pl-PL **schody** (gender, 2): “common” — Polish has no 'common' gender; plurale tantum nouns have no singular gender (non-virile plural).
- es-MX **la naranja** (senses[1], 3): “A bright color made by mixing red and yellow.” — As a color noun ('el naranja'), it is masculine, conflicting with headword 'la naranja'.

### `field.register` — 15 faults, 1 of them severity 3

- ja-JP **ありがとうございます** (register, 2): “neutral” — Uses polite 'ございます' form; register should be 'polite', as Note 0 itself states.
- th-TH **ทารก** (register, 2): “neutral” — Should be 'formal', as the entry's own notes state.
- zh-CN **恐惧** (register, 2): “neutral” — The note rightly says it is formal, yet the register field says neutral.
- hi-IN **ईर्ष्यालु** (register, 3): “neutral” — Formal Sanskritized word; everyday spoken Hindi uses 'जलन' (jalan) constructions.
- hi-IN **उपहार** (register, 2): “neutral” — As the note itself states, उपहार is formal; everyday speech prefers तोहफ़ा or गिफ़्ट.
- el-GR **τα λεφτά** (register, 2): “neutral” — 'λεφτά' is colloquial/informal compared to neutral 'χρήματα'.

## Kinds the judge named itself

Not in the closed set. Similar names are the same kind under different words; merge them by reading.

| name | faults | of them 3 | first instance |
| --- | ---: | ---: | ---: |
| `new:example.missing` | 18 | 1 | ar **قَابَلَ** (senses, 2): “” — A polysemous verb with three distinct senses needs examples to illustrate usage. |
| `new:homograph-conflation` | 1 | 0 | ja-JP **辛い** (senses, 2): “” — Conflates two distinct Japanese words (からい 'spicy/salty' and つらい 'painful') that share kanji. |
| `new:definition.incomplete` | 1 | 0 | pt-BR **aqui** (senses[0].definition, 2): “In or at the place where the speaker is.” — Also means 'to this place' with verbs of motion (e.g., 'Venha aqui'). |
