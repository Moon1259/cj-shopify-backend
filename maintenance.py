"""
One-off maintenance commands (run locally or in a Render shell). Same env vars as app.py.
"""
import argparse, csv, datetime, json, re, sys, time, os
import requests
import app
from industrial import (BLACKLIST_RE, CATEGORY_DENY_RE, CATEGORY_NAMES, INDUSTRIAL_CAT_RE, STRONG_RE,
                        categorize)

# --- NEW TOKEN SYSTEM COMPATIBLE WITH CLAUDE'S app.py ---
def get_shop_domain():
    return getattr(app, 'SHOP_DOMAIN', 
           getattr(app, 'STORE_DOMAIN',
           getattr(app, 'SHOP_STORE_DOMAIN',
           getattr(app, 'SHOPIFY_STORE_DOMAIN', os.getenv("SHOPIFY_STORE_DOMAIN") or os.getenv("SHOPIFY_STORE") or "factory-essentials-2.myshopify.com"))))

def get_api_version():
    return getattr(app, 'SHOP_API_VERSION',
           getattr(app, 'API_VERSION',
           os.getenv("SHOPIFY_API_VERSION", "2026-10")))

def get_token():
    # Claude's new method
    if hasattr(app, 'get_access_token'):
        t = app.get_access_token()
        if t: return t
    if hasattr(app, 'load_token'):
        try:
            tok = app.load_token()
            if tok.get('access_token'): return tok.get('access_token')
        except: pass
    if hasattr(app, 'shopify_headers'):
        h = app.shopify_headers()
        if h: return h.get('X-Shopify-Access-Token')
    return getattr(app, 'SHOP_TOKEN', os.getenv("SHOPIFY_TOKEN") or os.getenv("SHOPIFY_ACCESS_TOKEN") or "")

def shop_headers():
    if hasattr(app, 'shopify_headers'):
        return app.shopify_headers()
    return {"X-Shopify-Access-Token": get_token(), "Content-Type": "application/json"}

# ---------------------------------------------------------------- helpers
def paginate(path, key, params=None):
    """Follow Shopify cursor pagination (Link header)."""
    domain = get_shop_domain()
    ver = get_api_version()
    url = f"https://{domain}/admin/api/{ver}{path}"
    params = dict(params or {}, limit=250)
    while url:
        r = requests.get(url, params=params, headers=shop_headers(), timeout=60)
        if r.status_code == 429:
            time.sleep(2)
            continue
        r.raise_for_status()
        yield from r.json().get(key, [])
        nxt = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link", ""))
        url, params = (nxt.group(1) if nxt else None), None
        time.sleep(0.5)

def ours(p):
    tags = (p.get("tags") or "").lower()
    return p.get("product_type") in CATEGORY_NAMES or "cj-sync" in tags

# ---------------------------------------------------------------- 1. cleanup
def cmd_cleanup(a):
    extra = [w.strip() for w in (a.extra or "").split(",") if w.strip()]
    extra_re = re.compile(r"\b(?:%s)\b" % "|".join(map(re.escape, extra)), re.I) if extra else None
    hit = []
    for p in paginate("/products.json", "products", {"fields": "id,title,tags,product_type,vendor,handle"}):
        t = p["title"]
        reason = None
        if BLACKLIST_RE.search(t):
            reason = "fashion/junk word"
        elif extra_re and extra_re.search(t):
            reason = "extra word"
        elif a.strict and ours(p) and not STRONG_RE.search(t):
            reason = "no strong industrial term"
        if reason:
            hit.append((p, reason))
    print(f"{len(hit)} products flagged")
    for p, why in hit[:300]:
        print(f"  {p['id']}  [{why}]  {p['title'][:90]}")
    if not hit:
        return
    if not a.yes:
        print("\nDRY RUN. Re-run with --yes to back up and delete.")
        return
    backup = f"deleted-backup-{datetime.datetime.now():%Y%m%d-%H%M%S}.json"
    json.dump([p for p, _ in hit], open(backup, "w"), indent=1)
    print("backup written:", backup)
    ver = get_api_version()
    domain = get_shop_domain()
    for i, (p, _) in enumerate(hit, 1):
        for attempt in range(4):
            r = requests.delete(
                f"https://{domain}/admin/api/{ver}/products/{p['id']}.json",
                headers=shop_headers(), timeout=60)
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            break
        print(f"  [{i}/{len(hit)}] deleted {p['id']}" if r.status_code < 300 else f"  FAILED {p['id']} {r.status_code}")
        time.sleep(0.55)

