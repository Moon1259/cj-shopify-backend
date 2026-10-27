"""
CJdropshipping -> Shopify industrial store automation (Render free + GitHub free).

Responsibilities
  1. /cron/sync            : fetch a bounded batch of CJ products, price, categorise,
                             de-duplicate (cheapest supplier wins), push to Shopify,
                             append rows to a daily CSV in GitHub.
  2. /webhooks/shopify/orders : on orders/create, build ONE combined CJ order
                             (all line items in a single createOrderV2 call).
  3. /health               : keep-alive target.

All secrets come from environment variables. Nothing is hard-coded.
"""
import base64
import csv
import datetime
import hashlib
import hmac
import io
import json
import logging
import math
import os
import re
import threading
import time

import requests
from flask import Flask, abort, jsonify, request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cj-shopify")

# --------------------------------------------------------------------------- config
CJ_API_KEY = os.getenv("CJ_API_KEY", "")
CJ_BASE = "https://developers.cjdropshipping.com/api2.0/v1"

SHOP_DOMAIN = os.getenv("SHOPIFY_STORE", "factory-essentials-2.myshopify.com")
SHOP_TOKEN = os.getenv("SHOPIFY_TOKEN", "")
SHOP_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2025-07")
SHOP_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")

GH_TOKEN = os.getenv("GITHUB_TOKEN", "")
GH_REPO = os.getenv("GITHUB_REPO", "moon1259/industrial-pantry-products")
GH_BRANCH = os.getenv("GITHUB_BRANCH", "main")

CRON_SECRET = os.getenv("CRON_SECRET", "")
DEST_COUNTRY = os.getenv("DEST_COUNTRY", "US")     # country used to price CJ shipping
ORIGIN_COUNTRY = os.getenv("ORIGIN_COUNTRY", "CN")
MARGIN = float(os.getenv("MARGIN", "1.30"))
MAX_PER_RUN = int(os.getenv("MAX_PER_RUN", "40"))        # products processed per sync
TIME_BUDGET = int(os.getenv("TIME_BUDGET_SECONDS", "720"))
AUTO_PAY_CJ = os.getenv("AUTO_PAY_CJ", "0") == "1"       # pay CJ order from CJ balance
DEFAULT_QTY = 100

CJ_REMARK = (
    "BLIND DROPSHIPPING - do not include invoice, receipt, price list or any "
    "CJ branding in the parcel. Include product manuals. Customs/duties are paid "
    "by the customer (DDU). Ship ALL items of this order in ONE consolidated parcel."
)

# --------------------------------------------------------------------------- categories
# Order matters: FIRST match wins. No match -> Mechanical.
CATEGORIES = [
    ("Pulleys & Belts", ["pulley", "belt", "timing belt", "v-belt", "v belt", "conveyor belt", "chain"]),
    ("Electronics & SSD", ["ssd", "gpu", "graphics card", "thermal pad", "heatsink", "heat sink",
                           "mounting bracket", "circuit", "board", "microcontroller", "chip",
                           "sensor", "module", "plc", "vfd", "inverter"]),
    ("Utilities", ["motor", "pump", "compressor", "suction pump", "generator", "tank", "cleaning",
                   "maintenance", "lubricant", "safety", "general use"]),
    ("Gears & Shafts", ["gear", "shaft", "sprocket", "gear rack", "differential", "transfer case",
                        "seal", "shim", "washer", "circlip", "clutch", "synchronizer",
                        "shift fork", "pinion"]),
    ("Bearings & Linear Rails", ["bearing", "ball bearing", "roller bearing", "tapered bearing",
                                 "linear rail", "linear guide", "ball screw"]),
    ("Tools & Tool Kits", ["tool", "toolkit", "tool kit", "wrench", "drill", "cutter", "hammer",
                           "wall drill", "hilltee", "screwdriver", "wrist band", "wrist strap"]),
    ("Electrical", ["wire", "cable", "switch", "relay", "breaker", "control unit", "backup power",
                    "junction box", "wall switch", "power accessories", "power strip", "plug", "socket"]),
    ("Mechanical", ["mechanical", "coupling", "fastener", "screw", "bolt", "nut", "hydraulic",
                    "pneumatic", "valve", "folder"]),
]
FALLBACK_CATEGORY = "Mechanical"
_CAT_RE = [(name, [re.compile(r"\b" + re.escape(k) + r"s?\b") for k in kws]) for name, kws in CATEGORIES]

