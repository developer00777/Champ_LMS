# Champ LMS — DESIGN.md

Frontend design contract. Tokens live in `src/app.css`; this file explains them.
Reference direction: Nixtio's "E-learning Platform — Learning Plan Dashboard"
(Bogdan Nikitin, Dribbble): a black frame with centred icon nav and a notch
under the active tab, an off-white canvas, white 30px-radius cards on a dotted
path, pastel tiles, big numerals, ink pill and circle controls.

## 1. Visual theme & atmosphere
Calm learning dashboard. The shell frame is black in both themes. Light mode is
an off-white canvas with near-white cards; dark mode is a deep ink canvas with
charcoal cards and deep-tinted tiles (designed separately, not inverted).
Primary actions are ink (black in light, near-white in dark); Champ red
(`--brand`) is reserved for the mark, counts and highlights. Data gets colour through
pastel tiles, never through gradients on text.

## 2. Colour palette & roles
| Token | Light | Dark | Role |
|---|---|---|---|
| `--frame` | `#0c0c0d` | `#060607` | Top bar + outer frame |
| `--bg` | `#f4f4f1` | `#121215` | Content canvas |
| `--bg-alt` | `#eaeae6` | `#0d0d10` | Side rail panel |
| `--surface` | `#fdfdfb` | `#1b1b20` | Cards |
| `--surface2` | `#f0f0ec` | `#24242b` | Inputs, hovers, tracks |
| `--surface3` | `#e3e3de` | `#303038` | Pressed, dividers |
| `--text` | `#121214` | `#eeeef1` | Primary text |
| `--text-secondary` | `#4a4a51` | `#babac3` | Secondary text |
| `--muted` | `#6d6d75` | `#8f8f99` | Meta, labels |
| `--accent` | `#141416` (ink) | `#eeeef1` | Primary action, active, focus |
| `--on-accent` | `#fdfdfb` | `#121214` | Text on accent |
| `--brand` | `#e50914` | `#ff3b45` | Champ red: logo, counts |
| `--path` | `#4fb862` | `#4fd17f` | Dotted plan connector |
| `--success` / `--danger` / `--warn` / `--caution` / `--info` / `--violet` / `--teal` | deep variants | bright variants | Status + category, AA on `--surface` |
| `--tile-sky/-mint/-lilac/-butter/-peach` + `--tile-ink` | pastel | deep tint | Stat tiles, category chips |

Neutrals are near-neutral with a faint warm tint. No pure `#000`/`#fff`
surfaces. No purple-to-blue gradients, no cyan-on-dark.

## 3. Typography
- One family: **Satoshi** (Fontshare; 400/500/700/900), close to the
  reference. Card titles 500, page titles and numerals 700, logo 900.
- Fallbacks: `ui-sans-serif, system-ui, 'Segoe UI', sans-serif`.
- Scale: `--fs-hero: clamp(1.9rem, 1.2rem + 2.4vw, 3rem)`, h1 2rem, h2 1.4rem,
  h3 1.05rem, body 0.95–1rem, meta 0.78rem. Line-height 1.5 body, 1.1 display.
- Numerals in stat tiles use `font-variant-numeric: tabular-nums`.

## 4. Component stylings
- **Buttons:** `.btn-primary` ink pill (radius 999px), `.btn-ghost` neutral
  pill on `--surface2`. Hover: lift 1px + shadow. Active: `scale: .97`
  (individual `scale` property so it composes with existing transforms).
  Disabled: 45% opacity, no motion.
- **Cards:** `--surface`, 1px `--border`, `--radius-lg` (20px), shadow-sm;
  interactive cards lift 3px on hover with shadow-md.
- **Stat tiles:** pastel fill, 24px radius, big display numeral that counts up.
- **Inputs:** `--surface2` fill, 12px radius, focus = accent border + 4px soft
  accent ring.
- **Navigation:** centred icon tabs on the black frame; the active tab expands
  to icon + label and the canvas notch slides under it. Inactive tabs show a
  tooltip. Under 900px a drawer replaces the tabs.

## 5. Layout principles
- 4pt grid; spacing steps 4/8/12/16/20/24/32/48.
- Shell: 76px black top bar, canvas inset 10px with 30px top radius, content
  max 1440px, 28px gutters desktop, 16px mobile.
- Home: title + search → plan path (zig-zag, tiles atop the right column) →
  featured hero → course rows | 360px grey "My Quests" rail.

## 6. Depth & elevation
- `--shadow-sm`: hairline + 2px blur (resting cards).
- `--shadow` / `--shadow-md`: 12–24px soft lift (hover, popovers).
- `--shadow-lg`: modals.
- Dark mode relies on surface steps more than shadow.
- No glass: the top bar is an opaque part of the frame.

## 7. Do's and don'ts
- Do use one icon family (inline SVG, 1.75 stroke). Don't use emoji as UI chrome.
- Do animate only `transform`, `opacity`, `clip-path`, colour.
- Don't use coloured side stripes for new components (legacy pages keep theirs
  until redesigned).
- Don't clip gradients to text; don't add glows.

## 8. Responsive behaviour
- Breakpoints: 640 / 1024 / 1280.
- < 900px: tabs become an off-canvas drawer; top bar goes sticky.
- Touch targets ≥ 44px in the shell.
- Device class: pointer surface (desktop web) primary, phone secondary.
- **Motion budget:** 60fps; entries 420–520ms `cubic-bezier(.16,1,.3,1)`,
  feedback 120ms, state 240ms; stagger 45ms/item, max 10 steps. Container
  animations use `fill-mode: backwards` so no transform lingers (keeps
  `position: fixed` children working). Motion is on by default and switched
  off per browser from the profile menu (`data-motion="reduced"`, see
  `lib/stores/motion.ts`); the OS reduced-motion flag is not used because
  Windows sets it on slower machines for performance. App-wide entrances,
  click ripple and `use:tilt` live in `lib/actions/auto-motion.ts`; opt an
  area out of entrances with `data-no-motion`. No expressive tier.

## 9. Agent prompt guide
- Surfaces: `var(--surface)` on `var(--bg)`; borders `var(--border)`.
- Status text: `var(--danger|--warn|--success|--info)`; tints:
  `color-mix(in srgb, var(--danger) 14%, transparent)`.
- Entry motion: add `class="ui-rise"` (+ `style="--i:N"` for stagger) or the
  `use:reveal` action from `$lib/actions/motion`.
- Numbers: `use:countUp={value}`.