# ---------------------------------------------------------------- 2. backfill type + collections (+ estimated cost)
def cmd_backfill(a):
    app.load_collections(force=True)
    n = 0
    for p in paginate("/products.json", "products", {"fields": "id,title,tags,product_type,variants"}):
        if not ours(p) or BLACKLIST_RE.search(p["title"]):
            continue
        cat = categorize(p["title"])
        if p["product_type"] != cat:
            app.shop("PUT", f"/products/{p['id']}.json", {"product": {"id": p["id"], "product_type": cat}})
        app.assign_collection(p["id"], cat)
        if a.estimate_cost and p.get("variants"):
            v = p["variants"][0]
            inv = v["inventory_item_id"]
            cur = (app.shop("GET", f"/inventory_items/{inv}.json") or {}).get("inventory_item", {}).get("cost")
            if cur in (None, "", "0.00"):
                est = round(float(v["price"]) / app.PROFIT, 2)
                app.set_cost(inv, est)
        n += 1
        print(f"  {p['id']} -> {cat}  | {p['title'][:70]}")
    print(f"{n} products processed")

# ---------------------------------------------------------------- 3. CJ category tree
def cmd_cj_categories(_):
    data = app.cj("GET", "/product/getCategory") or []
    rows = []
    def walk(node, path):
        name = node.get("categoryName") or node.get("categoryFirstName") or node.get("categorySecondName") or ""
        here = path + [name] if name else path
        if node.get("categoryId"):
            rows.append((node["categoryId"], " > ".join(here)))
        for k in ("categoryFirstList", "categorySecondList", "children", "list"):
            for ch in node.get(k) or []:
                walk(ch, here)
    for n in data:
        walk(n, [])
    out = "cj-categories.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["categoryId", "path", "industrial_guess"])
        for cid, path in rows:
            w.writerow([cid, path, bool(INDUSTRIAL_CAT_RE.search(path) and not CATEGORY_DENY_RE.search(path))])
    good = [c for c, p in rows if INDUSTRIAL_CAT_RE.search(p) and not CATEGORY_DENY_RE.search(p)]
    print(f"{len(rows)} categories -> {out}; {len(good)} look industrial.")
    print("Review the CSV, then set CJ_CATEGORY_IDS=<comma separated ids> on Render.")

# ---------------------------------------------------------------- 4. heavy equipment fallback
QUOTE_ITEMS = [
    ("Heavy-Duty AC Induction Motor 3-75 kW", "Utilities"),
    ("Large Industrial Centrifugal Pump (Flow 50-500 m3/h)", "Utilities"),
    ("Industrial Diesel Generator Set 20-500 kVA", "Utilities"),
    ("Rotary Screw Air Compressor 7.5-75 kW", "Utilities"),
    ("Heavy-Duty Industrial Gearbox / Speed Reducer", "Gears & Shafts"),
    ("Hydraulic Power Unit / Pump Station", "Utilities"),
    ("Servo Motor and Drive System 1-15 kW", "Utilities"),
    ("Variable Frequency Drive (VFD) 5.5-110 kW", "Electronics & SSD"),
    ("Industrial PLC Control Cabinet (Custom)", "Electronics & SSD"),
]

def cmd_quote(_):
    app.load_collections(force=True)
    for title, cat in QUOTE_ITEMS:
        handle = app.slug(title + "-request-quote")
        if (app.shop("GET", "/products.json", params={"handle": handle, "fields": "id"}) or {}).get("products"):
            print("exists:", title)
            continue
        body = (f"<p><strong>Request a Quote.</strong> {title} is sourced to order from verified factory suppliers. "
                f"Email us the model, power rating and delivery country for a quotation and lead time.</p>"
                f"<p><strong>Part No:</strong> RFQ-{handle[:18].upper()}</p>")
        p = app.shop("POST", "/products.json", {"product": {
            "title": f"{title} - Request a Quote", "body_html": body, "vendor": "Factory Essentials",
            "product_type": cat, "tags": "request-quote, sourcing-needed, industrial", "handle": handle,
            "status": "active", "variants": [{"price": "0.00", "sku": f"RFQ-{handle[:18].upper()}",
                                              "inventory_management": "shopify", "inventory_policy": "deny"}]}})["product"]
        app.set_inventory(p["variants"][0]["inventory_item_id"], 0)
        app.assign_collection(p["id"], cat)
        print("created:", title)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cleanup")
    c.add_argument("--yes", action="store_true")
    c.add_argument("--strict", action="store_true")
    c.add_argument("--extra", default="")
    b = sub.add_parser("backfill")
    b.add_argument("--estimate-cost", action="store_true")
    sub.add_parser("cj-categories")
    sub.add_parser("quote-placeholders")
    args = ap.parse_args()
    {"cleanup": cmd_cleanup, "backfill": cmd_backfill, "cj-categories": cmd_cj_categories,
     "quote-placeholders": cmd_quote}[args.cmd](args)
