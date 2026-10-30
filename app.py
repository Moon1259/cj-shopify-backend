"""CJdropshipping -> Shopify industrial store automation - FINAL WITH PERMANENT AUTH FIX"""
import hmac, io, json, logging, math, os, re, threading, time, requests, base64, csv, datetime, hashlib
from flask import Flask, abort, jsonify, request, redirect
from urllib.parse import urlencode

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cj-shopify")

CJ_API_KEY = os.getenv("CJ_API_KEY", "")
CJ_BASE = "https://developers.cjdropshipping.com/api2.0/v1"
SHOP_DOMAIN = os.getenv("SHOPIFY_STORE", os.getenv("SHOP_DOMAIN", "factory-essentials-2.myshopify.com"))
SHOP_TOKEN = os.getenv("SHOPIFY_TOKEN", os.getenv("SHOPIFY_ACCESS_TOKEN", ""))
SHOP_API_KEY = os.getenv("SHOPIFY_API_KEY", "")
SHOP_API_SECRET = os.getenv("SHOPIFY_API_SECRET", "")
SHOP_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2025-07")
SHOP_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")
GH_TOKEN = os.getenv("GITHUB_TOKEN", "")
GH_REPO = os.getenv("GITHUB_REPO", "moon1259/industrial-pantry-products")
GH_BRANCH = os.getenv("GITHUB_BRANCH", "data")
CRON_SECRET = os.getenv("CRON_SECRET", "UmairPantry2026Secure!")
DEST_COUNTRY = os.getenv("DEST_COUNTRY", "US")
if DEST_COUNTRY.upper() == "ALL": DEST_COUNTRY = "US"
ORIGIN_COUNTRY = os.getenv("ORIGIN_COUNTRY", "CN")
MARGIN = float(os.getenv("MARGIN", "1.30"))
MAX_PER_RUN = int(os.getenv("MAX_PER_RUN", "500"))
TIME_BUDGET = int(os.getenv("TIME_BUDGET_SECONDS", os.getenv("TIME_BUDGET", "3000")))
AUTO_PAY_CJ = os.getenv("AUTO_PAY_CJ", "0") == "1"
DEFAULT_QTY = 100
CJ_REMARK = "BLIND DROPSHIPPING - do not include invoice, receipt, price list or any CJ branding."

TOKEN_FILE = "/tmp/shopify_token.json"
if os.path.exists(TOKEN_FILE):
    try:
        with open(TOKEN_FILE, "r") as f:
            d = json.load(f)
            if d.get("access_token"):
                SHOP_TOKEN = d.get("access_token")
                SHOP_DOMAIN = d.get("shop", SHOP_DOMAIN)
    except: pass

def save_token_to_file(shop, token):
    global SHOP_TOKEN, SHOP_DOMAIN
    SHOP_TOKEN = token; SHOP_DOMAIN = shop
    try:
        with open(TOKEN_FILE, "w") as f: json.dump({"shop": shop, "access_token": token, "saved_at": datetime.datetime.utcnow().isoformat()}, f)
    except: pass

# [Categories, CJ Client, Shopify Client, GitHub, Sync Logic - SAME AS YOUR FILE]
CATEGORIES=[("Pulleys & Belts",["pulley","belt","timing belt","v-belt","chain"]),("Electronics & SSD",["ssd","gpu","graphics card","thermal pad","heatsink","chip","sensor","plc","vfd"]),("Utilities",["motor","pump","compressor","generator","tank"]),("Gears & Shafts",["gear","shaft","sprocket","seal","clutch"]),("Bearings & Linear Rails",["bearing","linear rail","ball screw"]),("Tools & Tool Kits",["tool","toolkit","wrench","drill","cutter"]),("Electrical",["wire","cable","switch","relay","breaker"]),("Mechanical",["mechanical","coupling","fastener","bolt","valve"])]
FALLBACK_CATEGORY="Mechanical"
CAT_RE=[(n,[re.compile(r"\b"+re.escape(k)+r"s?\b") for k in kws]) for n,kws in CATEGORIES]
SEARCH_TERMS=list(dict.fromkeys(k for _,kws in CATEGORIES for k in kws if len(k)>2))
def categorize(t):
    tl=(t or "").lower()
    for name,pats in CAT_RE:
        if any(p.search(tl) for p in pats): return name
    return FALLBACK_CATEGORY
