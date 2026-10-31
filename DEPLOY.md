# Deployment steps (Render free + GitHub free)

## 0. Secrets
Never paste your CJ key, Shopify token or GitHub token into chat, code or the repo.
They only go into Render's Environment tab and GitHub Actions secrets (steps 3 and 5).

## 1. GitHub
1. Put these files in your repo `moon1259/industrial-pantry-products` (branch `main`):
   `app.py`, `requirements.txt`, `Procfile`, `.github/workflows/trigger-sync.yml`, `sample-products.csv`.
2. Create a second branch named **`data`** (GitHub: branch dropdown -> type `data` -> Create).
   The app saves daily CSVs and its progress file there. This matters: Render redeploys on every
   commit to `main`, so data commits must not land on `main`.
3. Create a token: Settings -> Developer settings -> Fine-grained tokens -> Generate.
   Repository access: only `industrial-pantry-products`. Permission: **Contents = Read and write**.
   Copy it for `GITHUB_TOKEN`.

## 2. Shopify
1. Use the Admin API token for `factory-essentials-2`. Scopes needed:
   `read_products, write_products, read_inventory, write_inventory, read_locations, read_orders, write_orders`.
2. Webhook: Settings -> Notifications -> Webhooks -> Create webhook.
   Event `Order creation`, format `JSON`, URL `https://YOUR-SERVICE.onrender.com/webhooks/shopify/orders`.
   Copy the **signing secret** shown at the bottom of that page for `SHOPIFY_WEBHOOK_SECRET`.
3. Token note: a token from a legacy custom app does not expire. Shopify has been moving new apps to the
   Dev Dashboard, whose tokens can expire. If yours stops working after a day, tell me and I will add an
   automatic token refresh.

## 3. Render
1. New -> Web Service -> connect the repo, branch `main`.
2. Runtime `Python 3`, Instance type **Free**.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
5. Environment variables:

| Name | Value |
|---|---|
| `CJ_API_KEY` | your CJ API key |
| `SHOPIFY_STORE` | `factory-essentials-2.myshopify.com` |
| `SHOPIFY_TOKEN` | your Shopify Admin API token |
| `SHOPIFY_WEBHOOK_SECRET` | signing secret from step 2.2 |
| `GITHUB_TOKEN` | token from step 1.3 |
| `GITHUB_REPO` | `moon1259/industrial-pantry-products` |
| `GITHUB_BRANCH` | `data` |
| `CRON_SECRET` | any long random string you invent |
| `DEST_COUNTRY` | country whose shipping cost sets your prices, e.g. `US` |
| `AUTO_PAY_CJ` | `0` at first (see step 7) |
| `MAX_PER_RUN` | `40` (raise once stable) |

## 4. Check it is alive
Open `https://YOUR-SERVICE.onrender.com/health`. You should see `{"ok": true, ...}`.

## 5. GitHub Actions schedule
Repo -> Settings -> Secrets and variables -> Actions -> New repository secret:
- `RENDER_URL` = `https://YOUR-SERVICE.onrender.com` (no trailing slash)
- `CRON_SECRET` = the same string as on Render

Then Actions tab -> "CJ to Shopify sync trigger" -> Run workflow, to test. After that it runs every 3 hours.

## 6. Keep the web service awake for orders
Render free sleeps after about 15 minutes idle, and a cold start can exceed Shopify's 5-second webhook
timeout. Shopify retries failed webhooks, so orders are not lost, but they can be delayed. To avoid that,
create a free UptimeRobot monitor that requests `/health` every 5 minutes.

## 7. First order test
1. Place a cheap test order in your store.
2. In CJ, confirm one order appeared containing all items. Shopify order gets tag `cj-sent` and a note
   with the CJ order id. On failure it gets tag `cj-failed` and the error in the note.
3. Only after that works, set `AUTO_PAY_CJ=1` if you want CJ orders paid from your CJ balance automatically.
   Keep balance topped up, otherwise CJ orders stay unpaid.

## 8. CJ account settings
CJ's API has no switch for blind shipping, no invoice, manuals, or customs. The app writes them into the
CJ order remark on every order, but the dependable way is to also set them in your CJ account
(shipping/packaging preferences) and confirm customs terms with your CJ agent.

## Limits to know
- Throughput: CJ's API allows roughly one request per second on a free key, and each product needs a few
  calls. The default is 40 products per run, about 320 a day. "All of CJ" is a multi-month crawl, not
  a one-time import.
- Parcel: all items go to CJ in one order, and CJ decides packing. If items sit in different warehouses
  CJ may still split the shipment.
- Duplicate detection compares normalised product titles, so near-identical listings with very different
  titles will not be merged.
- GitHub pauses scheduled workflows in repos with 60 days of no activity. The app's daily commits to
  `data` normally keep it active.

## v2 upgrade (points budget, industrial-only, collections, cost per item)
1. Copy `app.py`, `industrial.py`, `maintenance.py`, `.env.example` values and the new workflow into the repo (`main`).
2. Render env: add the variables from `.env.example` (DAILY_POINTS, ORDER_RESERVE, POINTS_PER_CALL, POINTS_PER_PRODUCT, PROFIT ...). Remove old MARGIN if set.
3. In a Render Shell (or locally with the same env vars) run, in this order:
   - `python maintenance.py cleanup`            (dry run, read the list)
   - `python maintenance.py cleanup --yes`      (backs up to JSON, deletes fashion/junk)
   - `python maintenance.py backfill --estimate-cost`   (re-type, put products into collections, fill estimated cost)
   - `python maintenance.py quote-placeholders` (heavy equipment "Request a Quote" items)
   - `python maintenance.py cj-categories`      (optional: CSV of CJ category ids, then set CJ_CATEGORY_IDS)
4. Delete `state/state.json` on the `data` branch once, so the keyword cursor restarts with the new keyword list.
5. Run the workflow manually; open `/health` and read `last_sync.points` and `last_sync.skipped`.
