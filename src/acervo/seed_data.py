"""Disposable demonstration vocabulary, and the shape it is written in.

Content is illustrative, not curated learning material. It exists so a freshly rebuilt account has
something to look at, and so the interface can be exercised without spending a model call.

Records here are in storage shape — snake_case, exactly the columns — because that is the shape they
were written in and re-typing four hundred lines of literals into the wire's casing would be a change
with no reader. `admin.py seed` projects them through the same table a pull uses.
"""

from __future__ import annotations

import hashlib

from acervo.clips.ids import clip_example_id

STAMP = "2026-08-28T12:00:00.000Z"
EDITOR = "acervoseed"


def at(day: str) -> str:
    """An instant in the demo year, in the format every Acervo timestamp uses."""
    return f"2026-{day}T12:00:00.000Z"


STARTER_TOPICS = (
    ("emotions", "Emotions", "💭"),
    ("actions", "Actions", "⚡"),
    ("nature", "Nature", "🌿"),
    ("culture", "Culture", "🎭"),
    ("food", "Food", "🍽️"),
    ("health", "Health", "🩺"),
    ("appearance", "Appearance", "👤"),
    ("technology", "Technology", "💻"),
    ("travel", "Travel", "🧭"),
    ("slang", "Slang", "💬"),
    ("social", "Social", "🤝"),
    ("places", "Places", "📍"),
    ("misc", "Misc", "📌"),
)

# The languages the demonstration vocabulary is in, and how each is presented. A language has to be
# configured before a word in it can be captured, so seeding these is what makes the seeded account
# usable rather than merely populated.
STARTER_VOCABULARIES = (
    ("es", "es", ["en"], "en", "Spanish", "\U0001F1EA\U0001F1F8"),
    ("en", "en", ["ru"], "ru", "English", "\U0001F1EC\U0001F1E7"),
    ("ru", "ru", ["en"], "en", "Russian", "\U0001F1F7\U0001F1FA"),
    ("zh-Hans", "en", ["ru", "en"], "ru", "Chinese (Simplified)", "\U0001F1E8\U0001F1F3"),
)

