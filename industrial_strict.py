"""
industrial_ok_strict_v2(name, manufacturer, source=None) -> (status, reason)

  BLOCKED     fashion / belt-rule failure / no industrial signal
  INCOMPLETE  industrial spare (VFD, PLC, bearing, valve, pump, motor, sensor, contactor ...) without a
              recognised manufacturer, or manufacturer not present in the product name
  BRAND_RISK  source is an unbranded marketplace (e.g. "cj") but a major brand is claimed -> likely counterfeit
              or trademark misuse. Never list these.
  PURE        passes every rule
"""
import re
import unicodedata


def _rx(words):
    parts = [re.escape(w).replace(r"\ ", r"[\s-]?").replace(r"\-", r"[\s-]?") for w in words]
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")s?(?![a-z0-9])", re.I)


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9+]+", "", s.lower())


# ---- 1. fashion block list (zero tolerance) -------------------------------------------------------------
FASHION_RE = _rx([
    "fashion", "women", "woman", "women's", "womens", "ladies", "lady", "girls", "sexy", "bikini", "lingerie",
    "handbag", "purse", "makeup", "cosmetic", "wig", "jewelry", "jewellery", "necklace", "heels", "dress fashion",
    "romper", "skirt", "blouse", "garter", "bodysuit", "boho", "waist trainer", "waist belt", "menstrual",
    "corset", "shapewear", "stocking", "cosplay", "costume", "dog", "pet", "toy", "baby", "kids",
])

# ---- 2. belt rule (critical) ----------------------------------------------------------------------------
BELT_WORD_RE = re.compile(r"(?<![a-z0-9])belt(?:s|ing)?(?![a-z0-9])", re.I)
BELT_OK_RE = _rx(["v-belt", "v belt", "vbelt", "timing belt", "conveyor belt", "industrial belt", "drive belt",
                  "serpentine belt", "synchronous belt", "fan belt industrial"])

# ---- 3. allow list: two pillars --------------------------------------------------------------------------
SAFETY_RE = _rx([
    "safety helmet", "hard hat", "welding helmet", "safety gloves", "work gloves", "cut resistant gloves",
    "chemical resistant gloves", "welding gloves", "nitrile gloves industrial", "fire extinguisher",
    "fire blanket", "fire hose", "fire suit", "fire resistant clothing", "fire proximity suit",
    "firefighter suit", "fire dress industrial", "safety goggles", "safety glasses", "face shield industrial",
    "ear muffs", "ear plugs industrial", "respirator", "dust mask industrial", "gas mask", "safety shoes",
    "steel toe boots", "safety boots", "safety harness", "high visibility vest", "hi-vis jacket",
    "coveralls industrial", "safety lockout tagout", "dust mask n95 industrial", "ear plugs", "face shield",
    "hi-vis vest", "lockout tagout",
])

# spares that MUST carry a recognised manufacturer
BRAND_REQUIRED_RE = _rx([
    "vfd", "inverter", "frequency converter", "servo drive", "plc", "hmi", "touch panel", "bearing", "valve",
    "pump", "motor", "gearmotor", "sensor", "contactor", "circuit breaker", "relay", "overload relay",
    "terminal block", "pneumatic cylinder", "cylinder", "hydraulic hose", "pneumatic fitting", "gearbox",
    "v-belt", "timing belt", "conveyor belt", "synchronous belt", "drive belt", "serpentine belt",
])
# other industrial items: allowed, brand optional
GENERIC_RE = _rx([
    "bolt", "hex nut", "lock nut", "screw", "washer", "o-ring", "oil seal", "gasket", "circlip", "roller chain",
    "sprocket", "pulley", "coupling", "bushing", "filter", "hose clamp", "fitting", "cable gland", "cable tie",
    "drill bit", "drill", "impact wrench", "wrench", "multimeter", "screwdriver", "hammer", "tool kit",
    "ssd", "heatsink", "thermal pad",
])

