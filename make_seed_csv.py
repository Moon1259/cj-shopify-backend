"""Builds industrial-seed-100.csv (40 safety + 60 spares). Every row must pass industrial_ok_strict_v2."""
import csv, sys
from industrial_strict import industrial_ok_strict_v2 as ok

# (name, manufacturer, category, subcategory, verify?)  -- verify=True: brand/model pairing I am less sure of
SAFETY = [
    ("Safety Helmet Hard Hat SecureFit H-700 Series - 3M", "3M", "Safety", "Helmet", 0),
    ("Safety Helmet Hard Hat V-Gard - MSA", "MSA", "Safety", "Helmet", 0),
    ("Safety Helmet Hard Hat Evolite - JSP", "JSP", "Safety", "Helmet", 0),
    ("Welding Helmet Speedglas 9100 - 3M", "3M", "Safety", "Welding Helmet", 0),
    ("Welding Helmet Viking 3350 Auto-Darkening - Lincoln Electric", "Lincoln Electric", "Safety", "Welding Helmet", 0),
    ("Safety Gloves HyFlex 11-840 - Ansell", "Ansell", "Safety", "Gloves", 0),
    ("Work Gloves HyFlex 11-801 - Ansell", "Ansell", "Safety", "Gloves", 0),
    ("Work Gloves M-Pact - Mechanix Wear", "Mechanix Wear", "Safety", "Gloves", 0),
    ("Cut Resistant Gloves HyFlex 11-518 - Ansell", "Ansell", "Safety", "Gloves", 0),
    ("Chemical Resistant Gloves AlphaTec - Ansell", "Ansell", "Safety", "Gloves", 1),
    ("Welding Gloves Cowhide MIG TIG - Lincoln Electric", "Lincoln Electric", "Safety", "Gloves", 1),
    ("Nitrile Gloves Industrial TouchNTuff 92-600 - Ansell", "Ansell", "Safety", "Gloves", 0),
    ("Fire Extinguisher ABC ProLine Pro 210 - Kidde", "Kidde", "Safety", "Fire Safety", 0),
    ("Fire Extinguisher ABC Dry Chemical B500 - Amerex", "Amerex", "Safety", "Fire Safety", 0),
    ("Fire Extinguisher ABC Red Line - Ansul", "Ansul", "Safety", "Fire Safety", 0),
    ("Fire Blanket 1.2 x 1.8 m - Kidde", "Kidde", "Safety", "Fire Safety", 1),
    ("Fire Hose Layflat 1.5 inch - Angus Fire", "Angus Fire", "Safety", "Fire Safety", 1),
    ("Fire Proximity Suit Aluminized - Newtex", "Newtex", "Safety", "Fire Protective Clothing", 1),
    ("Fire Resistant Clothing FR Coverall - Bulwark", "Bulwark", "Safety", "Fire Protective Clothing", 0),
    ("Firefighter Suit Structural Turnout V-Force - Lion", "Lion", "Safety", "Fire Protective Clothing", 0),
    ("Firefighter Suit Structural Turnout - Morning Pride", "Morning Pride", "Safety", "Fire Protective Clothing", 1),
    ("Fire Dress Industrial FR Coverall - Carhartt", "Carhartt", "Safety", "Fire Protective Clothing", 1),
    ("Safety Goggles GoggleGear 500 Series - 3M", "3M", "Safety", "Eye Protection", 0),
    ("Safety Glasses Hypershock - Uvex", "Uvex", "Safety", "Eye Protection", 1),
    ("Safety Glasses Rush+ - Bolle Safety", "Bolle Safety", "Safety", "Eye Protection", 1),
    ("Face Shield Industrial WP96 - 3M", "3M", "Safety", "Face Protection", 1),
    ("Ear Muffs Peltor Optime 105 - 3M", "3M", "Safety", "Hearing Protection", 0),
    ("Ear Muffs Impact Sport - Howard Leight", "Howard Leight", "Safety", "Hearing Protection", 0),
    ("Ear Plugs Industrial Laser Lite - Howard Leight", "Howard Leight", "Safety", "Hearing Protection", 0),
    ("Ear Plugs Industrial E-A-R Classic - 3M", "3M", "Safety", "Hearing Protection", 0),
    ("Respirator Half Facepiece 6200 - 3M", "3M", "Safety", "Respiratory", 0),
    ("Dust Mask Industrial N95 8210 - 3M", "3M", "Safety", "Respiratory", 0),
    ("Gas Mask Full Facepiece 6800 - 3M", "3M", "Safety", "Respiratory", 0),
    ("Steel Toe Boots Pit Boss - Timberland PRO", "Timberland PRO", "Safety", "Footwear", 0),
    ("Safety Shoes Steel Toe Second Shift - Caterpillar", "Caterpillar", "Safety", "Footwear", 1),
    ("Safety Harness ExoFit NEX - 3M DBI-SALA", "3M DBI-SALA", "Safety", "Fall Protection", 0),
    ("High Visibility Vest Class 2 - Portwest", "Portwest", "Safety", "Hi-Vis", 1),
    ("Hi-Vis Jacket Waterproof - Portwest", "Portwest", "Safety", "Hi-Vis", 1),
    ("Coveralls Industrial Tyvek 400 - DuPont", "DuPont", "Safety", "Coveralls", 0),
    ("Safety Lockout Tagout Padlock 410 - Master Lock", "Master Lock", "Safety", "Lockout Tagout", 0),
]
SPARES = [
    # VFD
    ("VFD ACS880-01 Industrial Drive 5.5 kW - ABB", "ABB", "Automation", "VFD", 0),
    ("VFD Sinamics V20 Inverter 2.2 kW - Siemens", "Siemens", "Automation", "VFD", 0),
    ("VFD Altivar ATV320 Inverter 4 kW - Schneider Electric", "Schneider Electric", "Automation", "VFD", 0),
    ("VFD VLT Micro Drive FC 51 Inverter 1.5 kW - Danfoss", "Danfoss", "Automation", "VFD", 0),
    ("VFD FR-D720S Inverter 0.75 kW - Mitsubishi Electric", "Mitsubishi Electric", "Automation", "VFD", 0),
    # PLC / HMI
    ("PLC S7-1200 CPU 1214C - Siemens", "Siemens", "Automation", "PLC", 0),
    ("PLC CompactLogix 5380 Controller - Allen-Bradley", "Allen-Bradley", "Automation", "PLC", 0),
    ("PLC Modicon M241 Logic Controller - Schneider Electric", "Schneider Electric", "Automation", "PLC", 0),
    ("PLC FX5U Programmable Controller - Mitsubishi Electric", "Mitsubishi Electric", "Automation", "PLC", 0),
    ("PLC CP1E Programmable Controller - Omron", "Omron", "Automation", "PLC", 0),
    ("HMI KTP700 Basic Touch Panel - Siemens", "Siemens", "Automation", "HMI", 0),
    # Bearings
    ("Bearing 6205-2RSH Deep Groove Ball - SKF", "SKF", "Transmission", "Bearing", 0),
    ("Bearing 6205DDU Deep Groove Ball - NSK", "NSK", "Transmission", "Bearing", 0),
    ("Bearing 6205-2RSR Deep Groove Ball - FAG", "FAG", "Transmission", "Bearing", 0),
    ("Bearing 6205-2RS Deep Groove Ball - Timken", "Timken", "Transmission", "Bearing", 1),
    ("Bearing 30205 Tapered Roller - Timken", "Timken", "Transmission", "Bearing", 0),
    ("Bearing 22210 E Spherical Roller - SKF", "SKF", "Transmission", "Bearing", 0),
    # Belts (industrial only)
    ("V-Belt B Type 1000mm Hi-Power - Gates", "Gates", "Transmission", "V-Belt", 0),
    ("Synchronous Belt PowerGrip GT3 - Gates", "Gates", "Transmission", "Timing Belt", 0),
    ("Timing Belt Synchroflex T10 - ContiTech", "ContiTech", "Transmission", "Timing Belt", 0),
    ("Conveyor Belt Industrial PVC - ContiTech", "ContiTech", "Transmission", "Conveyor Belt", 1),
    ("V-Belt Super TX - Optibelt", "Optibelt", "Transmission", "V-Belt", 1),
    # Valves
    ("Valve Fisher ET Control Globe - Emerson", "Emerson", "Fluid Control", "Valve", 1),
    ("Valve Solenoid Series 8210 - ASCO", "ASCO", "Fluid Control", "Valve", 0),
    ("Valve Solenoid Type 6013 - Burkert", "Burkert", "Fluid Control", "Valve", 0),
    ("Valve Ball 40G Series - Swagelok", "Swagelok", "Fluid Control", "Valve", 0),
    ("Valve Solenoid EV220B - Danfoss", "Danfoss", "Fluid Control", "Valve", 0),
    # Pumps
    ("Pump CM Centrifugal Water Industrial - Grundfos", "Grundfos", "Fluid Control", "Pump", 0),
    ("Pump CR 5 Vertical Multistage - Grundfos", "Grundfos", "Fluid Control", "Pump", 0),
    ("Pump Yonos PICO Circulation - Wilo", "Wilo", "Fluid Control", "Pump", 0),
    ("Pump Etanorm Centrifugal - KSB", "KSB", "Fluid Control", "Pump", 0),
    ("Pump Movitec Vertical Multistage - KSB", "KSB", "Fluid Control", "Pump", 0),
    # Motors
    ("Motor 1LE1 Three-Phase 2.2 kW IE3 - Siemens", "Siemens", "Drives", "Motor", 0),
    ("Motor M3BP Three-Phase 2.2 kW - ABB", "ABB", "Drives", "Motor", 0),
    ("Motor W22 Three-Phase 2.2 kW IE3 - WEG", "WEG", "Drives", "Motor", 0),
    ("Motor Super-E Three-Phase - Baldor", "Baldor", "Drives", "Motor", 1),
    ("Gearmotor DR Series - SEW-Eurodrive", "SEW-Eurodrive", "Drives", "Motor", 0),
    # Sensors
    ("Sensor Photoelectric WL Series Industrial - SICK", "SICK", "Automation", "Sensor", 0),
    ("Sensor Inductive Proximity IME Series - SICK", "SICK", "Automation", "Sensor", 0),
    ("Sensor Inductive Proximity NBB Series - Pepperl+Fuchs", "Pepperl+Fuchs", "Automation", "Sensor", 0),
    ("Sensor Inductive Efector IGS - ifm", "ifm", "Automation", "Sensor", 1),
    ("Sensor Inductive Proximity BES Series - Balluff", "Balluff", "Automation", "Sensor", 0),
    # Electrical
    ("Contactor LC1D09 - Schneider Electric", "Schneider Electric", "Electrical", "Contactor", 0),
    ("Contactor AF09 - ABB", "ABB", "Electrical", "Contactor", 0),
    ("Circuit Breaker Motor Protection 3RV2011 - Siemens", "Siemens", "Electrical", "Circuit Breaker", 0),
    ("Circuit Breaker Miniature MCB DX3 - Legrand", "Legrand", "Electrical", "Circuit Breaker", 0),
    ("Circuit Breaker Motor Protective PKZM0 - Eaton", "Eaton", "Electrical", "Circuit Breaker", 0),
    ("Overload Relay TeSys LRD Thermal - Schneider Electric", "Schneider Electric", "Electrical", "Relay", 0),
    ("Terminal Block UT 4 - Phoenix Contact", "Phoenix Contact", "Electrical", "Terminal", 0),
    ("Relay Solid State G3NA - Omron", "Omron", "Electrical", "Relay", 0),
    # Pneumatic / hydraulic
    ("Pneumatic Cylinder DSBC ISO 15552 - Festo", "Festo", "Pneumatics", "Cylinder", 0),
    ("Pneumatic Cylinder CDQ2 Compact - SMC", "SMC", "Pneumatics", "Cylinder", 0),
    ("Valve Pneumatic Solenoid SY5000 Industrial - SMC", "SMC", "Pneumatics", "Valve", 0),
    ("Hydraulic Hose 301SN - Parker", "Parker", "Pneumatics", "Hydraulic Hose", 1),
    ("Pneumatic Fitting QS Push-in - Festo", "Festo", "Pneumatics", "Fitting", 0),
    # Tools
    ("Drill Bit Set Industrial HSS-G - Bosch", "Bosch", "Tools", "Drill Bits", 1),
    ("Drill DCD996 Brushless Hammer - DeWalt", "DeWalt", "Tools", "Drills", 0),
    ("Drill DHP482 Cordless Hammer Driver - Makita", "Makita", "Tools", "Drills", 0),
    ("Multimeter 117 True RMS - Fluke", "Fluke", "Tools", "Test Equipment", 0),
    ("Impact Wrench M18 FUEL - Milwaukee", "Milwaukee", "Tools", "Wrenches", 0),
]
assert len(SAFETY) == 40 and len(SPARES) == 60, (len(SAFETY), len(SPARES))

