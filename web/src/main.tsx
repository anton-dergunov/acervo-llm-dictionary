import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { registerAcervoServiceWorker } from "./pwa";
import "./fonts";

const root = createRoot(document.getElementById("root")!);
// The carousel spike's own page (docs/plans/carousel-spike.md), loaded only when asked for.
if (new URLSearchParams(window.location.search).get("spike") === "carousel") {
  void import("./carousels/CarouselSpike").then(({ default: CarouselSpike }) => root.render(<StrictMode><CarouselSpike /></StrictMode>));
} else {
  root.render(<StrictMode><App /></StrictMode>);
}
registerAcervoServiceWorker();