def final_price(c,s): return round(math.floor((c+s)*MARGIN)+0.99,2)
STOP={"the","a","an","for","and","of","with","in","to","new","hot","sale"}
def dedupe_key(t): return hashlib.md5(" ".join(sorted({x for x in re.findall(r"[a-z0-9]+",(t or "").lower()) if x not in STOP})).encode()).hexdigest()
def slug(s): return re.sub(r"[^a-z0-9]+","-",(s or "").lower()).strip("-")[:90]

_cj_token={"value":None,"exp":0}; _cj_last=[0.0]; _cj_lock=threading.Lock()
def _cj_throttle():
    with _cj_lock:
        w=1.15-(time.time()-_cj_last[0])
        if w>0: time.sleep(w)
        _cj_last[0]=time.time()
def cj_token():
    if _cj_token["value"] and time.time()<_cj_token["exp"]: return _cj_token["value"]
    _cj_throttle()
    r=requests.post(f"{CJ_BASE}/authentication/getAccessToken",json={"apiKey":CJ_API_KEY},timeout=30).json()
    _cj_token["value"]=r["data"]["accessToken"]; _cj_token["exp"]=time.time()+14*24*3600
    return _cj_token["value"]
def cj(m,p,params=None,body=None,retries=3):
    for _ in range(retries):
        _cj_throttle()
        r=requests.request(m,f"{CJ_BASE}{p}",params=params,json=body,headers={"CJ-Access-Token":cj_token()},timeout=45)
        j=r.json()
        if j.get("result") is False and j.get("code") not in (200,None): raise RuntimeError(f"CJ {p}: {j}")
        return j.get("data")
def cj_list(k,pg): return (cj("GET","/product/list",params={"pageNum":pg,"pageSize":20,"productNameEn":k}) or {}).get("list") or []
def cj_detail(pid): return cj("GET","/product/query",params={"pid":pid})
def cj_variants(pid): return cj("GET","/product/variant/query",params={"pid":pid})
def cj_cheapest_freight(items,dest=None):
    data=cj("POST","/logistic/freightCalculate",body={"startCountryCode":ORIGIN_COUNTRY,"endCountryCode":dest or DEST_COUNTRY,"products":items}) or []
    opts=[(float(o.get("logisticPrice") or 0),o.get("logisticName")) for o in data if o.get("logisticName")]
    opts=[o for o in opts if o[0]>0] or opts
    return min(opts) if opts else (0.0,"DEFAULT")
def cj_stock(vid):
    try:
        data=cj("GET","/product/stock/queryByVid",params={"vid":vid})
        if not data: return None
        tot=sum(int(r.get("totalInventoryNum",0)) for r in data if isinstance(r.get("totalInventoryNum"),(int,float)))
        return tot if tot>0 else None
    except: return None

