# UI Redesign Brief — Privacy-Preserving Credit Scoring Demo

**For:** developer agent (Claude Code)
**Stack:** unchanged — vanilla HTML/CSS/JS, Express. No framework, no build step.
**Scope:** visual and interaction redesign of four existing views. No new pages, no backend changes, no new data.

---

## 0. The constraint that governs every choice

These screens are captured as **figures for a printed academic dissertation**, at roughly six inches wide, and may be reproduced in greyscale. That is not a styling preference, it is a hard requirement:

- Dark screenshots go muddy when downscaled and lose all detail in greyscale.
- Colour cannot be the only carrier of meaning — layer identity and eligibility must survive as text and shape.
- Nothing below 14px, anywhere.

So: light base, high contrast, generous type. "Fun" is delivered through **motion and sequencing**, not through dark gradients or novelty. That is the right trade here anyway — the interesting thing about this system is that a great deal happens and very little is revealed, and the way to make that engaging is to let the viewer watch it happen.

---

## 1. Design direction

**Concept: a working instrument panel, not a dashboard.**

Think flight recorder or lab bench rather than SaaS product. Precise, instrumented, a little bit alive. Three principles:

1. **Every action traces L1 → L2 → L3, visibly.** Layer chips are not decoration; they light up in sequence as each stage executes.
2. **Numbers are the hero.** Scores, hashes, latencies, byte counts. Treat them typographically as the main content, not as labels.
3. **What is hidden is designed as deliberately as what is shown.** The lender's privacy panel is the single most important component in this build.

---

## 2. What is wrong with the current design

Stated plainly, so the fixes are structural rather than cosmetic.

**The dark navy base (`#0A1628`) is wrong for this deliverable.** See §0. It also reads as generic crypto-product, which undercuts an academic argument.

**Red is overloaded, and this is the most damaging problem.** `#DC2626` currently means *L2 blockchain layer*, *privacy warning*, and *blocked write* — three meanings, one colour. Red must be reserved for blocked and error states only, because the regulator view's whole point is a genuine authorisation failure.

**The privacy panel is styled as a warning.** It is not a warning. It is the system's central claim, and currently it looks like something went wrong.

**Timing tables are inert.** A static table of latencies wastes the most interesting thing the demo does. Those numbers arrive in sequence — show them arriving.

**Unicode icons look unfinished** at screenshot resolution. Replace with a small consistent inline SVG set.

**No responsive handling, weak focus states, unlabelled controls.** Fix as part of the work, not after.

---

## 3. Design tokens

Define once in `styles/tokens.css`. No hardcoded hex anywhere else.

```css
:root {
  /* Base — warm neutral, prints cleanly */
  --bg:            #F7F7F5;
  --surface:       #FFFFFF;
  --surface-sunk:  #F0F0EE;
  --border:        #E2E2DE;
  --border-strong: #C9C9C3;

  /* Ink */
  --ink:           #14151A;
  --ink-secondary: #52525B;
  --ink-muted:     #8A8A93;

  /* Primary action */
  --primary:       #3730A3;
  --primary-hover: #312A8C;
  --primary-soft:  #EEF0FF;

  /* Architecture layers — semantic, used for chips and accents */
  --l1:            #047857;   /* ML                        */
  --l1-soft:       #ECFDF5;
  --l2:            #B45309;   /* Ledger — amber, NOT red   */
  --l2-soft:       #FFFBEB;
  --l3:            #6D28D9;   /* ZK proofs                 */
  --l3-soft:       #F5F3FF;

  /* State — red is reserved */
  --success:       #047857;
  --danger:        #B91C1C;
  --danger-soft:   #FEF2F2;
}
```

**Moving L2 from red to amber is required, not optional.** It is what frees red for genuine failure.

Every foreground/background pair must clear WCAG AA (4.5:1 body, 3:1 large text). Verify with a contrast checker; do not assume.

### Typography

```css
--font-sans: 'Inter', system-ui, sans-serif;
--font-mono: 'JetBrains Mono', 'SF Mono', monospace;
```

Mono is **mandatory** for hashes, DIDs, latencies, byte counts and transaction IDs. It signals machine output and makes truncated hashes legible.

| Token | Size / line-height / weight | Use |
|---|---|---|
| `--text-display` | 72px / 1 / 700, `tabular-nums` | The score |
| `--text-h1` | 28px / 1.2 / 650 | Page title |
| `--text-h2` | 19px / 1.3 / 600 | Panel heading |
| `--text-body` | 15px / 1.55 / 400 | Body |
| `--text-label` | 13px / 1.4 / 600, +0.04em, uppercase | Field labels, chips |
| `--text-mono` | 14px / 1.5 / 450 | Hashes, timings |

### Space, radius, elevation

