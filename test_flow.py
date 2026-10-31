"""Offline end-to-end test: fake CJ + fake Shopify at the HTTP layer. No network."""
import json, os, sys, time
os.environ.update(GITHUB_TOKEN="", CJ_API_KEY="k", SHOPIFY_TOKEN="t", DAILY_POINTS="250", ORDER_RESERVE="50", POINTS_PER_PRODUCT="20")
time.sleep = lambda s: None
import requests, app

CJ_ITEMS = [
    {"pid": "P1", "productNameEn": "Boho Brown Cotton Rope Shell Woven Waist Belt", "categoryName": "Women's Clothing"},
    {"pid": "P2", "productNameEn": "Rose-red Garter Belt And Stocking Set Sexy Lingerie", "categoryName": "Lingerie"},
    {"pid": "P3", "productNameEn": "Dog Car Seat Belt", "categoryName": "Pet Supplies"},
    {"pid": "P4", "productNameEn": "HTD 5M Rubber Timing Belt 15mm", "categoryName": "Industrial"},
    {"pid": "P5", "productNameEn": "6204-2RS Deep Groove Ball Bearing", "categoryName": "Bearings"},
    {"pid": "P6", "productNameEn": "Spur Gear 20 Teeth Steel", "categoryName": "Machinery"},
    {"pid": "P7", "productNameEn": "Nema 23 Stepper Motor 3Nm", "categoryName": "Motors"},
    {"pid": "P8", "productNameEn": "Mini Electric Belt Sander", "categoryName": "Tools"},
] + [{"pid": f"X{i}", "productNameEn": f"Hex Nut M{i} Stainless Steel", "categoryName": "Hardware"} for i in range(30)]

S = {"cj_calls": 0, "cj_cap": 10**9, "shop": [], "products": {}, "collects": []}


class R:
    def __init__(self, data, code=200, headers=None):
        self._d, self.status_code, self.headers = data, code, headers or {"content-type": "application/json"}
        self.text = json.dumps(data)

    def json(self):
        return self._d


def fake(method, url, **kw):
    body, params = kw.get("json"), kw.get("params") or {}
    if "cjdropshipping" in url:
        if "getAccessToken" in url:
            return R({"result": True, "code": 200, "data": {"accessToken": "tok"}})
        S["cj_calls"] += 1
        if S["cj_calls"] * 10 > S["cj_cap"]:
            return R({"result": False, "code": 1600100, "message": "Insufficient API points"})
        if "/product/list" in url:
            pg = params["pageNum"]
            return R({"result": True, "code": 200, "data": {"list": CJ_ITEMS if pg == 1 else []}})
        if "/product/query" in url:
            return R({"result": True, "code": 200, "data": {"description": "<p>desc</p>", "brandName": "",
                      "productImage": json.dumps(["https://cf.cjdropshipping.com/a.jpg"]),
                      "variants": [{"vid": "V" + params["pid"], "variantSku": "SKU-" + params["pid"],
                                    "variantSellPrice": 10, "variantWeight": 100}]}})
        if "freightCalculate" in url:
            return R({"result": True, "code": 200, "data": [{"logisticName": "CJPacket", "logisticPrice": 5}]})
    path = url.split("/admin/api/")[1].split("/", 1)[1]
    S["shop"].append((method, path, body))
    if path == "locations.json":
        return R({"locations": [{"id": 1}]})
    if path.startswith("custom_collections"):
        return R({"custom_collections": [{"id": 11, "title": "Gear & Shafts"}, {"id": 12, "title": "Mechanical"}]})
    if path.startswith("smart_collections.json") and method == "GET":
        return R({"smart_collections": [{"id": 21, "title": "Utilities", "rules": [{"column": "title", "relation": "contains", "condition": "x"}]}]})
    if path.startswith("smart_collections.json") and method == "POST":
        return R({"smart_collection": {"id": 30 + len(S["shop"]), "title": body["smart_collection"]["title"]}})
    if path.startswith("smart_collections/"):
        return R({})
    if path == "products.json" and method == "POST":
        pid = 1000 + len(S["products"])
        S["products"][pid] = body["product"]
        return R({"product": {"id": pid, "variants": [{"id": pid + 1, "inventory_item_id": pid + 2}]}})
    if path == "collects.json" and method == "GET":
        return R({"collects": []})
    if path == "collects.json" and method == "POST":
        S["collects"].append(body["collect"])
        return R({"collect": {}})
    return R({})


requests.request = fake
requests.post = lambda url, **kw: fake("POST", url, **kw)

STORE = {}
app.load_state = lambda: (STORE.setdefault("s", {"cursor": {"q": 0, "page": 1}, "products": {}, "dedupe": {}}), None)
app.save_state = lambda st, sha: None


def run(label):
    S.update(shop=[], collects=[], products={}, cj_calls=0)
    app.run_sync()
    print(f"--- {label}: created={len(S['products'])} cj_calls={S['cj_calls']} points={app.last_run['points']}")
    print("    skipped:", app.last_run["skipped"])


run("scenario A: budget 250, reserve 50")
titles = [p["title"] for p in S["products"].values()]
assert not any(w in " ".join(titles).lower() for w in ("boho", "garter", "dog")), "fashion leaked"
assert len(S["products"]) >= 5
assert S["cj_calls"] * 10 <= 200, "sync overspent its budget"
types = {p["title"]: p["product_type"] for p in S["products"].values()}
print("   ", types)
assert types["Mini Electric Belt Sander"] == "Tools & Tool Kits"
costs = [b for m, pth, b in S["shop"] if pth.startswith("inventory_items/")]
assert costs and costs[0]["inventory_item"]["cost"] == "15.00", costs[:1]       # 10 + 5
first = next(iter(S["products"].values()))
assert first["variants"][0]["price"] == "19.99", first["variants"][0]["price"]     # (10+5)*1.3 = 19.5 -> 19.99
print("    cost saved: 15.00 | price: 19.99")
cat_ids = {c["collection_id"] for c in S["collects"]}
print("    custom-collection assignments:", len(S["collects"]), "| collections hit:", cat_ids)
assert 11 in cat_ids or 12 in cat_ids
fixed = [x for x in S["shop"] if x[1].startswith("smart_collections/21")]
created = [x for x in S["shop"] if x[0] == "POST" and x[1] == "smart_collections.json"]
print("    smart rule fixed:", len(fixed), "| smart collections created:", len(created))
assert fixed and created
app.last_run.clear()
run("scenario A2: same day, run again -> must do nothing")
assert S["cj_calls"] == 0 or app.last_run.get("note")

# scenario B: user believes 1000 points, CJ really gives 100 -> CJ refuses, we learn
STORE.clear()
app.DAILY_POINTS = 1000
S["cj_cap"] = 100
run("scenario B: CJ says no after 100 points")
p = STORE["s"]["points"]
print("    saved:", p)
assert p["blocked"] and p["learned_limit"] <= 160
print("ALL FLOW TESTS PASS")
