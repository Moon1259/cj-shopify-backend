"""
Industrial-only gate, 8-category mapping, collection matching and the search keyword list.
Pure functions, no network. Used by app.py and maintenance.py.
"""
import re

CATEGORY_NAMES = [
    "Pulleys & Belts", "Electronics & SSD", "Utilities", "Gears & Shafts",
    "Bearings & Linear Rails", "Tools & Tool Kits", "Electrical", "Mechanical",
]
FALLBACK_CATEGORY = "Mechanical"


def _words(words):
    """regex alternation; spaces/hyphens interchangeable; optional plural s"""
    parts = [re.escape(w).replace(r"\ ", r"[\s-]?").replace(r"\-", r"[\s-]?") for w in words]
    return re.compile(r"\b(?:" + "|".join(parts) + r")s?\b", re.I)


# ------------------------------------------------------------------ 1. HARD BLACKLIST (always rejects)
BLACKLIST_RE = _words([
    # fashion / lingerie / body
    "boho", "garter", "lingerie", "bodysuit", "bra", "bikini", "panty", "panties", "thong", "stocking",
    "skirt", "dress", "gown", "coat", "trench", "jacket", "hoodie", "sweater", "shirt", "blouse", "jeans",
    "leggings", "cowboy", "boots", "sneaker", "heels", "sandal", "handbag", "purse", "wallet", "clutch bag",
    "clutch purse", "necklace", "bracelet", "earring", "jewelry", "jewellery", "wig", "makeup", "cosmetic",
    "eyelash", "perfume", "lipstick", "waist trainer", "waist belt", "waist cincher", "slimming belt",
    "slim belt", "sweat belt", "menstrual", "fat burning", "corset", "shapewear", "fringed", "tassel",
    "punk", "goth", "sexy", "adult toy", "costume", "cosplay", "fashion", "leather strap", "belt bag",
    "buckle belt", "pu leather belt", "waistband", "suspender", "elastic belt", "woven belt", "rope belt",
    "women", "woman", "women's", "womens", "ladies", "girls", "girl", "maternity", "bridal", "wedding",
    "nail polish", "nail art", "nail gel", "nail file", "nail clipper",
    # kids / pets / home-decor
    "baby", "toddler", "kids", "children", "toy", "doll", "plush", "dog", "puppy", "kitten", "pet",
    "leash", "cat litter", "cat food", "seat belt", "seatbelt", "yoga", "massage", "halloween", "christmas",
    "candle", "pillow case", "curtain", "bedding", "blanket", "phone case", "sticker", "poster", "umbrella",
])
BLACKLIST_RE = re.compile(r"\bwom[ae]n'?s?\b|" + BLACKLIST_RE.pattern, re.I)

CATEGORY_DENY_RE = re.compile(
    r"clothing|apparel|lingerie|underwear|dress|skirt|shoe|footwear|\bboots?\b|\bbags?\b|luggage|jewel|"
    r"watches|beauty|\bhair\b|\bwigs?\b|makeup|cosmetic|\bpets?\b|\btoys?\b|\bbaby\b|\bkids?\b|maternity|"
    r"wedding|costume|\bsexy\b|\badult\b|women|men's|\bmens\b|party|\bgifts?\b", re.I)

# CJ category names that look industrial (needed when the title only has an ambiguous word like "belt")
INDUSTRIAL_CAT_RE = re.compile(
    r"tool|hardware|industrial|machin|automobile|auto part|car part|motorcycle|vehicle|electrical|"
    r"electronic component|components|bearing|pneumatic|hydraulic|pump|motor|home improvement|building|"
    r"plumbing|fastener|welding|power|instrument|measure|safety|transmission", re.I)

# ------------------------------------------------------------------ 2. SEARCH KEYWORDS (specific, multi-word on purpose)
KEYWORDS = {
    "tiny": [
        # fasteners
        "machine screw", "self tapping screw", "set screw", "hex bolt", "anchor bolt",
        "hex nut", "lock nut", "flange nut", "threaded rod", "flat washer",
        "spring washer", "cotter pin", "rivet",
        # seals / bushings / bearings
        "o-ring", "oil seal", "shaft seal", "gasket", "shim", "circlip", "retaining ring",
        "rubber bushing", "sleeve bearing", "ball bearing", "roller bearing",
        "pillow block bearing", "linear bearing",
        # motion
        "timing belt", "v belt", "conveyor belt", "drive belt", "belt tensioner",
        "timing pulley", "roller chain", "sprocket", "linear guide", "linear rail", "ball screw",
        "shaft coupling", "spur gear",
        "worm gear", "gear rack", "pinion gear", "gearbox", "speed reducer",
        # fluid / pneumatic
        "hose clamp", "pipe fitting", "hydraulic fitting", "pneumatic fitting", "air hose", "hydraulic hose",
        "solenoid valve", "ball valve", "check valve", "air filter element",
        "oil filter", "hydraulic filter", "fuel filter", "grease fitting", "lubricator",
        # electrical / electronic
        "proximity sensor", "limit switch", "pressure sensor", "temperature sensor",
        "relay", "solid state relay", "contactor", "circuit breaker", "fuse", "terminal block", "cable tie",
        "cable gland", "push button switch", "din rail", "junction box", "thermal pad",
        "heatsink", "ssd",
        # tools / safety
        "tool kit", "precision screwdriver set",
    ],
    "heavy": [
        "servo motor", "stepper motor", "ac induction motor", "dc motor", "gear motor", "brushless motor",
        "water pump", "centrifugal pump", "vacuum pump", "hydraulic pump", "diaphragm pump", "suction pump",
        "air compressor", "generator", "industrial fan", "inverter vfd", "frequency converter",
        "plc controller",
    ],
}
ALL_KEYWORDS = KEYWORDS["tiny"] + KEYWORDS["heavy"]

