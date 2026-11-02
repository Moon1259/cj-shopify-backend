import industrial as ind

FASHION = [
    "Boho Brown Cotton Rope Shell Woven Waist Belt",
    "Punk-style Leather Strap Bodysuit With Single-leg Garter",
    "Rose-red Garter Belt And Stocking Set Sexy Lingerie",
    "Menstrual Belt, Waist Trainer Belt Fat Burning, Sweat Slim Belt",
    "Women's Trench Coat", "Fringed Mini Skirt", "Cowboy Boots", "Dog Car Seat Belt",
    "Bikini Set Swimwear", "Fashion Belt Men Genuine Leather Buckle",
]
INDUSTRIAL = {
    "Belt Tensioner Kit for Pontiac": ("Automobiles & Motorcycles", "Pulleys & Belts"),
    "Timing Belt Water Pump Kit for Subaru": ("Auto Parts", "Pulleys & Belts"),
    "Mini Electric Belt Sander": ("Tools", "Tools & Tool Kits"),
    "HTD 5M Rubber Timing Belt 15mm": ("Industrial", "Pulleys & Belts"),
    "6204-2RS Deep Groove Ball Bearing": ("Bearings", "Bearings & Linear Rails"),
    "Spur Gear 20 Teeth Steel": ("Machinery", "Gears & Shafts"),
    "NBR O-Ring Assortment Kit 382pcs": ("Hardware", "Gears & Shafts"),
    "220V 750W Self-Priming Water Pump": ("Pumps", "Utilities"),
    "Nema 23 Stepper Motor 3Nm": ("Motors", "Utilities"),
    "512GB SATA SSD": ("Computer", "Electronics & SSD"),
    "M8 Hex Nut Stainless Steel 100pcs": ("Hardware", "Mechanical"),
    "Cable Tie 4.8x300mm Nylon": ("Electrical", "Electrical"),
    "Servo Motor 750W 3000rpm": ("Industrial", "Utilities"),
    "SGR 15mm Linear Guide Rail 500mm": ("Machinery", "Bearings & Linear Rails"),
    "Precision Screwdriver Set 115 in 1": ("Tools", "Tools & Tool Kits"),
    "Roller Chain 08B-1 Drive Chain": ("Industrial", "Pulleys & Belts"),
}
bad = 0
for t in FASHION:
    ok, why = ind.industrial_ok(t, "")
    bad += ok
    print("BLOCK" if not ok else "LEAK!", why, "|", t)
for t, (cat, want) in INDUSTRIAL.items():
    ok, why = ind.industrial_ok(t, cat)
    got = ind.categorize(t)
    flag = ok and got == want
    bad += not flag
    print("OK   " if flag else "FAIL ", why, got, "|", t)
# ambiguous word, fashion category must lose; industrial category must win
print("belt+fashion cat :", ind.industrial_ok("Black Belt Unisex", "Clothing Accessories > Belts"))
print("belt+auto cat    :", ind.industrial_ok("Serpentine Belt 6PK", "Automobiles & Motorcycles"))
print("belt no category :", ind.industrial_ok("Black Belt Unisex", ""))
print("collection match :", ind.match_collection_title("Gear & Shafts"), "|",
      ind.match_collection_title("Bearings and Linear Rails"), "|", ind.match_collection_title("Home page"))
print("keywords:", len(ind.ALL_KEYWORDS))
assert 50 <= len(ind.ALL_KEYWORDS) <= 130
assert bad == 0, f"{bad} failures"
print("ALL PASS")
