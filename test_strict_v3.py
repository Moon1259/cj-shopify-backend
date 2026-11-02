from industrial_strict_v3 import industrial_ok_strict_v3 as ok, get_collection

BLOCK = [
    "Fashion Men Belt Leather", "Boho Brown Cotton Rope Shell Woven Waist Belt",
    "Rose-red Garter Belt And Stocking Set Sexy Lingerie", "Menstrual Belt, Waist Trainer Belt Fat Burning",
    "Women's Trench Coat", "Dog Car Seat Belt", "Casual Canvas Belt Men", "Men's Leather Drive Belt Buckle",
    "Belt Tensioner Kit", "Belt Sander Mini Electric",            # allowed only as '... industrial'
    "Nail Gun Industrial", "Wire Hair Clip", "SKF 6205 Ball Bearing", "Siemens PLC Industrial",
    "Scented Candle Gift Set", "Bluetooth Speaker Mini",
    "Wire Basket Storage",                                         # weak keyword, no qualifier, no category
]
PASS = [
    "V-Belt B Type Drive Belt Industrial 1000mm", "Timing Belt Industrial HTD 5M", "Conveyor Belt Industrial PVC",
    "Belt Tensioner Industrial Adjustable Idler", "Belt Sander Industrial Benchtop", "Safety Helmet Hard Hat White Industrial",
    "Ball Bearing 6205 Industrial Generic", "Wire Industrial Copper Flexible", "Steel Toe Boots Work",
]
bad = 0
for n in BLOCK:
    got = ok(n); bad += got != "BLOCKED"; print("OK  " if got == "BLOCKED" else "FAIL", got, "|", n)
for n in PASS:
    got = ok(n); bad += got != "PURE"; print("OK  " if got == "PURE" else "FAIL", got, "|", n)
# category as 2nd signal
assert ok("Wire Basket Storage", "Home & Garden") == "BLOCKED"
assert ok("Hex Nut M8 Stainless Steel", "Hardware") == "PURE"
assert ok("Hex Nut M8 Stainless Steel", "Women's Clothing") == "BLOCKED"
# mapper
MAP = {"Welding Gloves Heat Resistant Industrial": "Utilities", "Belt Sander Industrial Benchtop": "Tools & Tool Kits",
       "Limit Switch Industrial": "Electronics & SSD", "Switch Industrial Emergency Stop": "Electrical",
       "Pressure Gauge Industrial": "Mechanical", "Pressure Sensor Industrial": "Electronics & SSD",
       "V-Belt Industrial A Type": "Pulleys & Belts", "Pillow Block Bearing Industrial": "Bearings & Linear Rails",
       "Spur Gear Industrial": "Gears & Shafts", "Mystery Widget": "Mechanical"}
for n, want in MAP.items():
    got = get_collection(n); bad += got != want; print("OK  " if got == want else "FAIL", got, "|", n)
assert not bad, f"{bad} failures"
print("ALL V3 TESTS PASS")