_shop_last=[0.0]
def shop(m,p,body=None,params=None):
    if not SHOP_TOKEN: raise RuntimeError("SHOPIFY_TOKEN not set - use /auth")
    url=f"https://{SHOP_DOMAIN}/admin/api/{SHOP_API_VERSION}{p}"
    for _ in range(5):
        w=0.55-(time.time()-_shop_last[0])
        if w>0: time.sleep(w)
        _shop_last[0]=time.time()
        r=requests.request(m,url,json=body,params=params,timeout=45,headers={"X-Shopify-Access-Token":SHOP_TOKEN})
        if r.status_code==429: time.sleep(float(r.headers.get("Retry-After",2))); continue
        if r.status_code==404: return None
        if r.status_code>=400: raise RuntimeError(f"{m} {p} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else {}
    raise RuntimeError("Shopify rate-limited")

_loc={}
def shop_location_id():
    if "id" not in _loc: _loc["id"]=shop("GET","/locations.json")["locations"][0]["id"]
    return _loc["id"]
def set_inventory(iid,qty): shop("POST","/inventory_levels/set.json",{"location_id":shop_location_id(),"inventory_item_id":iid,"available":int(qty)})

def _gh(m,p,body=None,params=None):
    r=requests.request(m,f"https://api.github.com/repos/{GH_REPO}/contents/{p}",headers={"Authorization":f"Bearer {GH_TOKEN}","Accept":"application/vnd.github+json"},json=body,params=params,timeout=45)
    if r.status_code==404: return None
    r.raise_for_status(); return r.json()
def gh_read(p):
    j=_gh("GET",p,params={"ref":GH_BRANCH})
    if not j: return None,None
    return base64.b64decode(j["content"]).decode("utf-8"),j["sha"]
def gh_write(p,text,sha,msg):
    body={"message":msg,"branch":GH_BRANCH,"content":base64.b64encode(text.encode("utf-8")).decode()}
    if sha: body["sha"]=sha
    return _gh("PUT",p,body=body)

STATE_PATH="state/state.json"
CSV_HEADER=["Handle","Title","Body (HTML)","Vendor","Product Category","Type","Tags","Price","SKU","Inventory Qty","Image Src","Image Position","Image Alt Text","Status"]
def load_state():
    if not GH_TOKEN: return {"cursor":{"kw":0,"page":1},"products":{},"dedupe":{}},None
    txt,sha=gh_read(STATE_PATH); st=json.loads(txt) if txt else {}
    st.setdefault("cursor",{"kw":0,"page":1}); st.setdefault("products",{}); st.setdefault("dedupe",{}); return st,sha
def save_state(state,sha):
    if not GH_TOKEN: return
    gh_write(STATE_PATH,json.dumps(state,indent=1),sha,"sync_state")
def append_csv(rows):
    if not (GH_TOKEN and rows): return
    path=f"exports/products-{datetime.date.today().isoformat()}.csv"
    existing,sha=gh_read(path); buf=io.StringIO(); w=csv.writer(buf,lineterminator="\n")
    if not existing: w.writerow(CSV_HEADER)
    else: buf.write(existing)
    w.writerows(rows); gh_write(path,buf.getvalue(),sha,f"export {datetime.date.today()}")
def build_body(d,sku,q): return (d or "")+f"<p><strong>Part No:</strong> {sku}</p>"
def process_product(item,state):
    pid=item.get("pid"); title=item.get("productNameEn") or ""
    if not pid or not title: return None
    key=dedupe_key(title); detail=cj_detail(pid) or {}; variants=detail.get("variants") or cj_variants(pid)
    variants=[v for v in variants if v.get("vid") and float(v.get("variantSellPrice") or 0)>0]
    if not variants: return None
    v=min(variants,key=lambda x:float(x["variantSellPrice"])); cost=float(v["variantSellPrice"]); ship,_=cj_cheapest_freight([{"vid":v["vid"],"quantity":1}]); total=cost+ship
    prev=state["dedupe"].get(key)
    if prev and prev["pid"]!=pid and total>=prev["total"]: return None
    state["dedupe"][key]={"pid":pid,"total":total}; sku=v.get("variantSku") or pid; category=categorize(title); price=final_price(cost,ship); qty=cj_stock(v["vid"]) or DEFAULT_QTY
    vendor=(detail.get("brandName") or "").strip() or "FactoryEssentials"; body_html=build_body(detail.get("description") or "",sku,qty); tags=f"{sku}, {category}"
    images=[]; img_set=detail.get("productImageSet") or item.get("productImage")
    if isinstance(img_set,str):
        try: img_set=json.loads(img_set)
        except: img_set=[img_set]
    for u in (img_set or [])[:5]:
        if isinstance(u,str) and u.startswith("http"): images.append(u)
    if not images and item.get("productImage"): images=[item["productImage"]]
    handle=slug(f"{title}-{sku}"); existing=state["products"].get(pid)
    prod_payload={"title":title,"body_html":body_html,"vendor":vendor,"product_type":category,"tags":tags,"status":"active","handle":handle}
    variant_payload={"price":f"{price:.2f}","sku":sku,"barcode":v["vid"],"inventory_management":"shopify","inventory_policy":"deny","requires_shipping":True,"weight":float(v.get("variantWeight") or 0),"weight_unit":"g"}
    if existing:
        shop("PUT",f"/products/{existing['sid']}.json",{"product":{**prod_payload,"id":existing["sid"],"variants":[{"id":existing["vsid"],**variant_payload}]}})
    else:
        res=shop("POST","/products.json",{"product":{**prod_payload,"variants":[variant_payload],"images":[{"src":u,"position":i+1,"alt":title[:120]} for i,u in enumerate(images)]}})
        p=res["product"]; state["products"][pid]={"sid":p["id"],"vsid":p["variants"][0]["id"],"inv":p["variants"][0]["inventory_item_id"]}; set_inventory(p["variants"][0]["inventory_item_id"],qty)
    return [[handle,title,body_html,vendor,category,tags,f"{price:.2f}",sku,qty,images[0] if images else "",title[:120],"active"]] if images else [[handle,title,body_html,vendor,category,tags,f"{price:.2f}",sku,qty,"",title[:120],"active"]]

_sync_lock=threading.Lock(); last_run={"at":None,"processed":0,"errors":0}
def run_sync():
    if not _sync_lock.acquire(blocking=False): return
    try:
        state,sha=load_state(); started=time.time(); done=errors=0; csv_rows=[]; empty=0; cur=state["cursor"]
        while done<MAX_PER_RUN and time.time()-started<TIME_BUDGET and empty<=len(SEARCH_TERMS):
            kw=SEARCH_TERMS[cur["kw"]%len(SEARCH_TERMS)]
            try: items=cj_list(kw,cur["page"])
            except: break
            if not items: cur["kw"]=(cur["kw"]+1)%len(SEARCH_TERMS); cur["page"]=1; empty+=1; continue
            empty=0
            for it in items:
                if done>=MAX_PER_RUN or time.time()-started>TIME_BUDGET: break
                try:
                    rows=process_product(it,state)
                    if rows: csv_rows.extend(rows); done+=1
                except Exception as e: errors+=1
            cur["page"]+=1
        try: append_csv(csv_rows)
        except: pass
        save_state(state,sha); last_run.update(at=datetime.datetime.utcnow().isoformat(),processed=done,errors=errors)
    finally: _sync_lock.release()

_orders_seen=set()
def verify_hmac(raw,header):
    if not SHOP_WEBHOOK_SECRET: return False
    digest=base64.b64encode(hmac.new(SHOP_WEBHOOK_SECRET.encode(),raw,hashlib.sha256).digest()).decode()
    return hmac.compare_digest(digest,header or "")
def forward_order_to_cj(order):
    oid=order["id"]
    if oid in _orders_seen or "cj-sent" in (order.get("tags") or ""): return
    _orders_seen.add(oid)
    try:
        products=[]
        for li in order.get("line_items",[]):
            if not li.get("variant_id"): continue
            var=shop("GET",f"/variants/{li['variant_id']}.json"); vid=(var or {}).get("variant",{}).get("barcode")
            if not vid: raise RuntimeError(f"no CJ vid for {li.get('sku')}")
            products.append({"vid":vid,"quantity":int(li["quantity"])})
        a=order.get("shipping_address") or {}; country=a.get("country_code") or DEST_COUNTRY
        logistic=cj_cheapest_freight([{"vid":p["vid"],"quantity":p["quantity"]} for p in products],country)
        payload={"orderNumber":f"SHP-{order.get('name',oid)}".replace("#",""),"shippingCountryCode":country,"shippingCountry":a.get("country"),"shippingProvince":a.get("province"),"shippingCity":a.get("city"),"shippingAddress":a.get("address1"),"shippingCustomerName":a.get("name") or order.get("email"),"shippingZip":a.get("zip"),"shippingPhone":a.get("phone") or "","email":order.get("email") or "","remark":CJ_REMARK,"logisticName":logistic[1] if logistic[1]!="DEFAULT" else "","fromCountryCode":ORIGIN_COUNTRY,"products":products}
        res=cj("POST","/shopping/order/createOrderV2",body=payload); cj_id=(res or {}).get("orderId") or ""
        shop("PUT",f"/orders/{oid}.json",{"order":{"id":oid,"tags":((order.get("tags") or "")+", cj-sent").strip(", "),"note":f"CJ order: {cj_id}"}})
    except Exception as e:
        _orders_seen.discard(oid); log.error(f"order {oid} failed: {e}")

@app.get("/")
def root():
    return f"ok - CJ Live - Token: {'SET' if SHOP_TOKEN else 'NOT SET /auth'} - Shop: {SHOP_DOMAIN} - Branch: {GH_BRANCH}"

@app.get("/health")
def health():
    return jsonify(ok=True,last_sync=last_run,shop=SHOP_DOMAIN,token_set=bool(SHOP_TOKEN),branch=GH_BRANCH,max_per_run=MAX_PER_RUN,time_budget=TIME_BUDGET)

@app.get("/auth")
def auth_start():
    shop=request.args.get("shop","").strip()
    if not shop: return "Missing ?shop=YOURSHOP.myshopify.com",400
    if not shop.endswith(".myshopify.com"): shop=f"{shop}.myshopify.com"
    scopes="write_products,read_products,write_orders,read_orders,read_locations,write_inventory,read_inventory"
    redirect_uri="https://cj-shopify-backend.onrender.com/auth/callback"
    params={"client_id":SHOP_API_KEY,"scope":scopes,"redirect_uri":redirect_uri,"state":"123"}
    return redirect(f"https://{shop}/admin/oauth/authorize?{urlencode(params)}")

@app.get("/auth/callback")
def auth_callback():
    code=request.args.get("code"); shop=request.args.get("shop")
    if not code or not shop: return "Missing code/shop",400
    r=requests.post(f"https://{shop}/admin/oauth/access_token",json={"client_id":SHOP_API_KEY,"client_secret":SHOP_API_SECRET,"code":code},timeout=30)
    data=r.json(); token=data.get("access_token")
    if not token: return f"Failed: {data}",500
    save_token_to_file(shop,token)
    log.info(f"[INFO] Access token saved for {shop}")
    return f"<h1>✅ PERMANENT TOKEN SAVED!</h1><p>Shop: {shop}</p><p style='background:#000;color:#0f0;padding:15px;word-break:break-all'>{token}</p><p>Add this to Render as SHOPIFY_TOKEN and SHOPIFY_ACCESS_TOKEN</p><p><a href='/health'>Health</a></p>"

@app.post("/cron/sync")
def cron_sync():
    if not CRON_SECRET or request.headers.get("X-Cron-Secret")!=CRON_SECRET: abort(401)
    threading.Thread(target=run_sync,daemon=True).start()
    return jsonify(started=True),202

@app.post("/webhooks/shopify/orders")
def shopify_orders():
    raw=request.get_data()
    if not verify_hmac(raw,request.headers.get("X-Shopify-Hmac-Sha256")): abort(401)
    threading.Thread(target=forward_order_to_cj,args=(json.loads(raw),),daemon=True).start()
    return "",200

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000)))
