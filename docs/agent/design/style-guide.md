# Editorial Style Guide

> **REQUIRED** for all frontend changes in Resume Matcher.

## Design Principles

1. **Pure white canvas** — Clean, minimal background
2. **Monochromatic palette** — Black text, white backgrounds, zinc-gray containers
3. **Flat, no-shadow aesthetic** — Clean lines, no depth effects
4. **High-end typography** — Playfair Display serif for headings, legible sans for body
5. **Color inversion interactions** — Buttons and controls invert colors on hover/select

## Color Palette

| Name | Hex | Usage |
|------|-----|-------|
| Canvas | `#FFFFFF` | Background, cards |
| Ink | `#000000` | Text, borders, primary buttons |
| Panel | `#F4F4F5` | Secondary fills, muted containers |
| Destructive | `#DC2626` | Delete, remove, error states (only semantic color) |
| Gray | `#71717A` | Secondary text, disabled states |

## Typography

```css
font-serif     /* Headings: Playfair Display */
font-sans      /* Body text: Geist */
font-mono      /* Labels, metadata: Space Grotesk */
```

| Use | Font | Size | Weight |
|-----|------|------|--------|
| Headers | serif | 2xl+ | 500–700 |
| Body | sans | base | 400 |
| Labels | mono | sm | bold, uppercase |
| Metadata | mono | xs | 400 |

## Components

### Buttons
- **Base**: `rounded-none` (square corners), `border border-black`, no shadow
- **Primary** (`bg-black text-white`): hover to `bg-white text-black`
- **Outline** (`bg-white text-black`): hover to `bg-black text-white`
- **Destructive** (`bg-red-600 text-white`): hover to `bg-white text-red-600`
- **Secondary** (`bg-zinc-100`): hover to `bg-zinc-200`
- **Ghost**: transparent, no border, hover to `bg-gray-100`
- **Link**: text only, underline on hover

### Inputs
- `border border-black rounded-none`
- Focus: `ring-2 ring-black`

### Cards
- `border border-black bg-white`
- Hover: `bg-zinc-50` (subtle fill, no shadow)
- No rounded corners

### Dialogs
- White background, black border
- Centered, `max-w-lg`
- No shadows, clean overlay

### Grid Background
- Subtle 40px × 40px grid: `rgba(0, 0, 0, 0.05)` lines on white
- Use `.bg-grid-lines` utility class
- Decorative only, does not distract from content

## Status Indicators

```jsx
// Active/Selected state
<div className="w-3 h-3 bg-black" />
<span className="text-black font-bold">ACTIVE</span>

// Destructive/Error state
<div className="w-3 h-3 bg-red-600" />
<span className="text-red-600 font-bold">ERROR</span>
```

## Quick Reference

```jsx
// Editorial button
<button className="rounded-none border border-black bg-black text-white hover:bg-white hover:text-black">

// Editorial card
<div className="bg-white border border-black hover:bg-zinc-50">

// Editorial label
<label className="font-mono text-sm uppercase tracking-wider font-bold">

// Grid background
<div className="bg-white bg-grid-lines">
```

## Anti-Patterns

❌ Hard shadows (offset drop-shadows, blur)
❌ Rounded corners (`rounded-*` except `rounded-none`)
❌ Gradients
❌ Decorative icons or ornaments
❌ Pastel or muted colors (use pure black, white, gray, or signal red only)
❌ Colored text for semantic meaning (use icons/labels instead)
❌ Translate/press effects on hover (use color inversion only)