# single words that are NOT enough alone (need an industrial CJ category as 2nd signal)
WEAK_TERMS = ["belt", "chain", "motor", "pump", "valve", "filter", "hose", "clamp", "switch", "cable", "wire",
              "sensor", "module", "board", "chip", "tool", "screw", "nut", "gear", "shaft", "seal", "tank",
              "fan", "plug", "socket", "connector", "terminal", "fitting", "bracket", "spring", "clutch",
              "bearing", "bolt", "washer", "coupling"]
WEAK_RE = _words(WEAK_TERMS)

_STRONG_EXTRA = ["pulley", "sprocket", "bushing", "gasket", "o-ring", "circlip", "pinion", "gearbox",
                 "sander", "angle grinder", "drill", "wrench", "screwdriver", "pliers", "hammer", "soldering",
                 "multimeter", "caliper", "toolkit", "hex key", "allen key", "heat gun", "puller",
                 "plc", "vfd", "inverter", "contactor", "heatsink", "ssd", "relay", "lubricant", "tensioner"]
_WEAK_ONLY_KEYWORDS = {"fuse", "shim", "generator"}  # fine as search terms, not as title proof
STRONG_RE = _words([k for k in ALL_KEYWORDS if k not in _WEAK_ONLY_KEYWORDS] + _STRONG_EXTRA)


def industrial_ok(title: str, cj_category: str = ""):
    """(allowed, reason). Blacklist wins; then strong title term; else weak term + industrial CJ category."""
    t = title or ""
    c = cj_category or ""
    if BLACKLIST_RE.search(t):
        return False, "blacklist-title"
    if CATEGORY_DENY_RE.search(c):
        return False, "blacklist-category"
    if STRONG_RE.search(t):
        return True, "strong"
    if (WEAK_RE.search(t) or re.search(r"\b(?:fuse|shim|generator)s?\b", t, re.I)) and INDUSTRIAL_CAT_RE.search(c):
        return True, "weak+category"
    return False, "no-industrial-signal"


# ------------------------------------------------------------------ 3. 8-CATEGORY MAPPING (first match, else Mechanical)
TOOL_OVERRIDE_RE = _words(["sander", "angle grinder", "grinder", "drill", "wrench", "screwdriver", "pliers",
                           "hammer", "soldering iron", "multimeter", "caliper", "tool kit", "toolkit",
                           "tool set", "hex key", "allen key", "heat gun", "puller"])

CATEGORY_KEYWORDS = [
    ("Pulleys & Belts", ["pulley", "belt", "timing belt", "v-belt", "conveyor belt", "chain", "tensioner"]),
    ("Electronics & SSD", ["ssd", "solid state drive", "gpu", "graphics card", "thermal pad", "heatsink",
                           "heat sink", "mounting bracket", "circuit", "board", "microcontroller", "chip",
                           "sensor", "module", "plc", "vfd", "inverter", "frequency converter"]),
    ("Utilities", ["motor", "pump", "compressor", "generator", "tank", "cleaning", "maintenance", "lubricant",
                   "lubricator", "grease", "safety", "glove", "fan", "blower", "general use"]),
    ("Gears & Shafts", ["gear", "gearbox", "reducer", "shaft", "sprocket", "differential", "transfer case",
                        "seal", "o-ring", "gasket", "shim", "washer", "circlip", "retaining ring", "clutch",
                        "synchronizer", "shift fork", "pinion"]),
    ("Bearings & Linear Rails", ["bearing", "bushing", "linear rail", "linear guide", "linear slide",
                                 "ball screw", "lead screw", "pillow block"]),
    ("Tools & Tool Kits", ["tool", "toolkit", "wrench", "drill", "cutter", "hammer", "hilltee", "screwdriver",
                           "wrist band", "wrist strap"]),
    ("Electrical", ["wire", "cable", "switch", "relay", "breaker", "contactor", "fuse", "terminal",
                    "cable tie", "gland", "connector", "junction box", "din rail", "control unit",
                    "backup power", "power strip", "plug", "socket"]),
    ("Mechanical", ["mechanical", "coupling", "fastener", "screw", "bolt", "nut", "rivet", "pin", "hydraulic",
                    "pneumatic", "valve", "hose", "clamp", "fitting", "filter", "spring"]),
]
_CAT_RE = [(n, _words(k)) for n, k in CATEGORY_KEYWORDS]


def categorize(title: str) -> str:
    if TOOL_OVERRIDE_RE.search(title or ""):
        return "Tools & Tool Kits"
    for name, rx in _CAT_RE:
        if rx.search(title or ""):
            return name
    return FALLBACK_CATEGORY


# ------------------------------------------------------------------ 4. match YOUR existing Shopify collection titles to the 8 categories
def _norm(s: str) -> frozenset:
    toks = re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split()
    return frozenset(t[:-1] if t.endswith("s") and len(t) > 3 else t for t in toks if t != "and")


_CAT_NORM = {_norm(n): n for n in CATEGORY_NAMES}


def match_collection_title(title: str):
    """'Gear & Shafts' / 'Gears and Shafts' -> 'Gears & Shafts'. None if not one of our 8."""
    return _CAT_NORM.get(_norm(title))
