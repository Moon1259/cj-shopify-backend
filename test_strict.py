from industrial_strict import industrial_ok_strict_v2 as f

CASES = [
    # (name, manufacturer, source, expected status)
    ("Fashion Men Belt Leather", "", None, "BLOCKED"),
    ("Boho Brown Cotton Rope Woven Waist Belt", "", None, "BLOCKED"),
    ("Rose-red Garter Belt And Stocking Set Sexy Lingerie", "", None, "BLOCKED"),
    ("Women's Trench Coat", "", None, "BLOCKED"),
    ("Dog Car Seat Belt", "", None, "BLOCKED"),
    ("Belt Tensioner Kit for Pontiac", "", None, "BLOCKED"),            # user's rule: 'belt' without allowed type
    ("Mini Electric Belt Sander", "", None, "BLOCKED"),                 # same rule (flagged in the answer)
    ("V-Belt B Type 1000mm - Gates", "Gates", None, "PURE"),
    ("Timing Belt Synchroflex T10 - ContiTech", "ContiTech", None, "PURE"),
    ("Conveyor Belt Industrial PVC - ContiTech", "ContiTech", None, "PURE"),
    ("Optibelt Super TX V-Belt", "Optibelt", None, "PURE"),             # brand contains 'belt' but is not the word
    ("VFD 5.5kW", "", None, "INCOMPLETE"),
    ("VFD 5.5kW ACS880-01", "NoName", None, "INCOMPLETE"),
    ("VFD 5.5kW ACS880-01", "ABB", None, "INCOMPLETE"),                 # brand not in the product name
    ("VFD 5.5kW ACS880-01 - ABB", "ABB", None, "PURE"),
    ("Bearing 6205", "", None, "INCOMPLETE"),
    ("Ball Valve 1 inch Stainless", "", None, "INCOMPLETE"),
    ("VFD 5.5kW ACS880-01 - ABB", "ABB", "cj", "BRAND_RISK"),           # CJ does not sell genuine ABB
    ("Safety Helmet Hard Hat White - 3M", "3M", None, "PURE"),
    ("Steel Toe Boots Pit Boss - Timberland PRO", "Timberland PRO", None, "PURE"),
    ("Hi-Vis Jacket Waterproof - Portwest", "Portwest", None, "PURE"),
    ("Scented Candle Gift Set", "", None, "BLOCKED"),
]
bad = 0
for name, m, src, want in CASES:
    got, why = f(name, m, src)
    bad += got != want
    print("OK  " if got == want else "FAIL", f"{got:10}", why, "|", name)
assert not bad, f"{bad} failures"
print("ALL STRICT TESTS PASS")
