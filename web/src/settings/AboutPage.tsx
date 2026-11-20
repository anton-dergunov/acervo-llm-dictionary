/**
 * Settings ▸ About: which version this is, and the credit for everything the app ships that someone
 * else made. The IPA guide's recordings are under CC BY and CC BY-SA, which ask a changed copy to name
 * its author, its licence with a link, where it came from and that it was changed; the fonts, the
 * Mandarin stroke data and the dictionaries carry their own licences.
 *
 * Static, like Reading: nothing here comes from the server. Loaded when opened, since the recordings'
 * table is the IPA guide's and too large to ride in the bundle every page loads.
 */

import { TABLE, type Credit } from "../ipa/table";
import { catalogue } from "../dictionaries";
import { appVersionLabel } from "../version";
import { Group, Link, Row, Value, useSubPage } from "./kit";

const SOUNDS = { id: "about-sounds", title: "Sounds in the IPA guide" };

/** Each recording with what it plays for, in the table's order. */
function recordings(): { sound: string; credit: Credit; plays: string[] }[] {
  const plays = new Map<string, string[]>();
  const add = (sound: string | undefined, label: string) => {
    if (!sound) return;
    plays.set(sound, [...(plays.get(sound) ?? []), label]);
  };
  for (const row of [...TABLE.consonants, ...TABLE.affricates, ...TABLE.combinations, ...TABLE.vowels]) add(row.sound, row.symbol);
  for (const row of TABLE.diacritics) add(row.sound, row.example ?? row.symbol);
  for (const contour of TABLE.tones.contours) add(contour.sound, `tone ${contour.letters}`);
  for (const row of [...TABLE.pinyin.initials, ...TABLE.pinyin.finals]) add(row.sound, `Pinyin ${row.letters}`);
  for (const tone of TABLE.pinyin.tones) add(tone.sound, `Pinyin tone ${tone.number}`);
  return Array.from(plays, ([sound, labels]) => ({ sound, credit: TABLE.recordings[sound], plays: labels }));
}

const outside = { target: "_blank", rel: "noreferrer" } as const;

function SoundCredits() {
  return <Group title="Recordings" count={`${Object.keys(TABLE.recordings).length}`}
    foot="From Wikimedia Commons. A recording under CC BY-SA keeps that licence in its changed form.">
    {recordings().map(({ sound, credit, plays }) => <Row key={sound} stack
      label={<span className="about-plays">{plays.join(" · ")}</span>}
      hint={<>
        {credit.author} · {credit.licenceUrl ? <a href={credit.licenceUrl} {...outside}>{credit.licence}</a> : credit.licence}
        {" · "}<a href={credit.page} {...outside}>{credit.source}</a> · {credit.changes}
      </>} />)}
  </Group>;
}

export default function AboutPage() {
  const { sub, open } = useSubPage();
  if (sub?.id === SOUNDS.id) return <SoundCredits />;
  return <>
    <Group title="Acervo">
      <Row label="Version"><Value mono>{appVersionLabel()}</Value></Row>
    </Group>
    <Group title="Credits">
      <Link label="Sounds in the IPA guide" hint="Who recorded each sound, and under what licence"
        value={`${Object.keys(TABLE.recordings).length}`} onOpen={() => open(SOUNDS)} />
      <Row label="Mandarin stroke data" hint={<>Make Me a Hanzi, via hanzi-writer-data 2.0.1 · Arphic Public License</>} />
      <Row label="Fonts" hint="Literata, IBM Plex Sans and IBM Plex Mono; the IPA face, built from Noto Sans; the ivy leaf ❧, drawn from EB Garamond · all SIL Open Font License 1.1" />
    </Group>
    <Group title="Dictionaries" foot="Only the list ships with the app; a dictionary is downloaded when you add it.">
      {catalogue.map((entry) => <Row key={entry.id} label={entry.name} hint={entry.attribution} />)}
    </Group>
  </>;
}