8px scale: `4, 8, 12, 16, 24, 32, 48, 64`.
Radius: `--r-sm: 6px`, `--r-md: 10px`, `--r-lg: 16px`, `--r-full: 999px`.

Two shadows only — heavy shadows print as grey smudge:

```css
--shadow-1: 0 1px 2px rgba(20,21,26,.06), 0 1px 3px rgba(20,21,26,.04);
--shadow-2: 0 4px 12px rgba(20,21,26,.08), 0 2px 4px rgba(20,21,26,.04);
```

---

## 4. Motion

This is where the personality lives. Fast and functional — every animation communicates state, none decorates.

```css
--ease: cubic-bezier(.22,.61,.36,1);
--dur-fast: 140ms;
--dur-base: 240ms;
--dur-slow: 420ms;
```

| Moment | Behaviour |
|---|---|
| Score reveal | Count up 0 → final over 900ms, ease-out; band bar fills in parallel |
| Pipeline execution | Each layer chip goes idle → **active** (pulsing ring) → **done** (check), in sequence as its stage completes |
| Timing rows | Stream in one at a time as each stage finishes — not all at once at the end |
| Commitment hash | Brief hex scramble (~400ms) before settling on the real value |
| Proof verification | Progress indicator on the L3 chip during generation; firm check on success |
| Blocked write | Button shakes horizontally 3× over 300ms, then a red `REJECTED` stamp rotates in at −8° |
| Loan approval | Success state on the button; ledger row slides into history. No confetti |

Wrap all of it in `@media (prefers-reduced-motion: reduce)` with instant state changes as the fallback.

---

## 5. Page by page

### 5.1 Landing (`index.html`)

Currently a plain role-selection page. Make it teach the architecture before the user clicks anything.

- Title, one-sentence description, three role cards.
- Each card carries role name, one line of purpose, and the layer chips that role touches — **Borrower: L1+L2 · Lender: L2+L3 · Regulator: L2**.
- Below the cards, a **horizontal pipeline diagram**: `Consent → Features → Score → Commitment → Ledger → Proof → Verify → Decision`, each node tinted by its layer. Static here; it becomes live on the borrower and lender pages.
- Card hover: lift 2px, border takes the role's dominant layer colour.

### 5.2 Borrower (`borrower.html`)

Keep the two-column split. Left = controls, right = results.

**Left panel** — largely as-is, but the searchable dropdown needs real keyboard support (§7).

**Right panel — restructure around the reveal:**

1. **Score block.** 72px tabular figure, counting up. Beneath it a segmented band bar (400 / 550 / 700 / 850) with a marker at the borrower's position. Band label as a pill in the band's colour.
2. **Live pipeline strip.** The same node sequence from the landing page, animating through as the process runs. This is the centrepiece of the page.
3. **Data cards** — Default Probability, Credit Band, Commitment (mono, middle-truncated, copy button), Ledger Status with transaction ID.
4. **Timing breakdown → horizontal waterfall bars.** Each bar tinted by layer, width proportional to duration, value in mono at the end. This makes the L2-dominates finding visible at a glance instead of requiring arithmetic across a table.

**Required empty state — sub-band borrowers.** 22.8% of borrowers score below 400 and can generate no proof at all. This is correct behaviour and must not render as an error. Design a distinct neutral state:

> *"Score below the lowest verification band (400). No proof can be generated — this borrower cannot be verified through the privacy-preserving route."*

Use `--ink-secondary` and a neutral icon. **Do not use red.**

### 5.3 Lender (`lender.html`)

This page produces the dissertation's key figure. Design accordingly.

**Left panel** — borrower select, then threshold as four **segmented buttons**. The segmented control is doing real work: it visually enforces that thresholds are *restricted to fixed bands*, which is the privacy mitigation. Add a caption:

> *"Thresholds are restricted to four fixed bands. Free selection would allow a lender to binary-search the exact score."*

**Right panel:**

1. **Verdict block** — large, unambiguous ELIGIBLE / NOT ELIGIBLE with the threshold tested. Icon + text, never colour alone.
2. **Proof card** — validity, proof size in bytes, generation and verification times, all mono. Small and dense; it should read like an instrument readout.
3. **The disclosure panel — redesign completely. This is the most important component in the build.**

   Not a red warning box. A confident, well-composed **disclosure ledger** in two columns:

   | ✓ Lender receives | ✕ Lender does not receive |
   |---|---|
   | Eligibility verdict (1 bit) | Credit score |
   | Threshold tested | Behavioural features |
   | Proof validity | Margin above threshold |
   | | Raw transaction data |
   | | Model weights |

   Left column in `--success`. Right column as **redaction bars** — grey blocks where the value would be. Redaction reads instantly, screenshots beautifully, and survives greyscale printing better than any other treatment.

   Give it `--shadow-2` and generous padding. It should feel like the conclusion of the page, not a footnote.

