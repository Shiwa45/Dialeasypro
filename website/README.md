# DialSathi website

Static marketing site for DialSathi (formerly DialEasy / DialEasypro). One file, no build step.

## Pages
Hash-routed, so it works on any static host (Netlify, Vercel, S3, Nginx, cPanel):
`#home` · `#product` · `#modules` · `#app` · `#integrations` · `#pricing` · `#security` · `#about` · `#contact`
Section links also work, e.g. `#hrms`, `#billing`, `#recruitment`, `#batches`.

## Before going live
- **Contact email** — `hello@dialsathi.in` is a placeholder (Contact page).
- **Domain** — workspace addresses are shown as `yourcompany.dialsathi.in`; change if your domain differs.
- **Demo form** — validates and shows a confirmation but does not send anything yet. Wire the
  `submit` handler in the `<script>` (search "demo form") to your backend, e.g. a new
  `/api/v1/public/demo-request/` endpoint or `/api/v1/public/register/`.
- **Pricing** — taken from `setup_initial_data.py` (Starter ₹999, Growth ₹2,499, Business ₹5,999,
  yearly ₹9,590 / ₹23,990 / ₹57,590). Update `data-m` / `data-y` on the plan cards if plans change.
- Dashboard, call and campaign figures in the mockups are sample data and are labelled as such.

## Brand
- `assets/dialsathi-mark.svg` — brass mark (app icon / favicon)
- `assets/dialsathi-logo-light.svg`, `assets/dialsathi-logo-dark.svg` — mark + wordmark
- Font: Plus Jakarta Sans 400–800 (Google Fonts), same as the DialEasy React CRM.
- Colours: the React CRM's theme — forest rail #0c4634 → #062a20, mint #7de8b3 / #3fd08f,
  green actions #0f8a5f, blue accent #1d64d8, page #f3f6fa. Dark mode uses the CRM's dark tokens.
- Animations respect the visitor's "reduce motion" setting.
