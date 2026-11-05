# Refreshing the sections

Everything ends the same way: run `python3 tools/sync.py ...` from the repo root, look at what it printed,
commit and push to `main`. Vercel redeploys by itself. The sync never talks to the network; it copies from
folders you give it.

## All at once

```bash
git clone https://github.com/maiasuperfoods/maia-creative-dashboard ../maia-creative-dashboard
git clone https://github.com/maiasuperfoods/maia-weekly-business-review ../maia-weekly-business-review
git clone https://github.com/maiasuperfoods/competitor-intelligence ../competitor-intelligence
python3 -I tools/sync.py --creative ../maia-creative-dashboard --wbr ../maia-weekly-business-review --ci ../competitor-intelligence
git add -A && git commit -m "Refresh the sections" && git push
```

## Weekly Business Review and Customer Service Report

The numbers live in the database of the Claude page https://claude.ai/artifact/LcXDzCN1AfkGiLN4mmUvo1 .
To bring a fresh copy here:

1. Save these collections of that page's database to a new folder, one sub-folder per collection, one JSON file per
   document (ArtifactData `list`, `limit` 1000, with an `out_dir`): weeks, actuals, inventory, strategists, meta, cs,
   plan, items, settings, comments.
2. `python3 -I tools/sync.py --wbr ../maia-weekly-business-review --wbr-export <that folder>`

   This runs the review repo's own `scripts/export.py`, which refuses to write if anything in the export looks like
   a customer's email address, phone number or card number. If it stops, do not work around it.

Without `--wbr-export` the sync copies whatever snapshot the review repo holds.

When the review page itself changes (a new version is published), update
`src/weekly-business-review.html` in the review repo first; the sync rebuilds the page from it.

## Cash Flow Forecast

The model lives in Google Sheets. The holdco cash flow chat in Claude saves each update as a new sheet titled
`Holdco_CashFlow_Model_...` in admin@trymaia.co's Drive, so the newest one by last edit is the current model.
The daily refresh does this itself; by hand:

1. Google Drive connector: `search_files` for titles containing `Holdco_CashFlow_Model`, take the one edited last.
2. `download_file_content` with that id and exportMimeType
   `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`. The result is too large to show, so the session
   saves it to a file; note that file's path.
3. `python3 tools/cashflow_import.py <that file> --id <sheet id> --title "<sheet title>" --edited <YYYY-MM-DD of the last edit>`
4. `python3 -I tools/sync.py`. It prints the number of weeks and the lowest closing cash, and stops if the lowest
   weekly cash does not match the model's own summary row.

The tabs it reads are "1. Inputs", "7. Cash Flow Weekly", "7b. CM Weekly" (optional), "8. Monthly Summary",
"9. Ramp Scenarios" and "10. Committed POs". If one is renamed the import stops and lists the tabs it found.

## Creative Dashboard

The creative repo's GitHub Action rebuilds its `public/` folder every day. `--creative <clone>` copies that folder
to `public/s/creative/` and rewrites the links between its pages so they stay inside this site.

## Competitor Intelligence

- AVIA Cortisol Detox: `--ci <clone>` copies the study page and its datasets from the run folder. Funnel screenshots
  were uploaded to the Claude dashboard only, so in this copy each one shows a note pointing to the Claude page.
- A new study: add `public/s/competitors/studies/<id>/` with `page.html` (the dashboard's page), `study.json`
  (`title`, `asOf`, `live`, `params`, and `datasets`: dataset id to file) and the data files, then add a view to the
  Competitor Intelligence entry in `sources/sections.json`.

## Org Chart

Copy the current page from https://claude.ai/artifact/EZCd6yrm3abTw2Ep75v5Nc into `public/s/org/index.html`
(keep the `<!doctype html>`, `<head>` and `<body>` wrapper that file has), and set its `asOf` in
`sources/sections.json`.

## Locked out

If no admin can sign in, run this in the Supabase SQL editor (project `joogjxthmtndysxvkyov`), then sign in with
the temporary password and choose a new one:

```sql
update public.os_members
   set pass_hash = extensions.crypt('a-temporary-password', extensions.gen_salt('bf', 10)), must_change = true
 where email = 'you@example.com';
delete from public.os_login_attempts where email = 'you@example.com';
```