# Disposable demonstration vocabulary. Content is illustrative, not curated learning material.
DEMO_LEXEMES: tuple[dict, ...] = (
    {
        "key": "picar", "language": "es", "headword": "picar", "lemma": "picar",
        "primary_gloss": "to sting", "emotion": "wincing slightly, as if something just bit you",
        "ipa": "/piˈkaɾ/", "pos": "verb", "register": "neutral", "emoji": "🌶️",
        "topics": ["food", "health", "actions"], "status": "active",
        "short_gloss": "to itch; to sting; to chop; to nibble",
        "created_at": at("02-11"), "edited_at": at("08-24"),
        "notes": [
            "One of the most overloaded verbs in everyday Spanish — the sense is almost always carried by the object, not the verb.",
            "In Mexico, picar for “to be spicy” is far more common than ser picante.",
            "picar algo before dinner is the standard way to say “have a nibble”; the noun el picoteo follows from it.",
        ],
        "attestations": [
            {"key": "salsa", "text": "cuidado que esa salsa pica un monton eh",
             "source_kind": "conversation", "source_title": "Course chat", "captured_at": at("02-11")},
            {"key": "pisto", "text": "Se pican las verduras en dados de un centimetro y se reservan.",
             "translation": "The vegetables are diced into one-centimetre cubes and set aside.",
             "source_kind": "web", "source_title": "Receta — pisto manchego",
             "source_url": "https://example.com/pisto", "captured_at": at("03-03")},
        ],
        "senses": [
            {"key": "itch", "definition": "Producir una sensación de comezón o escozor en alguna parte del cuerpo.",
             "glosses": [{"lang": "en", "terms": ["to itch", "to feel prickly"]}],
             "examples": [
                 {"key": "nariz", "text": "Me pica la nariz, creo que voy a estornudar.",
                  "translation": "My nose itches, I think I’m going to sneeze.",
                  "origin": "tatoeba", "matched": "pica", "matched_translation": "itches",
                  "emotion": "twitchy and restless, a sneeze building behind the words"},
                 {"key": "lana", "text": "La lana de este jersey pica muchísimo.",
                  "translation": "The wool of this jumper is really itchy.",
                  "origin": "tatoeba", "matched": "pica", "matched_translation": "itchy",
                  "emotion": "exasperated, tugging at the collar of the jumper"},
             ],
             "images": [{"key": "itch", "prompt": "A hand hovering near an itchy nose, flat vector, bold shapes, limited palette, no text",
                         "style_id": "flat-vector", "seed": 184521}]},
            {"key": "spicy", "definition": "Dicho de un alimento: producir una sensación ardiente en la boca.",
             "domain": "cooking", "glosses": [{"lang": "en", "terms": ["to be spicy", "to be hot"]}],
             "examples": [
                 {"key": "salsa", "text": "¿Te pica mucho la salsa?",
                  "translation": "Is the sauce very spicy for you?",
                  "origin": "attestation", "attestation": "salsa", "matched": "pica",
                  "matched_translation": "spicy",
                  "video": ("Easy Spanish — Comiendo en un mercado", "Easy Spanish", 461, 468)},
             ],
             "images": [{"key": "spicy", "prompt": "A chilli pepper glowing on a spoon of red sauce, soft storybook gouache, warm light, no text",
                         "style_id": "storybook", "seed": 771402}]},
            {"key": "chop", "definition": "Cortar algo en trozos muy pequeños con un cuchillo.",
             "domain": "cooking", "glosses": [{"lang": "en", "terms": ["to chop", "to mince", "to dice"]}],
             "examples": [
                 {"key": "cebolla", "text": "Pica la cebolla bien fina antes de sofreírla.",
                  "translation": "Chop the onion very finely before frying it.",
                  "origin": "attestation", "attestation": "pisto", "matched": "Pica",
                  "matched_translation": "Chop", "model_id": "demo-model"},
             ]},
            {"key": "nibble", "definition": "Comer una cantidad pequeña de algo, generalmente entre horas.",
             "glosses": [{"lang": "en", "terms": ["to nibble", "to snack"]}],
             "examples": [
                 {"key": "cenar", "text": "Vamos a picar algo antes de cenar.",
                  "translation": "Let’s have a nibble before dinner.",
                  "origin": "llm", "model_id": "demo-model",
                  "matched": "picar", "matched_translation": "nibble",
                  "note": "Waiting for review — check whether “nibble” reads as too British."},
             ]},
            {"key": "sting", "definition": "Dicho de un insecto o de un ave: morder o herir con el pico o el aguijón.",
             "glosses": [{"lang": "en", "terms": ["to bite", "to sting"]}],
             "examples": [
                 {"key": "mosquitos", "text": "Me picaron los mosquitos toda la noche.",
                  "translation": "The mosquitoes bit me all night.",
                  "origin": "tatoeba", "matched": "picaron", "matched_translation": "bit"},
             ]},
        ],
        "study": {"reps": 21, "lapses": 4, "stability": 18.3, "difficulty": 8.4,
                  "retrievability": 0.71, "last_review": at("08-22")},
    },
    {
        "key": "desmayarse", "language": "es", "headword": "desmayarse", "lemma": "desmayarse",
        "primary_gloss": "to faint", "emotion": "alarmed, the word itself going light-headed",
        "ipa": "/desmaˈjaɾse/", "pos": "verb", "register": "neutral", "emoji": "😵‍💫",
        "topics": ["health", "actions"], "status": "active",
        "created_at": at("01-14"), "edited_at": at("06-02"),
        "notes": ["Always pronominal in this meaning. Desmayar without the pronoun is literary and means “to lose heart”."],
        "attestations": [
            {"key": "criatura", "text": "Me desmaye cuando vi a la aterradora criatura",
             "source_kind": "book", "source_title": "Cuentos de la selva — Horacio Quiroga",
             "captured_at": at("01-14")},
        ],
        "senses": [
            {"key": "faint", "definition": "Perder el sentido y el conocimiento de forma temporal.",
             "domain": "medicine", "glosses": [{"lang": "en", "terms": ["to faint", "to pass out"]}],
             "examples": [
                 {"key": "criatura", "text": "Me desmayé cuando vi a la aterradora criatura.",
                  "translation": "I fainted when I saw the terrifying creature.",
                  "origin": "attestation", "attestation": "criatura", "matched": "desmayé",
                  "matched_translation": "fainted"},
                 {"key": "directo", "text": "Se desmayó en pleno directo, delante de las cámaras.",
                  "translation": "She passed out live on air, in front of the cameras.",
                  "origin": "subtitle", "matched": "desmayó", "matched_translation": "passed out", "clip": "seg_4b1c7d2e9a350f68cd41",
                  "video": ("DW Español — Informe semanal", "DW Español", 252, 258)},
             ],
             "images": [{"key": "swoon", "prompt": "A figure swooning backwards, stars circling, 1970s sci-fi paperback, muted print palette, no text",
                         "style_id": "retro-futurist", "seed": 991204}]},
            {"key": "overcome", "definition": "Quedar sobrecogido por una emoción muy intensa.",
             "glosses": [{"lang": "en", "terms": ["to be overcome", "to swoon"]}],
             "examples": [
                 {"key": "emocion", "text": "Casi me desmayo de la emoción.",
                  "translation": "I almost swooned with excitement.",
                  "origin": "tatoeba", "matched": "desmayo", "matched_translation": "swooned"},
             ]},
        ],
        "study": {"reps": 14, "lapses": 1, "stability": 96.4, "difficulty": 4.1,
                  "retrievability": 0.93, "last_review": at("08-19")},
    },
    {
        "key": "sobremesa", "language": "es", "headword": "la sobremesa", "lemma": "sobremesa",
        "primary_gloss": "after-dinner talk", "emotion": "unhurried and content, in no rush to leave",
        "ipa": "/soβɾeˈmesa/", "pos": "noun", "gender": "feminine", "register": "neutral", "emoji": "☕",
        "topics": ["culture", "food", "social"], "status": "active",
        "short_gloss": "the talk that keeps everyone at the table after a meal",
        "created_at": at("03-08"), "edited_at": at("03-08"),
        "notes": [
            "No English word covers it — this is the case where the Spanish definition does the work and the gloss cannot.",
            "Common collocations: hacer sobremesa, una sobremesa larga, alargar la sobremesa.",
        ],
        "senses": [
            {"key": "table", "definition": "Tiempo que se está a la mesa después de haber comido, charlando con los demás comensales.",
             "glosses": [{"lang": "en", "terms": ["after-dinner conversation", "lingering at the table"]}],
             "examples": [
                 {"key": "seis", "text": "La comida duró una hora, pero la sobremesa se alargó hasta las seis.",
                  "translation": "Lunch lasted an hour, but the sobremesa stretched until six.",
                  "origin": "llm", "model_id": "demo-model", "matched": "sobremesa",
                  "matched_translation": "sobremesa"},
             ],
             "images": [{"key": "table", "prompt": "Empty coffee cups and crumbs on a sunlit table, chairs pushed back, soft storybook gouache, no text",
                         "style_id": "storybook", "seed": 442019}]},
        ],
        "study": {"reps": 5, "lapses": 0, "stability": 12.9, "difficulty": 5.2,
                  "retrievability": 0.88, "last_review": at("08-16")},
    },
    {
        "key": "mejoren", "language": "es", "headword": "que se mejoren", "lemma": "que se mejoren",
        "primary_gloss": "get well soon", "emotion": "warm and sincere, wishing someone well",
        "ipa": "/ke se meˈxoɾen/", "pos": "expression", "register": "neutral", "emoji": "💖",
        "topics": ["health", "social"], "status": "learned", "short_gloss": "get better; feel better soon",
        "created_at": at("01-30"), "edited_at": at("05-19"),
        "notes": ["Plural form; use que te mejores to one person you address informally."],
        "attestations": [
            {"key": "familia", "text": "espero que se mejoren pronto un abrazo a toda la familia",
             "source_kind": "conversation", "source_title": "Course chat", "captured_at": at("01-30")},
        ],
        "senses": [
            {"key": "recover", "definition": "Fórmula para desear a alguien una pronta recuperación.",
             "glosses": [{"lang": "en", "terms": ["get better", "feel better soon"]},
                         {"lang": "ru", "terms": ["выздоравливайте"]}],
             "examples": [
                 {"key": "familia", "text": "Espero que se mejoren pronto. Un abrazo a toda la familia.",
                  "translation": "I hope you get better soon. A hug to the whole family.",
                  "origin": "attestation", "attestation": "familia", "matched": "que se mejoren",
                  "matched_translation": "you get better",
                  "emotion": "warm and tender, a goodbye full of care"},
             ]},
        ],
        "study": {"reps": 26, "lapses": 0, "stability": 402.7, "difficulty": 2.8,
                  "retrievability": 0.97, "last_review": at("08-02")},
    },
    {
        "key": "atasco", "language": "es", "headword": "el atasco", "lemma": "atasco",
        "primary_gloss": "traffic jam", "emotion": "exasperated, resigned to sitting there",
        "ipa": "/aˈtasko/", "pos": "noun", "gender": "masculine", "register": "neutral",
        "dialect": "es-ES", "emoji": "🚗", "topics": ["travel", "places"], "status": "active",
        "short_gloss": "traffic jam", "created_at": at("02-02"), "edited_at": at("02-02"),
        "notes": ["Peninsular. In Mexico you will hear el embotellamiento or el tráfico."],
        "senses": [
            {"key": "jam", "definition": "Congestión de vehículos que impide circular con normalidad.",
             "glosses": [{"lang": "en", "terms": ["traffic jam", "gridlock"]}],
             "examples": [
                 {"key": "m30", "text": "Ayer hubo un atasco tremendo en la M-30.",
                  "translation": "Yesterday there was a terrible traffic jam on the M-30.",
                  "origin": "manual", "matched": "atasco", "matched_translation": "traffic jam"},
             ]},
        ],
        "study": {"reps": 9, "lapses": 1, "stability": 44.1, "difficulty": 4.9,
                  "retrievability": 0.9, "last_review": at("08-12")},
    },
    {
        "key": "currar", "language": "es", "headword": "currar", "lemma": "currar",
        "primary_gloss": "to graft", "emotion": "matter-of-fact, a little weary",
        "ipa": "/kuˈraɾ/", "pos": "verb", "register": "colloquial", "dialect": "es-ES", "emoji": "👷",
        "topics": ["slang", "actions"], "status": "active", "short_gloss": "to work; to graft",
        "created_at": at("04-21"), "edited_at": at("04-21"),
        "notes": ["Noun form el curro = the job. Both are everyday Peninsular colloquial, not rude."],
        "senses": [
            {"key": "work", "definition": "Trabajar, especialmente de forma dura o continuada.",
             "glosses": [{"lang": "en", "terms": ["to work", "to graft", "to slog"]}],
             "examples": [
                 {"key": "siete", "text": "Lleva currando desde las siete de la mañana.",
                  "translation": "He’s been working since seven in the morning.",
                  "origin": "subtitle", "matched": "currando", "matched_translation": "working", "clip": "seg_9e02fa47b6d15c83a7b0",
                  "video": ("RTVE — Aquí la tierra", "RTVE", 723, 729)},
             ]},
        ],
        "study": {"reps": 3, "lapses": 2, "stability": 4.2, "difficulty": 9.1,
                  "retrievability": 0.44, "last_review": at("08-26")},
    },
    {
        "key": "espolvorear", "language": "es", "headword": "espolvorear", "lemma": "espolvorear",
        "primary_gloss": "to sprinkle", "emotion": "light and delicate, a small careful gesture",
        "ipa": "/espolβoɾeˈaɾ/", "pos": "verb", "register": "neutral", "emoji": "🧀",
        "topics": ["food", "actions"], "status": "inbox", "short_gloss": "to sprinkle; to dust",
        "created_at": at("08-27"), "edited_at": at("08-27"),
        "attestations": [
            {"key": "canela", "text": "Espolvoree canela sobre el pastel.",
             "translation": "I sprinkled cinnamon on the cake.", "source_kind": "unknown",
             "captured_at": at("08-27")},
        ],
        "senses": [
            {"key": "sprinkle", "definition": "Esparcir sobre algo una materia hecha polvo.",
             "domain": "cooking", "glosses": [{"lang": "en", "terms": ["to sprinkle", "to dust"]}],
             "examples": [
                 {"key": "canela", "text": "Espolvoreé canela sobre el pastel.",
                  "translation": "I sprinkled cinnamon on the cake.",
                  "origin": "attestation", "attestation": "canela",
                  "model_id": "demo-model", "matched": "Espolvoreé", "matched_translation": "sprinkled"},
             ]},
        ],
    },
    {
        "key": "panza", "language": "es", "headword": "tirarse panza arriba", "lemma": "tirarse panza arriba",
        "primary_gloss": "to sprawl", "emotion": "lazy and contented, sinking into it",
        "pos": "phrase", "register": "colloquial", "emoji": "🏖️", "topics": ["travel", "actions"],
        "status": "active", "short_gloss": "to sprawl out on your back",
        "created_at": at("05-05"), "edited_at": at("05-05"),
        "senses": [
            {"key": "sprawl", "definition": "Tumbarse boca arriba de manera relajada, sin hacer nada.",
             "glosses": [{"lang": "en", "terms": ["to lie on one’s back", "to sprawl out"]}],
             "examples": [
                 {"key": "playa", "text": "Me gusta tirarme panza arriba en la playa.",
                  "translation": "I like to lie on my back at the beach.",
                  "origin": "manual", "matched": "tirarme panza arriba",
                  "matched_translation": "lie on my back"},
             ]},
        ],
        "study": {"reps": 7, "lapses": 0, "stability": 61.5, "difficulty": 3.6,
                  "retrievability": 0.94, "last_review": at("08-10")},
    },
    {
        "key": "balsa", "language": "es", "headword": "la balsa", "lemma": "balsa",
        "primary_gloss": "raft", "emotion": "plain and even, simply naming the thing",
        "ipa": "/ˈbalsa/", "pos": "noun", "gender": "feminine", "register": "neutral", "emoji": "🛶",
        "topics": ["travel", "nature"], "status": "active",
        "created_at": at("01-22"), "edited_at": at("01-22"),
        "senses": [
            {"key": "raft", "definition": "Embarcación plana formada por maderos unidos entre sí.",
             "glosses": [{"lang": "en", "terms": ["raft"]}],
             "examples": [
                 {"key": "rio", "text": "Cruzaron el río en una balsa improvisada.",
                  "translation": "They crossed the river on a makeshift raft.",
                  "origin": "llm", "model_id": "demo-model", "matched": "balsa",
                  "matched_translation": "raft"},
             ]},
            {"key": "pond", "definition": "Hueco del terreno que se llena de agua, natural o artificialmente.",
             "glosses": [{"lang": "en", "terms": ["pond", "pool"]}],
             "examples": [
                 {"key": "quieta", "text": "El agua de la balsa estaba completamente quieta.",
                  "translation": "The water of the pond was completely still.",
                  "origin": "tatoeba", "matched": "balsa", "matched_translation": "pond"},
             ]},
        ],
        "study": {"reps": 11, "lapses": 0, "stability": 74.2, "difficulty": 3.9,
                  "retrievability": 0.95, "last_review": at("08-08")},
    },
    {
        "key": "malo", "language": "es", "headword": "ponerse malo", "lemma": "ponerse malo",
        "primary_gloss": "to get sick", "emotion": "sympathetic, slightly under the weather",
        "pos": "phrase", "register": "colloquial", "dialect": "es-ES", "emoji": "🤒",
        "topics": ["health"], "status": "active", "short_gloss": "to get sick",
        "created_at": at("02-18"), "edited_at": at("02-18"),
        "senses": [
            {"key": "ill", "definition": "Empezar a encontrarse mal de salud.",
             "glosses": [{"lang": "en", "terms": ["to become ill", "to get sick"]}],
             "examples": [
                 {"key": "cenar", "text": "Me he puesto muy malo después de cenar.",
                  "translation": "I’ve become very ill after dinner.",
                  "origin": "manual", "matched": "puesto muy malo",
                  "matched_translation": "become very ill"},
             ]},
        ],
        "study": {"reps": 12, "lapses": 2, "stability": 30.8, "difficulty": 6.4,
                  "retrievability": 0.83, "last_review": at("08-20")},
    },
    {
        "key": "tobillo", "language": "es", "headword": "el tobillo", "lemma": "tobillo",
        "primary_gloss": "ankle", "emotion": "plain and even, simply naming the thing",
        "ipa": "/toˈβiʎo/", "pos": "noun", "gender": "masculine", "register": "neutral", "emoji": "🦵",
        "topics": ["health", "appearance"], "status": "learned", "short_gloss": "ankle",
        "created_at": at("01-19"), "edited_at": at("01-19"),
        "senses": [
            {"key": "ankle", "definition": "Parte del cuerpo donde se une el pie con la pierna.",
             "domain": "medicine", "glosses": [{"lang": "en", "terms": ["ankle"]}],
             "examples": [
                 {"key": "escaleras", "text": "Me torcí el tobillo bajando las escaleras.",
                  "translation": "I twisted my ankle going down the stairs.",
                  "origin": "llm", "model_id": "demo-model", "matched": "tobillo",
                  "matched_translation": "ankle"},
             ]},
        ],
        "study": {"reps": 19, "lapses": 0, "stability": 388.1, "difficulty": 2.4,
                  "retrievability": 0.98, "last_review": at("07-01")},
    },
    {
        "key": "azafata", "language": "es", "headword": "la azafata", "lemma": "azafata",
        "primary_gloss": "flight attendant", "emotion": "bright and professional, welcoming",
        "ipa": "/aθaˈfata/", "pos": "noun", "gender": "feminine", "register": "neutral", "emoji": "👩‍✈️",
        "topics": ["travel", "social"], "status": "active", "short_gloss": "flight attendant",
        "created_at": at("03-30"), "edited_at": at("03-30"),
        "notes": ["Masculine counterpart: el auxiliar de vuelo."],
        "senses": [
            {"key": "attendant", "definition": "Persona encargada de atender a los pasajeros a bordo de un avión.",
             "glosses": [{"lang": "en", "terms": ["flight attendant", "stewardess"]}],
             "examples": [
                 {"key": "cinturon", "text": "La azafata nos pidió abrocharnos el cinturón.",
                  "translation": "The flight attendant asked us to fasten our seatbelts.",
                  "origin": "llm", "model_id": "demo-model", "matched": "azafata",
                  "matched_translation": "flight attendant"},
             ]},
        ],
        "study": {"reps": 6, "lapses": 1, "stability": 21.6, "difficulty": 5.8,
                  "retrievability": 0.86, "last_review": at("08-18")},
    },
    {
        "key": "turmoil", "language": "en", "headword": "turmoil", "lemma": "turmoil",
        "primary_gloss": "turmoil", "emotion": "unsettled and churning, the word carrying weight",
        "ipa": "/ˈtɜːmɔɪl/", "pos": "noun", "register": "formal", "emoji": "🌪️",
        "topics": ["emotions", "misc"], "status": "active", "short_gloss": "суматоха; смятение",
        "created_at": at("02-25"), "edited_at": at("07-14"),
        "notes": ["Mass noun — no plural. Usually in turmoil, rarely a turmoil."],
        "attestations": [
            {"key": "markets", "text": "Markets remained in turmoil as the deadline passed without an agreement.",
             "source_kind": "web", "source_title": "Markets live blog",
             "source_url": "https://example.com/markets", "captured_at": at("02-25")},
        ],
        "senses": [
            {"key": "confusion", "definition": "A state of great confusion, disturbance or uncertainty.",
             "glosses": [{"lang": "ru", "terms": ["суматоха", "смятение", "потрясения"]}],
             "examples": [
                 {"key": "country", "text": "The country was in turmoil for weeks after the vote.",
                  "translation": "Страна несколько недель находилась в смятении после голосования.",
                  "translation_lang": "ru", "origin": "attestation", "attestation": "markets",
                  "matched": "turmoil", "matched_translation": "смятении"},
                 {"key": "mind", "text": "Her mind was in turmoil and she could not sleep.",
                  "translation": "В её голове царила суматоха, и она не могла заснуть.",
                  "translation_lang": "ru", "origin": "wiktionary", "matched": "turmoil",
                  "matched_translation": "суматоха"},
             ]},
        ],
        "study": {"reps": 8, "lapses": 1, "stability": 33.4, "difficulty": 5.5,
                  "retrievability": 0.89, "last_review": at("08-21")},
    },
    {
        "key": "hoax", "language": "en", "headword": "hoax", "lemma": "hoax",
        "primary_gloss": "hoax", "emotion": "wry and sceptical, not taken in",
        "ipa": "/həʊks/", "pos": "noun", "register": "neutral", "emoji": "🎭",
        "topics": ["culture", "misc"], "status": "active", "short_gloss": "мистификация; розыгрыш",
        "created_at": at("04-02"), "edited_at": at("04-02"),
        "senses": [
            {"key": "deception", "definition": "A deliberate deception intended to make people believe something untrue.",
             "glosses": [{"lang": "ru", "terms": ["мистификация", "розыгрыш", "обман"]}],
             "examples": [
                 {"key": "photo", "text": "The photograph turned out to be an elaborate hoax.",
                  "translation": "Фотография оказалась тщательно подготовленной мистификацией.",
                  "translation_lang": "ru", "origin": "llm", "model_id": "demo-model",
                  "matched": "hoax", "matched_translation": "мистификацией"},
             ]},
        ],
        "study": {"reps": 4, "lapses": 0, "stability": 17.2, "difficulty": 4.4,
                  "retrievability": 0.91, "last_review": at("08-23")},
    },
    {
        "key": "library", "language": "zh-Hans", "headword": "图书馆", "lemma": "图书馆",
        "primary_gloss": "library", "emotion": "calm and quiet, as if keeping your voice down",
        "reading": "tu2 shu1 guan3", "pos": "noun", "register": "neutral", "emoji": "📚",
        "topics": ["places", "culture"], "status": "active", "short_gloss": "библиотека; library",
        "created_at": at("06-11"), "edited_at": at("06-11"),
        "notes": ["图 (picture) + 书 (book) + 馆 (public building) — the third character recurs in 博物馆 and 体育馆."],
        "senses": [
            {"key": "library", "definition": "A building where books are kept and may be borrowed.",
             "definition_lang": "en",
             "glosses": [{"lang": "ru", "terms": ["библиотека"]}, {"lang": "en", "terms": ["library"]}],
             "examples": [
                 {"key": "afternoon", "text": "我在图书馆学习了一下午。",
                  "translation": "I studied at the library all afternoon.",
                  "origin": "llm", "model_id": "demo-model", "matched": "图书馆",
                  "matched_translation": "library"},
             ]},
        ],
    },
)


