"""
CJdropshipping -> Shopify industrial catalog (v2). Render free + GitHub free.

v2 changes
  * points ledger: every CJ call is charged against DAILY_POINTS; sync stops cleanly, orders keep a reserve
  * industrial-only gate (industrial.py): blacklist -> strong title term -> weak term + industrial CJ category
  * list-stage filtering: junk is rejected from the list response, so it costs zero extra points
  * product -> collection assignment (custom: /collects.json, smart: product_type rule)
  * Cost per item saved on the Shopify inventory item (cost = CJ price + shipping)
"""
import base64, csv, datetime, hashlib, hmac, io, json, logging, math, os, re, threading, time

import requests
from flask import Flask, abort, jsonify, request

from industrial import (ALL_KEYWORDS, CATEGORY_NAMES, categorize, industrial_ok, match_collection_title)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cj-shopify")


def env_f(name, default):
    return float(os.getenv(name, default))


def env_i(name, default):
    return int(float(os.getenv(name, default)))


# --------------------------------------------------------------------------- config
CJ_API_KEY = os.getenv("CJ_API_KEY", "")
CJ_BASE = "https://developers.cjdropshipping.com/api2.0/v1"
SHOP_DOMAIN = os.getenv("SHOPIFY_STORE", "factory-essentials-2.myshopify.com")
SHOP_TOKEN = os.getenv("SHOPIFY_TOKEN", "")
SHOP_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-07")
SHOP_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
GH_TOKEN = os.getenv("GITHUB_TOKEN", "")
GH_REPO = os.getenv("GITHUB_REPO", "moon1259/industrial-pantry-products")
GH_BRANCH = os.getenv("GITHUB_BRANCH", "data")
CRON_SECRET = os.getenv("CRON_SECRET", "")
DEST_COUNTRY = os.getenv("DEST_COUNTRY", "US")
ORIGIN_COUNTRY = os.getenv("ORIGIN_COUNTRY", "CN")

PROFIT = env_f("PROFIT", os.getenv("MARGIN", "1.30"))          # price = (cost + shipping) * PROFIT
DAILY_POINTS = env_i("DAILY_POINTS", 250)                      # what you believe CJ gives per day
ORDER_RESERVE = env_i("ORDER_RESERVE", 50)                     # never spent by catalog sync
POINTS_PER_CALL = env_i("POINTS_PER_CALL", 10)
POINTS_PER_PRODUCT = env_i("POINTS_PER_PRODUCT", 20)           # detail + freight; +1 call if STOCK_LOOKUP=1
AUTO_CALIBRATE = os.getenv("AUTO_CALIBRATE", "1") == "1"       # learn the real limit from the CJ error
MAX_PER_RUN = env_i("MAX_PER_RUN", 40)
TIME_BUDGET = env_i("TIME_BUDGET", env_i("TIME_BUDGET_SECONDS", 600))
PAGE_SIZE = env_i("PAGE_SIZE", 50)                             # bigger page = more candidates per 10 points
MAX_PAGES_PER_TERM = env_i("MAX_PAGES_PER_TERM", 3)
STOCK_LOOKUP = os.getenv("STOCK_LOOKUP", "0") == "1"
FREIGHT_MODE = os.getenv("FREIGHT_MODE", "exact")              # exact = CJ freight call; estimate = weight formula
SHIP_BASE = env_f("SHIP_BASE", 3.0)
SHIP_PER_KG = env_f("SHIP_PER_KG", 8.0)
CJ_CATEGORY_IDS = [c.strip() for c in os.getenv("CJ_CATEGORY_IDS", "").split(",") if c.strip()]
AUTO_CREATE_COLLECTIONS = os.getenv("AUTO_CREATE_COLLECTIONS", "1") == "1"
FIX_SMART_RULES = os.getenv("FIX_SMART_RULES", "1") == "1"
AUTO_PAY_CJ = os.getenv("AUTO_PAY_CJ", "0") == "1"
DEFAULT_QTY = 100

CJ_REMARK = ("BLIND DROPSHIPPING - no invoice, receipt, price list or CJ branding in the parcel. Include product "
             "manuals. Customs/duties paid by the customer (DDU). Ship ALL items of this order in ONE parcel.")


