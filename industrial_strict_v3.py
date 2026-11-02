"""
V3: generic-only strict filter + collection mapper. No manufacturer names anywhere.

  industrial_ok_strict_v3(name, category="") -> "PURE" | "BLOCKED"
  industrial_check_v3(name, category="")     -> (status, reason)
  get_collection(name)                       -> one of your 8 Shopify collections (safety -> Utilities)

`category` = the supplier's category text (CJ categoryName). It is used twice: the fashion/pet block also
scans it, and a weak keyword (wire, switch, pump ...) is accepted only with "industrial"/"generic" in the name
OR an industrial-looking category.
"""
import re

from industrial import INDUSTRIAL_CAT_RE
from industrial_strict import _rx

COLLECTIONS = ["Gears & Shafts", "Utilities", "Pulleys & Belts", "Electronics & SSD",
               "Bearings & Linear Rails", "Tools & Tool Kits", "Electrical", "Mechanical"]

# ---- 1. block lists -----------------------------------------------------------------------------------
FASHION_RE = _rx([
    "fashion", "women", "woman", "ladies", "lady", "sexy", "bikini", "lingerie", "handbag", "purse",
    "wallet fashion", "makeup", "cosmetic", "wig", "nail", "eyelash", "jewelry", "jewellery", "necklace",
    "bracelet", "romper", "skirt", "blouse", "heels", "dress fashion",
    # extras that were seen in the bad import
    "garter", "bodysuit", "boho", "corset", "stocking", "menstrual", "waist trainer", "waist belt", "costume",
    "cosplay", "dog", "pet", "toy", "kids", "baby", "girls", "hair",
])
# major manufacturers: a generic store must not use them (trademark). Ambiguous words (Delta, Lion...) left out.
BRAND_RE = _rx([
    "ABB", "Siemens", "Schneider", "SKF", "NSK", "FAG", "Timken", "Gates", "ContiTech", "Optibelt", "Danfoss",
    "Omron", "Festo", "SMC", "Parker", "Grundfos", "Wilo", "KSB", "WEG", "SICK", "3M", "Honeywell", "MSA",
    "Ansell", "Makita", "DeWalt", "Bosch", "Fluke", "Eaton", "Legrand", "Mitsubishi", "Allen-Bradley",
    "Rockwell", "Emerson", "Burkert", "Swagelok", "Milwaukee", "Hilti", "Kidde", "Lincoln Electric", "Uvex",
    "Phoenix Contact", "Yaskawa", "Hiwin", "THK", "Master Lock", "DuPont", "Carhartt", "Portwest", "Caterpillar",
    "Pepperl+Fuchs", "Balluff", "Keyence", "Panasonic", "Fuji Electric", "Lenze", "SEW", "Baldor",
])

# ---- 2. belt rule ------------------------------------------------------------------------------------
BELT_WORD_RE = re.compile(r"(?<![a-z0-9])belt(?:s|ing)?(?![a-z0-9])", re.I)
BELT_OK_RE = _rx(["v-belt", "v belt", "vbelt", "timing belt", "conveyor belt", "industrial belt", "drive belt",
                  "serpentine belt", "synchronous belt", "fan belt industrial", "belt tensioner industrial",
                  "belt sander industrial"])
# even with an allowed phrase, apparel words mean it is a clothing belt ("Men's Leather Drive Belt")
BELT_APPAREL_RE = _rx(["leather", "buckle", "waist", "casual", "jeans", "men", "mens", "male", "female",
                       "unisex", "cotton", "canvas", "trouser", "cowboy", "western", "dress"])

