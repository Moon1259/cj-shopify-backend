"""Builds industrial-v3-100.csv: 10 safety (Utilities) + 90 industrial. Generic names only.
PriceUSD / Stock are PLACEHOLDER ESTIMATES (I have no CJ data); the sync replaces them with real CJ cost x 1.3."""
import csv, sys
from industrial_strict_v3 import industrial_check_v3, get_collection

# (name, expected collection, sub-category, price)
ROWS = [
 # ---- 10 safety -> Utilities
 ("Safety Helmet Hard Hat White Industrial", "Utilities", "Safety Helmet", 12.5),
 ("Welding Helmet Auto Darkening Industrial", "Utilities", "Welding Helmet", 24.5),
 ("Safety Gloves Cut Resistant Work Gloves Industrial", "Utilities", "Safety Gloves", 6.5),
 ("Welding Gloves Heat Resistant Cowhide Industrial", "Utilities", "Welding Gloves", 11),
 ("Safety Goggles Anti-Fog Industrial", "Utilities", "Safety Goggles", 5.5),
 ("Ear Muffs Noise Reduction Industrial", "Utilities", "Hearing Protection", 14),
 ("Respirator Half Face Dual Cartridge Industrial", "Utilities", "Respirator", 22),
 ("Safety Shoes Steel Toe Industrial", "Utilities", "Safety Footwear", 38),
 ("Safety Harness Full Body Industrial", "Utilities", "Fall Protection", 29),
 ("High Visibility Vest Reflective Industrial", "Utilities", "Hi-Vis", 6),
 # ---- Gears & Shafts (13)
 ("Spur Gear Industrial Steel Module 1 20 Teeth", "Gears & Shafts", "Spur Gear", 8.5),
 ("Spur Gear Industrial Steel Module 2 30 Teeth", "Gears & Shafts", "Spur Gear", 14),
 ("Spur Gear Industrial Brass Module 1 40 Teeth", "Gears & Shafts", "Spur Gear", 11),
 ("Helical Gear Industrial Steel Module 1.5 25 Teeth", "Gears & Shafts", "Helical Gear", 19),
 ("Helical Gear Industrial Steel Module 2 40 Teeth", "Gears & Shafts", "Helical Gear", 28),
 ("Gear Rack Industrial Steel Module 1 1000mm", "Gears & Shafts", "Gear Rack", 24),
 ("Gear Rack Industrial Steel Module 2 500mm", "Gears & Shafts", "Gear Rack", 21),
 ("Gear Rack and Pinion Industrial Set Module 1.5", "Gears & Shafts", "Gear Rack", 36),
 ("Shaft Industrial Hardened Steel 10mm x 300mm", "Gears & Shafts", "Shaft", 7.5),
 ("Shaft Industrial Hardened Steel 20mm x 500mm", "Gears & Shafts", "Shaft", 15),
 ("Linear Shaft Industrial Chrome Plated 12mm x 400mm", "Gears & Shafts", "Shaft", 13),
 ("Shaft Industrial Stainless Steel Keyed 25mm x 600mm", "Gears & Shafts", "Shaft", 26),
 ("Sprocket Industrial Steel 08B 15 Teeth", "Gears & Shafts", "Sprocket", 9),
 # ---- Pulleys & Belts (13)
 ("V-Belt B Type Drive Belt Industrial 1000mm", "Pulleys & Belts", "Industrial Belt", 11),
 ("V-Belt Industrial A Type 800mm", "Pulleys & Belts", "Industrial Belt", 6.5),
 ("V-Belt Industrial C Type 1500mm", "Pulleys & Belts", "Industrial Belt", 16),
 ("V-Belt Industrial SPA Wedge 1250mm", "Pulleys & Belts", "Industrial Belt", 12),
 ("Timing Belt Industrial HTD 5M 15mm Width 600mm", "Pulleys & Belts", "Timing Belt", 9),
 ("Timing Belt Industrial GT2 6mm Width 2m", "Pulleys & Belts", "Timing Belt", 7),
 ("Timing Belt Industrial T10 25mm Width 1000mm", "Pulleys & Belts", "Timing Belt", 18),
 ("Synchronous Belt Industrial Open-End Rubber 5m", "Pulleys & Belts", "Timing Belt", 26),
 ("Conveyor Belt Industrial PVC 500mm Wide per Meter", "Pulleys & Belts", "Conveyor Belt", 24),
 ("Serpentine Belt Industrial Ribbed 6PK 1200mm", "Pulleys & Belts", "Industrial Belt", 15),
 ("Belt Tensioner Industrial Adjustable Idler", "Pulleys & Belts", "Belt Tensioner", 32),
 ("Pulley Industrial V-Groove Cast Iron Single Groove 100mm", "Pulleys & Belts", "Pulley", 17),
 ("Timing Pulley Industrial Aluminum HTD 5M 30 Teeth", "Pulleys & Belts", "Pulley", 12),
 # ---- Bearings & Linear Rails (13)
 ("Ball Bearing 6205 Industrial Generic", "Bearings & Linear Rails", "Bearing", 7.5),
 ("Ball Bearing 6204 Industrial Generic 2RS Sealed", "Bearings & Linear Rails", "Bearing", 5.5),
 ("Ball Bearing 6305 Industrial Deep Groove Generic", "Bearings & Linear Rails", "Bearing", 8.5),
 ("Ball Bearing 608 Industrial Miniature Generic Pack of 10", "Bearings & Linear Rails", "Bearing", 6.5),
 ("Roller Bearing Industrial Tapered 30205 Generic", "Bearings & Linear Rails", "Bearing", 11),
 ("Roller Bearing Industrial Cylindrical NU205 Generic", "Bearings & Linear Rails", "Bearing", 15),
 ("Roller Bearing Industrial Needle HK2020 Generic", "Bearings & Linear Rails", "Bearing", 7),
 ("Pillow Block Bearing Industrial UCP205 Generic", "Bearings & Linear Rails", "Pillow Block", 13),
 ("Pillow Block Bearing Industrial UCP208 Generic", "Bearings & Linear Rails", "Pillow Block", 22),
 ("Bearing Housing Industrial Cast Iron 205 Generic", "Bearings & Linear Rails", "Bearing Housing", 15),
 ("Linear Rail Guide Industrial MGN12 500mm with Carriage", "Bearings & Linear Rails", "Linear Rail", 29),
 ("Linear Guide Industrial HGR20 1000mm with Block", "Bearings & Linear Rails", "Linear Rail", 69),
 ("Linear Rail Guide Industrial SBR16 Supported Rail 800mm", "Bearings & Linear Rails", "Linear Rail", 32),
 # ---- Tools & Tool Kits (13)
 ("Drill Bit Industrial HSS Set 19 Pieces", "Tools & Tool Kits", "Drill Bit", 14),
 ("Drill Bit Industrial Titanium Coated 10mm", "Tools & Tool Kits", "Drill Bit", 5.5),
 ("Drill Bit Industrial Masonry SDS Plus 12mm", "Tools & Tool Kits", "Drill Bit", 6),
 ("Wrench Industrial Adjustable 12 inch", "Tools & Tool Kits", "Wrench", 11),
 ("Wrench Industrial Combination Set 12 Pieces", "Tools & Tool Kits", "Wrench", 26),
 ("Wrench Industrial Torque Click Type 1/2 inch", "Tools & Tool Kits", "Wrench", 38),
 ("Screwdriver Industrial Precision Set 32 Pieces", "Tools & Tool Kits", "Screwdriver", 13),
 ("Screwdriver Industrial Insulated VDE Set 7 Pieces", "Tools & Tool Kits", "Screwdriver", 24),
 ("Pliers Industrial Combination 8 inch", "Tools & Tool Kits", "Pliers", 9),
 ("Belt Sander Industrial Benchtop 4 x 36 inch", "Tools & Tool Kits", "Belt Sander", 118),
 ("Grease Gun Industrial Manual Heavy Duty 400cc", "Tools & Tool Kits", "Grease Gun", 17),
 ("Tool Kit Industrial Maintenance 108 Pieces", "Tools & Tool Kits", "Tool Kit", 56),
 ("Tool Kit Industrial Mechanic Socket Set 46 Pieces", "Tools & Tool Kits", "Tool Kit", 34),
 # ---- Electrical (13)
 ("Contactor Generic AC 3 Phase 25A 220V Coil", "Electrical", "Contactor", 14),
 ("Contactor Generic AC 3 Phase 40A 24V Coil", "Electrical", "Contactor", 19),
 ("Circuit Breaker Generic 3 Pole 63A MCB", "Electrical", "Circuit Breaker", 12),
 ("Circuit Breaker Generic 1 Pole 32A DIN Rail", "Electrical", "Circuit Breaker", 5.5),
 ("Circuit Breaker Generic Motor Protection 10-16A", "Electrical", "Circuit Breaker", 24),
 ("Terminal Block Industrial DIN Rail 2.5mm Pack of 50", "Electrical", "Terminal Block", 11),
 ("Terminal Block Industrial Screw Type 12 Position Strip", "Electrical", "Terminal Block", 6.5),
 ("Cable Tie Industrial Nylon 4.8x300mm Pack of 100", "Electrical", "Cable Tie", 5.5),
 ("Cable Tie Industrial Stainless Steel 7.9x300mm Pack of 50", "Electrical", "Cable Tie", 14),
 ("Wire Industrial Copper Flexible 2.5mm 100m", "Electrical", "Wire", 58),
 ("Relay Generic 24V DC 8 Pin 10A", "Electrical", "Relay", 6.5),
 ("Relay Generic Solid State 40A SSR", "Electrical", "Relay", 9),
 ("Switch Industrial Emergency Stop Push Button", "Electrical", "Switch", 8),
 # ---- Electronics & SSD (12)
 ("Proximity Sensor Industrial Inductive NPN M12 4mm", "Electronics & SSD", "Proximity Sensor", 7),
 ("Proximity Sensor Industrial Inductive PNP M18 8mm", "Electronics & SSD", "Proximity Sensor", 8.5),
 ("Proximity Sensor Industrial Capacitive M18", "Electronics & SSD", "Proximity Sensor", 11),
 ("Proximity Sensor Industrial Photoelectric Diffuse", "Electronics & SSD", "Proximity Sensor", 13),
 ("Limit Switch Industrial Roller Lever Micro", "Electronics & SSD", "Limit Switch", 8),
 ("Limit Switch Industrial Heavy Duty Waterproof", "Electronics & SSD", "Limit Switch", 15),
 ("Pressure Sensor Industrial 0-10 bar 4-20mA", "Electronics & SSD", "Pressure Sensor", 19),
 ("Pressure Sensor Industrial 0-16 bar G1/4 Stainless", "Electronics & SSD", "Pressure Sensor", 24),
 ("Industrial Sensor Generic Temperature PT100 Probe", "Electronics & SSD", "Sensor", 9.5),
 ("Industrial Sensor Generic Ultrasonic Distance", "Electronics & SSD", "Sensor", 16),
 ("Electronic Module Generic 4 Channel Relay Board Industrial", "Electronics & SSD", "Electronic Module", 7),
 ("Electronic Module Generic Motor Driver 20A Industrial", "Electronics & SSD", "Electronic Module", 12),
 # ---- Mechanical (13)
 ("Gate Valve Industrial Brass 1 inch", "Mechanical", "Valve", 15),
 ("Ball Valve Industrial Stainless 1/2 inch", "Mechanical", "Valve", 9),
 ("Ball Valve Industrial Brass 3 Way 1 inch", "Mechanical", "Valve", 21),
 ("Hydraulic Hose Industrial 1/2 inch 2 Layer Steel Braid 1m", "Mechanical", "Hydraulic Hose", 14),
 ("Pressure Gauge Industrial 0-10 bar Stainless 63mm", "Mechanical", "Pressure Gauge", 9),
 ("Pump Industrial Centrifugal Water 750W", "Mechanical", "Pump", 68),
 ("Air Filter Industrial Compressor Intake Element", "Mechanical", "Filter", 8),
 ("Oil Filter Industrial Hydraulic Spin-On", "Mechanical", "Filter", 12),
 ("O-Ring Industrial NBR Assortment Kit 382 Pieces", "Mechanical", "O-Ring", 10),
 ("Mechanical Seal Industrial Water Pump 20mm", "Mechanical", "Mechanical Seal", 14),
 ("Coupling Industrial Jaw Flexible 25mm", "Mechanical", "Coupling", 11),
 ("Fastener Industrial Hex Bolt and Nut Assortment Kit", "Mechanical", "Fastener", 14),
 ("Screw Industrial Stainless Hex Socket M8 Assortment", "Mechanical", "Screw", 12),
]
assert len(ROWS) == 100 and sum(r[1] == "Utilities" for r in ROWS) == 10, (len(ROWS),)
CODE = {"Utilities": "SAF", "Gears & Shafts": "GRS", "Pulleys & Belts": "BLT", "Bearings & Linear Rails": "BRG",
        "Tools & Tool Kits": "TLS", "Electrical": "ELC", "Electronics & SSD": "ELN", "Mechanical": "MEC"}
out, bad, seen = [], [], {}
for i, (name, want, sub, price) in enumerate(ROWS):
    status, why = industrial_check_v3(name, "")
    got = get_collection(name)
    if status != "PURE" or got != want or not (5 <= price <= 120):
        bad.append((name, status, why, got, want))
    seen[want] = seen.get(want, 0) + 1
    stock = 50 + (i * 53) % 451                                  # deterministic spread 50..500 (placeholder)
    out.append([f"IND-{CODE[want]}-{seen[want]:03d}", name, got, sub, f"{price:g}", stock, status,
                "PLACEHOLDER price/stock - not CJ data; sync overwrites with CJ cost x 1.3" +
                ("; generic safety item" if want == "Utilities" else "; generic industrial")])
if bad:
    print("PROBLEMS:", *bad, sep="\n  ")
    sys.exit(1)
with open("industrial-v3-100.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["SKU", "ProductName", "Collection", "Category", "PriceUSD", "Stock", "Status", "SourceNote"])
    w.writerows(out)
print("100 rows OK:", seen)
