# Founder OS

The sign-in protected home for the business: one site with the Weekly Business Review, the cash flow
forecast, the customer service report, the creative dashboard, competitor intelligence and the org chart.
Meant to be served at `br.renaissancecommerce.com` from Vercel.

Every section is a **read-only copy** of a page whose working version lives somewhere else (a Claude page,
a Google Sheet, another repo). Nothing is edited here. The header above each section says how fresh the
copy is and links to the original.

This repo holds revenue, the cash plan, supplier payments and per-person numbers. **Keep it private.**

## What is where

| Path | What it is |
|---|---|
| `middleware.js` | The sign-in gate. Runs on Vercel before every page and file; nothing is served without a session. |
| `supabase/schema.sql` | The sign-in tables and functions (already applied to Supabase project `joogjxthmtndysxvkyov`). |
| `public/index.html` | The shell: navigation, the home page, and the frame each section opens in. |
| `public/account.html`, `public/people.html` | Change password; add, reset and remove people (admins). |
| `public/s/<section>/` | The mirrored sections (see the table below). |
| `sources/sections.json` | The list of sections the navigation is built from. Add a section here. |
| `sources/cashflow/` | The cash flow model export and a note of which sheet it came from. |
| `tools/sync.py` | Rebuilds the sections from their sources and stamps how fresh each is. |
| `tools/dev-server.mjs` | Local preview through the real gate with a stand-in for Supabase. |
| `docs/refresh.md` | How to refresh each section, step by step. |

## Sections and where they come from

| Section | Source | How it gets here |
|---|---|---|
| Weekly Business Review, Customer Service Report | Claude page `LcXDzCN1AfkGiLN4mmUvo1` (its database) | `tools/sync.py --wbr <clone> [--wbr-export <folder>]` |
| Cash Flow Forecast | Google Sheet (see `sources/cashflow/source.json`) | replace `sources/cashflow/model-export.txt`, run `tools/sync.py` |
| Creative Dashboard (MAIA, AVIA, weekly recaps) | repo `maiasuperfoods/maia-creative-dashboard`, rebuilt daily by its own GitHub Action | `tools/sync.py --creative <clone>` |
| Competitor Intelligence, AVIA Cortisol Detox | repo `maiasuperfoods/competitor-intelligence`, run `avia-cortisol-detox-2026-10-24-v3` | `tools/sync.py --ci <clone>` |
| Competitor Intelligence, MAIA Haskap | Claude dashboard `7rd7XGoHUG71n3VMDMEpWV` (page and data files copied once into `public/s/competitors/studies/haskap/`) | fixed study; re-copy only if the study is redone |
| Org Chart | Claude page `EZCd6yrm3abTw2Ep75v5Nc` | copy the page into `public/s/org/index.html` when the chart changes |

## Sign-in

- Each person has their own email and password. An admin adds people on **People and access**; the site shows a
  temporary password once, the admin passes it on, and the person must choose their own at first sign-in.
- Removing a person ends their access within a minute. Resetting a password signs them out everywhere.
- Eight wrong passwords for one email lock that email for 15 minutes.
- Passwords are stored as bcrypt hashes and sessions as SHA-256 hashes in Supabase tables that have row level
  security on and no policies; the site reaches them only through the `os_*` functions. The key in
  `middleware.js` is the project's publishable key and can do nothing else.
- There is no "forgot password" email. An admin resets it. If every admin is locked out, add or reset a row in
  `os_members` from the Supabase SQL editor (see `docs/refresh.md`, "Locked out").

## Deploy (one time)

1. Vercel, Add New, Project, Import this repo. Framework preset **Other**, no build command. `vercel.json` sets the rest.
2. Project, Settings, Domains: add `br.renaissancecommerce.com` and create the CNAME record Vercel shows at the DNS host of renaissancecommerce.com.
3. Open the site in a private window. You must see the sign-in form, and
   `https://br.renaissancecommerce.com/s/wbr/data/db.json` must also show the sign-in form, not data.

Every push to `main` redeploys.

## Preview locally

```bash
node tools/dev-server.mjs          # http://localhost:4173, owner@example.test / temp-pass-1234
```

## Adding a section later

Put the page under `public/s/<name>/` (any self-contained page works), add an entry to `sources/sections.json`,
run `python3 tools/sync.py`, commit and push.
