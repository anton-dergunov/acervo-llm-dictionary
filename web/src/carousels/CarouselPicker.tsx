/** Chooses which of the spike's carousels this device's make dialogs use. Deleted with the spike. */

import { VARIANTS, setCarouselVariant, useCarouselVariant, type CarouselVariant } from "./variants";

export function CarouselPicker() {
  const variant = useCarouselVariant();
  const about = VARIANTS.find((one) => one.id === variant)?.about;
  return <div className="carousel-picker">
    <label>Carousel on trial{" "}
      <select value={variant} onChange={(event) => setCarouselVariant(event.target.value as CarouselVariant)}>
        {VARIANTS.map((one) => <option key={one.id} value={one.id}>{one.label}</option>)}
      </select>
    </label>
    {about && <p>{about}</p>}
  </div>;
}
