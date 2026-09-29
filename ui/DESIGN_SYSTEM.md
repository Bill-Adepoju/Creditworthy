# Design System: Privacy-Preserving Credit Scoring UI

> Comprehensive design guide for UI overhaul. Style: **Fun Corporate** - Professional but approachable, inviting, and distinct from generic templates.

---

## Design Philosophy

### What We're NOT
- Generic dark-mode dashboard template
- AI-generated corporate website
- Overly technical/developer-focused
- Boring enterprise software

### What We ARE
- **Approachable fintech** - Financial technology that feels human
- **Nigerian banking context** - Modern, aspirational, trustworthy
- **Educational demo** - Clear explanations without being condescending
- **Privacy-focused** - The UI should FEEL secure without being intimidating

---

## Color Palette

### Primary Colors
| Name | Hex | Usage |
|------|-----|-------|
| Deep Navy | `#0A1628` | Main background |
| Slate Blue | `#1E3A5F` | Card backgrounds |
| Teal Accent | `#00BFA6` | Primary actions, success states |
| Coral Highlight | `#FF6B6B` | Warnings, important info |
| Gold Accent | `#FFD93D` | Premium feel, highlights |

### Layer Colors (from architecture)
| Layer | Color | Hex |
|-------|-------|-----|
| L1 (ML) | Fresh Green | `#22C55E` |
| L2 (Blockchain) | Deep Red | `#DC2626` |
| L3 (ZK Proofs) | Royal Purple | `#7C3AED` |

### Neutrals
| Name | Hex | Usage |
|------|-----|-------|
| Pure White | `#FFFFFF` | Text, icons |
| Light Gray | `#94A3B8` | Secondary text |
| Muted | `#475569` | Disabled, borders |

---

## Typography

### Font Stack
```css
font-family: 'Inter', 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
```

### Type Scale
| Element | Size | Weight | Line Height |
|---------|------|--------|-------------|
| H1 (Page title) | 2rem (32px) | 700 | 1.2 |
| H2 (Section) | 1.25rem (20px) | 600 | 1.3 |
| H3 (Card title) | 1rem (16px) | 600 | 1.4 |
| Body | 0.938rem (15px) | 400 | 1.6 |
| Small/Caption | 0.813rem (13px) | 400 | 1.5 |
| Mono (values) | 0.875rem (14px) | 500 | 1.4 |

---

## Component Styles

### Cards
```css
.card {
    background: linear-gradient(135deg, #1E3A5F 0%, #0F2744 100%);
    border-radius: 16px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
    padding: 24px;
}
```

### Buttons

**Primary Button**
```css
.btn-primary {
    background: linear-gradient(135deg, #00BFA6 0%, #00897B 100%);
    color: white;
    border: none;
    border-radius: 12px;
    padding: 14px 28px;
    font-weight: 600;
    font-size: 0.938rem;
    cursor: pointer;
    transition: transform 0.2s, box-shadow 0.2s;
}
.btn-primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 191, 166, 0.3);
}
```

**Threshold Buttons (Lender)**
```css
.threshold-btn {
    background: rgba(255, 255, 255, 0.05);
    border: 2px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    padding: 16px 12px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
}
.threshold-btn.selected {
    background: rgba(124, 58, 237, 0.2);
    border-color: #7C3AED;
    box-shadow: 0 0 20px rgba(124, 58, 237, 0.3);
}
```

### Select/Dropdown with Search
```css
.select-search {
    position: relative;
}
.select-search input {
    width: 100%;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 12px;
    padding: 14px 16px;
    color: white;
    font-size: 0.938rem;
}
.select-search .dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: #1E3A5F;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    max-height: 240px;
    overflow-y: auto;
    z-index: 100;
}
.select-search .option {
    padding: 12px 16px;
    cursor: pointer;
    transition: background 0.15s;
}
.select-search .option:hover {
    background: rgba(0, 191, 166, 0.1);
}
```

### Score Display
```css
.score-display {
    text-align: center;
    padding: 32px;
}
.score-value {
    font-size: 4rem;
    font-weight: 700;
    background: linear-gradient(135deg, #00BFA6, #FFD93D);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.score-bar {
    height: 8px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 4px;
    overflow: hidden;
    margin-top: 16px;
}
.score-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.8s ease-out;
}
```

### Layer Badges
```css
.layer-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.layer-badge.l1 { background: rgba(34, 197, 94, 0.2); color: #22C55E; }
.layer-badge.l2 { background: rgba(220, 38, 38, 0.2); color: #DC2626; }
.layer-badge.l3 { background: rgba(124, 58, 237, 0.2); color: #7C3AED; }
```

### Status Messages
```css
.status {
    padding: 16px 20px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 0.938rem;
}
.status.success {
    background: rgba(34, 197, 94, 0.15);
    border: 1px solid rgba(34, 197, 94, 0.3);
    color: #22C55E;
}
.status.error {
    background: rgba(220, 38, 38, 0.15);
    border: 1px solid rgba(220, 38, 38, 0.3);
    color: #FF6B6B;
}
.status.warning {
    background: rgba(255, 217, 61, 0.15);
    border: 1px solid rgba(255, 217, 61, 0.3);
    color: #FFD93D;
}
```

---

## Layout Principles

### Grid System
- Max width: 1280px, centered
- Main content: 2-column grid (sidebar 360px + main flexible)
- Gap: 24px between cards
- Padding: 32px on desktop, 16px on mobile

### Visual Hierarchy
1. **Page title** - Top left, large, clear
2. **Navigation** - Subtle top-right back link
3. **Action panel** - Left sidebar, inputs and actions
4. **Results panel** - Right side, larger, output focused
5. **Educational panels** - Below or integrated, color-coded

---

## Interaction Patterns

### Loading States
- Use skeleton loaders, not spinners
- Buttons show "Processing..." text
- Disable interactions during async operations

### Transitions
- All color/transform transitions: 0.2s ease
- Score reveal: 0.8s ease-out with slight overshoot
- Card entrance: fade-in 0.3s + slide-up 16px

### Feedback
- Immediate visual feedback on click
- Success/error messages appear smoothly
- Clear WHAT happened and WHY

---

## Borrower Labels (Demo Mode)

Instead of showing scores, use descriptive labels:

| Internal Score | Display Label |
|----------------|---------------|
| 700+ | Borrower A - Premium |
| 550-699 | Borrower B - Standard |
| 400-549 | Borrower C - Basic |
| < 400 | Borrower D - Limited |

The actual score is revealed AFTER processing, maintaining the demo narrative.

---

## Privacy Panel Design (Lender)

The "What Lender Does NOT Receive" section is critical. Design it to be:
- Visually prominent (red/coral tones)
- Each hidden item has icon + title + explanation
- Feels like a "secure vault" aesthetic

---

## Accessibility

- Minimum contrast ratio: 4.5:1 for text
- Focus states visible with outline
- All interactive elements keyboard accessible
- Screen reader labels on icons

---

## Implementation Notes

### File Structure
```
ui/
├── public/
│   ├── styles/
│   │   └── main.css       # Shared styles
│   ├── index.html         # Landing page
│   ├── borrower.html      # Borrower view
│   ├── lender.html        # Lender view
│   └── regulator.html     # Regulator view
├── server.js
├── DESIGN_SYSTEM.md       # This file
└── FRONTEND_TRACKER.md    # Progress tracking
```

### CSS Organization
1. Reset/base styles
2. Variables (colors, typography)
3. Layout utilities
4. Component styles
5. Page-specific overrides

---

*Created: 2026-09-26*
*Style: Fun Corporate*
