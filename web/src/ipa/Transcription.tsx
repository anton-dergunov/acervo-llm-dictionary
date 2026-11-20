import { lazy, Suspense, useState } from "react";

/* The panel and its table load on the first tap (from the precache, so offline too), which keeps the
   table out of the bundle every page loads. */
const SoundsPanel = lazy(() => import("./SoundsPanel"));

/**
 * A transcription that opens the IPA guide: tap it to see each sound in it, with a plain description
 * and a recording. A button, so the article's word look-up leaves the tap alone. It goes inside a
 * `.pron-row`, which the panel is placed by: under the transcription, or as the row's last line.
 */
export function Transcription({ ipa, reading = null, language = null, className = "" }: {
  ipa: string;
  /** The word's reading, for a Mandarin word's Pinyin rows. */
  reading?: string | null;
  language?: string | null;
  /** The article's change mark, when the transcription was just edited. */
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  return <>
    <button type="button" className={`ipa ipa-open${className}`} aria-haspopup="dialog" aria-expanded={open}
      title="What these symbols mean" onClick={() => setOpen((was) => !was)}>{ipa}</button>
    {open && <Suspense fallback={null}>
      <SoundsPanel ipa={ipa} reading={reading} language={language} onClose={() => setOpen(false)} />
    </Suspense>}
  </>;
}