# Search terms used to crawl CJ's catalogue for industrial items (de-duplicated, ordered)
SEARCH_TERMS = list(dict.fromkeys(k for _, kws in CATEGORIES for k in kws if len(k) > 2))


def categorize(text: str) -> str:
    t = (text or "").lower()
    for name, patterns in _CAT_RE:
        if any(p.search(t) for p in patterns):
            return name
    return FALLBACK_CATEGORY


def final_price(cost: float, shipping: float) -> float:
    """(cost + shipping) * 1.30, then snapped to the .99 of the dollar the value falls in.
    15.00 -> 19.50 -> 19.99"""
    raw = (cost + shipping) * MARGIN
    return round(math.floor(raw) + 0.99, 2)


STOP = {"the", "a", "an", "for", "and", "of", "with", "in", "to", "new", "hot", "sale", "high", "quality"}


def dedupe_key(title: str) -> str:
    toks = {t for t in re.findall(r"[a-z0-9]+", (title or "").lower()) if t not in STOP}
    return hashlib.md5(" ".join(sorted(toks)).encode()).hexdigest()


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:90]


# --------------------------------------------------------------------------- CJ client
_cj_lock = threading.Lock()
_cj_last = [0.0]
_cj_token = {"value": None, "exp": 0}


def _cj_throttle():
    # CJ free tier is ~1 request/second
    with _cj_lock:
        wait = 1.15 - (time.time() - _cj_last[0])
        if wait > 0:
            time.sleep(wait)
        _cj_last[0] = time.time()


def cj_token() -> str:
    if _cj_token["value"] and time.time() < _cj_token["exp"]:
        return _cj_token["value"]
    _cj_throttle()
    r = requests.post(f"{CJ_BASE}/authentication/getAccessToken", json={"apiKey": CJ_API_KEY}, timeout=30)
    j = r.json()
    if not j.get("result"):
        raise RuntimeError(f"CJ auth failed: {j}")
    _cj_token["value"] = j["data"]["accessToken"]
    _cj_token["exp"] = time.time() + 14 * 24 * 3600  # token lives 15 days
    return _cj_token["value"]


def cj(method: str, path: str, params=None, body=None, retries=3):
    for attempt in range(retries):
        _cj_throttle()
        r = requests.request(method, f"{CJ_BASE}{path}", params=params, json=body,
                             headers={"CJ-Access-Token": cj_token()}, timeout=45)
        if r.status_code == 429 or (r.headers.get("content-type", "").startswith("application/json")
                                    and r.json().get("code") == 1600200):
            time.sleep(3 * (attempt + 1))
            continue
        j = r.json()
        if j.get("result") is False or j.get("code") not in (200, None):
            raise RuntimeError(f"CJ {path} error: {j.get('code')} {j.get('message')}")
        return j.get("data")
    raise RuntimeError(f"CJ {path}: rate-limited after retries")


def cj_list(keyword: str, page: int):
    data = cj("GET", "/product/list", params={"pageNum": page, "pageSize": 20, "productNameEn": keyword})
    return (data or {}).get("list") or []


def cj_detail(pid: str):
    return cj("GET", "/product/query", params={"pid": pid})


def cj_variants(pid: str):
    return cj("GET", "/product/variant/query", params={"pid": pid}) or []


def cj_cheapest_freight(items, dest=None):
    """items = [{'vid':..., 'quantity':n}] -> (price, logisticName) of cheapest option."""
    data = cj("POST", "/logistic/freightCalculate", body={
        "startCountryCode": ORIGIN_COUNTRY,
        "endCountryCode": dest or DEST_COUNTRY,
        "products": items,
    }) or []
    opts = [(float(o.get("logisticPrice") or 0), o.get("logisticName")) for o in data if o.get("logisticName")]
    opts = [o for o in opts if o[0] > 0] or opts
    if not opts:
        raise RuntimeError("no CJ shipping options")
    return min(opts)


def cj_stock(vid: str):
    """Confirmed integer stock, or None if CJ does not give a confirmed number."""
    try:
        data = cj("GET", "/product/stock/queryByVid", params={"vid": vid})
    except Exception as e:  # noqa
        log.warning("stock lookup failed for %s: %s", vid, e)
        return None
    if not data:
        return None
    total, seen = 0, False
    for row in data:
        n = row.get("totalInventoryNum")
        if isinstance(n, (int, float)):
            total += int(n)
            seen = True
    return total if seen and total > 0 else None