# --------------------------------------------------------------------------- pricing
def final_price(cost: float, shipping: float) -> float:
    """(CJ price + shipping) * PROFIT, snapped to .99.   (10 + 5) * 1.30 = 19.50 -> 19.99"""
    return round(math.floor((cost + shipping) * PROFIT) + 0.99, 2)


STOP = {"the", "a", "an", "for", "and", "of", "with", "in", "to", "new", "hot", "sale", "high", "quality"}


def dedupe_key(title):
    toks = {t for t in re.findall(r"[a-z0-9]+", (title or "").lower()) if t not in STOP}
    return hashlib.md5(" ".join(sorted(toks)).encode()).hexdigest()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:90]


# --------------------------------------------------------------------------- points ledger
class PointsExhausted(Exception):
    pass


class Ledger:
    """Daily CJ points. Persisted in state.json. Sync may spend (limit - ORDER_RESERVE); orders bypass it."""

    def __init__(self, state):
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        p = state.setdefault("points", {})
        if p.get("date") != today:
            learned = p.get("learned_limit")
            p.clear()
            p.update(date=today, used=0, blocked=False)
            if learned:
                p["learned_limit"] = learned
        self.p = p

    @property
    def limit(self):
        if AUTO_CALIBRATE and self.p.get("learned_limit"):
            return min(DAILY_POINTS, self.p["learned_limit"])
        return DAILY_POINTS

    @property
    def remaining(self):
        return max(0, self.limit - ORDER_RESERVE - self.p["used"])

    def charge(self, n=POINTS_PER_CALL):
        if self.p["blocked"] or n > self.remaining:
            raise PointsExhausted(f"budget: used {self.p['used']}/{self.limit} (reserve {ORDER_RESERVE})")
        self.p["used"] += n

    def can_afford_product(self):
        need = POINTS_PER_PRODUCT + (POINTS_PER_CALL if STOCK_LOOKUP else 0)
        return not self.p["blocked"] and self.remaining >= need

    def cj_said_no(self):
        """CJ itself refused: our count was too optimistic. Learn from it."""
        self.p["blocked"] = True
        if AUTO_CALIBRATE and self.p["used"] > 0:
            self.p["learned_limit"] = self.p["used"] + ORDER_RESERVE


# --------------------------------------------------------------------------- CJ client
_cj_lock = threading.Lock()
_cj_last = [0.0]
_cj_token = {"value": None, "exp": 0}


def _cj_throttle():
    with _cj_lock:
        wait = 1.15 - (time.time() - _cj_last[0])
        if wait > 0:
            time.sleep(wait)
        _cj_last[0] = time.time()


def cj_token():
    if _cj_token["value"] and time.time() < _cj_token["exp"]:
        return _cj_token["value"]
    _cj_throttle()
    j = requests.post(f"{CJ_BASE}/authentication/getAccessToken", json={"apiKey": CJ_API_KEY}, timeout=30).json()
    if not j.get("result"):
        raise RuntimeError(f"CJ auth failed: {j}")
    _cj_token.update(value=j["data"]["accessToken"], exp=time.time() + 14 * 24 * 3600)
    return _cj_token["value"]


POINTS_MSG = re.compile(r"(insufficient|not enough|exceed|run out|no more).{0,30}point|point.{0,30}(insufficient|exhaust|limit)", re.I)


def cj(method, path, params=None, body=None, ledger=None, retries=3):
    """ledger=None -> order path (not budgeted). ledger=Ledger -> charged BEFORE the call."""
    for attempt in range(retries):
        if ledger:
            ledger.charge()
        _cj_throttle()
        r = requests.request(method, f"{CJ_BASE}{path}", params=params, json=body,
                             headers={"CJ-Access-Token": cj_token()}, timeout=45)
        try:
            j = r.json()
        except ValueError:
            j = {}
        msg = str(j.get("message") or "")
        if POINTS_MSG.search(msg):
            if ledger:
                ledger.cj_said_no()
            raise PointsExhausted(msg)
        if r.status_code == 429 or j.get("code") == 1600200:          # QPS limit, not points: wait and retry
            time.sleep(3 * (attempt + 1))
            continue
        if j.get("result") is False or j.get("code") not in (200, None):
            raise RuntimeError(f"CJ {path} error: {j.get('code')} {msg}")
        return j.get("data")
    raise RuntimeError(f"CJ {path}: rate-limited after retries")