def record_id(owner_id: str, collection: str, key: str) -> str:
    """Return a stable owner-scoped id in the one format Acervo record ids come in."""
    return hashlib.sha256(f"{owner_id}:{collection}:{key}".encode()).hexdigest()[:15]

def sync_fields(created: str = STAMP, edited: str | None = None) -> dict:
    """Replication metadata, minus `revision`: the server's save hook allocates that."""
    return {
        "deleted": False,
        "created_at": created,
        "edited_at": edited or created,
        "edited_by": EDITOR,
    }


def demo_records(owner_id: str) -> list[tuple[str, dict]]:
    rid = lambda collection, key: record_id(owner_id, collection, key)
    topics = {key: rid("topics", key) for key, _, _ in STARTER_TOPICS}
    records: list[tuple[str, dict]] = [
        ("vocabularies", {"id": rid("vocabularies", language), "owner": owner_id,
                          "language": language, "definition_lang": definition_lang,
                          "gloss_langs": gloss_langs, "notes_lang": notes_lang,
                          "display_name": name, "flag": flag,
                          "vocab_order": order, **sync_fields()})
        for order, (language, definition_lang, gloss_langs, notes_lang, name, flag)
        in enumerate(STARTER_VOCABULARIES)
    ]
    records += [
        ("topics", {"id": topics[key], "owner": owner_id, "name": name, "icon": icon,
                    "topic_order": order, **sync_fields()})
        for order, (key, name, icon) in enumerate(STARTER_TOPICS)
    ]

    for entry in DEMO_LEXEMES:
        key = entry["key"]
        stamps = sync_fields(entry.get("created_at", STAMP), entry.get("edited_at"))
        base = {"owner": owner_id, **stamps}
        lexeme_id = rid("lexemes", key)
        records.append(("lexemes", {
            "id": lexeme_id, **base,
            "language": entry["language"], "headword": entry["headword"], "lemma": entry["lemma"],
            "reading": entry.get("reading", ""), "ipa": entry.get("ipa", ""), "pos": entry["pos"],
            "gender": entry.get("gender", ""), "register": entry.get("register", ""),
            "dialect": entry.get("dialect", ""), "emoji": entry["emoji"],
            "topics": [topics[topic] for topic in entry["topics"]], "status": entry["status"],
            "short_gloss": entry.get("short_gloss", ""),
            "primary_gloss": entry.get("primary_gloss", ""), "emotion": entry.get("emotion", ""),
            "notes": entry.get("notes", []),
            "clips_searched_at": entry.get("clips_searched_at", ""),
        }))

        attestations: dict[str, str] = {}
        for attestation in entry.get("attestations", ()):
            attestation_id = rid("attestations", f"{key}-{attestation['key']}")
            attestations[attestation["key"]] = attestation_id
            records.append(("attestations", {
                "id": attestation_id, **base, "lexeme": lexeme_id,
                "text": attestation["text"], "translation": attestation.get("translation", ""),
                "source_url": attestation.get("source_url", ""),
                "source_title": attestation.get("source_title", ""),
                "source_kind": attestation["source_kind"], "captured_at": attestation["captured_at"],
                "photo_ref": "", "photo_region": None,
            }))

        for order, sense in enumerate(entry["senses"]):
            sense_id = rid("senses", f"{key}-{sense['key']}")
            records.append(("senses", {
                "id": sense_id, **base, "lexeme": lexeme_id, "definition": sense["definition"],
                "definition_lang": sense.get("definition_lang", entry["language"]),
                "glosses": sense["glosses"], "domain": sense.get("domain", ""),
                "emoji": sense.get("emoji", ""), "sense_order": order,
            }))
            for example in sense["examples"]:
                title, channel, start, end = example.get("video", ("", "", 0, 0))
                clip_ref = example.get("clip", "")
                video_ref = f"corpus/{key}-{example['key']}.mp4" if title else ""
                records.append(("examples", {
                    # A clip example's id is derived from its sense and the segment it quotes, so
                    # the seed writes what every other writer of one would write.
                    "id": clip_example_id(sense_id, clip_ref) if clip_ref
                    else rid("examples", f"{key}-{sense['key']}-{example['key']}"), **base,
                    "sense": sense_id, "text": example["text"], "text_lang": entry["language"],
                    "translation": example.get("translation", ""),
                    "translation_lang": example.get("translation_lang", "en") if example.get("translation") else "",
                    "origin": example["origin"],
                    "source_attestation": attestations.get(example.get("attestation", ""), ""),
                    "model_id": example.get("model_id", ""),
                    "video_ref": video_ref, "video_title": title, "video_channel": channel,
                    "video_start": start, "video_end": end, "clip_ref": clip_ref,
                    "image_ref": "", "emotion": example.get("emotion", ""),
                    "note": example.get("note", ""), "matched_form": example.get("matched", ""),
                    "matched_translation_form": example.get("matched_translation", ""),
                }))
            for image in sense.get("images", ()):
                records.append(("image_prompts", {
                    "id": rid("image_prompts", f"{key}-{image['key']}"), **base, "lexeme": lexeme_id,
                    "sense": sense_id, "prompt": image["prompt"], "style_id": image["style_id"],
                    "seed": image["seed"], "model_id": "demo-prompt", "prompt_version": "demo-v1",
                    "image_ref": "", "image_model_id": "", "example": None,
                    "attempts": 0, "failure_reason": "", "suppressed": False,
                }))

        study = entry.get("study")
        if study:
            records.append(("study_states", {
                "id": rid("study_states", f"{key}-anki"), **base, "lexeme": lexeme_id, "sense": None,
                "system": "anki", "note_id": 0, "card_ids": [], "reps": study["reps"], "lapses": study["lapses"],
                "stability": study["stability"], "difficulty": study["difficulty"],
                "retrievability": study["retrievability"], "last_review": study["last_review"],
                "synced_at": STAMP,
            }))

    return records