KNOWN_BRANDS = [
    "ABB", "Siemens", "Schneider Electric", "Schneider", "Danfoss", "Mitsubishi Electric", "Mitsubishi",
    "Allen-Bradley", "Rockwell Automation", "Omron", "SKF", "NSK", "FAG", "Schaeffler", "INA", "Timken", "NTN",
    "Gates", "ContiTech", "Optibelt", "Fenner", "Emerson", "ASCO", "Fisher", "Burkert", "Swagelok", "Grundfos",
    "Wilo", "KSB", "Xylem", "WEG", "Baldor", "Leroy-Somer", "Nord", "SEW-Eurodrive", "SICK", "Pepperl+Fuchs",
    "ifm", "Balluff", "Turck", "Keyence", "Banner", "Festo", "SMC", "Parker", "Bosch Rexroth", "Eaton",
    "Legrand", "Hager", "Phoenix Contact", "WAGO", "Weidmuller", "Lenze", "Yaskawa", "Fuji Electric", "Delta",
    "Panasonic", "Honeywell", "3M", "3M DBI-SALA", "MSA", "Ansell", "Uvex", "Moldex", "Kidde", "Amerex",
    "Ansul", "Lincoln Electric", "Miller", "Jackson Safety", "Makita", "DeWalt", "Bosch", "Milwaukee", "Hilti",
    "Klein Tools", "Stanley", "Fluke", "Master Lock", "Brady", "DuPont", "Lakeland", "Bulwark", "Carhartt",
    "Portwest", "Timberland PRO", "Keen", "Caterpillar", "Radians", "Kishigo", "JSP", "Showa", "Mechanix Wear",
    "Newtex", "Lion", "Angus Fire", "Pyramex", "Bolle Safety", "Howard Leight", "Peltor", "Morning Pride",
    "Schunk", "Hiwin", "THK", "Bonfiglioli", "Siemens Energy", "Hydac", "Donaldson", "Mann+Hummel",
]
_BRANDS = {_norm(b): b for b in KNOWN_BRANDS}
_MAJOR = {_norm(b) for b in ["ABB", "Siemens", "Schneider Electric", "Schneider", "SKF", "NSK", "FAG", "Timken",
                             "Gates", "ContiTech", "Optibelt", "Danfoss", "Allen-Bradley", "Omron", "Festo",
                             "SMC", "Parker", "Grundfos", "Wilo", "KSB", "WEG", "SICK", "3M", "Honeywell",
                             "MSA", "Ansell", "Makita", "DeWalt", "Bosch", "Fluke", "Eaton", "Legrand"]}


def industrial_ok_strict_v2(name, manufacturer="", source=None):
    name, mfr = (name or "").strip(), (manufacturer or "").strip()
    if not name:
        return "BLOCKED", "empty name"
    # 1 fashion
    m = FASHION_RE.search(name)
    if m:
        return "BLOCKED", f"fashion keyword: {m.group(0)}"
    # 2 belt rule
    if BELT_WORD_RE.search(name) and not BELT_OK_RE.search(name):
        return "BLOCKED", "belt rule: not an industrial belt type"
    # 3 must be on an allow list
    is_safety = bool(SAFETY_RE.search(name))
    needs_brand = bool(BRAND_REQUIRED_RE.search(name))
    is_generic = bool(GENERIC_RE.search(name))
    if not (is_safety or needs_brand or is_generic):
        return "BLOCKED", "no industrial signal"
    # 4 brand-claim guard for unbranded marketplaces
    key = _norm(mfr)
    if source and source.lower() in {"cj", "cjdropshipping", "aliexpress", "unknown"} and key in _MAJOR:
        return "BRAND_RISK", f"{mfr} claimed on an unbranded source ({source}); counterfeit/trademark risk"
    # 5 manufacturer rules
    if needs_brand:
        if key not in _BRANDS:
            return "INCOMPLETE", "spare requires a recognised manufacturer" + (f" (got '{mfr}')" if mfr else "")
        if key not in _norm(name):
            return "INCOMPLETE", "manufacturer name must appear in the product name"
    elif is_safety and mfr and key not in _BRANDS:
        return "INCOMPLETE", f"unrecognised safety brand '{mfr}'"
    return "PURE", "ok"