def cj_list(query, page, ledger):
    params = {"pageNum": page, "pageSize": PAGE_SIZE}
    params.update({"categoryId": query["value"]} if query["type"] == "cat" else {"productNameEn": query["value"]})
    return (cj("GET", "/product/list", params=params, ledger=ledger) or {}).get("list") or []


def cj_detail(pid, ledger):
    return cj("GET", "/product/query", params={"pid": pid}, ledger=ledger)


def cj_cheapest_freight(items, dest=None, ledger=None):
    data = cj("POST", "/logistic/freightCalculate", ledger=ledger, body={
        "startCountryCode": ORIGIN_COUNTRY, "endCountryCode": dest or DEST_COUNTRY, "products": items}) or []
    opts = [(float(o.get("logisticPrice") or 0), o.get("logisticName")) for o in data if o.get("logisticName")]
    opts = [o for o in opts if o[0] > 0] or opts
    if not opts:
        raise RuntimeError("no CJ shipping options")
    return min(opts)


def cj_stock(vid, ledger):
    try:
        data = cj("GET", "/product/stock/queryByVid", params={"vid": vid}, ledger=ledger)
    except PointsExhausted:
        raise
    except Exception as e:  # noqa
        log.warning("stock lookup failed %s: %s", vid, e)
        return None
    nums = [int(r["totalInventoryNum"]) for r in (data or []) if isinstance(r.get("totalInventoryNum"), (int, float))]
    return sum(nums) if nums and sum(nums) > 0 else None


def estimate_shipping(grams):
    return round(SHIP_BASE + SHIP_PER_KG * max(grams, 50) / 1000.0, 2)


# --------------------------------------------------------------------------- Shopify client
_shop_last = [0.0]


def shop(method, path, body=None, params=None):
    url = f"https://{SHOP_DOMAIN}/admin/api/{SHOP_API_VERSION}{path}"
    for _ in range(5):
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


def set_inventory(inv_item, qty):
    shop("POST", "/inventory_levels/set.json",
         {"location_id": shop_location_id(), "inventory_item_id": inv_item, "available": int(qty)})


def set_cost(inv_item, cost):
    """Fills 'Cost per item' so Shopify shows profit/margin."""
    shop("PUT", f"/inventory_items/{inv_item}.json",
         {"inventory_item": {"id": inv_item, "cost": f"{cost:.2f}", "tracked": True}})


# --------------------------------------------------------------------------- collections
_COLL = {}


def load_collections(force=False):
    """Map each of the 8 categories to YOUR existing collection (custom or smart); create smart ones if missing."""
    if _COLL and not force:
        return _COLL
    _COLL.clear()
    for kind, path, key in (("custom", "/custom_collections.json", "custom_collections"),
                            ("smart", "/smart_collections.json", "smart_collections")):
        for c in (shop("GET", path, params={"limit": 250}) or {}).get(key, []):
            cat = match_collection_title(c["title"])
            if cat and cat not in _COLL:
                _COLL[cat] = {"id": c["id"], "kind": kind, "title": c["title"], "rules": c.get("rules") or []}
    for cat in CATEGORY_NAMES:
        c = _COLL.get(cat)
        rule = {"column": "type", "relation": "equals", "condition": cat}
        if c is None and AUTO_CREATE_COLLECTIONS:
            res = shop("POST", "/smart_collections.json", {"smart_collection": {
                "title": cat, "rules": [rule], "disjunctive": False, "published": True}})["smart_collection"]
            _COLL[cat] = {"id": res["id"], "kind": "smart", "title": cat, "rules": [rule]}
            log.info("created smart collection %s", cat)
        elif c and c["kind"] == "smart" and FIX_SMART_RULES and rule not in c["rules"]:
            shop("PUT", f"/smart_collections/{c['id']}.json", {"smart_collection": {
                "id": c["id"], "rules": [rule], "disjunctive": False}})
            c["rules"] = [rule]
            log.info("fixed rules of smart collection %s", c["title"])
    return _COLL


def assign_collection(product_id, category):
    """Put product in the collection of its category (and out of the other 7 custom ones).
    Smart collections need nothing: product_type == category already matches their rule."""
    coll = load_collections()
    target = coll.get(category)
    custom_ids = {c["id"]: cat for cat, c in coll.items() if c["kind"] == "custom"}
    have = (shop("GET", "/collects.json", params={"product_id": product_id, "limit": 250}) or {}).get("collects", [])
    in_target = False
    for col in have:
        cid = col["collection_id"]
        if target and cid == target["id"]:
            in_target = True
        elif cid in custom_ids and custom_ids[cid] != category:
            shop("DELETE", f"/collects/{col['id']}.json")
    if target and target["kind"] == "custom" and not in_target:
        try:
            shop("POST", "/collects.json", {"collect": {"product_id": product_id, "collection_id": target["id"]}})
        except RuntimeError as e:
            if "422" not in str(e):
                raise