# ---- 3. allow lists ----------------------------------------------------------------------------------
SAFETY_RE = _rx([
    "safety helmet", "hard hat", "welding helmet", "safety gloves", "work gloves", "cut resistant gloves",
    "chemical resistant gloves", "welding gloves", "safety goggles", "safety glasses", "face shield",
    "ear muffs", "ear plugs", "respirator", "dust mask", "safety shoes", "steel toe boots", "steel toe",
    "safety boots", "safety harness", "high visibility vest", "hi-vis", "fire extinguisher", "fire blanket",
    "fire hose",
])
STRONG_RE = _rx([
    "spur gear", "helical gear", "bevel gear", "worm gear", "gear rack", "sprocket", "pinion",
    "v-belt", "v belt", "timing belt", "conveyor belt", "industrial belt", "drive belt", "serpentine belt",
    "synchronous belt", "belt tensioner", "belt sander", "pulley", "ball bearing", "roller bearing",
    "pillow block", "bearing housing", "bearing", "linear rail", "linear guide", "ball screw",
    "drill bit", "grease gun", "tool kit", "contactor", "circuit breaker", "terminal block", "cable tie",
    "proximity sensor", "limit switch", "pressure sensor", "gate valve", "ball valve", "check valve",
    "solenoid valve", "hydraulic hose", "pressure gauge", "air filter", "oil filter", "o-ring",
    "mechanical seal", "oil seal", "hex bolt", "hex nut", "lock nut", "circlip",
])
WEAK_RE = _rx(["shaft", "gear", "wire", "switch", "relay", "sensor", "electronic module", "wrench", "screwdriver",
               "pliers", "pump", "coupling", "fastener", "screw", "bolt", "nut", "washer", "valve", "hose",
               "filter", "seal", "cable", "motor", "tool"])
QUALIFIER_RE = _rx(["industrial", "generic", "heavy duty", "heavy-duty"])


def industrial_check_v3(name, category=""):
    n, c = (name or "").strip(), (category or "").strip()
    if not n:
        return "BLOCKED", "empty name"
    m = FASHION_RE.search(n) or FASHION_RE.search(c)
    if m:
        return "BLOCKED", f"fashion/pet keyword: {m.group(0)}"
    m = BRAND_RE.search(n)
    if m:
        return "BLOCKED", f"brand name (trademark risk): {m.group(0)}"
    if BELT_WORD_RE.search(n):
        if not BELT_OK_RE.search(n):
            return "BLOCKED", "belt rule: not an allowed industrial belt type"
        m = BELT_APPAREL_RE.search(n)
        if m:
            return "BLOCKED", f"belt rule: apparel word '{m.group(0)}'"
    if SAFETY_RE.search(n) or STRONG_RE.search(n):
        return "PURE", "ok"
    if WEAK_RE.search(n) and (QUALIFIER_RE.search(n) or INDUSTRIAL_CAT_RE.search(c)):
        return "PURE", "ok (weak keyword + industrial qualifier/category)"
    return "BLOCKED", "no industrial keyword"


def industrial_ok_strict_v3(name, category=""):
    return industrial_check_v3(name, category)[0]


# ---- 4. collection mapper (first matching rule wins) -------------------------------------------------
_RULES = [
    ("Utilities", SAFETY_RE),                                                       # all safety items
    ("Tools & Tool Kits", _rx(["belt sander"])),
    ("Electronics & SSD", _rx(["proximity sensor", "limit switch", "pressure sensor", "sensor",
                               "electronic module", "microcontroller", "ssd", "plc", "vfd", "inverter",
                               "circuit board", "heatsink", "thermal pad"])),
    ("Pulleys & Belts", _rx(["belt", "pulley", "tensioner", "roller chain", "drive chain"])),
    ("Bearings & Linear Rails", _rx(["bearing", "linear rail", "linear guide", "linear slide", "ball screw",
                                    "pillow block", "bushing"])),
    ("Gears & Shafts", _rx(["gear", "shaft", "gear rack", "rack and pinion", "sprocket", "pinion", "clutch",
                            "differential"])),
    ("Tools & Tool Kits", _rx(["drill bit", "drill", "wrench", "screwdriver", "pliers", "grease gun", "tool kit",
                               "toolkit", "tool", "cutter", "hammer"])),
    ("Electrical", _rx(["contactor", "circuit breaker", "breaker", "terminal block", "terminal", "cable tie",
                        "cable", "wire", "relay", "switch", "fuse", "power socket", "wall socket"])),
    ("Mechanical", _rx(["mechanical seal", "seal", "valve", "hose", "pressure gauge", "gauge", "filter",
                        "o-ring", "coupling", "fastener", "screw", "bolt", "nut", "washer", "pump",
                        "hydraulic", "pneumatic"])),
    ("Utilities", _rx(["motor", "compressor", "generator", "lubricant", "cleaning", "maintenance", "tank"])),
]


def get_collection(name):
    for coll, rx in _RULES:
        if rx.search(name or ""):
            return coll
    return "Mechanical"
