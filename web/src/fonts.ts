/* Self-hosted faces. Acervo is offline-first and self-hosted, so no webfont CDN is used.
   Only the subsets the vocabulary actually needs are imported — latin and latin-ext for Spanish,
   English and their neighbours, cyrillic for Russian. CJK is deliberately left to the system faces
   named in the stylesheet: those files are megabytes, and the stack covers them.

   **Every weight and style the interface uses must be imported for every script**, which is not a
   tidiness point. A missing face does not fall back within the family — it falls out of the family
   altogether, onto the next name in the stack. Cyrillic at weight 600 was missing here, so a
   Russian gloss (`.gloss-line .tm b`) was drawn by the first stack entry that had the glyphs, which
   was a CJK face setting Cyrillic on CJK metrics: letters a full em apart, in the wrong shapes.
   That is what the gap looks like, and it looks like a styling bug rather than a missing file. */

import "@fontsource/literata/latin-400.css";
import "@fontsource/literata/latin-500.css";
import "@fontsource/literata/latin-600.css";
import "@fontsource/literata/latin-700.css";
import "@fontsource/literata/latin-400-italic.css";
import "@fontsource/literata/latin-600-italic.css";
import "@fontsource/literata/latin-ext-400.css";
import "@fontsource/literata/latin-ext-500.css";
import "@fontsource/literata/latin-ext-600.css";
import "@fontsource/literata/latin-ext-700.css";
import "@fontsource/literata/latin-ext-400-italic.css";
import "@fontsource/literata/latin-ext-600-italic.css";
import "@fontsource/literata/cyrillic-400.css";
import "@fontsource/literata/cyrillic-500.css";
import "@fontsource/literata/cyrillic-600.css";
import "@fontsource/literata/cyrillic-700.css";
import "@fontsource/literata/cyrillic-400-italic.css";
import "@fontsource/literata/cyrillic-600-italic.css";

import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-sans/latin-400-italic.css";
import "@fontsource/ibm-plex-sans/latin-ext-400.css";
import "@fontsource/ibm-plex-sans/latin-ext-500.css";
import "@fontsource/ibm-plex-sans/latin-ext-600.css";
import "@fontsource/ibm-plex-sans/cyrillic-400.css";
import "@fontsource/ibm-plex-sans/cyrillic-500.css";
import "@fontsource/ibm-plex-sans/cyrillic-600.css";
import "@fontsource/ibm-plex-sans/cyrillic-400-italic.css";

import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "@fontsource/ibm-plex-mono/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-ext-400.css";
import "@fontsource/ibm-plex-mono/latin-ext-500.css";
import "@fontsource/ibm-plex-mono/latin-ext-600.css";
import "@fontsource/ibm-plex-mono/cyrillic-400.css";
import "@fontsource/ibm-plex-mono/cyrillic-500.css";
import "@fontsource/ibm-plex-mono/cyrillic-600.css";

/* IPA. Plex Mono has no phonetic letters, tone letters or combining marks; macOS quietly fills them
   from a system face and Android does not, so a transcription came out as empty boxes. `.ipa`
   names this family after Plex Mono. */
import "@fontsource/noto-sans/latin-400.css";
import "@fontsource/noto-sans/latin-ext-400.css";