# --------------------------------------------------------------------------- GitHub storage
def _gh(method, path, body=None, params=None):
    r = requests.request(method, f"https://api.github.com/repos/{GH_REPO}/contents/{path}", json=body,
                         params=params, timeout=45,
                         headers={"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json"})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def gh_read(path):
    j = _gh("GET", path, params={"ref": GH_BRANCH})
    return (base64.b64decode(j["content"]).decode(), j["sha"]) if j else (None, None)


def gh_write(path, text, sha, message):
    body = {"message": message, "branch": GH_BRANCH, "content": base64.b64encode(text.encode()).decode()}
    if sha:
        body["sha"] = sha
    _gh("PUT", path, body=body)


STATE_PATH = "state/state.json"
CSV_HEADER = ["Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type", "Tags", "Price", "SKU",
              "Inventory Qty", "Image Src", "Image Position", "Image Alt Text", "Status"]


def load_state():
    st, sha = {}, None
    if GH_TOKEN:
        txt, sha = gh_read(STATE_PATH)
        st = json.loads(txt) if txt else {}
    st.setdefault("cursor", {"q": 0, "page": 1})
    st.setdefault("products", {})
    st.setdefault("dedupe", {})
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
def build_queries():
    if CJ_CATEGORY_IDS:                                   # category crawl (see maintenance.py cj-categories)
        return [{"type": "cat", "value": c} for c in CJ_CATEGORY_IDS]
    return [{"type": "kw", "value": k} for k in ALL_KEYWORDS]


def parse_images(detail, item):
    raw = detail.get("productImageSet") or detail.get("productImage") or item.get("productImage")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = [raw]
    urls = [u for u in (raw or []) if isinstance(u, str) and u.startswith("http")][:5]
    if not urls and item.get("productImage"):
        urls = [item["productImage"]]
    return urls


def process_product(item, state, ledger):
    pid, title = item.get("pid"), item.get("productNameEn") or ""
    detail = cj_detail(pid, ledger) or {}
    variants = [v for v in (detail.get("variants") or []) if v.get("vid") and float(v.get("variantSellPrice") or 0) > 0]
    if not variants:
        return None
    v = min(variants, key=lambda x: float(x["variantSellPrice"]))
    cost = float(v["variantSellPrice"])
    if FREIGHT_MODE == "estimate":
        ship = estimate_shipping(float(v.get("variantWeight") or detail.get("productWeight") or 0))
    else:
        ship, _ = cj_cheapest_freight([{"vid": v["vid"], "quantity": 1}], ledger=ledger)
    total = cost + ship                                           # <- what Shopify stores as "Cost per item"

    key = dedupe_key(title)                                       # cheapest-supplier logic
    prev = state["dedupe"].get(key)
    if prev and prev["pid"] != pid:
        if total >= prev["total"]:
            return None
        old = state["products"].pop(prev["pid"], None)
        if old:
            try:
                shop("DELETE", f"/products/{old['sid']}.json")
            except Exception as e:  # noqa
                log.warning("could not delete superseded product: %s", e)
    state["dedupe"][key] = {"pid": pid, "total": total}

    sku = v.get("variantSku") or item.get("productSku") or pid
    category = categorize(title)
    price = final_price(cost, ship)                               # (cost + shipping) * 1.30 -> .99
    qty = cj_stock(v["vid"], ledger) if STOCK_LOOKUP else None
    shop_qty = qty if qty is not None else DEFAULT_QTY
    vendor = (detail.get("brandName") or "").strip() or "Factory Essentials"
    body_html = (detail.get("description") or "") + f"<p><strong>Part No:</strong> {sku}</p>"
    if qty is None:
        body_html += "<p><strong>In Stock</strong></p>"
    tags = f"{sku}, {category}, industrial, cj-sync"
    images = parse_images(detail, item)
    handle = slug(f"{title}-{sku}")

    prod = {"title": title, "body_html": body_html, "vendor": vendor, "product_type": category,
            "tags": tags, "status": "active", "handle": handle}
    var = {"price": f"{price:.2f}", "sku": sku, "barcode": v["vid"], "inventory_management": "shopify",
           "inventory_policy": "deny", "requires_shipping": True,
           "weight": float(v.get("variantWeight") or 0), "weight_unit": "g"}
    existing, sid, inv_item = state["products"].get(pid), None, None
    if existing:
        res = shop("PUT", f"/products/{existing['sid']}.json", {"product": {
            "id": existing["sid"], **prod, "variants": [{"id": existing["vsid"], **var}]}})
        if res:
            sid, inv_item = existing["sid"], existing["inv"]
    if sid is None:
        p = shop("POST", "/products.json", {"product": {**prod, "variants": [var], "images": [
            {"src": u, "position": i + 1, "alt": title[:120]} for i, u in enumerate(images)]}})["product"]
        sid, inv_item = p["id"], p["variants"][0]["inventory_item_id"]
        state["products"][pid] = {"sid": sid, "vsid": p["variants"][0]["id"], "inv": inv_item}
    set_cost(inv_item, total)
    set_inventory(inv_item, shop_qty)
    assign_collection(sid, category)

    rows = []
    for i, u in enumerate(images or [""]):
        rows.append([handle, title, body_html, vendor, "Hardware", category, tags, f"{price:.2f}", sku, shop_qty,
                     u, 1, title[:120], "active"] if i == 0 else
                    [handle, "", "", "", "", "", "", "", "", "", u, i + 1, title[:120], ""])
    return rows


