"""The twenty-two owner-scoped tables, plus `users`.

Ported column for column and index for index from the PocketBase bootstrap migration this replaces.
Two of those indexes carry reasoning that must survive the move, and both comments are below.

Timestamps are `TEXT` of exactly 24 characters throughout. The migration already stored `created_at`
and `edited_at` that way; `captured_at`, `last_review` and `synced_at` were PocketBase `date` fields
normalised back to the same 24-character form on every read, so storing the wire form directly is
what removes a conversion rather than what adds one.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    text,
)

metadata = MetaData()

# The fifteen replicated tables, in graph order: topics before lexemes, lexemes before senses and
# attestations, those before examples, sense-linked image prompts and pronunciations. Applying a batch in this order
# means a relation always resolves, so it is also the merge order the write route uses — and,
# reversed and with the first two dropped, the tombstone order.
#
# Loops and stories come last, and both halves of that matter. Neither is a word's descendant — each
# is an owner-level artefact that *references* words — so they hang off nothing and could sit
# anywhere after `lexemes`. Last is where they go anyway, because that is what puts them inside the
# word reset: a loop every one of whose captions names a deleted word is a track nothing describes,
# and a story whose every word is gone is one nothing asked for. A favourite bed follows the loop it
# was kept from, and goes with it in that reset.
REPLICATED = (
    "vocabularies",
    "topics",
    "lexemes",
    "senses",
    "attestations",
    "examples",
    "image_prompts",
    "pronunciations",
    "study_states",
    "loops",
    "loop_items",
    "loop_cues",
    "stories",
    "story_parts",
    "story_words",
    "beds",
)


def _owner() -> Column:
    return Column("owner", String(15), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def _sync_fields() -> list[Column]:
    return [
        Column("deleted", Boolean, nullable=False, default=False),
        Column("created_at", String(24), nullable=False),
        Column("edited_at", String(24), nullable=False),
        Column("edited_by", String(32), nullable=False),
        Column("revision", Integer, nullable=False, default=0),
    ]


users = Table(
    "users",
    metadata,
    Column("id", String(15), primary_key=True),
    Column("email", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    # Mixed into the token signing key, so changing a password invalidates outstanding tokens. The
    # one PocketBase auth behaviour worth reproducing.
    Column("token_key", Text, nullable=False),
    Column("verified", Boolean, nullable=False, default=True),
    Column("created_at", String(24), nullable=False),
    Column("updated_at", String(24), nullable=False),
    # Safe here for the same reason as on `sync_state`: this table is never replicated, so it cannot
    # be the constraint two offline devices independently satisfy.
    Index("idx_users_email", "email", unique=True),
)

# The replication cursor: one strictly increasing sequence per owner, and the record id doubles as
# the dataset identity a client checks its cursor against. Deliberately its own table and never
# replicated — a counter only the server may advance must not be a field a stale device can
# overwrite. The unique index is safe here for exactly the same reason: this row never syncs, so it
# cannot be the constraint two offline devices independently satisfy.
sync_state = Table(
    "sync_state",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("sequence", Integer, nullable=False, default=0),
    Index("idx_sync_state_owner", "owner", unique=True),
)

# Which (provider, model) pairs answer, per kind, for this owner. Its own table and never
# replicated: it is server state read through a route rather than vocabulary, and a client that
# cannot reach the server cannot capture anyway. No `revision`, `deleted` or `edited_by` — nothing
# merges this, so none of the three would have a reader, and their absence is what makes the table
# structurally unreplicable rather than merely unreplicated. The unique index is safe for exactly
# `sync_state`'s reason: this row never syncs, so it cannot be the constraint two offline devices
# independently satisfy.
#
# **No row means "use the deployment default"**, which is a legitimate answer rather than a gap, so
# nothing creates one eagerly — see `repository/model_selection.py`.
model_selection = Table(
    "model_selection",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    # {kind: [{"provider": id, "model": model}, ...]} — exactly the document the route takes and
    # returns, so the column and the wire are one shape and neither can drift from the other.
    # Ordering *is* the content here, which in rows would be a `position` integer renumbered on
    # every save; `vocabularies.gloss_langs` is the same call already made in this schema.
    Column("chains", JSON, nullable=False, default=dict),
    Column("edited_at", String(24), nullable=False),
    Index("idx_model_selection_owner", "owner", unique=True),
)

# How this owner wants sense images drawn. Server state for the same reason `model_selection` is:
# the drawing happens on the server, so unlike the editor's wrapping preference this cannot live on
# the device. Never replicated, no `revision`/`deleted`/`edited_by`, and the unique index is safe for
# `sync_state`'s reason — this row never syncs, so it cannot be a constraint two offline devices
# each satisfy on their own.
#
# **No row means "use the deployment default"**, exactly as with `model_selection`, so nothing
# creates one eagerly — see `repository/image_settings.py`.
image_settings = Table(
    "image_settings",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    # Whether pictures are drawn on their own at all — by the sweep, and by a client enriching a
    # word that was just saved. It deliberately does not gate the buttons: you pressed those, so
    # you meant them, and switching this off is how you get a word with no pictures and then add
    # the one you want by hand.
    Column("draw_enabled", Boolean, nullable=False, default=True),
    # The styles switched **off**, never the ones switched on. A set of switched-on ids left the
    # online dictionary sources permanently silent when one was added later; a style added to
    # `config/image-styles.yaml` must be on by default, and only this direction gives that.
    Column("styles_off", JSON, nullable=False, default=list),
    # Present each style with a few of its example subjects, sampled per word, which pushes the
    # writer toward styles it would otherwise pass over. `StyleTable.hints()` on or off.
    Column("boost_variety", Boolean, nullable=False, default=True),
    Column("edited_at", String(24), nullable=False),
    # Whether a story's later pictures are drawn with its earlier pictures of the same people and
    # places as references: `all` (the default), `artwork` (every style but the photographic ones),
    # or `off`. Run 1 of experiments/story-picture-reference lost 4–0 in the photoreal style, and
    # run 2 — the shipped, picture-first prompt, on twelve fresh stories — won 7–0 with 3 ties in
    # photographic styles and never lost, so every style is the default. Declared last so a
    # database that gained it by `ALTER TABLE` has its columns in the order a fresh one does.
    Column("story_continuity", String(16), nullable=False, default="all"),
    Index("idx_image_settings_owner", "owner", unique=True),
)

pronunciation_settings = Table(
    "pronunciation_settings",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    # Which spoken fields are recorded when a word is saved, rather than on first press:
    # {"headword": bool, "definitions": bool, "examples": bool}. Only target-language text is
    # recorded in advance; everything else waits until somebody presses play.
    Column("pregenerate", JSON, nullable=False, default=dict),
    # Which order reads each of the three uses: {"words": "plain"|"expressive", "examples": …,
    # "loops": …}. It replaces a boolean that only decided whether a *direction was sent*, which
    # meant switching emotion off still spent the expensive voice on every sentence. Choosing the
    # directed order is what asking for emotion now means — one mechanism where there were two.
    Column("delivery", JSON, nullable=False, default=dict),
    # The owner's voice per model per language: {provider: {model: {language: voice}}}. Absent means
    # the first voice the catalogue declares, so a voice list that grows never changes a choice.
    Column("voices", JSON, nullable=False, default=dict),
    # Who says a loop's guide lines — translations, remarks, announcements — in the same shape, where
    # the owner chose a second voice for them. Absent means the voice above says every line.
    Column("guide_voices", JSON, nullable=False, default=dict),
    Column("edited_at", String(24), nullable=False),
    Index("idx_pronunciation_settings_owner", "owner", unique=True),
)

clip_settings = Table(
    "clip_settings",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    # Whether the spoken-usage corpus is consulted on its own at all — by the sweep, and by a client
    # enriching a word that was just saved. Like `image_settings.draw_enabled` it deliberately does
    # not gate the route: you pressed that, so you meant it.
    Column("search_enabled", Boolean, nullable=False, default=True),
    # Whether the selector is told to reject a passage whose subject cannot be recovered from the
    # passage itself. **Off by default**, which is the deliberate half: real speech is messy, a
    # learner meets it by walking into a conversation already under way, and preserving that is what
    # a clip is for. The switch is for someone who wants the tidier version.
    Column("self_contained_only", Boolean, nullable=False, default=False),
    Column("edited_at", String(24), nullable=False),
    Index("idx_clip_settings_owner", "owner", unique=True),
)

# The owner's standing rules for everything a text model writes for them — "I am vegan", "I read
# Spanish at B2" — appended to those prompts by `services/prompts.with_rules`. Free text, one per
# owner, and like the other settings tables **no row means none**.
prompt_rules = Table(
    "prompt_rules",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("rules", String(4000), nullable=False, default=""),
    Column("edited_at", String(24), nullable=False),
    Index("idx_prompt_rules_owner", "owner", unique=True),
)

# When this owner's nightly run happens, and which of its steps are on. Server state for
# `sync_state`'s reason, and like the other settings tables **no row means the defaults**.
schedule_settings = Table(
    "schedule_settings",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    # The hour, 0–23, in the deployment's zone (`ACERVO_TIMEZONE`).
    Column("hour", Integer, nullable=False, default=2),
    # {step name: bool}; a step not named keeps its default.
    Column("steps", JSON, nullable=False, default=dict),
    Column("edited_at", String(24), nullable=False),
    Index("idx_schedule_settings_owner", "owner", unique=True),
)

# Work the server does on this owner's behalf, one row per request for it. Server state for
# `sync_state`'s reason — never replicated, no `revision`/`deleted`/`edited_by` — and the durable
# record the runner in `acervo/work/` reads (`docs/architecture/jobs.md`).
#
# The row is written in the **same transaction** as the write that makes the work necessary, which
# is what retires "never let a queue be the only record that work is needed": either both exist or
# neither does. What the work still lacks is re-derived from the graph when each step runs, so the
# row says *which word*, never *which pictures*.
jobs = Table(
    "jobs",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    # A job another job created — a capture's per-word `enrich` — so the whole tree reads as one.
    Column("parent", String(15), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True),
    Column("kind", String(40), nullable=False),
    # What the job is about: a lexeme, an image prompt, a channel — or nothing, as `""`.
    Column("subject_kind", String(20), nullable=False, default=""),
    Column("subject_id", String(64), nullable=False, default=""),
    Column("input", JSON, nullable=False, default=dict),
    # queued → running → done | failed | cancelled
    Column("state", String(12), nullable=False),
    # save, import, ingest, manual, schedule, backfill
    Column("trigger", String(12), nullable=False),
    Column("steps", JSON, nullable=False, default=list),
    # A second request arrived while this one was running; the runner queues a fresh job after it.
    Column("rerun", Boolean, nullable=False, default=False),
    # Cancellation is cooperative, and may be asked for by another process (`admin jobs cancel`).
    Column("cancel_requested", Boolean, nullable=False, default=False),
    # A failure stays listed until the owner dismisses it; everything else is pruned by age.
    Column("dismissed", Boolean, nullable=False, default=False),
    Column("error", String(40), nullable=True),
    Column("message", String(500), nullable=True),
    # A job waiting out a provider's rest yields the lane rather than holding it. `""` means now.
    Column("not_before", String(24), nullable=False, default=""),
    Column("created_at", String(24), nullable=False),
    Column("started_at", String(24), nullable=True),
    Column("finished_at", String(24), nullable=True),
    Index("idx_jobs_owner_state", "owner", "state"),
    Index("idx_jobs_parent", "parent"),
    # At most one open `enrich` per word. Safe for `sync_state`'s reason — this row never syncs — and
    # it is the guard, not the mechanism: `repository/jobs.enqueue_enrich` checks first, so meeting
    # this index in anger would be a bug.
    Index(
        "idx_jobs_open_enrich",
        "owner",
        "subject_id",
        unique=True,
        sqlite_where=text("kind = 'enrich' AND state IN ('queued', 'running')"),
    ),
)

# The languages this owner studies, and how they want each presented. Replicated like any other
# record and deliberately without a unique index on `language`: uniqueness is forbidden on a
# replicated collection, because it is exactly the constraint two offline devices can each satisfy on
# their own. The client refuses a duplicate at graph level instead.
vocabularies = Table(
    "vocabularies",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("language", String(35), nullable=False),
    Column("definition_lang", String(35), nullable=False),
    Column("gloss_langs", JSON, nullable=False, default=list),
    Column("notes_lang", String(35), nullable=False),
    Column("display_name", String(120), nullable=False, default=""),
    Column("flag", String(32), nullable=False, default=""),
    Column("vocab_order", Integer, nullable=False, default=0),
    *_sync_fields(),
    Index("idx_vocabularies_owner_revision", "owner", "revision"),
    Index("idx_vocabularies_owner_language", "owner", "language"),
)

topics = Table(
    "topics",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("name", String(120), nullable=False),
    Column("icon", String(120), nullable=False, default=""),
    Column("topic_order", Integer, nullable=False, default=0),
    *_sync_fields(),
    Index("idx_topics_owner_revision", "owner", "revision"),
    Index("idx_topics_owner_name", "owner", "name"),
)

lexemes = Table(
    "lexemes",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("language", String(35), nullable=False),
    Column("headword", String(240), nullable=False),
    Column("lemma", String(240), nullable=False),
    Column("reading", String(240), nullable=False, default=""),
    Column("ipa", String(240), nullable=False, default=""),
    Column("pos", String(32), nullable=False),
    Column("gender", String(32), nullable=False, default=""),
    Column("register", String(32), nullable=False, default=""),
    Column("dialect", String(35), nullable=False, default=""),
    Column("emoji", String(32), nullable=False, default=""),
    # A list of topic ids rather than a join table: it is what `getStringSlice` projected, nothing on
    # the server queries by topic, and the same-owner rule is a validation concern either way.
    Column("topics", JSON, nullable=False, default=list),
    Column("status", String(32), nullable=False),
    Column("short_gloss", String(500), nullable=False, default=""),
    # The one term a loop speaks, and how the word itself sounds when said. `short_gloss` is right
    # for the list and wrong for a beat: `house, home` cannot be spoken on one. Named for what they
    # are rather than for what consumes them, so a flashcard or a quiz can read both without either
    # name lying. `emotion` is the same field an example carries, one level up.
    Column("primary_gloss", String(240), nullable=False, default=""),
    Column("emotion", String(300), nullable=False, default=""),
    Column("notes", JSON, nullable=False, default=list),
    # The instant the spoken-usage corpus was last successfully consulted for this lexeme, or "".
    # Empty means never, which is what the sweep looks for; set with no `subtitle` examples means
    # consulted and nothing was good enough, which is a normal answer and not a gap.
    Column("clips_searched_at", String(24), nullable=False, default=""),
    *_sync_fields(),
    Index("idx_lexemes_owner_revision", "owner", "revision"),
    Index("idx_lexemes_owner_language_headword", "owner", "language", "headword"),
)

senses = Table(
    "senses",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("lexeme", String(15), ForeignKey("lexemes.id", ondelete="CASCADE"), nullable=False),
    Column("definition", String(2000), nullable=False),
    Column("definition_lang", String(35), nullable=False),
    Column("glosses", JSON, nullable=False, default=list),
    Column("domain", String(120), nullable=False, default=""),
    # The sense's own picture-in-a-glyph, beside the word's: what the article's sense selector shows.
    Column("emoji", String(32), nullable=False, default=""),
    Column("sense_order", Integer, nullable=False, default=0),
    *_sync_fields(),
    Index("idx_senses_owner_revision", "owner", "revision"),
    Index("idx_senses_owner_lexeme_order", "owner", "lexeme", "sense_order"),
)

attestations = Table(
    "attestations",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("lexeme", String(15), ForeignKey("lexemes.id", ondelete="CASCADE"), nullable=False),
    Column("text", String(5000), nullable=False),
    Column("translation", String(5000), nullable=False, default=""),
    Column("source_url", Text, nullable=False, default=""),
    Column("source_title", String(500), nullable=False, default=""),
    Column("source_kind", String(32), nullable=False),
    Column("captured_at", String(24), nullable=False),
    # The photo the word was met in, relative to the media root, and where on it the word and its
    # sentence are. Empty and null for an attestation that was typed or pasted.
    Column("photo_ref", String(500), nullable=False, default=""),
    Column("photo_region", JSON, nullable=True),
    *_sync_fields(),
    Index("idx_attestations_owner_revision", "owner", "revision"),
    Index("idx_attestations_owner_lexeme", "owner", "lexeme"),
)

examples = Table(
    "examples",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("sense", String(15), ForeignKey("senses.id", ondelete="CASCADE"), nullable=False),
    Column("text", String(5000), nullable=False),
    Column("text_lang", String(35), nullable=False),
    Column("translation", String(5000), nullable=False, default=""),
    Column("translation_lang", String(35), nullable=False, default=""),
    Column("origin", String(32), nullable=False),
    # Not a cascade: an attestation and the example drawn from it are two records, and tombstoning
    # one must not remove the other.
    Column("source_attestation", String(15), ForeignKey("attestations.id"), nullable=True),
    Column("model_id", String(240), nullable=False, default=""),
    Column("video_ref", String(500), nullable=False, default=""),
    Column("video_title", String(500), nullable=False, default=""),
    Column("video_channel", String(500), nullable=False, default=""),
    Column("video_start", Integer, nullable=False, default=0),
    Column("video_end", Integer, nullable=False, default=0),
    # The corpus's own stable `segment_id`, so the stored sentence can be audited against the
    # segment it names at any time. Not a foreign key: the corpus is a separate service.
    Column("clip_ref", String(120), nullable=False, default=""),
    Column("image_ref", String(500), nullable=False, default=""),
    # How a native speaker would sound saying this sentence, as a short English direction a voice
    # that takes one can follow ("exasperated, scratching and complaining"). Empty is neutral.
    Column("emotion", String(300), nullable=False, default=""),
    Column("note", String(2000), nullable=False, default=""),
    Column("matched_form", String(240), nullable=False, default=""),
    Column("matched_translation_form", String(240), nullable=False, default=""),
    *_sync_fields(),
    Index("idx_examples_owner_revision", "owner", "revision"),
    Index("idx_examples_owner_sense", "owner", "sense"),
    Index("idx_examples_owner_attestation", "owner", "source_attestation"),
)

image_prompts = Table(
    "image_prompts",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("lexeme", String(15), ForeignKey("lexemes.id", ondelete="CASCADE"), nullable=False),
    Column("sense", String(15), ForeignKey("senses.id", ondelete="CASCADE"), nullable=True),
    Column("prompt", String(10000), nullable=False),
    Column("style_id", String(120), nullable=False),
    Column("seed", Integer, nullable=False, default=0),
    Column("model_id", String(240), nullable=False),
    Column("prompt_version", String(128), nullable=False),
    Column("image_ref", String(500), nullable=False, default=""),
    Column("image_model_id", String(240), nullable=False, default=""),
    # Which sentence the picture illustrates. Not a cascade, for the reason `source_attestation`
    # above is not one: deleting the example must not delete the picture drawn from it.
    Column("example", String(15), ForeignKey("examples.id"), nullable=True),
    # Why an undrawn row is undrawn. Without these three, `image_ref = ""` meant both "briefed, not
    # yet drawn" and "drawing was refused", so a sweep defined as "which senses lack a picture"
    # retried a permanently blocked sense forever.
    Column("attempts", Integer, nullable=False, default=0),
    Column("failure_reason", String(500), nullable=False, default=""),
    # The owner has ruled on this sense. Deliberately not a tombstone: `image_prompt_id` is derived
    # from `sense`, so a tombstoned row is invisible to the sweep, which re-briefs the sense and
    # mints the same id — tombstoning does not prevent regeneration, it guarantees a collision.
    Column("suppressed", Boolean, nullable=False, default=False),
    *_sync_fields(),
    Index("idx_image_prompts_owner_revision", "owner", "revision"),
    Index("idx_image_prompts_owner_lexeme", "owner", "lexeme"),
    Index("idx_image_prompts_owner_sense", "owner", "sense"),
)

pronunciations = Table(
    "pronunciations",
    metadata,
    # `pronunciation_id(target_kind, target_id)`, derived rather than random, so a record has at most
    # one clip per spoken field and recording it again rewrites that row instead of adding a second.
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("lexeme", String(15), ForeignKey("lexemes.id", ondelete="CASCADE"), nullable=False),
    # What was read: the headword of a lexeme, the definition of a sense, the text of an example or an
    # attestation. Not a foreign key, because it points at one of four tables; validation resolves it.
    Column("target_kind", String(16), nullable=False),
    Column("target_id", String(15), nullable=False),
    # The words actually spoken, so a clip whose record has since been edited is recognisably stale.
    Column("text", String(5000), nullable=False),
    Column("lang", String(35), nullable=False),
    # The delivery direction actually sent, which is empty whenever the voice could not take one.
    Column("emotion", String(300), nullable=False, default=""),
    Column("audio_ref", String(500), nullable=False),
    Column("audio_mime", String(80), nullable=False),
    Column("provider_id", String(80), nullable=False),
    Column("model_id", String(240), nullable=False),
    Column("voice", String(120), nullable=False, default=""),
    *_sync_fields(),
    Index("idx_pronunciations_owner_revision", "owner", "revision"),
    Index("idx_pronunciations_owner_lexeme", "owner", "lexeme"),
)

study_states = Table(
    "study_states",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("lexeme", String(15), ForeignKey("lexemes.id", ondelete="CASCADE"), nullable=False),
    Column("system", String(80), nullable=False),
    Column("note_id", Integer, nullable=False, default=0),
    Column("card_ids", JSON, nullable=False, default=list),
    Column("reps", Integer, nullable=False, default=0),
    Column("lapses", Integer, nullable=False, default=0),
    Column("stability", Float, nullable=False, default=0.0),
    Column("difficulty", Float, nullable=False, default=0.0),
    Column("retrievability", Float, nullable=False, default=0.0),
    Column("last_review", String(24), nullable=False, default=""),
    Column("synced_at", String(24), nullable=False, default=""),
    *_sync_fields(),
    Index("idx_study_states_owner_revision", "owner", "revision"),
    Index("idx_study_states_owner_lexeme_system", "owner", "lexeme", "system"),
)

loops = Table(
    "loops",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("language", String(35), nullable=False),
    # Style, seed and engine version replay the bed byte-identically, and `bed_fingerprint` is what
    # proves a replay produced the same one. That is why the resolved BedSpec is not stored: nothing
    # else in this model holds opaque JSON, and these four make it unnecessary.
    Column("style_id", String(120), nullable=False, default=""),
    Column("seed", Integer, nullable=False, default=0),
    Column("engine_version", String(64), nullable=False, default=""),
    Column("bed_fingerprint", String(64), nullable=False, default=""),
    # Which of the generator's formats this loop is (`classic`, `radio-lesson`, …), and the values
    # of the switches it offers. Not opaque: the format is the generator's catalogue id and the
    # switches are the listener's own choices, both sent with every render of this loop.
    Column("format", String(64), nullable=False, default=""),
    Column("switches", JSON, nullable=False, default=dict),
    # The format asked for, when the render lacked something it requires and made its fallback
    # instead — `format` then names what the track actually is. Empty otherwise.
    Column("fallback_from", String(64), nullable=False, default=""),
    # There is no status column. An empty `audio_ref` is *not rendered yet*, and the job says the
    # rest; a fifth fact would be a thing to keep in step with four that already say all of it.
    Column("audio_ref", String(500), nullable=False, default=""),
    Column("audio_mime", String(80), nullable=False, default=""),
    Column("duration_seconds", Float, nullable=False, default=0.0),
    # Sparse and renumbered on reorder, with no uniqueness constraint: ordering is respected rather
    # than enforced, which is the data rule for every replicated collection.
    Column("loop_order", Integer, nullable=False, default=0),
    *_sync_fields(),
    Index("idx_loops_owner_revision", "owner", "revision"),
    Index("idx_loops_owner_language_order", "owner", "language", "loop_order"),
)

loop_items = Table(
    "loop_items",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("loop", String(15), ForeignKey("loops.id", ondelete="CASCADE"), nullable=False),
    Column("lexeme", String(15), ForeignKey("lexemes.id", ondelete="CASCADE"), nullable=False),
    Column("item_order", Integer, nullable=False, default=0),
    # What was *said*, denormalised on purpose: editing the word afterwards must not make the player
    # caption a recording that no longer matches it. Identical reasoning to `pronunciations.text`,
    # and the reason both are safe — and the reason deleting the word leaves these rows alone.
    Column("source_text", String(240), nullable=False),
    Column("target_text", String(240), nullable=False),
    Column("emotion", String(300), nullable=False, default=""),
    # Where the word's own block in the words section starts and ends, and when each side is first
    # heard in it — what a retrieval display turns on. A side the format never says there has no
    # reveal. Every line, and when it is said, is `loop_cues`.
    Column("start_seconds", Float, nullable=False, default=0.0),
    Column("source_reveal_seconds", Float, nullable=True),
    Column("target_reveal_seconds", Float, nullable=True),
    Column("end_seconds", Float, nullable=False, default=0.0),
    *_sync_fields(),
    Index("idx_loop_items_owner_revision", "owner", "revision"),
    Index("idx_loop_items_owner_loop_order", "owner", "loop", "item_order"),
    Index("idx_loop_items_owner_lexeme", "owner", "lexeme"),
)

# Every line of a loop, in the order it is heard: the words, their translations, and whatever else
# the format says — an example, a remark, a line of a story, an announcement. `cue_group` is what a
# player shows together (a word's own lines, a line and its translation), numbered as the generator
# numbers it. The text is denormalised for `loop_items.source_text`'s reason: it records what was
# said. Written by the render and only by it, so a re-render tombstones the old lines and writes new
# ones; a line has no identity worth keeping across two recordings.
loop_cues = Table(
    "loop_cues",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("loop", String(15), ForeignKey("loops.id", ondelete="CASCADE"), nullable=False),
    Column("cue_order", Integer, nullable=False, default=0),
    Column("cue_group", Integer, nullable=False, default=0),
    Column("kind", String(32), nullable=False),
    Column("section", String(16), nullable=False),
    # The word the line belongs to, or none for a line of no word (an intro, a story line).
    Column("loop_item", String(15), ForeignKey("loop_items.id", ondelete="CASCADE"), nullable=True),
    Column("side", String(16), nullable=False, default=""),
    Column("role", String(16), nullable=False),
    Column("language", String(35), nullable=False),
    Column("text", String(600), nullable=False),
    Column("take", Integer, nullable=False, default=0),
    Column("start_seconds", Float, nullable=False, default=0.0),
    Column("end_seconds", Float, nullable=False, default=0.0),
    *_sync_fields(),
    Index("idx_loop_cues_owner_revision", "owner", "revision"),
    Index("idx_loop_cues_owner_loop_order", "owner", "loop", "cue_order"),
)

# What the writer wrote for a loop, kept on the server and never replicated: it exists only to be
# sent back with a re-render, so new music says the same lines — and finds their takes in the cache
# — rather than asking for new ones. It is the generator's own shape and nothing here reads it.
# Exempt from the replicated rules, like `jobs`: one row per loop, keyed by it.
loop_scripts = Table(
    "loop_scripts",
    metadata,
    Column("loop", String(15), ForeignKey("loops.id", ondelete="CASCADE"), primary_key=True),
    _owner(),
    Column("format", String(64), nullable=False),
    Column("script", JSON, nullable=False),
    Column("written_at", String(24), nullable=False),
)

# A bed the owner kept: the music of one loop, to be asked for again for another. Style and seed
# replay it for any words (the bed does not depend on them), and `bed_fingerprint` is what proves a
# replay made the same one. It is a record of its own rather than a flag on the loop, so deleting the
# loop does not take the favourite with it; the reference then points at a tombstone, as a loop
# item's does at a deleted word.
beds = Table(
    "beds",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("style_id", String(120), nullable=False),
    Column("seed", Integer, nullable=False, default=0),
    Column("engine_version", String(64), nullable=False, default=""),
    Column("bed_fingerprint", String(64), nullable=False, default=""),
    Column("source_loop", String(15), ForeignKey("loops.id", ondelete="CASCADE"), nullable=False),
    *_sync_fields(),
    Index("idx_beds_owner_revision", "owner", "revision"),
)

stories = Table(
    "stories",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("language", String(35), nullable=False),
    # Which kind of story was asked for, and what it is drawn in. Both are ids into tracked config
    # files rather than enums in the code, exactly as `image_prompts.style_id` is: a type added to
    # `config/story-types.yaml` needs no schema change and no migration.
    Column("type_id", String(64), nullable=False, default=""),
    Column("style_id", String(120), nullable=False, default=""),
    Column("title", String(240), nullable=False, default=""),
    Column("title_translation", String(240), nullable=False, default=""),
    Column("emoji", String(16), nullable=False, default=""),
    # Who wrote it. Provenance, for the reason `examples.model_id` is: the model that *answered*,
    # which under a chain is not knowable before the call.
    Column("model_id", String(120), nullable=False, default=""),
    # There is no status column, for the reason `loops` has none. A story with no live `story_parts`
    # was asked for and never written, and the job says why; a part with an empty `image_ref` is one
    # that has not been drawn. Both facts are already in the graph.
    Column("story_order", Integer, nullable=False, default=0),
    *_sync_fields(),
    # What the owner asked the writer for in their own words — "set it in 1920s Buenos Aires", "make
    # the dog the narrator" — kept on the story, for `type_id`'s reason: Try again on a story that
    # was never written must write the story that was asked for. Declared last so a database that
    # gained it by `ALTER TABLE` has its columns in the order a fresh one does.
    Column("guidance", Text, nullable=False, default=""),
    Index("idx_stories_owner_revision", "owner", "revision"),
    Index("idx_stories_owner_language_order", "owner", "language", "story_order"),
)

story_parts = Table(
    "story_parts",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("story", String(15), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
    Column("part_order", Integer, nullable=False, default=0),
    Column("heading", String(240), nullable=False, default=""),
    Column("heading_translation", String(240), nullable=False, default=""),
    # The story itself. `Text` rather than a bounded `String` because a part is prose and the bound
    # would be arbitrary; the model is told how long a part should be, and validation checks it.
    Column("text", Text, nullable=False, default=""),
    Column("translation", Text, nullable=False, default=""),
    # The brief this part's picture was drawn from, kept on the part rather than in `image_prompts`:
    # that table's id is derived from a *sense* id, and a story part is not a sense. One row, one
    # picture, no second identity to hold in step.
    Column("image_prompt", Text, nullable=False, default=""),
    Column("image_ref", String(500), nullable=False, default=""),
    Column("image_model_id", String(120), nullable=False, default=""),
    Column("attempts", Integer, nullable=False, default=0),
    Column("failure_reason", String(500), nullable=False, default=""),
    *_sync_fields(),
    # The part read aloud. Kept on the part for the reason the picture is: a part is not a word, so
    # the `pronunciations` collection (whose `lexeme` is required) cannot hold it. The pair and the
    # voice are recorded because a story is spoken in **one** of them: the first part to be recorded
    # chooses, and every later part asks for exactly that.
    # Declared last so a database that gained them by `ALTER TABLE` has its columns in the order a
    # fresh one does.
    Column("audio_provider_id", String(120), nullable=False, default=""),
    Column("audio_model_id", String(120), nullable=False, default=""),
    Column("audio_voice", String(120), nullable=False, default=""),
    # `[{"text", "direction", "audioRef", "audioMime", "durationSeconds"}]`, in reading order, and
    # **one file per passage**. A part with no passages has not been recorded; there is no status
    # column and no separate reference to get out of step with that. A clear voice records one
    # passage covering the whole part, so the shape is the same either way and the reader simply has
    # nothing to tap.
    #
    # One file each rather than one joined file, because **a passage must start where its first word
    # does**. A joined file has to be seeked into, and a browser seeks a compressed stream to a page
    # boundary — measured at one second in the Ogg libsndfile writes — landing after the target
    # (missing the first words) or before it (playing the end of the sentence before). There is no
    # asking again: the element reports the time that was asked for, not the time it gave. A file
    # that begins at the passage is exact by construction and needs no seek at all.
    Column("audio_segments", JSON, nullable=False, default=list),
    Index("idx_story_parts_owner_revision", "owner", "revision"),
    Index("idx_story_parts_owner_story_order", "owner", "story", "part_order"),
)

story_words = Table(
    "story_words",
    metadata,
    Column("id", String(15), primary_key=True),
    _owner(),
    Column("story", String(15), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False),
    Column("lexeme", String(15), ForeignKey("lexemes.id", ondelete="CASCADE"), nullable=False),
    Column("word_order", Integer, nullable=False, default=0),
    # The headword as it was asked for, denormalised for the reason `loop_items.source_text` is:
    # editing the word afterwards must not make the story claim it taught something else. It is also
    # why deleting the word leaves this row alone.
    Column("source_text", String(240), nullable=False),
    # The surface forms the story actually used, which is how the reader marks them in the text. A
    # word is inflected, so the form in the story is rarely the headword, and only the writer knows
    # which forms it reached for. **Empty means the story did not manage to use the word** — a fact
    # worth showing rather than hiding, and the reason this is a list and not a boolean.
    Column("forms", JSON, nullable=False, default=list),
    *_sync_fields(),
    # The words of the *translation* that render this one, found in the text the way `forms` are
    # found in the original. Reported by the translator, which is the only thing that knows what it
    # called the word, and kept only where they really appear in what it wrote. Empty is ordinary —
    # a story translated before this existed, or a word the translator could not point to — and the
    # reader simply marks nothing. Declared last so a database that gained it by `ALTER TABLE` has
    # its columns in the order a fresh one does.
    Column("translation_forms", JSON, nullable=False, default=list),
    Index("idx_story_words_owner_revision", "owner", "revision"),
    Index("idx_story_words_owner_story_order", "owner", "story", "word_order"),
    Index("idx_story_words_owner_lexeme", "owner", "lexeme"),
)

TABLES = {table.name: table for table in metadata.tables.values()}
