# Design System: Industry

Rules for the demo UI. Tokens live in `public/styles/tokens.css` and components in `public/styles/components.css`; when this file and the CSS disagree, the CSS wins. The UI is shown on a projector at defences and captured as dissertation figures, so it must read well large and in greyscale.

## Look

- **Colour:** light ground (`--bg`), near-black ink, one steel accent (`--accent`, with a 100–900 ramp). Accent-coloured body text uses `--accent-700`.
- **No green, amber or purple.** "Success" is steel. Red (`--danger`) appears only on the REJECTED stamp, chaincode errors and validation errors.
- **Type:** Barlow Condensed for headings, Barlow for body text, JetBrains Mono for hashes, DIDs and timings. Numbers use tabular figures.
- **Shape:** radius 0 everywhere. Cards are transparent with a hairline border and `+` corner marks (`.blueprint` plus four `<i class="corner …">`). The primary button is the only solid object.
- **Data** sits in hairline grids with shared borders, not filled boxes.
- **Emphasis:** `--accent-900` is the only full-colour field, used for the ELIGIBLE verdict and the band pill.
- **Hatching** (135° hairlines) marks things that are withheld or blocked: the lender's "does not receive" column and the regulator's write panel.

## Layers

Told apart by treatment, not hue, and always labelled with text:

| Layer | Chip style |
|---|---|
| L1 · ML | tinted |
| L2 · Ledger | outline |
| L3 · ZK Proof | solid |

## Icons

Lucide at stroke width 1.5, inlined in `public/scripts/icons.js`. Use `<i data-icon="name" data-size="18"></i>`. To add an icon, add its paths to that file. No emoji or Unicode glyphs as icons, apart from `+`/`−` on collapsible toggles.

## Motion

Reveals are sequential so an audience can follow cause and effect. Step durations are tokens (`--step-borrower`, `--step-retrieve`, `--step-prove`, `--step-verify`); read them with `getComputedStyle`. With `prefers-reduced-motion`, durations drop to near zero and sequences still complete.

## Copy

- Title case for buttons and card titles; uppercase only for labels, chips and kickers.
- In-progress buttons use "…ing..." ("Verifying...").
- Empty values show `---`. Money looks like `₦2,000,000`, time like `1284.6 ms`, sizes like `256 bytes`.
- Attribute every operation to its layer with a chip.

## Accessibility

- 2px accent focus ring on `:focus-visible` only; the skip link is kept.
- Text contrast is at least 4.5:1; `--ink-faint` is for icons only.
- Hit targets are at least 44px tall.
- Combobox, radiogroup and `aria-live` semantics are part of the components; keep them.
