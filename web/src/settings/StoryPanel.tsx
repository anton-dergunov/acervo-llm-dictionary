/**
 * Settings ▸ Stories: which voice reads a story, whether it is recorded when the story is made, and
 * whether its later pictures are drawn from its earlier ones.
 *
 * Both are **owner** state, stored beside the other pronunciation choices and read by the server
 * when it records — a phone that has never opened this screen still gets the story recorded the way
 * it was chosen here. The panel is `LoopPanel`'s shape for the same reason: a story is one more use
 * of the pronunciation orders, chosen on the page of the thing that uses it rather than on the
 * Pronunciation page, which is for the words.
 *
 * Nothing here is a device fact. Whether a recording is *kept on this device* is Settings ▸
 * Pronunciation's switch, because a part's recording is kept with the clips: the same kind of
 * thing, about the same size.
 *
 * The picture choice is stored with the other picture settings (`/images/settings`), because the
 * server reads it when it draws; it is shown here because it is a question about stories.
 */

import { AcervoApiError, backendSession, type PronunciationOrder, type PronunciationSettings, type StoryContinuity } from "../api";
import { SETTINGS, useServerSetting } from "./cache";
import { Group, Placeholder, Segmented, Toggle } from "./kit";

/* The same two orders as everywhere else, said in terms of what each does to a story. The costs are
   measured, not felt: a directed voice is one call to a text model to decide where a part breaks and
   then one call to the voice per passage, and a clear one is a single call for the whole part. */
const ORDERS: { value: PronunciationOrder; label: string; hint: string }[] = [
  { value: "expressive", label: "Expressive", hint: "Each passage in its own manner; tap one to hear it" },
  { value: "plain", label: "Clear", hint: "A part read in one go, one call a part" }
];

/* Measured rather than felt (experiments/story-picture-reference): drawn from its earlier pictures,
   a story was preferred 17 times in 29 and lost 4, all four in the first run's photoreal style;
   with the picture-first prompt that shipped, it did not lose in any style. */
const CONTINUITY: { value: StoryContinuity; label: string; hint(photographic: string): string }[] = [
  { value: "all", label: "Every style", hint: () => "Later pictures are drawn from the earlier ones" },
  { value: "artwork", label: "Drawn only", hint: (photographic) => `Not in photographic styles${photographic ? ` (${photographic})` : ""}` },
  { value: "off", label: "Off", hint: () => "Each picture from its own description alone" }
];

export default function StoryPanel({ onNotify }: { onNotify(message: string): void }) {
  const voice = useServerSetting(SETTINGS.pronunciations);
  const pictures = useServerSetting(SETTINGS.images);

  const failed = (error: unknown) =>
    onNotify(error instanceof AcervoApiError ? error.message : "That could not be saved.");

  const choosePictures = async (storyContinuity: StoryContinuity) => {
    const before = pictures.value;
    if (!before) return;
    pictures.set({ ...before, storyContinuity, chosen: true });
    try { pictures.set(await backendSession.saveImageSettings({ storyContinuity })); }
    catch (error) { pictures.set(before); failed(error); }
  };

  /* Optimistic, then reconciled, then rolled back if the server refused — the shape `LoopPanel` and
     `PronunciationPanel` use, because it is the same record being written. */
  const apply = async (
    changes: Parameters<typeof backendSession.savePronunciationSettings>[0],
    optimistic: PronunciationSettings
  ) => {
    const before = voice.value;
    if (!before) return;
    voice.set(optimistic);
    try { voice.set(await backendSession.savePronunciationSettings(changes)); }
    catch (error) { voice.set(before); failed(error); }
  };

  const settings = voice.value;
  const photographic = (pictures.value?.styles ?? []).filter((style) => style.photographic)
    .map((style) => style.label).join(", ");

  return <>
    {settings ? <>
      <Group title="Voice">
        <Segmented
          label="Narration" value={settings.delivery.stories} options={ORDERS}
          onChange={(order) => void apply(
            { delivery: { stories: order } },
            { ...settings, delivery: { ...settings.delivery, stories: order }, chosen: true }
          )}
        />
      </Group>
      <Group>
        <Toggle
          label="Record narration when a story is made" hint="Off, a part records the first time it plays"
          checked={settings.pregenerate.stories}
          onChange={(on) => void apply(
            { pregenerate: { stories: on } },
            { ...settings, pregenerate: { ...settings.pregenerate, stories: on }, chosen: true }
          )}
        />
      </Group>
    </> : <Placeholder rows={2} />}

    {pictures.value && <Group title="Pictures">
      <Segmented
        label="Keep characters and places consistent" value={pictures.value.storyContinuity}
        options={CONTINUITY.map((choice) => ({ value: choice.value, label: choice.label, hint: choice.hint(photographic) }))}
        onChange={(choice) => void choosePictures(choice)}
      />
    </Group>}
  </>;
}
