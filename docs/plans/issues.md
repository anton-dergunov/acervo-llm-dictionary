# Issues

Small defects, each deleted once fixed.

- **A story passage cut mid-sentence lets the voice invent the rest.** The narration step cut «Sin
  mostrar ningún temor,» as a passage of its own, and the voice read it as eleven seconds of speech,
  finishing the sentence with words that are in no story («el joven luchó contra aquellos seres…»).
  Found by [`experiments/take-verification/`](../../experiments/take-verification/README.md). Either
  the segmenter (`prompts/acervo_story_narrate.md`) should not end a passage on a comma, or the
  recording should be refused when it is far longer than its text — its duration was the outlier of
  all 2,445 recordings (z = 10.1; the next 4.8), and that check costs nothing.