_sync_lock = threading.Lock()
last_run = {}


def run_sync():
    if not _sync_lock.acquire(blocking=False):
        return
    state = sha = ledger = None
    csv_rows, done, errors, skipped = [], 0, 0, {}
    try:
        state, sha = load_state()
        ledger = Ledger(state)
        if not ledger.can_afford_product():
            log.info("no points left today (%s)", ledger.p)
            last_run.update(at=_now(), processed=0, note="points exhausted", points=ledger.p)
            return
        load_collections(force=True)
        queries, cur, started = build_queries(), state["cursor"], time.time()
        while done < MAX_PER_RUN and time.time() - started < TIME_BUDGET and ledger.can_afford_product():
            q = queries[cur["q"] % len(queries)]
            if cur["page"] > MAX_PAGES_PER_TERM:
                cur.update(q=(cur["q"] + 1) % len(queries), page=1)
                continue
            items = cj_list(q, cur["page"], ledger)
            if not items:
                cur.update(q=(cur["q"] + 1) % len(queries), page=1)
                continue
            for it in items:
                if done >= MAX_PER_RUN or not ledger.can_afford_product() or time.time() - started > TIME_BUDGET:
                    break
                ok, why = industrial_ok(it.get("productNameEn"), it.get("categoryName"))
                if not ok:                                         # rejected from the list row: 0 points spent
                    skipped[why] = skipped.get(why, 0) + 1
                    continue
                try:
                    rows = process_product(it, state, ledger)
                    if rows:
                        csv_rows.extend(rows)
                        done += 1
                except PointsExhausted:
                    raise
                except Exception as e:  # noqa
                    errors += 1
                    log.error("product %s failed: %s", it.get("pid"), e)
            else:
                cur["page"] += 1                                   # whole page consumed -> next page
    except PointsExhausted as e:
        log.warning("points exhausted: %s", e)
    except Exception as e:  # noqa
        errors += 1
        log.error("sync crashed: %s", e)
    finally:
        try:
            append_csv(csv_rows)
        except Exception as e:  # noqa
            log.error("csv push failed: %s", e)
        if state is not None:
            try:
                save_state(state, sha)
            except Exception as e:  # noqa
                log.error("state save failed: %s", e)
        last_run.update(at=_now(), processed=done, errors=errors, skipped=skipped,
                        points=(ledger.p if ledger else None))
        log.info("sync done: %s listed, %s errors, skipped %s, points %s", done, errors, skipped,
                 ledger.p if ledger else None)
        _sync_lock.release()


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# --------------------------------------------------------------------------- orders (ONE CJ order, many products)
_seen_orders = set()


