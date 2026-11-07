# Vendored scripts

The prototype is static and loads nothing from a package manager, so the two libraries the make
dialogs' carousel uses are copied here as their browser builds, unchanged. The application imports
the same versions from npm (`web/package.json`).

| File | Package | Version | Licence |
|---|---|---|---|
| `embla-carousel.umd.js` | [embla-carousel](https://github.com/davidjerleke/embla-carousel) | 8.6.0 | MIT, © David Jerleke |
| `embla-carousel-wheel-gestures.umd.js` | [embla-carousel-wheel-gestures](https://github.com/xiel/embla-carousel-wheel-gestures) | 8.1.0 | MIT, © Felix Leupold |

Upgrading is copying the new builds from `web/node_modules/` after upgrading them there.