# --------------------------------------------------------------------------- Shopify client
_shop_last = [0.0]


def shop(method: str, path: str, body=None, params=None):
    url = f"https://{SHOP_DOMAIN}/admin/api/{SHOP_API_VERSION}{path}"
    for attempt in range(5):
        wait = 0.55 - (time.time() - _shop_last[0])
        if wait > 0:
            time.sleep(wait)
        _shop_last[0] = time.time()
        r = requests.request(method, url, json=body, params=params, timeout=45,
                             headers={"X-Shopify-Access-Token": SHOP_TOKEN})
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After", 2)))
            continue
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise RuntimeError(f"Shopify {method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else {}
    raise RuntimeError("Shopify rate-limited after retries")


_loc = {}


def shop_location_id():
    if "id" not in _loc:
        _loc["id"] = shop("GET", "/locations.json")["locations"][0]["id"]
    return _loc["id"]


def set_inventory(inventory_item_id, qty):
    shop("POST", "/inventory_levels/set.json", {
        "location_id": shop_location_id(), "inventory_item_id": inventory_item_id, "available": int(qty)})


# --------------------------------------------------------------------------- GitHub storage
def _gh(method, path, body=None, params=None):
    r = requests.request(method, f"https://api.github.com/repos/{GH_REPO}/contents/{path}",
                         json=body, params=params, timeout=45,
                         headers={"Authorization": f"Bearer {GH_TOKEN}",
                                  "Accept": "application/vnd.github+json"})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def gh_read(path):
    j = _gh("GET", path, params={"ref": GH_BRANCH})
    if not j:
        return None, None
    return base64.b64decode(j["content"]).decode("utf-8"), j["sha"]


def gh_write(path, text, sha, message):
    body = {"message": message, "branch": GH_BRANCH,
            "content": base64.b64encode(text.encode("utf-8")).decode()}
    if sha:
        body["sha"] = sha
    _gh("PUT", path, body=body)


STATE_PATH = "state/state.json"
CSV_HEADER = ["Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type", "Tags", "Price",
              "SKU", "Inventory Qty", "Image Src", "Image Position", "Image Alt Text", "Status"]


def load_state():
    if not GH_TOKEN:
        return {"cursor": {"kw": 0, "page": 1}, "products": {}, "dedupe": {}}, None
    txt, sha = gh_read(STATE_PATH)
    st = json.loads(txt) if txt else {}
    st.setdefault("cursor", {"kw": 0, "page": 1})
    st.setdefault("products", {})      # cj pid -> shopify ids
    st.setdefault("dedupe", {})        # title-key -> {pid,total}
    return st, sha


def save_state(state, sha):
    if GH_TOKEN:
        gh_write(STATE_PATH, json.dumps(state, indent=1), sha, "sync state")


def append_csv(rows):
    if not (GH_TOKEN and rows):
        return
    path = f"exports/products-{datetime.date.today().isoformat()}.csv"
    existing, sha = gh_read(path)
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    if not existing:
        w.writerow(CSV_HEADER)
    w.writerows(rows)
    gh_write(path, (existing or "") + buf.getvalue(), sha, f"daily export {datetime.date.today()}")


# --------------------------------------------------------------------------- product sync
def build_body(desc_html, sku, confirmed_qty):
    html = desc_html or ""
    html += f"<p><strong>Part No:</strong> {sku}</p>"
    if confirmed_qty is None:
        html += "<p><strong>In Stock</strong></p>"
    return html


def process_product(item, state):
    """Return CSV rows for the product, or None when skipped."""
    pid = item.get("pid")
    title = item.get("productNameEn") or ""
    if not pid or not title:
        return None

    key = dedupe_key(title)
    detail = cj_detail(pid) or {}
    variants = detail.get("variants") or cj_variants(pid)
    variants = [v for v in variants if v.get("vid") and float(v.get("variantSellPrice") or 0) > 0]
    if not variants:
        return None
    v = min(variants, key=lambda x: float(x["variantSellPrice"]))      # cheapest variant
    cost = float(v["variantSellPrice"])
    ship, _ = cj_cheapest_freight([{"vid": v["vid"], "quantity": 1}])
    total = cost + ship

    # ---- AI cheapest-supplier logic: same product from several suppliers -> keep cheapest
    prev = state["dedupe"].get(key)
    if prev and prev["pid"] != pid:
        if total >= prev["total"]:
            log.info("skip %s: cheaper duplicate already listed (%.2f <= %.2f)", pid, prev["total"], total)
            return None
        old = state["products"].pop(prev["pid"], None)
        if old:
            try:
                shop("DELETE", f"/products/{old['sid']}.json")
            except Exception as e:  # noqa
                log.warning("could not delete superseded product: %s", e)
    state["dedupe"][key] = {"pid": pid, "total": total}

    sku = v.get("variantSku") or item.get("productSku") or pid
    category = categorize(f"{title} {item.get('categoryName') or detail.get('categoryName') or ''}")
    price = final_price(cost, ship)
    qty = cj_stock(v["vid"])
    shop_qty = qty if qty is not None else DEFAULT_QTY
    vendor = (detail.get("brandName") or "").strip() or "Factory Essentials"
    desc = detail.get("description") or ""
    body_html = build_body(desc, sku, qty)
    tags = f"{sku}, {category}"

    images = []
    img_set = detail.get("productImageSet") or detail.get("productImage") or item.get("productImage")
    if isinstance(img_set, str):
        try:
            img_set = json.loads(img_set)
        except Exception:  # noqa
            img_set = [img_set]
    for u in (img_set or [])[:5]:
        if isinstance(u, str) and u.startswith("http"):
            images.append(u)
    if not images and item.get("productImage"):
        images = [item["productImage"]]
    handle = slug(f"{title}-{sku}")

    existing = state["products"].get(pid)
    prod_payload = {
        "title": title, "body_html": body_html, "vendor": vendor, "product_type": category,
        "tags": tags, "status": "active", "handle": handle,
    }
    variant_payload = {
        "price": f"{price:.2f}", "sku": sku, "barcode": v["vid"],          # barcode carries CJ vid
        "inventory_management": "shopify", "inventory_policy": "deny",
        "requires_shipping": True, "weight": float(v.get("variantWeight") or 0), "weight_unit": "g",
    }
    sid = inv_item = None
    if existing:
        res = shop("PUT", f"/products/{existing['sid']}.json", {"product": {
            "id": existing["sid"], **prod_payload,
            "variants": [{"id": existing["vsid"], **variant_payload}]}})
        if res:
            sid, inv_item = existing["sid"], existing["inv"]
    if sid is None:
        res = shop("POST", "/products.json", {"product": {
            **prod_payload, "variants": [variant_payload],
            "images": [{"src": u, "position": i + 1, "alt": title[:120]} for i, u in enumerate(images)]}})
        p = res["product"]
        sid, inv_item = p["id"], p["variants"][0]["inventory_item_id"]
        state["products"][pid] = {"sid": sid, "vsid": p["variants"][0]["id"], "inv": inv_item}
    set_inventory(inv_item, shop_qty)

    rows = []
    for i, u in enumerate(images or [""]):
        if i == 0:
            rows.append([handle, title, body_html, vendor, "Hardware", category, tags, f"{price:.2f}",
                         sku, shop_qty, u, 1, title[:120], "active"])
        else:
            rows.append([handle, "", "", "", "", "", "", "", "", "", u, i + 1, title[:120], ""])
    return rows


_sync_lock = threading.Lock()
last_run = {"at": None, "processed": 0, "errors": 0}


def run_sync():
    if not _sync_lock.acquire(blocking=False):
        log.info("sync already running")
        return
    try:
        state, sha = load_state()
        started, done, errors, csv_rows, empty_streak = time.time(), 0, 0, [], 0
        cur = state["cursor"]
        while done < MAX_PER_RUN and time.time() - started < TIME_BUDGET and empty_streak <= len(SEARCH_TERMS):
            kw = SEARCH_TERMS[cur["kw"] % len(SEARCH_TERMS)]
            try:
                items = cj_list(kw, cur["page"])
            except Exception as e:  # noqa
                log.error("list failed (%s p%s): %s", kw, cur["page"], e)
                errors += 1
                break
            if not items:
                cur["kw"] = (cur["kw"] + 1) % len(SEARCH_TERMS)
                cur["page"] = 1
                empty_streak += 1
                continue
            empty_streak = 0
            for it in items:
                if done >= MAX_PER_RUN or time.time() - started > TIME_BUDGET:
                    break
                try:
                    rows = process_product(it, state)
                    if rows:
                        csv_rows.extend(rows)
                        done += 1
                except Exception as e:  # noqa
                    errors += 1
                    log.error("product %s failed: %s", it.get("pid"), e)
            else:
                cur["page"] += 1
        try:
            append_csv(csv_rows)
        except Exception as e:  # noqa
            log.error("csv push failed: %s", e)
        save_state(state, sha)
        last_run.update(at=datetime.datetime.utcnow().isoformat(), processed=done, errors=errors)
        log.info("sync finished: %s products, %s errors", done, errors)
    finally:
        _sync_lock.release()


# --------------------------------------------------------------------------- orders
_seen_orders = set()


def verify_hmac(raw: bytes, header: str) -> bool:
    if not SHOP_WEBHOOK_SECRET:
        return False
    digest = base64.b64encode(hmac.new(SHOP_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(digest, header or "")


def forward_order_to_cj(order: dict):
    oid = order["id"]
    if oid in _seen_orders or "cj-sent" in (order.get("tags") or ""):
        return
    _seen_orders.add(oid)
    try:
        # Resolve CJ vid (stored in the variant barcode) for each line item
        products = []
        for li in order.get("line_items", []):
            if not li.get("variant_id"):
                continue
            var = shop("GET", f"/variants/{li['variant_id']}.json")
            vid = (var or {}).get("variant", {}).get("barcode")
            if not vid:
                raise RuntimeError(f"line item {li.get('sku')} has no CJ vid")
            products.append({"vid": vid, "quantity": int(li["quantity"]), "storeLineItemId": str(li["id"])})
        if not products:
            raise RuntimeError("no CJ-mapped products in order")

        a = order.get("shipping_address") or {}
        country = a.get("country_code") or DEST_COUNTRY
        # ONE order, many products -> CJ consolidates and ships as one parcel
        _, logistic = cj_cheapest_freight([{"vid": p["vid"], "quantity": p["quantity"]} for p in products], country)
        payload = {
            "orderNumber": f"SHP-{order.get('name', oid)}".replace("#", ""),
            "shippingCountryCode": country, "shippingCountry": a.get("country"),
            "shippingProvince": a.get("province"), "shippingCity": a.get("city"),
            "shippingCounty": "", "shippingAddress": a.get("address1"),
            "shippingAddress2": a.get("address2") or "",
            "shippingCustomerName": a.get("name") or order.get("email"),
            "shippingZip": a.get("zip"), "shippingPhone": a.get("phone") or order.get("phone") or "",
            "email": order.get("email") or "", "remark": CJ_REMARK,
            "logisticName": logistic, "fromCountryCode": ORIGIN_COUNTRY,
            "products": products,
        }
        res = cj("POST", "/shopping/order/createOrderV2", body=payload)
        cj_order_id = (res or {}).get("orderId") or (res or {}).get("orderNum") or ""
        if AUTO_PAY_CJ and cj_order_id:
            try:
                cj("POST", "/shopping/pay/payBalance", body={"orderId": cj_order_id})
            except Exception as e:  # noqa
                log.error("CJ auto-pay failed for %s: %s", cj_order_id, e)
        shop("PUT", f"/orders/{oid}.json", {"order": {
            "id": oid, "tags": ((order.get("tags") or "") + ", cj-sent").strip(", "),
            "note": f"CJ order: {cj_order_id}"}})
        log.info("order %s -> CJ %s (%s items, 1 parcel)", oid, cj_order_id, len(products))
    except Exception as e:  # noqa
        _seen_orders.discard(oid)
        log.error("order %s failed: %s", oid, e)
        try:
            shop("PUT", f"/orders/{oid}.json", {"order": {
                "id": oid, "tags": ((order.get("tags") or "") + ", cj-failed").strip(", "),
                "note": f"CJ forward failed: {e}"}})
        except Exception:  # noqa
            pass


# --------------------------------------------------------------------------- routes
@app.get("/")
@app.get("/health")
def health():
    return jsonify(ok=True, last_sync=last_run, syncing=_sync_lock.locked())


@app.post("/cron/sync")
def cron_sync():
    if not CRON_SECRET or request.headers.get("X-Cron-Secret") != CRON_SECRET:
        abort(401)
    threading.Thread(target=run_sync, daemon=True).start()
    return jsonify(started=True), 202


@app.post("/webhooks/shopify/orders")
def shopify_orders():
    raw = request.get_data()
    if not verify_hmac(raw, request.headers.get("X-Shopify-Hmac-Sha256")):
        abort(401)
    order = json.loads(raw)
    threading.Thread(target=forward_order_to_cj, args=(order,), daemon=True).start()
    return "", 200                       # answer fast, Shopify expects <5s


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
