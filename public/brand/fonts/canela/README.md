# Canela webfont files

Canela (Commercial Type) is the primary headline face of the Renaissance Commerce font system.
Its font files are deliberately not committed to this repo. The CSS in `public/assets/os.css and middleware.js` loads:

- `Canela-LightItalic.woff2` — display headlines (weight 300, italic)
- `Canela-Light.woff2` — decorative Roman numerals only (weight 300, upright)

from this folder. Until both files are here, headline letters fall back to a system serif italic for anyone
who does not have Canela installed on their own machine.

Use the production webfont files from a Commercial Type web licence: https://commercialtype.com/catalog/canela
