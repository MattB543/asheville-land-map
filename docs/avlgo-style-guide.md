# AVL GO style guide (for land.avlgo.com)

How AVL GO (avlgo.com) looks, written so a plain CSS + Vite app can match it.

**Sources.** The repo is `C:\Users\matth\projects\asheville-event-feed`, read at local `main` = `536c6ae`. Every `file:line` below is relative to that repo. `origin/main` is 15 commits ahead, but those commits only touch `EventCard.tsx`, `EventFeed.tsx` and `ui/Calendar.tsx`, so line numbers in those three files may be off by a few lines. None of the style changes. I also inspected the live site (https://avlgo.com) with computed styles on 2026-09-30.

**How AVL GO is built.** Next.js 16 + Tailwind CSS v4.1.17 (`@tailwindcss/postcss`, `postcss.config.mjs`). There is no `tailwind.config`. Custom tokens live in `app/globals.css` under `@theme inline`, and everything else is inline Tailwind utility classes. Tailwind v4 defines its default colours in `oklch()`. The hex values below are sRGB conversions of `node_modules/tailwindcss/theme.css:10-275`, and they match Tailwind's published hex values.

**Reference screenshots** are in `claude/artifacts/screenshots/`:
- `avlgo-home-desktop-light.png`
- `avlgo-events-desktop-light.png`
- `avlgo-events-desktop-dark.png`
- `avlgo-mobile-events-and-home.png` (390 px wide)

> **Read this first: live fonts differ from the CSS.** `globals.css:2` `@import`s DM Sans and Fraunces from Google Fonts, but the production build drops that `@import`. The live CSS contains no `googleapis` URL and makes no font request. So:
> - **Body text renders in Inter.** It is loaded by `next/font` (`layout.tsx:2,7,152`). The `.__className` on `<body>` beats `body { font-family: 'DM Sans' }` (`globals.css:68`).
> - **Display headings (`.font-display`) render in Georgia.** Fraunces never loads, so the stack `'Fraunces', Georgia, serif` (`globals.css:73`) falls through to Georgia.
>
> Match what users see: **Inter for UI, Georgia (via the same stack) for display headings.** See §3.

---

## 1. Brand

| Item | Value | Source |
|---|---|---|
| Name | **AVL GO**: capitals, with a space. Used in titles, the footer, the login and the manifest. | `layout.tsx:10`, `page.tsx:148`, `manifest.ts:6` |
| Other spellings (avoid) | "AVLGO" (meta description only), "AVLGo.com" (OG image only) | `layout.tsx:13`, `public/avlgo-og.png` |
| Page title pattern | `%s \| AVL GO` | `layout.tsx:21` |
| Tagline | "Asheville events / All in one place"; OG image: "All Asheville events in one place" | `page.tsx:75-77`, `layout.tsx:67` |
| Contact | hi@avlgo.com | `InfoBanner.tsx:38` |
| Owner credit | "Built by Matt at Brooks Solutions, LLC." and "© {year} AVL GO." | `page.tsx:258-273`, `EventPageLayout.tsx:46-63` |

### Wordmark / logo

| Asset | File | Notes |
|---|---|---|
| Header wordmark | `public/avlgo_banner_logo_v2.svg` | "AVL" drawn as a mountain line, then "GO". One colour, `#0871aa` (fill and stroke). viewBox 2272.5 × 635.6 (≈ 3.58 : 1). |
| Older wordmark | `public/avlgo_banner_logo.svg` | Not referenced anywhere. Don't use it. |
| Favicon | `public/avlgo_favicon.svg` (900×900), `.ico` 32 px | White "GO" on a `#0871aa` square (`layout.tsx:46-52`). |
| Touch / PWA icons | `apple-touch-icon.png` 180, `favicon-192.png`, `favicon-512.png` | `layout.tsx:51`, `manifest.ts:17-47` |
| Social card | `public/avlgo-og.png` 1200×630 | Brand-blue background with white wordmark + serif text. |

**Header logo size** (`Header.tsx:28,70`):

| Viewport | Height |
|---|---|
| Below 640 px | 24 px |
| 640–1023 px | 30 px |
| 1024 px and up | 32 px (measured at 114 × 32) |

Width is `auto`.

**Dark mode.** The logo is not swapped; it is inverted to white with `filter: brightness(0) invert(1)` (Tailwind `dark:brightness-0 dark:invert`).

**Clear space.** The source has no stated rule. In the header it gets 12–16 px above and below (`py-3 sm:py-4`) and 24 px before the nav (`gap-6`, `Header.tsx:64`). Keep at least ½ the logo height clear on every side.

**Link target.** The logo always links to `/` (home). On land.avlgo.com, point it at `https://avlgo.com/`.

### Tone of voice

- **Short, plain, confident.** Sentence fragments are fine: "Dozens of sources. No ads or sponsorships. No broken incentives. Just awesome events." (`page.tsx:80-82`).
- **Civic and non-commercial:** "Built for Asheville, not for profit." (`page.tsx:237`), "No sponsors. No promotions. Free forever." (`page.tsx:166`).
- **Friendly, occasionally exclamatory, first-person plural:** "We'll grab your events automatically!" (`page.tsx:210`).
- **Local texture:** "Flyers spotted around Asheville — tap any poster to read what it says." (`posters/page.tsx:170`).
- **Casing:**
  - Title Case for nav, tabs and buttons: "All Events", "Top 30", "Your List", "Upload a poster".
  - Page and section headings are mostly sentence case: "Top 30 events in the next 30 days", "Jump into an event list".
- **Empty states give a next step:** "Try removing a filter to see more of the Top 30." (`EventFeed.tsx:2373`).
- **Uppercase is rare.** It is used only for small group labels (`FilterModal.tsx:662`).

---

## 2. Color

### 2.1 Brand scale: `--color-brand-*` (`globals.css:34-45`)

| Token | Hex | Main use |
|---|---|---|
| brand-50 | `#e8f4f8` | Tag background, active-tab background, hover wash, icon tiles |
| brand-100 | `#c5e3ed` | Tag border, avatar/medallion background, chip-input chip |
| brand-200 | `#9fd0e1` | Callout border |
| brand-300 | `#6bbdd4` | Dark-mode tag text, dark link hover; light border on "All Events"/"Top 30" home tiles |
| brand-400 | `#3aa9c7` | **Dark-mode accent text / links** |
| brand-500 | `#0a8bbf` | **Focus ring**, spinner, active filter-button border |
| **brand-600** | **`#0871aa`** | **THE brand colour.** Primary buttons, links, card titles, logo, `theme-color` |
| brand-700 | `#065c8a` | Primary hover, tag text (light) |
| brand-800 | `#044869` | Dark tag/callout border |
| brand-900 | `#033651` | Dark hover washes (`/50`) |
| brand-950 | `#021f30` | Dark tag background (`/50`), dark active tab (`/30`) |

Usage counts across `app/` and `components/`: brand-600 ×209, brand-400 ×110, brand-500 ×80, brand-700 ×75.

**Warm accent** (`globals.css:15-16,24-25,48-49`):
- `--accent-warm` / `warm-500` = `#e8825f`; `warm-600` = `#d4714f`.
- `--accent-warm-soft` is `#fdf0eb` in light and `#2a1f1a` in dark.
- Used only in the page texture (`globals.css:77-87`), the poster focus outline (`:330`) and the poster lightbox chips (`PosterLightbox.tsx:31`). Treat it as a rare decorative accent, not a UI colour.

**Secondary "teal"** (hard-coded hex, Top 30 only). Used for the "Email Alerts" / "Cal Sync" outline buttons and the active sort pill (`EventFeed.tsx:2281,2288,2340`; `Top30SubscribeBanner.tsx:22-42`):

| Role | Light | Dark |
|---|---|---|
| Text | `#2a7d9c` | `#7ec8e3` |
| Border | `#a8d8e8` | `#3a6a7a` |
| Hover background | `#e8f4f8` | `#1a3a4a` |
| Banner background | `#e8f4f8` | `#1a3a4a` |
| Banner border | `#c5e4ed` | `#2a5a6a` |

Optional; brand-600 does the same job everywhere else.

**Custom grey scale.** `--color-secondary-*` (`globals.css:52-62`) is defined but never used. Ignore it.

### 2.2 Neutrals: Tailwind v4 `gray` (cool, slightly blue)

| gray | 50 | 100 | 200 | 300 | 400 | 500 | 600 | 700 | 800 | 900 | 950 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hex | `#f9fafb` | `#f3f4f6` | `#e5e7eb` | `#d1d5dc` | `#99a1af` | `#6a7282` | `#4a5565` | `#364153` | `#1e2939` | `#101828` | `#030712` |

### 2.3 Semantic roles

| Role | Light | Dark | Source |
|---|---|---|---|
| Page background (app pages) | gray-50 `#f9fafb` | gray-950 `#030712` | `EventPageLayout.tsx:29`, `posters/page.tsx:127`, `loading.tsx:5` |
| Page background (home only) | `--background` `#faf9f7` (warm off-white) + `.bg-texture` | `#0f0f0f` | `globals.css:13,22`; `page.tsx:55` |
| `body` background / text | `#faf9f7` / `#1a1a1a` | `#0f0f0f` / `#f0ede8` | `globals.css:13-14,22-23,65-67` |
| Surface (header, cards, lists, modals, inputs) | `#ffffff` | gray-900 `#101828` (inputs, menus: gray-800 `#1e2939`) | `Header.tsx:17`, `EventFeed.tsx:2111`, `FilterBar.tsx:147` |
| Subtle fill (row hover, modal footer, inset panels) | gray-50 | gray-800 | `EventCard.tsx:901`, `FilterModal.tsx:428,1044` |
| Muted fill (segmented track, neutral active tab, date chip) | gray-100 `#f3f4f6` | gray-800 | `EventFeed.tsx:2299`, `EventTabSwitcher.tsx:46`, `EventCard.tsx:572` |
| Text, strong (h1/h2, titles) | gray-900 `#101828` | white / gray-100 `#f3f4f6` | `page.tsx:74`, `EventFeed.tsx:2275` |
| Text, date-group heading | gray-800 `#1e2939` | gray-100 | `EventFeed.tsx:2108` |
| Text, body/summary | gray-600 `#4a5565` (summaries); inherited `#1a1a1a` | gray-300 `#d1d5dc`; `#f0ede8` | `EventCard.tsx:1171`, `globals.css:14` |
| Text, label | gray-700 `#364153` | gray-200 `#e5e7eb` | `SubmitEventModal.tsx:262` |
| Text, secondary/meta | gray-500 `#6a7282` | gray-400 `#99a1af` | `EventCard.tsx:981`, `ActiveFilters.tsx:67` |
| Text, faint (placeholder, separators, chevrons) | gray-400 | gray-500 | `FilterBar.tsx:140,147` |
| Border, default | gray-200 `#e5e7eb` | gray-700 `#364153` (header: gray-800) | `Header.tsx:17`, `FilterBar.tsx:133` |
| Border, strong (list-row dividers, form inputs, outline buttons) | gray-300 `#d1d5dc` | gray-600 `#4a5565` | `EventCard.tsx:450`, `SubmitEventModal.tsx:271`, `SaveFeedModal.tsx:61` |
| Accent / link | brand-600 `#0871aa` | brand-400 `#3aa9c7` | `EventCard.tsx:518`, `ActiveFilters.tsx:118` |
| Link hover | underline, or brand-700 / brand-800 | brand-300 | `EventCard.tsx:521`, `ActiveFilters.tsx:118` |
| Primary button fill | brand-600 → hover brand-700, white text | **same** (no dark variant) | `SaveFeedModal.tsx:54` |
| Focus ring | 2 px brand-500 `#0a8bbf` (`focus:ring-2 focus:ring-brand-500 focus:border-brand-500`) | same | `FilterBar.tsx:147`, `SubmitEventModal.tsx:271` |
| Success / "Free" | bg green-50 `#f0fdf4`, text green-700 `#008236`, border green-200 `#b9f8cf` | bg green-950/50, text green-400 `#05df72`, border green-800 `#016630` | `EventCard.tsx:582` |
| Include (tri-state) | green-500 `#00c950` | same | `TriStateCheckbox.tsx:33` |
| Error / exclude / favourite | red-500 `#fb2c36` text & borders; red-600 `#e7000b` toast / destructive text; red-50/100 washes | red-400 `#ff6467` | `SubmitEventModal.tsx:245,253`, `Toast.tsx:113`, `EventCard.tsx:659` |
| Warning / highlight | amber-500 `#fe9a00` (only the "great match" star) | same | `EventCard.tsx:535` |
| Info (posters notice) | bg blue-50 `#eff6ff`, text blue-900, border blue-800/40 | bg blue-950/30, text blue-200 | `posters/page.tsx:174-175` |
| "Daily" badge | purple-50 / purple-700 `#8200db` / purple-200 | purple-950/50 / purple-400 / purple-800 | `EventCard.tsx:1004` |
| Overlay / backdrop | `rgb(0 0 0 / .5)` (+ optional `blur(8px)`); lightbox `rgb(0 0 0 / .9)` | same | `SubmitEventModal.tsx:201`, `SaveFeedModal.tsx:23`, `PosterLightbox.tsx:170` |
| Browser `theme-color` | `#0871aa` | `#0a0a0a` | `layout.tsx:120-123`, `manifest.ts:13` |

### 2.4 Chips and badges: colour sets

| Chip | Light (bg / text / border) | Dark (bg / text / border) | Source |
|---|---|---|---|
| Tag | brand-50 / brand-700 / brand-100 | brand-950 @50% / brand-300 / brand-800 | `EventCard.tsx:866` |
| Date/time | gray-100 / gray-700 / gray-200 | gray-800 / gray-300 / gray-600 | `EventCard.tsx:572` |
| Price (paid / unknown), **bold** | gray-50 / gray-700 / gray-200 | gray-800 / gray-300 / gray-600 | `EventCard.tsx:584` |
| Price "Free", **bold** | green-50 / green-700 / green-200 | green-950 @50% / green-400 / green-800 | `EventCard.tsx:583` |
| Filter chip (active) | brand-100 / brand-800 / brand-200 | brand-900 @50% / brand-200 / brand-700 | `ui/FilterChip.tsx:16` |
| Filter chip (default) | gray-100 / gray-700 / gray-200 | gray-800 / gray-200 / gray-700 | `ui/FilterChip.tsx:14` |

### 2.5 How the mode is chosen

- `next-themes` with `attribute="class"`, `defaultTheme="system"`, `enableSystem`, `enableColorScheme` and `disableTransitionOnChange` (`ThemeProvider.tsx:12-17`).
- The `<html>` element gets class `light` or `dark`. Tailwind's dark variant is `&:where(.dark, .dark *)` (`globals.css:7`).
- The preference is stored as `localStorage.theme` = `light` | `dark` | `system`.
- An inline `<head>` script (`layout.tsx:130-139`) adds `.dark` before first paint.
- The header toggle offers **Light / Dark / System** (`ThemeToggle.tsx:36-40`).
- **localStorage is per-origin.** A choice made on avlgo.com will not carry over to land.avlgo.com. Default to System.

---

## 3. Typography

### 3.1 Families and loading

| Role | Stack (as rendered) | Loaded by | Weights in use |
|---|---|---|---|
| UI / body (everything) | `Inter, "Inter Fallback"` | `next/font/google` `Inter({ subsets: ['latin'] })`: a self-hosted variable font, axis `wght 100–900`, `font-display: swap` (`layout.tsx:2,7,152`) | 400, 500, 600, 700 |
| Display (home hero, home section heads, home footer tagline, poster lightbox title) | `'Fraunces', Georgia, serif` → **renders as Georgia** | nothing (see top note) | 400, 600, 700 |
| Mono | not styled (`--font-mono: var(--font-geist-mono)` is undefined, `globals.css:31-32`) | none | none |

**The size-matched fallback `next/font` generates** (copied from the live CSS; include it):

```css
@font-face { font-family: 'Inter Fallback'; src: local('Arial');
  ascent-override: 90.44%; descent-override: 22.52%; line-gap-override: 0%; size-adjust: 107.12%; }
```

**Reproducing Inter in Vite.** Use one of these:

- **Google Fonts** (same variable axis `next/font` uses):
  ```html
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@100..900&display=swap" rel="stylesheet">
  ```
- **Self-host (recommended for civic-mapper).** The app already self-hosts DM Sans in `viz/public/fonts/` (`viz/src/design-system.css:7-30`). The Azure CSP has `font-src 'self' data:` (`viz/public/staticwebapp.config.json:68`). Vercel sets no CSP today. Add an Inter variable `.woff2` (latin, `wght 100 900`) to `viz/public/fonts/` with an `@font-face` in the same style, and drop the Google `<link>`.
- **Display font.** To match live, declare the stack `'Fraunces', Georgia, serif` and **do not load Fraunces**. If AVL GO later fixes its import, load it with exactly the source URL (`globals.css:2`):
  ```
  https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;0,9..144,700&display=swap
  ```

### 3.2 Type scale

Sizes are Tailwind v4 defaults; each size carries its own line height (`theme.css:299-318`).

| Role | Font | Size / line-height | Weight | Tracking / other | Colour | Source |
|---|---|---|---|---|---|---|
| Hero h1 (home) | Display | 36/40 → sm 48/48 → lg **60/60** | 700 | `-0.025em` (−1.5 px at 60) | gray-900 / white; line 2 brand-600 / brand-400 | `page.tsx:74-77` (live: 60 px, −1.5 px) |
| Hero lead | Inter | 18 → sm **20**, `line-height: 1.625` (32.5 px) | 500 | none | gray-800 / gray-200 | `page.tsx:79` |
| Section heading (home) | Display | 24/32 → sm **30/36** | 600 | centred | gray-900 / white | `page.tsx:105,147` |
| **Page title (app pages)** | Inter | 18/28 → sm **24/32** | 700 | none | gray-900 / gray-100 | `EventFeed.tsx:2275`, `posters/page.tsx:135` |
| Detail-page h1 | Inter | 24/32 → lg 30/36 | 700 | none | gray-900 / gray-100 | `EventContent.tsx:280` |
| Group heading (sticky date) | Inter | **20/28** | 700 | none | gray-800 / gray-100 | `EventFeed.tsx:2108` |
| Modal title | Inter | 20/28 | 700 | none | gray-900 / gray-100 | `FilterModal.tsx:384`, `SubmitEventModal.tsx:204` |
| Panel section heading | Inter | 18/28 | 600 | 20 px brand icon, 8 px gap | gray-900 / gray-100 | `FilterModal.tsx:399-400` |
| **Card title** | Inter | **16/20** (`leading-tight`) | 700 | none | **brand-600 / brand-400**, underline on hover | `EventCard.tsx:518,952` |
| Tile / feature title | Inter | 16/24 | 600 | none | gray-900 / white | `page.tsx:153` |
| Compact-row title | Inter | 14/20 | 500 | none | brand-600 / brand-400 | `EventCard.tsx:838` |
| Body / summary | Inter | **14**, `line-height: 1.625` | 400 | none | gray-600 / gray-300 | `EventCard.tsx:1171` |
| Body (default) | Inter | 16/24 | 400 | none | `#1a1a1a` / `#f0ede8` | `globals.css:65-68` |
| Form label | Inter | 14/20 | 500 | none | gray-700 / gray-200 | `SubmitEventModal.tsx:262` |
| Button (default) | Inter | 14/20 | 500 (hero CTA 16/24, 600) | none | none | `PosterUploadButton.tsx:14`, `page.tsx:86` |
| Nav tab | Inter | 12/16 → sm 14/20 | 500 | none | see §6 | `EventTabSwitcher.tsx:44` |
| Meta / secondary | Inter | **12/16** | 400 (date line 500) | none | gray-500 / gray-400 (date: gray-900 / gray-100) | `EventCard.tsx:974,981` |
| Chip / badge | Inter | 12/16 | 500 (price 700) | none | §2.4 | `EventCard.tsx:572-585` |
| Menu sub-line | Inter | 10 px | 400 | none | gray-500 / gray-400 | `FilterBar.tsx:212,234` |
| Group label (rare) | Inter | 12/16 | 600 | `uppercase`, `0.05em` | gray-500 / gray-400 | `FilterModal.tsx:662` |

---

## 4. Spacing and layout

| Item | Value | Source |
|---|---|---|
| Spacing unit | 4 px (`--spacing: 0.25rem`). Common steps: 4, 6, 8, 12, 16, 20, 24, 32, 40, 48 | `theme.css:277` |
| Content max-width | **1280 px** (`max-w-7xl`), centred | `Header.tsx:18`, `EventFeed.tsx:1774` |
| Side gutters | **12 px** (<640) · **24 px** (≥640) · **32 px** (≥1024) (`px-3 sm:px-6 lg:px-8`) | `Header.tsx:18`, `page.tsx:73` |
| Feed on mobile | Container `px-0`: lists go full-bleed and each row pads 12 px itself | `EventFeed.tsx:1774`, `EventCard.tsx:449` |
| Breakpoints | sm 640 · md 768 · **lg 1024** (header switches from two rows to one) · xl 1280 (card gains a third column) | `theme.css:279-283`, `Header.tsx:20,63` |
| Header | Height **65 px** desktop (64 + 1 px border); **86 px** at 390 px wide (two rows: logo + actions, then tabs + credit). Padding 12 / 16 px vertical. **Not sticky.** | `Header.tsx:17-18`; measured live |
| Header spacing | Logo → tabs 24 px · tabs 4 px apart (2 px mobile) · right actions 8 px apart (4 px mobile) | `Header.tsx:64,75,31`; `EventTabSwitcher.tsx:41` |
| Sticky elements | Date-group headings `position: sticky; top: 0; z-index: 10` · "Similar Events" bar `z-index: 20` · scroll-to-top pill fixed `bottom: 24px`, centred, `z-index: 50` | `EventFeed.tsx:2108,2876`; `SimilarEventsSection.tsx:180` |
| Toolbar | Search + buttons row: height 36 → 40 px, gap 6 → 8 px, 24 px below | `FilterBar.tsx:136-147` |
| List row padding | Mobile 16 × 12 px; desktop full 24 × 20 px; compact 10 × 20 px | `EventCard.tsx:449,890-891,831` |
| Card grid (desktop) | `192px 1fr` (gap 16) → xl `192px 384px 1fr` | `EventCard.tsx:890-893` |
| Gaps between groups | 40 px between date groups · 12–16 px in tile grids · 48 px section padding (home) | `EventFeed.tsx:2061`; `page.tsx:104,108,150` |
| Card / panel padding | Tiles 16 px · feature cards 20 px · modals 24 px (Filter modal 16) · callouts 12 × 16 px | `HomeFilterButton.tsx:13`, `page.tsx:151`, `SubmitEventModal.tsx:203,214`, `EventFeed.tsx:1939` |
| Footer | `margin-top: 32px`, 32 px vertical padding, white / gray-900, top border, centred 14 px gray-500 | `EventPageLayout.tsx:46` |
| z-index | Sticky 10–20 · menus 30–50 · modals 50 · toasts 50 | various |

---

## 5. Shape and depth

### Radius

Usage counts: `rounded-lg` ×210, `rounded` ×79, `rounded-xl` ×52, `rounded-full` ×51, `rounded-md` ×43.

| Radius | px | Used on |
|---|---|---|
| `rounded` | **4** | Chips/tags/badges, card action buttons, card thumbnails (desktop), card menus, tooltips |
| `rounded-md` | **6** | Header icon buttons, nav tabs, segmented-control items, theme menu |
| `rounded-lg` | **8** | **Default:** buttons, inputs/search, list containers, dropdowns, toasts, callouts, mobile card image |
| `rounded-xl` | **12** | Home tiles, feature cards, modals, login card, empty-state panel, `.icon-circle` |
| `rounded-full` | pill | Hero/secondary CTAs, filter chips, avatar, scroll-to-top, spinners, footer links |

List containers are `8px` on all corners (the sticky heading is `8px 8px 0 0` and the list body `0 0 8px 8px`); on mobile they have **no radius and no side border** (`sm:` only).

### Borders

- Always 1 px solid: gray-200 by default, gray-300 for list dividers and form inputs.
- No 2 px borders except spinners and a `border-t-2` above "Similar Events" (`SimilarEventsSection.tsx:179`).

### Shadows

Tailwind v4 defaults (`theme.css:358-364`):

| Token | Value | Used on |
|---|---|---|
| sm | `0 1px 3px 0 rgb(0 0 0/.1), 0 1px 2px -1px rgb(0 0 0/.1)` | List containers, active segment, mobile card image |
| md | `0 4px 6px -1px rgb(0 0 0/.1), 0 2px 4px -2px rgb(0 0 0/.1)` | Secondary pill CTA, slider thumb |
| **lg** | `0 10px 15px -3px rgb(0 0 0/.1), 0 4px 6px -4px rgb(0 0 0/.1)` | **All dropdowns / menus, toasts, tooltips, login card**; tile hover (tinted `brand-600/5`) |
| xl | `0 20px 25px -5px rgb(0 0 0/.1), 0 8px 10px -6px rgb(0 0 0/.1)` | Modals, scroll-top hover |
| 2xl | `0 25px 50px -12px rgb(0 0 0/.25)` | Save-feed modal |
| Brand glow | `shadow-lg` tinted `brand-600/25` → `/40` on hover | Hero CTA (`page.tsx:86`) |
| Card lift | `0 8px 24px -8px rgb(0 0 0/.1)` (dark `.4`) + `translateY(-2px)` | Feature cards (`globals.css:216-229`) |

### Blur

Used sparingly:
- `backdrop-blur-sm` (8 px) on the Save-feed modal backdrop (`SaveFeedModal.tsx:23`).
- `backdrop-blur-sm` on the floating "Filtering..." pill (`bg-white/95`, `EventFeed.tsx:1805`).
- The code comments say to avoid blur and filters on scrolling lists for performance (`globals.css:294-297`).

---

## 6. Components (recipes)

`a / b` means light / dark. Hover states are in brackets.

### Header / nav (`Header.tsx`)

**Header bar**
- White / gray-900 background, 1 px bottom border gray-200 / gray-800. No shadow, not sticky.
- Inner container: 1280 px max, standard gutters.

**Desktop layout (lg and up)**
- One row: `[logo 32px]` then 24 px, then tabs; `justify-between`.
- Right side: credit "Open-sourced by Matt" in 14 px gray-500 at **50 % opacity**, underlined (hover gray-600). Then icon buttons.

**Mobile layout (below lg)**
- Row 1: logo + icon buttons.
- Row 2: tabs + credit (12 px).
- 8 px between rows.

**Icon button** (`ThemeToggle.tsx:48`, `SubmitEventButton.tsx:14`, `UserMenu.tsx:59`)
- 6 px padding, 16 px lucide icon in gray-600 / gray-300. Renders about 30 × 30 px.
- 1 px border gray-200 / gray-700, white / gray-800 background, radius 6.
- Hover: gray-100 / gray-700.

**Nav tabs** (`EventTabSwitcher.tsx:41-82`)
- Link pills, 6 × 12 px (4 × 8 on mobile), 14 px (12 on mobile), weight 500, radius 6. `transition-colors`.
- Inactive: gray-500 / gray-400 (hover: gray-700 text on gray-50).
- Active (feature tabs): brand-600 on brand-50 (dark: brand-400 on brand-950 @30%).
- Active "All Events": gray-900 on gray-100 (dark: white on gray-800).

### Footer (`EventPageLayout.tsx:46-63`; home variant `page.tsx:234-274`)

**App footer**
- White / gray-900 background, 1 px top border, 32 px vertical padding, centred 14 px gray-500 / gray-400.
- Lines: "Built by [Matt] at Brooks Solutions, LLC." / "© YYYY AVL GO. Not affiliated with…". Links are underlined, hover gray-700.

**Home footer**
- Display-font tagline at 20–24 px ("Built for Asheville, not for profit.").
- Pill links: 8 × 16 px, gray-100 / gray-800 background (hover gray-200 / gray-700), 14 px, full radius.

### Buttons

Base for all: Inter, `cursor: pointer`, `transition: color, background-color, border-color 150ms cubic-bezier(.4,0,.2,1)`.

| Variant | Recipe | Source |
|---|---|---|
| **Primary** | bg brand-600, white, weight 500, radius 8 [hover brand-700]. Same in dark. | `SaveFeedModal.tsx:54`, `PosterUploadButton.tsx:14` |
| Primary sizes | **sm** 6 × 12 px, 14 px · **md** 8 × 16 px, 14 px (or 8 × 24) · **lg** 12 × 24 px, 16 px, often full-width with a 20 px icon | `EventContent.tsx:358`; `EmailDigestSettings.tsx:495`, `FilterModal.tsx:1047`; `SaveFeedModal.tsx:54` |
| Hero CTA (pill) | brand-600, white, weight 600, full radius, 16 × 48 px, 20 px icon + 10 px gap, `shadow-lg` in brand-600 @25% (hover @40%), shimmer sweep on hover | `page.tsx:86`, `globals.css:195-213` |
| Secondary CTA (pill) | brand-600, white, weight 600, full radius, 12 × 24 px, `shadow-md` (hover `shadow-lg`), trailing arrow | `EventFeed.tsx:2551` |
| **Secondary / outline** | Transparent, 1 px gray-300 / gray-600, text gray-700 / gray-300, weight 500, radius 8 [hover bg gray-50 / gray-800] | `SaveFeedModal.tsx:61` |
| **Neutral toolbar** | White / gray-800, 1 px gray-200 / gray-700, text gray-700 / gray-200, radius 8, height 36 → 40 px, 0 × 10–12 px [hover gray-50 / gray-700]. "On" state: border brand-500 plus a brand-600 count. | `FilterBar.tsx:132-133,174-184` |
| Small card action | 6 × 10 px, 12 px, gray-600 / gray-400, 1 px gray-200 / gray-700, **radius 4**, height 30 px, 14 px icon [hover brand-50 bg + brand-600 text]. Favourite "on": red-500 on red-50, border red-200. | `EventCard.tsx:606,657-661,686` |
| **Ghost** (close, clear) | 4–8 px padding, gray-400 icon, radius 8 [hover gray-600 text, gray-100 / gray-800 bg] | `SaveFeedModal.tsx:30`, `FilterModal.tsx:387` |
| Text button | 14 px brand-600 / brand-400 [hover brand-800 / brand-300 + underline] | `ActiveFilters.tsx:118` |
| Destructive text | 14 px weight 500, red-600 / red-400 [hover red-700 / red-300] | `FilterModal.tsx:985` |
| Disabled | `opacity: .5` (sometimes `.6`) + `cursor: not-allowed`; the login submit uses bg brand-400 | `SubmitEventModal.tsx:306`, `login/page.tsx:200` |
| Active / pressed | No pressed style; only hover changes | none |

### Links

- Inline content links: brand-600 / brand-400, no underline, underline on hover (`EventCard.tsx:521`).
- Footer and credit links: inherit the muted grey, always underlined, darker on hover (`EventPageLayout.tsx:53`).
- Arrow link: "or view today's events →", 16 px weight 500 brand-600 [hover brand-700] with a 16 px `ArrowRight` (`page.tsx:94-97`).

### Tabs and segmented controls

**Segmented control** (`EventFeed.tsx:2299-2330`)
- Track: gray-100 / gray-800, radius 8, 4 px padding, 8 px gap.
- Items: 6 × 12 px, 14 px, weight 500, radius 6.
- Active item: white / gray-700 background, brand-600 / brand-400 text, `shadow-sm`.
- Inactive item: gray-600 / gray-400 (hover gray-800 / gray-200).

**Inline text toggle** (`EventFeed.tsx:2635-2670`)
- "Top Events | All Events": 14 px weight 400, active brand-600, inactive gray-400.
- Separator is a gray-300 "|".

**Page-level tabs** (e.g. posters Upcoming / All) reuse the header tab pill (`posters/page.tsx:46-52`).

### Chips / badges / pills

| Chip | Recipe | Source |
|---|---|---|
| Badge / tag | `inline-flex`, 2 × 8 px, 12 px, weight 500, **radius 4**, 1 px border, colours from §2.4. Tags sit 6 px apart and are clipped to one line. | `EventCard.tsx:572,866` |
| Filter chip | Pill (full radius), 4 × 10 px, 12 px, weight 500, 1 px border, optional × (12 px) in a round hover target (`hover: black/10`) | `ui/FilterChip.tsx:33-45` |
| Chip-input chip | Pill, 4 × 10 px, 14 px, brand-100 / brand-800 text (dark brand-900 @50% / brand-200) | `ui/ChipInput.tsx:65` |
| Detail-page tag | Same colours as a tag but a **pill** (full radius) | `EventContent.tsx:342` |

### Cards and lists

**Event list** (the core pattern; `EventFeed.tsx:2107-2111`, `EventCard.tsx`)
- Group = a sticky heading (white, 20 px bold date text, 12 / 8 / 16 px padding, bordered, radius 8 top only) + a body (white, bordered, radius 8 bottom only, `shadow-sm`). On mobile both are edge-to-edge without borders.
- Rows are separated by a 1 px gray-300 / gray-600 **bottom border** (`EventCard.tsx:450,892`). Row hover: gray-50 / gray-800. Transitions: 300 ms on the full card, opacity on the compact row.

**Compact row** (desktop "minimized", `EventCard.tsx:831-882`)
- 10 × 20 px, at 80 % opacity until hover.
- Left: title (14 px weight 500 brand-600) + " - " + venue (14 px gray-500, truncated).
- Right: up to 3 tags, then the date chip, then a 14 px chevron.

**Full desktop row** (`EventCard.tsx:890-1200`)
- Grid: `192px | 1fr` (xl: `192px | 384px | 1fr`), gap 16 px, padding 24 × 20 px.
- **Image:** 192 × 128 px, radius 4, gray-200 placeholder, `object-fit: cover; object-position: center 20%`. Fallback photo is `/asheville-default.jpg`.
- **Middle column:**
  - Title: 16 px bold brand-600, leading 1.25.
  - Date line: 12 px weight 500 gray-900.
  - Location: 12 px gray-500, one line.
  - Chips at the bottom: price, then tags.
- **Right column:**
  - Summary: 14 px gray-600, leading 1.625.
  - "View original" link: 12 px weight 500 brand-600.
  - Action row: Calendar ▾, ♥ count, share, ⋮.

**Mobile card** (`EventCard.tsx:449-600`)
- 16 × 12 px padding.
- Full-width image, 130 px tall (192 px when expanded), radius 8, `shadow-sm`.
- Then title + 16 px chevron, 12 px organiser, a 2-line summary, and a chip row.
- The card expands on tap.

**Home tile** (`HomeFilterButton.tsx:13-18`)
- White / gray-900, 1 px gray-200 @80%, radius 12, 16 px padding.
- 36 px icon tile (radius 8, brand-50 background, 20 px brand-600 icon), 14 px weight 500 label, trailing 16 px arrow.
- Hover: border brand-400, `shadow-lg` tinted brand-600 @5%, `translateY(-2px)`, arrow moves 4 px right and turns brand-500. 200 ms.

**Feature card** (`page.tsx:151-160`, `globals.css:216-245`)
- 20 px padding, radius 12; `.card-lift` hover.
- `.icon-circle`: 48 × 48 px, radius 12, gradient `brand-50 → #f0f9ff` (dark: brand-600 @15% → @8%).

**Callout** (`EventFeed.tsx:1939-1941`)
- brand-50 / brand-950 @50%, 1 px brand-200 / brand-800, radius 8, 12 × 16 px.
- 18 px brand icon + 14 px brand-700 / brand-300 text.

### Inputs / selects / search

**Search** (`FilterBar.tsx:139-170`)
- Height 36 → 40 px, 14 px text, left padding 36–40 px for a 16 px gray-400 `Search` icon at 10–12 px.
- 1 px gray-200 / gray-700 border, white / gray-800 background, radius 8, placeholder gray-400 / gray-500 ("Search events...").
- Focus: `outline: none; box-shadow: 0 0 0 2px #0a8bbf; border-color: #0a8bbf`.
- Right-hand action (6 px padding, radius 6): brand-500 submit arrow (hover brand-600), or a ghost × to clear.

**Form field** (`SubmitEventModal.tsx:259-297`)
- Label: 14 px weight 500 gray-700 / gray-200, 4 px below.
- Input: full width, 8 × 12 px, 1 px gray-300 / gray-600, white / gray-800 background, gray-900 / gray-100 text, radius 8, same focus ring.
- Error: border red-500 + a 14 px red-500 message 4 px below.
- Fields sit 16 px apart; two-column rows use a 16 px gap.

**Select.** AVL GO has **no `<select>`**. Style one like the form input, with `appearance: none` and a 16 px lucide `ChevronDown` in gray-400 on the right.

**Checkbox / radio.** Native, 16 px (`FilterModal.tsx:419,631`). The source asks for brand-600 via `text-brand-600`, but there is no `@tailwindcss/forms` plugin, so live they show the browser-default colour. Use `accent-color: #0871aa` to get what was intended.
- Option rows: 4–6 × 8 px, radius 8, hover gray-50 / gray-800.
- Tri-state box: 16 px, radius 4, green-500 ✓ or red-500 × (`TriStateCheckbox.tsx:29-38`).

**Toggle grid** (days / times, `FilterModal.tsx:463-466,569-572`)
- Buttons: 8 px vertical padding, 12 px weight 500, radius 4.
- On: brand-600 fill, white text. Off: white / gray-700 with 1 px gray-200 border.

**Range slider** (`ui/PriceSlider.tsx:58-69`)
- Track: 8 px tall, gray-200 / gray-700, full radius.
- Thumb: 20 px, brand-600, 2 px white border, `shadow-md`, `scale(1.1)` on hover.

### Dropdowns / popovers / tooltips

**Menu** (`FilterBar.tsx:198`, `UserMenu.tsx:101`)
- Absolute, 4–8 px below the trigger, right-aligned.
- White / gray-800 (user menu: gray-900), 1 px gray-200 / gray-700, **radius 8**, `shadow-lg`, `z-index: 30–50`, min-width 160–220 px.
- Items: 8 × 12–16 px, 12–14 px text, gray-700 / gray-300, 8 px gap, 14–16 px icon, hover gray-100 / gray-700.
- Two-line item: 12 px weight 500 title + 10 px gray-500 sub-line.
- Divider: 1 px gray-200 / gray-700.
- Selected: brand-600 text, weight 500 (`ThemeToggle.tsx:63-66`).
- The theme menu uses radius 6 and card menus use radius 4 (`EventCard.tsx:618,710`); **use 8**.

**Tooltip** (`EventCard.tsx:692-694`)
- 4 × 8 px, 12 px weight 500 white on gray-800 / gray-700, radius 4, `shadow-lg`, 4 px CSS-triangle arrow, `fade-in 150ms`.

### Modals

**Backdrop.** Fixed full-screen, `rgb(0 0 0/.5)`, flex-centred, 16 px padding, `z-index: 50`.

**Dialog** (`SubmitEventModal.tsx:202`, `SaveFeedModal.tsx:26`)
- White / gray-900, **radius 12**, `shadow-xl`, optional 1 px gray-200 / gray-800 border.
- Width: `max-width: 28rem` (confirm) / `32rem` (form) / `42rem` (filters).
- Height: `max-height: 90vh; overflow-y: auto`.
- Entry animation: `fade-in 150ms` (`SaveFeedModal.tsx:26`).

**Parts**
- Header: 24 px padding (16 in filters), bottom border, 20 px bold title, ghost × (20 px icon) on the right.
- Body: 24 px padding, 24 px between sections.
- Footer: 12 × 16 px, top border, gray-50 / gray-800 background, primary button right-aligned (`FilterModal.tsx:1044-1047`).

**On mobile** the filter dialog goes full-screen with no radius (`FilterModal.tsx:379`).

**Confirm-style modal** (`SaveFeedModal.tsx:36-64`)
- 64 px round brand-100 medallion with a 32 px brand-600 icon, centred title and text.
- Stacked full-width primary + outline buttons, 12 px apart.

### Loading and empty states

**Skeleton** (`EventCardSkeleton.tsx:3-41`, `loading.tsx:20-33`)
- gray-200 / gray-700 blocks, radius 4–8, `animate-pulse` (opacity 1 → .5, 2 s).
- Header placeholders are gray-100 / gray-800.

**Spinner** (`EventFeed.tsx:2175,1807`; `ActiveFilters.tsx:41`)
- Ring: 32 px with a 4 px border (or 16 px with 2 px), brand-500 with a transparent top, `animate-spin` (1 s linear). Neutral variant: gray-400.
- Inline alternative: lucide `Loader2` 16–20 px spinning next to 14 px gray-500 text ("Loading more events...").

**Floating status pill** (`EventFeed.tsx:1805`)
- Centred, `bg-white/95` + `blur(8px)`, full radius, `shadow-lg`, 1 px border, spinner + "Filtering...".

**Empty state** (`EventFeed.tsx:2194-2215`)
- Centred, 80 × 16 px padding.
- 48 px icon in gray-400 (brand-500 for CTA variants), 16 px below.
- 18 px weight 600 gray-700 / gray-300 heading, 8 px below.
- 14 px gray-500 text at `max-width: 28rem`.
- Optional primary button 24 px below.
- Boxed variant: white panel, 1 px border, radius 12, 32 px padding (`posters/page.tsx:202`).

**Toast** (`ui/Toast.tsx:92-153`)
- Fixed bottom-right, 16 px inset, stacked 8 px apart.
- 12 × 16 px, radius 8, `shadow-lg`, 16 px icon + 14 px weight 500 text + × button.
- Colours: success gray-900, error red-600, info brand-600, all with white text.
- `slide-in` from the right, 200 ms ease-out.

### Icons

- Library: **lucide** (`lucide-react ^0.554.0`, `package.json`). For Vite use the `lucide` vanilla package or `lucide-static` SVGs. Default stroke is 2 (3 inside checkboxes).
- Sizes:

| Size | Where |
|---|---|
| 12 px | Chip × |
| 14 px | Card actions, menu items |
| **16 px** | Header / toolbar / inline — the default |
| 18 px | Filter button, callout |
| 20 px | Section icons, CTA icons, close × |
| 24 px | Feature cards |
| 48 px | Empty states |

- Icons inherit the text colour. Accent icons are brand-600 / brand-400; resting chevrons are gray-400.

---

## 7. Motion

| What | Duration / easing | Source |
|---|---|---|
| Default hover (colour, border, background) | **150 ms `cubic-bezier(0.4, 0, 0.2, 1)`** | `theme.css:444-445` |
| Tile hover (lift −2 px, border, shadow, arrow +4 px) | 200 ms, same easing | `HomeFilterButton.tsx:13,18` |
| `.card-lift` | `transform, box-shadow 0.2s ease` | `globals.css:216-225` |
| Card expand / collapse / hide (slides 16 px left while fading) | 300 ms | `EventCard.tsx:449,890` |
| Chevron rotate 180° | 150–200 ms | `EventCard.tsx:542` |
| Tooltip / modal fade-in | 150 ms ease-out | `globals.css:130-141` |
| Toast slide-in (`translateX(100%) → 0`) | 200 ms ease-out | `ui/Toast.tsx:142-153` |
| Staggered list fade-up (16 px) | 500 ms ease-out, 50 ms steps | `globals.css:144-177` |
| Heart pop | 300 ms ease-out | `globals.css:107-127` |
| CTA shimmer sweep | 500 ms ease | `globals.css:195-213` |
| Scroll-to-top pill show / hide (opacity + 16 px rise) | 300 ms | `EventFeed.tsx:2876` |
| Theme switch | **No transition** (`disableTransitionOnChange`) | `ThemeProvider.tsx:17` |
| Reduced motion | Only the poster wall honours `prefers-reduced-motion`. **Do this everywhere in the new app.** | `globals.css:402-411` |

---

## 8. Paste-ready tokens

```html
<!-- In <head>, before any CSS. Inter as next/font serves it (variable 100–900, swap). -->
<!-- Self-hosting Inter in viz/public/fonts is preferred (see §3.1); if so, drop these three lines. -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@100..900&display=swap" rel="stylesheet">

<!-- No-flash theme script (mirrors layout.tsx:130-139, but also honours 'system') -->
<script>
  (function () {
    try {
      var t = localStorage.getItem('theme');
      var dark = t === 'dark' || ((!t || t === 'system') && matchMedia('(prefers-color-scheme: dark)').matches);
      document.documentElement.classList.add(dark ? 'dark' : 'light');
    } catch (e) {}
  })();
</script>
```

```css
@font-face {
  font-family: 'Inter Fallback'; src: local('Arial');
  ascent-override: 90.44%; descent-override: 22.52%; line-gap-override: 0%; size-adjust: 107.12%;
}

:root {
  color-scheme: light;

  /* Brand (globals.css:35-45) */
  --avl-brand-50: #e8f4f8;  --avl-brand-100: #c5e3ed; --avl-brand-200: #9fd0e1;
  --avl-brand-300: #6bbdd4; --avl-brand-400: #3aa9c7; --avl-brand-500: #0a8bbf;
  --avl-brand-600: #0871aa; --avl-brand-700: #065c8a; --avl-brand-800: #044869;
  --avl-brand-900: #033651; --avl-brand-950: #021f30;
  --avl-warm-500: #e8825f;  --avl-warm-600: #d4714f;

  /* Tailwind v4 gray, sRGB */
  --avl-gray-50: #f9fafb;  --avl-gray-100: #f3f4f6; --avl-gray-200: #e5e7eb;
  --avl-gray-300: #d1d5dc; --avl-gray-400: #99a1af; --avl-gray-500: #6a7282;
  --avl-gray-600: #4a5565; --avl-gray-700: #364153; --avl-gray-800: #1e2939;
  --avl-gray-900: #101828; --avl-gray-950: #030712;

  /* Status (Tailwind v4, sRGB) */
  --avl-green-50: #f0fdf4; --avl-green-200: #b9f8cf; --avl-green-500: #00c950; --avl-green-700: #008236;
  --avl-red-50: #fef2f2;   --avl-red-200: #ffc9c9;   --avl-red-500: #fb2c36;   --avl-red-600: #e7000b;
  --avl-amber-500: #fe9a00;
  --avl-purple-50: #faf5ff; --avl-purple-200: #e9d4ff; --avl-purple-700: #8200db;

  /* Semantic: light */
  --avl-bg-page: var(--avl-gray-50);       /* app pages; home uses #faf9f7 */
  --avl-bg-surface: #ffffff;               /* header, panels, cards, modals, inputs */
  --avl-bg-subtle: var(--avl-gray-50);     /* row hover, modal footer, inset panel */
  --avl-bg-muted: var(--avl-gray-100);     /* segmented track, neutral active tab */
  --avl-bg-control: #ffffff;               /* inputs, toolbar buttons, menus */
  --avl-bg-control-hover: var(--avl-gray-50);
  --avl-bg-skeleton: var(--avl-gray-200);
  --avl-overlay: rgb(0 0 0 / 0.5);

  --avl-text: #1a1a1a;                     /* inherited body text */
  --avl-text-strong: var(--avl-gray-900);  /* titles, headings */
  --avl-text-heading: var(--avl-gray-800); /* sticky group headings */
  --avl-text-body: var(--avl-gray-600);    /* summaries, paragraphs */
  --avl-text-label: var(--avl-gray-700);
  --avl-text-muted: var(--avl-gray-500);   /* meta, secondary */
  --avl-text-faint: var(--avl-gray-400);   /* placeholder, chevrons */

  --avl-border: var(--avl-gray-200);
  --avl-border-strong: var(--avl-gray-300);/* list dividers, form inputs */
  --avl-border-header: var(--avl-gray-200);

  --avl-accent: var(--avl-brand-600);      /* primary fill (both modes) */
  --avl-accent-hover: var(--avl-brand-700);
  --avl-on-accent: #ffffff;
  --avl-link: var(--avl-brand-600);        /* accent TEXT: titles, links, active tab */
  --avl-link-hover: var(--avl-brand-700);
  --avl-accent-soft-bg: var(--avl-brand-50);
  --avl-accent-soft-border: var(--avl-brand-100);
  --avl-accent-soft-text: var(--avl-brand-700);
  --avl-focus: var(--avl-brand-500);

  --avl-free-bg: var(--avl-green-50); --avl-free-text: var(--avl-green-700); --avl-free-border: var(--avl-green-200);
  --avl-error: var(--avl-red-500);    --avl-danger: var(--avl-red-600);

  /* Type */
  --avl-font-sans: 'Inter', 'Inter Fallback', system-ui, sans-serif;
  --avl-font-display: 'Fraunces', Georgia, serif;   /* renders Georgia; see §3 */
  --avl-text-xs: 0.75rem;   --avl-lh-xs: 1rem;
  --avl-text-sm: 0.875rem;  --avl-lh-sm: 1.25rem;
  --avl-text-base: 1rem;    --avl-lh-base: 1.5rem;
  --avl-text-lg: 1.125rem;  --avl-lh-lg: 1.75rem;
  --avl-text-xl: 1.25rem;   --avl-lh-xl: 1.75rem;
  --avl-text-2xl: 1.5rem;   --avl-lh-2xl: 2rem;
  --avl-text-3xl: 1.875rem; --avl-lh-3xl: 2.25rem;
  --avl-leading-tight: 1.25; --avl-leading-relaxed: 1.625;
  --avl-tracking-tight: -0.025em;

  /* Shape and depth */
  --avl-radius-sm: 4px;    /* chips, card actions, thumbnails, tooltips */
  --avl-radius-md: 6px;    /* tabs, icon buttons, segment items */
  --avl-radius-lg: 8px;    /* buttons, inputs, panels, menus, toasts */
  --avl-radius-xl: 12px;   /* tiles, modals, empty panels */
  --avl-radius-full: 9999px;
  --avl-shadow-sm: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
  --avl-shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);
  --avl-shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
  --avl-shadow-xl: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1);
  --avl-shadow-brand: 0 10px 15px -3px rgb(8 113 170 / 0.25), 0 4px 6px -4px rgb(8 113 170 / 0.25);
  --avl-ring: 0 0 0 2px var(--avl-focus);

  /* Layout and motion */
  --avl-container: 1280px;
  --avl-gutter: 12px;        /* 24px at >=640, 32px at >=1024 */
  --avl-header-h: 65px;      /* desktop incl. 1px border; ~86px two-row mobile */
  --avl-ease: cubic-bezier(0.4, 0, 0.2, 1);
  --avl-dur-fast: 150ms; --avl-dur-base: 200ms; --avl-dur-slow: 300ms;
}
@media (min-width: 640px)  { :root { --avl-gutter: 24px; } }
@media (min-width: 1024px) { :root { --avl-gutter: 32px; } }

/* Dark: class-driven, like AVL GO (the theme script above sets .dark on <html>) */
:root.dark {
  color-scheme: dark;
  --avl-bg-page: var(--avl-gray-950);      /* home uses #0f0f0f */
  --avl-bg-surface: var(--avl-gray-900);
  --avl-bg-subtle: var(--avl-gray-800);
  --avl-bg-muted: var(--avl-gray-800);
  --avl-bg-control: var(--avl-gray-800);
  --avl-bg-control-hover: var(--avl-gray-700);
  --avl-bg-skeleton: var(--avl-gray-700);

  --avl-text: #f0ede8;
  --avl-text-strong: var(--avl-gray-100);
  --avl-text-heading: var(--avl-gray-100);
  --avl-text-body: var(--avl-gray-300);
  --avl-text-label: var(--avl-gray-200);
  --avl-text-muted: var(--avl-gray-400);
  --avl-text-faint: var(--avl-gray-500);

  --avl-border: var(--avl-gray-700);
  --avl-border-strong: var(--avl-gray-600);
  --avl-border-header: var(--avl-gray-800);

  /* --avl-accent stays brand-600: buttons don't change in dark */
  --avl-link: var(--avl-brand-400);
  --avl-link-hover: var(--avl-brand-300);
  --avl-accent-soft-bg: rgb(2 31 48 / 0.5);   /* brand-950 @50% */
  --avl-accent-soft-border: var(--avl-brand-800);
  --avl-accent-soft-text: var(--avl-brand-300);

  --avl-free-bg: rgb(3 46 21 / 0.5);          /* green-950 @50% */
  --avl-free-text: #05df72;                   /* green-400 */
  --avl-free-border: #016630;                 /* green-800 */
  --avl-error: #ff6467;                       /* red-400 */
}

html { font-family: var(--avl-font-sans); }
body { margin: 0; background: var(--avl-bg-page); color: var(--avl-text);
       font-family: var(--avl-font-sans); font-size: 1rem; line-height: 1.5; }
.avl-display { font-family: var(--avl-font-display); }
.avl-logo { height: 24px; width: auto; }
@media (min-width: 640px)  { .avl-logo { height: 30px; } }
@media (min-width: 1024px) { .avl-logo { height: 32px; } }
:root.dark .avl-logo { filter: brightness(0) invert(1); }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; }
}
```

Copy `avlgo_banner_logo_v2.svg`, `avlgo_favicon.svg`, `avlgo_favicon.ico` and `apple-touch-icon.png` from `asheville-event-feed/public/`, or reference them at `https://avlgo.com/...`.

---

## 9. Applying it to the land-value map (civic-mapper `viz/`)

**Swap the base palette.** Retarget the existing semantic variables in `viz/src/design-system.css` (currently CLE purple + DM Sans + Tailwind *slate*) onto the `--avl-*` tokens:

| civic-mapper variable | Point it at |
|---|---|
| `--accent-primary` | `--avl-accent` |
| `--accent-primary-hover` | `--avl-accent-hover` |
| `--bg-base` | `--avl-bg-page` |
| `--bg-surface` | `--avl-bg-surface` |
| `--text-primary` | `--avl-text-strong` |
| `--text-secondary` | `--avl-text-body` |
| `--text-tertiary` | `--avl-text-muted` |
| `--border-default` | `--avl-border` |
| `--font-sans` | `--avl-font-sans` |
| `--radius-*` | 4 / 6 / 8 / 12 |

Also change the `:focus-visible` outline to 2 px `--avl-focus`.

| Map app element | Use |
|---|---|
| `.workspace-header` | AVL GO header recipe (§6). White surface, 1 px `--avl-border-header` bottom border, gutters 12/24/32. `.avl-logo` links to `https://avlgo.com/`. The map is full-bleed, so the header content may run full width instead of 1280 px. Right side: icon buttons (30 px, radius 6) and the theme toggle. |
| `.workspace-tabs` / `.workspace-tab` | Header nav-tab pill: 14 px weight 500, radius 6, active `--avl-link` on `--avl-accent-soft-bg`. Put it beside the logo with a 24 px gap, as on AVL GO. |
| `.analysis-sidebar`, `.control-panel`, `.parking-controls-card` | Surface panel: `--avl-bg-surface`, 1 px `--avl-border`, radius 8, `--avl-shadow-sm`, 16 px padding. Panel headings: 18 px weight 600 with a 20 px brand lucide icon. Sticky group-style headings: 20 px bold. |
| `.headline-stat` | Big number in Inter 24–30 px bold `--avl-text-strong`; label as meta (12 px `--avl-text-muted`). |
| `.btn-primary` / `.btn-secondary` / `.btn-ghost` / `.btn-sm` / `.btn-icon` | Primary / outline / ghost / sm / icon-button recipes (§6). Header "Share" = primary sm; "Report PDF" = outline sm. |
| `.input`, `.select`, `.field-title-select`, `.label` | Form-field recipe: radius 8, 1 px `--avl-border-strong`, `--avl-ring` on focus, with a chevron. |
| `.range-slider` | PriceSlider recipe: 8 px gray-200 track, 20 px brand-600 thumb, 2 px white border. |
| `.legend` chrome (not the ramp) | 12 px `--avl-text-muted` labels, radius 4 on the ramp bar, 1 px `--avl-border` around it. |
| MapLibre popup (`.maplibregl-popup-content`, from `main.ts:1643`) | Menu/popover recipe: surface, 1 px border, radius 8, `--avl-shadow-lg`, 12–16 px padding, 14 px body. Title 16 px bold `--avl-text-strong`. Label/value rows: 12 px muted label, 14 px strong value. Tip colour = surface. |
| `.badge-*` | Tag chip (radius 4, brand-50 / brand-700 / brand-100); success = the "Free" chip. |
| `.modal*`, `.toast*`, `.skeleton`, `.spinner` | Modal, toast, skeleton and spinner recipes (§6). |
| New list page | Copy the AVL GO event list. 1280 px container; search toolbar on top; groups = sticky 20 px bold heading + white bordered body (radius 8). Rows use the **compact-row** pattern: 14 px weight 500 `--avl-link` parcel/address, " - " + muted secondary, chips/values right-aligned, 1 px `--avl-border-strong` dividers, gray-50 hover. Page title 18 → 24 px bold. Empty and loading states per §6. |

**Do not change**
- The data colour ramps and scales (`#ramp` options, legend ramp segments, parcel/hex fill and 3D extrusion colours).
- The basemap styles.
- The exempt/no-data swatches.
- Data attributions (OSM / Overture / county sources per `ATTRIBUTION.md`).

Brand blue belongs to UI chrome only. Don't add it to data layers, where it would read as a data value. Whether the CLE co-brand lockup (`.workspace-cle-lockup`) stays is an owner decision; it isn't a style-guide call.

---

## Appendix: inconsistencies in the source (pick the first option)

1. **Fonts.** The CSS names DM Sans and Fraunces, but live renders Inter and Georgia (see the top note). Use Inter and the Georgia-rendering stack.
2. **Page backgrounds.** Home uses `#faf9f7` / `#0f0f0f` (warm/neutral). All app pages use gray-50 / gray-950 (cool). A third dark value, `#0a0a0a`, is used for `theme-color` (`layout.tsx:122`). The manifest background is `#ffffff` (`manifest.ts:12`). **Use the app-page values.**
3. **Radius drift.** Menus are 4 px in cards, 6 px in the theme menu and 8 px elsewhere. Tags are 4 px on cards but pills on the detail page. **Use 8 px for menus and 4 px for tags.**
4. **Active tab colour.** "All Events" is neutral (gray-100); the other tabs are brand (brand-50) (`EventTabSwitcher.tsx:46,57`). **Use brand.**
5. **Off-brand colours.** The "Show More Events" button is Tailwind `blue-600` `#155dfc` (`EventFeed.tsx:2767`). "Great match" rows are tinted `blue-50/40` (`EventCard.tsx:457`). **Use brand-600.**
6. **Teal secondary.** It is hard-coded hex used only on Top 30 (§2.1). It is optional.
7. **Light-only component.** `ui/FilterPopover.tsx` has no dark styles. Don't copy it.
8. **Dead tokens.** The `--color-secondary-*` scale and `--font-sans`/`--font-mono` (which point at undefined Geist variables) do nothing.
9. **Reduced motion and focus.** Only the poster wall handles reduced motion. Buttons have no custom `:focus-visible` style (browser default). **Add both in the new app** using `--avl-ring`.
