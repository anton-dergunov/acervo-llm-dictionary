/**
 * The carousel spike on a page of its own, at `?spike=carousel`: a make dialog with the three
 * catalogues the real dialogs show, drawn from the bundled pictures, so every variant can be tried
 * without the server, a vocabulary or a selection. Deleted with the spike.
 */

import { useState } from "react";
import { ChoiceCarousel, ChoiceGrid, centred, type CatalogueChoice } from "../ChoiceCarousel";
import { artFor } from "../art";
import { DiceIcon, PictureIcon } from "../icons";
import MakeDialog, { MakeSection } from "../MakeDialog";
import "../styles.css";

const FILES = import.meta.glob("../art/*/*.webp", { eager: true, query: "?url", import: "default" }) as Record<string, string>;

function named(id: string): string {
  const words = id.replace(/[-_]+/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function catalogue(group: "styles" | "kinds" | "music", about?: (label: string) => string): CatalogueChoice[] {
  return Object.keys(FILES)
    .filter((path) => path.startsWith(`../art/${group}/`))
    .map((path) => path.slice(`../art/${group}/`.length, -".webp".length))
    .sort()
    .map((id) => {
      const label = named(id);
      return {
        id, label, about: about?.(label),
        art: <img className="choice-img" src={artFor(group, id) ?? ""} alt="" draggable={false} />
      };
    });
}

const SURPRISE: CatalogueChoice = { id: "surprise", label: "Surprise me", about: "A different style each time.",
  art: <span className="choice-stand-in icon" aria-hidden="true"><DiceIcon /></span> };
const SUIT: CatalogueChoice = { id: "suit", label: "To suit the story",
  art: <span className="choice-stand-in icon" aria-hidden="true"><PictureIcon /></span> };

const MUSIC = centred(SURPRISE, catalogue("music", (label) => `${label}: what it sounds like, in a sentence long enough to need a second line now and then.`));
const KINDS = centred({ ...SURPRISE, about: undefined }, catalogue("kinds"));
const PICTURES = centred(SUIT, catalogue("styles"));

type Group = "music" | "kind" | "pictures";
const GROUPS: Record<Group, { label: string; choices: CatalogueChoice[] }> = {
  music: { label: "Music style", choices: MUSIC },
  kind: { label: "Kind of story", choices: KINDS },
  pictures: { label: "Picture style", choices: PICTURES }
};

export default function CarouselSpike() {
  const [values, setValues] = useState<Record<Group, string>>({ music: "surprise", kind: "surprise", pictures: "suit" });
  const [browsing, setBrowsing] = useState<Group | null>(null);
  const set = (group: Group) => (id: string) => setValues((now) => ({ ...now, [group]: id }));
  const footer = <span className="carousel-spike-readout">
    {(Object.keys(GROUPS) as Group[]).map((group) => GROUPS[group].choices.find((one) => one.id === values[group])?.label).join(" · ")}
  </span>;

  if (browsing) {
    const { label, choices } = GROUPS[browsing];
    return <MakeDialog title="Carousel spike" back={{ title: label, onBack: () => setBrowsing(null) }} footer={footer} onClose={() => setBrowsing(null)}>
      <ChoiceGrid label={label} choices={choices} value={values[browsing]} onChange={(id) => { set(browsing)(id); setBrowsing(null); }} />
    </MakeDialog>;
  }
  return <MakeDialog title="Carousel spike" footer={footer} onClose={() => undefined}>
    <MakeSection label="What to try">
      <p className="make-note">Swipe slowly, flick fast, drag past several pictures and let go, drag beyond the row's edge,
        and tap. On the desktop, the sideways wheel slowly and quickly, and a drag with the mouse button held.
        The line at the foot shows what is chosen.</p>
    </MakeSection>
    {(Object.keys(GROUPS) as Group[]).map((group) => <MakeSection key={group} label={GROUPS[group].label}>
      <ChoiceCarousel label={GROUPS[group].label} choices={GROUPS[group].choices} value={values[group]}
        onChange={set(group)} onAll={() => setBrowsing(group)} />
    </MakeSection>)}
    <textarea className="make-guidance" aria-label="Anything else? (optional)" rows={3}
      placeholder="Here so the body scrolls, as the real dialogs do on a small screen." />
  </MakeDialog>;
}