def verify_hmac(raw, header):
    if not SHOP_WEBHOOK_SECRET:
        return False
    digest = base64.b64encode(hmac.new(SHOP_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(digest, header or "")


def _tags(order, add=(), remove=()):
    cur = [t.strip() for t in (order.get("tags") or "").split(",") if t.strip()]
    return ", ".join([t for t in cur if t not in remove] + [t for t in add if t not in cur])


def forward_order_to_cj(order):
    oid = order["id"]
    if oid in _seen_orders or "cj-sent" in (order.get("tags") or ""):
        return
    _seen_orders.add(oid)
    try:
        products = []
        for li in order.get("line_items", []):
            if not li.get("variant_id"):
                continue
            vid = ((shop("GET", f"/variants/{li['variant_id']}.json") or {}).get("variant") or {}).get("barcode")
            if not vid:
                raise RuntimeError(f"line item {li.get('sku')} has no CJ vid")
            products.append({"vid": vid, "quantity": int(li["quantity"]), "storeLineItemId": str(li["id"])})
        if not products:
            raise RuntimeError("no CJ-mapped products in order")
        a = order.get("shipping_address") or {}
        country = a.get("country_code") or DEST_COUNTRY
        _, logistic = cj_cheapest_freight([{"vid": p["vid"], "quantity": p["quantity"]} for p in products], country)
        res = cj("POST", "/shopping/order/createOrderV2", body={
            "orderNumber": f"SHP-{order.get('name', oid)}".replace("#", ""),
            "shippingCountryCode": country, "shippingCountry": a.get("country"),
            "shippingProvince": a.get("province"), "shippingCity": a.get("city"), "shippingCounty": "",
            "shippingAddress": a.get("address1"), "shippingAddress2": a.get("address2") or "",
            "shippingCustomerName": a.get("name") or order.get("email"), "shippingZip": a.get("zip"),
            "shippingPhone": a.get("phone") or order.get("phone") or "", "email": order.get("email") or "",
            "remark": CJ_REMARK, "logisticName": logistic, "fromCountryCode": ORIGIN_COUNTRY, "products": products})
        cj_id = (res or {}).get("orderId") or (res or {}).get("orderNum") or ""
        if AUTO_PAY_CJ and cj_id:
            try:
                cj("POST", "/shopping/pay/payBalance", body={"orderId": cj_id})
            except Exception as e:  # noqa
                log.error("CJ auto-pay failed %s: %s", cj_id, e)
        shop("PUT", f"/orders/{oid}.json", {"order": {
            "id": oid, "tags": _tags(order, add=["cj-sent"], remove=["cj-failed"]), "note": f"CJ order: {cj_id}"}})
        log.info("order %s -> CJ %s (%s lines, 1 parcel)", oid, cj_id, len(products))
    except Exception as e:  # noqa
        _seen_orders.discard(oid)
        log.error("order %s failed: %s", oid, e)
        try:
            shop("PUT", f"/orders/{oid}.json", {"order": {
                "id": oid, "tags": _tags(order, add=["cj-failed"]), "note": f"CJ forward failed: {e}"}})
        except Exception:  # noqa
            pass


# --------------------------------------------------------------------------- routes
@app.get("/")
@app.get("/health")
def health():
    return jsonify(ok=True, syncing=_sync_lock.locked(), last_sync=last_run)


@app.post("/cron/sync")
def cron_sync():
    if not CRON_SECRET or request.headers.get("X-Cron-Secret") != CRON_SECRET:
        abort(401)
    threading.Thread(target=run_sync, daemon=True).start()
    return jsonify(started=True), 202


@app.post("/cron/retry-orders")
def retry_orders():
    if not CRON_SECRET or request.headers.get("X-Cron-Secret") != CRON_SECRET:
        abort(401)
    orders = (shop("GET", "/orders.json", params={"status": "open", "limit": 100}) or {}).get("orders", [])
    failed = [o for o in orders if "cj-failed" in (o.get("tags") or "")]
    for o in failed:
        threading.Thread(target=forward_order_to_cj, args=(o,), daemon=True).start()
    return jsonify(retrying=len(failed)), 202


@app.post("/webhooks/shopify/orders")
def shopify_orders():
    raw = request.get_data()
    if not verify_hmac(raw, request.headers.get("X-Shopify-Hmac-Sha256")):
        abort(401)
    threading.Thread(target=forward_order_to_cj, args=(json.loads(raw),), daemon=True).start()
    return "", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=env_i("PORT", 10000))