rows, bad = [], []
for i, (grp, tag) in enumerate(((SAFETY, "SAF"), (SPARES, None)), 1):
    for n, (name, mfr, cat, sub, verify) in enumerate(grp, 1):
        status, why = ok(name, mfr)
        if status != "PURE":
            bad.append((name, status, why))
        t = tag or {"VFD": "VFD", "PLC": "PLC", "HMI": "HMI", "Bearing": "BRG", "V-Belt": "BLT", "Timing Belt": "BLT",
                    "Conveyor Belt": "BLT", "Valve": "VLV", "Pump": "PMP", "Motor": "MTR", "Sensor": "SEN",
                    "Contactor": "ELC", "Circuit Breaker": "ELC", "Relay": "ELC", "Terminal": "ELC",
                    "Cylinder": "PNE", "Hydraulic Hose": "PNE", "Fitting": "PNE"}.get(sub, "TLS")
        rows.append([f"IND-{t}-{len(rows)+1:03d}", name, mfr, cat, sub, "", 0, status,
                     "UNSOURCED - supplier quote needed" + ("; VERIFY brand/model pairing" if verify else "")])
if bad:
    print("FAILED STRICT FILTER:", *bad, sep="\n  ")
    sys.exit(1)
with open("industrial-seed-100.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["SKU", "ProductName", "Manufacturer", "Category", "SubCategory", "PriceUSD", "Stock", "Status", "SourceNote"])
    w.writerows(rows)
print(len(rows), "rows written; all PURE;", sum("VERIFY" in r[-1] for r in rows), "flagged VERIFY")