4. **Loan approval** appears only on eligibility, as now.

### 5.4 Regulator (`regulator.html`)

- Read-only framing established immediately: a persistent `READ-ONLY` badge in the header, `--l2` tinted.
- Records render as a **vertical timeline** rather than a flat list — commitment anchored, then each loan event in sequence, timestamps in mono. Reads as an audit trail, which is what it is.
- **The blocked-write demo is the fun moment — give it room.** A clearly labelled "Attempt Write (Demonstration)" button, the shake, then the stamped rejection showing the real chaincode error string in mono on `--danger-soft`:

  ```
  access denied: RegulatoryObserverMSP is not authorized
  to perform write operations
  ```

  This is a dissertation figure. Make it unmistakable.
- Query metadata — time, access type, organisation MSP — in a compact mono footer.

---

## 6. Components to build

Reusable CSS classes plus small JS behaviours.

| Component | Notes |
|---|---|
| `.chip-layer` | L1/L2/L3 tag with idle / active / done states |
| `.pipeline` | Node sequence with connectors; static and animated variants |
| `.score-display` | Large tabular figure, count-up, segmented band bar |
| `.waterfall` | Horizontal timing bars, layer-tinted, mono values |
| `.disclosure-table` | Two-column received/withheld with redaction bars |
| `.combobox` | Searchable select — **must** support arrow keys, Enter, Escape, `aria-expanded`, `aria-activedescendant` |
| `.segmented` | Threshold selector, single-select, roving tabindex |
| `.hash` | Mono, middle-truncated, click-to-copy with confirmation |
| `.timeline` | Regulator audit trail |
| `.stamp` | Rotated REJECTED overlay |

---

## 7. Accessibility — non-negotiable

- Every interactive element keyboard-reachable, in logical order.
- Visible focus: `2px solid var(--primary)` with `2px` offset. Never remove an outline without replacing it.
- The combobox needs the full ARIA pattern. It is the most-used control in the app and currently the least accessible.
- Layer identity must not rely on colour alone — chips carry the literal text "L1" / "L2" / "L3".
- Eligible / Not eligible must not rely on colour alone — icon plus text.
- `aria-live="polite"` on result regions so completion is announced.
- Honour `prefers-reduced-motion`.

---

## 8. Responsive

- **≥1024px** — two columns, controls 380px fixed, results fluid.
- **768–1023px** — single column, controls above results, sticky action button.
- **<768px** — single column full width, pipeline scrolls horizontally, waterfall bars stack.

Mobile is unlikely to be demonstrated but must not be visibly broken.

---

## 9. Screenshot readiness

Before declaring done:

- [ ] Every screen legible when the capture is downscaled to 6 inches wide.
- [ ] Every screen checked in greyscale — layer distinction survives via text and shape, not hue.
- [ ] No console output, debug text or placeholder copy in any capturable state.
- [ ] A `?demo=clean` query parameter that hides dev affordances, so captures are consistent.
- [ ] A realistic populated state reachable for each view without fabricating data.

---

## 10. Build order

1. `tokens.css` — colours, type, space, radius, shadow, motion. Nothing else starts until this lands.
2. Shared components — `.chip-layer`, `.hash`, `.combobox`, buttons, cards.
3. Landing page — smallest surface, validates the system.
4. Borrower — score display, pipeline, waterfall, sub-band empty state.
5. Lender — verdict, proof card, **disclosure table**.
6. Regulator — timeline, blocked-write demo.
7. Responsive breakpoints.
8. Accessibility pass — keyboard, ARIA, contrast, reduced motion.
9. Screenshot pass — greyscale, downscale, clean mode.

---

## 11. Acceptance criteria

- [ ] No hardcoded colour values outside `tokens.css`
- [ ] Red appears only for blocked and error states
- [ ] All text ≥14px; hashes, timings and byte counts in mono
- [ ] Layer chips animate idle → active → done during execution
- [ ] Score counts up; band bar fills; commitment hash scrambles then settles
- [ ] Timing shown as a waterfall, not a table
- [ ] Sub-band borrowers render as a neutral state, never an error
- [ ] Threshold selector visibly communicates that bands are fixed, with the caption explaining why
- [ ] Disclosure table uses redaction bars and reads as the page's conclusion
- [ ] Blocked-write demo shakes, stamps, and shows the real chaincode error string
- [ ] Every interactive element keyboard-reachable with a visible focus ring
- [ ] Combobox implements the full ARIA pattern
- [ ] All colour pairs pass WCAG AA
- [ ] `prefers-reduced-motion` honoured throughout
- [ ] Every view legible at 6-inch figure width and in greyscale

---

## 12. Out of scope

No backend changes, no framework, no build step, no new pages, no new data, no changes to measured values or demo behaviour. If a change appears to require any of these, stop and raise it rather than proceeding.