"""Piped over stdin into the server container, read-only: the stored words this measurement compares.

    ssh <host> "docker exec -i acervo-server-1 python3 -" \
        < experiments/dictionary-checks/extract_remote.py > experiments/dictionary-checks/out/words.json

Never written to disk on the server. Opens the database by URI in read-only mode (`mode=ro`) with
`PRAGMA query_only`. Prints one JSON object: every live lexeme's language, headword, lemma, reading,
ipa, gender and part of speech, the model that wrote its first generated example (senses record no model), and each vocabulary's language
and region. No owner id, email, notes or examples.
"""

import json
import os
import sqlite3

conn = sqlite3.connect(f"file:{os.environ['ACERVO_DB_PATH']}?mode=ro", uri=True)
conn.execute("PRAGMA query_only = ON")


def rows(sql):
    cursor = conn.execute(sql)
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


lexemes = rows(
    "SELECT l.id, l.language, l.headword, l.lemma, l.reading, l.ipa, l.gender, l.pos, "
    "(SELECT e.model_id FROM examples e JOIN senses s ON s.id = e.sense "
    " WHERE s.lexeme = l.id AND e.deleted = 0 AND e.model_id != '' "
    " ORDER BY s.sense_order LIMIT 1) AS model_id "
    "FROM lexemes l WHERE l.deleted = 0"
)
vocabularies = rows("SELECT language, region FROM vocabularies WHERE deleted = 0")
print(json.dumps({"lexemes": lexemes, "vocabularies": vocabularies}, ensure_ascii=False))
