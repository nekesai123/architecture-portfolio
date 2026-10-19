# UI Screenshot Capture Pipeline

Reusable end-to-end pipeline that produces **localization-verified UI screenshots** of the
LogiSim freight-forwarding demo: English UI, English demo data, programmatically asserted.

## What it does

1. **Isolated demo database** — creates a throwaway `logistics_demo_seed` database
   (never touches shared/acceptance databases), boots the application WAR against it
   (Flyway migrates automatically), loads the standard seed set, then applies
   `seed-en-overlay.sql` to translate business corpus (customer names, todo items,
   alert titles, audit descriptions) to English.
2. **Real browser capture** — Playwright (headless Chromium, 1600x900 @2x) logs in,
   switches the locale radio to `en-US`, waits for **actual data rows** (not just page
   chrome — the classic bug this guards against is capturing the loading-spinner frame),
   then screenshots each target page.
3. **Zero-CJK gate** — before every screenshot, the whole rendered page text is scanned
   for CJK / fullwidth characters (`[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]`). Any hit
   fails the shot, prints the offending string with its attribution (frontend seed file
   vs runtime), and blocks the capture. "All English" is a programmatic assertion, not
   an eyeball check.
4. **Evidence + cleanup** — logs locale evidence (`en-US` radio checked, localStorage
   key), kills the WAR process, verifies no orphan process and port release, drops the
   throwaway database.

## Usage

```bash
export PG_PASSWORD='<redacted>'          # DB password (never hardcoded)
export DEMO_DB_HOST='<your-pg-host>'     # defaults to 127.0.0.1
python3 run_all.py                       # war path & port probed automatically
```

Outputs 4 PNGs to `shots/`: dashboard, CRM customers, tracking board, RBAC guard page.

## Design notes

- **Data locale is independent of UI locale.** The UI framework is bilingual (zh/en
  i18n); business corpus lives in the frontend demo seed (`spa/src/data/seed/*.ts` in
  the product repo) and in DB seed SQL. This pipeline's overlay handles the DB side;
  permanent corpus changes belong in the frontend seed files.
- **Wait-for-data, not wait-for-chrome.** Each target page declares what "data has
  arrived" looks like (todo rows, customer table rows, lane cards) and waits for it
  with a generous timeout plus a settle delay.
- **Zero-CJK failure is actionable**: each offending string is logged with the file:line
  of its source (e.g. `spa/src/data/seed/crm.ts:22`), so fixing corpus gaps is
  mechanical.

## Extending

Add a page: append a target (route, wait-condition description, output filename) to
`take_screenshots()` in `run_all.py`. Add corpus: extend `seed-en-overlay.sql` or the
frontend seed files, then re-run — the CJK gate will verify.
