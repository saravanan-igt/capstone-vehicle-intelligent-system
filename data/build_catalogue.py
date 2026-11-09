"""Builds the SYNTHETIC vehicle catalogue: structured data (data/raw) and brochure documents (data/documents/vehicles).

    python data/build_catalogue.py

All makes, models, prices and specifications are fictional and were authored for this capstone. On-road
components follow simple synthetic rates (registration 10% in IN-MH, 13% in IN-KA, 1% for electric vehicles;
insurance 4%; other charges INR 15,000). Two deliberate data-quality cases are kept for testing: Lumen Pulse Standard has no insurance quote
(on-road cost unverifiable) and Lumen Pulse Turbo has a stale price (2025-01-15)."""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
BROCHURES = ROOT / "documents" / "vehicles"
SOURCE = "Synthetic Catalogue v2026-10 (capstone)"
PRICE_DATE = "2026-10-01"
REG_RATE = {"IN-MH": 0.10, "IN-KA": 0.13}

# (key, make, model, body, category, overview, features, warranty, service, colours, dimensions, variants)
# variant: (id, name, fuel, transmission, seating, ex_showroom, specs, regions, extra_features, overrides)
MODELS = [
    ("aurora-breeze", "Aurora", "Breeze", "hatchback", "private",
     "The Breeze is Aurora's city hatchback: light controls, a tight turning circle and low running costs for "
     "first-time owners and daily commuters.",
     ["7-inch touchscreen with smartphone mirroring", "Rear parking sensors", "ISOFIX child-seat mounts",
      "Electronic stability control"],
     "3 years / 1,00,000 km", "Every 10,000 km or 12 months", ["Arctic White", "Sunset Red", "Graphite Grey"],
     {"length_mm": 3845, "width_mm": 1735, "height_mm": 1530, "wheelbase_mm": 2450, "turning_radius_m": 4.8},
     [("aur-breeze-lxi", "LXi", "petrol", "manual", 5, 650000,
       {"engine_cc": 1197, "power_kw": 61, "claimed_efficiency": "20.1 km/l", "airbags": 6, "boot_litres": 268},
       ["IN-MH", "IN-KA"], ["Manual air conditioning", "Steel wheels with covers"], {}),
      ("aur-breeze-zxi-amt", "ZXi AMT", "petrol", "automatic", 5, 780000,
       {"engine_cc": 1197, "power_kw": 61, "claimed_efficiency": "19.4 km/l", "airbags": 6, "boot_litres": 268},
       ["IN-MH"], ["Automatic climate control", "15-inch alloy wheels", "Push-button start"], {})]),
    ("aurora-vista", "Aurora", "Vista", "sedan", "private",
     "The Vista is a roomy three-box sedan with a 480-litre boot, aimed at families who want comfort on long "
     "highway drives.",
     ["9-inch touchscreen", "Rear AC vents", "Cruise control", "Hill-hold assist"],
     "3 years / 1,00,000 km", "Every 10,000 km or 12 months", ["Pearl White", "Midnight Blue", "Silver"],
     {"length_mm": 4490, "width_mm": 1765, "height_mm": 1485, "wheelbase_mm": 2650},
     [("aur-vista-sx", "SX", "petrol", "manual", 5, 1150000,
       {"engine_cc": 1497, "power_kw": 85, "claimed_efficiency": "18.0 km/l", "airbags": 6, "boot_litres": 480},
       ["IN-MH", "IN-KA"], ["LED projector headlamps"], {}),
      ("aur-vista-sxo-cvt", "SX(O) CVT", "petrol", "automatic", 5, 1390000,
       {"engine_cc": 1497, "power_kw": 85, "claimed_efficiency": "17.2 km/l", "airbags": 6, "boot_litres": 480},
       ["IN-MH"], ["Electric sunroof", "Ventilated front seats", "360-degree camera"], {})]),
    ("aurora-nano", "Aurora", "Nano Plus", "hatchback", "private",
     "The Nano Plus is the most affordable Aurora: a compact four-door hatchback designed for narrow city "
     "streets and easy parking.",
     ["Dual front airbags", "ABS with EBD", "Bluetooth audio"],
     "2 years / 40,000 km", "Every 10,000 km or 12 months", ["Solid White", "Lemon Yellow"],
     {"length_mm": 3495, "width_mm": 1515, "height_mm": 1560, "wheelbase_mm": 2380, "turning_radius_m": 4.5},
     [("aur-nano-std", "STD", "petrol", "manual", 4, 460000,
       {"engine_cc": 998, "power_kw": 49, "claimed_efficiency": "24.4 km/l", "airbags": 2, "boot_litres": 214},
       ["IN-MH", "IN-KA"], [], {}),
      ("aur-nano-vxi", "VXi", "petrol", "manual", 4, 540000,
       {"engine_cc": 998, "power_kw": 49, "claimed_efficiency": "24.1 km/l", "airbags": 2, "boot_litres": 214},
       ["IN-MH"], ["Power windows (front and rear)", "Central locking"], {})]),
    ("aurora-quest", "Aurora", "Quest", "suv", "private",
     "The Quest is a compact SUV with a factory-fitted CNG option, built for buyers who want SUV styling with "
     "very low fuel costs.",
     ["8-inch touchscreen", "Reverse camera", "Roof rails", "Tyre pressure monitoring"],
     "3 years / 1,00,000 km", "Every 10,000 km or 12 months", ["Glacier White", "Forest Green", "Grey"],
     {"length_mm": 3995, "width_mm": 1790, "height_mm": 1640, "wheelbase_mm": 2500, "ground_clearance_mm": 200},
     [("aur-quest-cng", "S-CNG", "cng", "manual", 5, 990000,
       {"engine_cc": 1462, "power_kw": 64, "claimed_efficiency": "25.5 km/kg", "airbags": 6, "boot_litres": 120},
       ["IN-MH"], ["Twin CNG cylinders under the boot floor"], {}),
      ("aur-quest-zxi-at", "ZXi AT", "petrol", "automatic", 5, 1240000,
       {"engine_cc": 1462, "power_kw": 75, "claimed_efficiency": "19.8 km/l", "airbags": 6, "boot_litres": 328},
       ["IN-MH", "IN-KA"], ["Head-up display", "Wireless phone charger"], {})]),
    ("kestrel-trail", "Kestrel", "Trail", "suv", "private",
     "The Trail is a body-on-frame SUV with strong low-end torque and generous ground clearance for rough "
     "roads; the X 4x4 adds a third row and low-range transfer case.",
     ["10-inch touchscreen", "Hill-descent control", "Terrain modes", "LED headlamps"],
     "3 years / unlimited km", "Every 15,000 km or 12 months", ["Everest White", "Napoli Black", "Red Rage"],
     {"length_mm": 4395, "width_mm": 1820, "height_mm": 1844, "wheelbase_mm": 2750},
     [("kes-trail-s", "S", "diesel", "manual", 5, 1680000,
       {"engine_cc": 1493, "power_kw": 85, "claimed_efficiency": "19.1 km/l", "airbags": 6,
        "ground_clearance_mm": 205}, ["IN-MH", "IN-KA"], [], {}),
      ("kes-trail-x-4x4", "X 4x4", "diesel", "automatic", 7, 2450000,
       {"engine_cc": 2184, "power_kw": 128, "claimed_efficiency": "14.8 km/l", "airbags": 6,
        "ground_clearance_mm": 226}, ["IN-MH"], ["Low-range 4x4 transfer case", "Third-row seats"], {})]),
    ("kestrel-volt", "Kestrel", "Volt", "suv", "private",
     "The Volt is Kestrel's electric compact SUV with a 45 kWh battery and DC fast charging from 10 to 80 "
     "percent in about 56 minutes on a 60 kW charger.",
     ["Connected-car app", "Regenerative braking with paddles", "Vehicle-to-load socket", "Air purifier"],
     "3 years / 1,25,000 km; battery 8 years / 1,60,000 km", "Every 15,000 km or 12 months",
     ["Pristine White", "Oxide Blue"],
     {"length_mm": 4200, "width_mm": 1800, "height_mm": 1600, "wheelbase_mm": 2600},
     [("kes-volt-ev", "Long Range", "electric", "automatic", 5, 1890000,
       {"battery_kwh": 45, "power_kw": 110, "claimed_range_km": 465, "airbags": 6, "dc_fast_charge_kw": 60},
       ["IN-MH"], [], {})]),
    ("kestrel-ridge", "Kestrel", "Ridge", "suv", "private",
     "The Ridge is a sub-four-metre SUV with a turbo-petrol option and a five-star synthetic crash rating, "
     "popular with young families upgrading from a hatchback.",
     ["7-inch touchscreen", "Rear camera", "Six airbags as standard", "Electronic stability control"],
     "3 years / 1,00,000 km", "Every 10,000 km or 12 months", ["Daytona Grey", "Flame Red", "Pure White"],
     {"length_mm": 3995, "width_mm": 1804, "height_mm": 1620, "wheelbase_mm": 2498, "ground_clearance_mm": 208},
     [("kes-ridge-e", "E", "petrol", "manual", 5, 890000,
       {"engine_cc": 1199, "power_kw": 65, "claimed_efficiency": "17.4 km/l", "airbags": 6, "boot_litres": 382},
       ["IN-MH", "IN-KA"], [], {}),
      ("kes-ridge-s", "S", "petrol", "manual", 5, 1020000,
       {"engine_cc": 1199, "power_kw": 65, "claimed_efficiency": "17.4 km/l", "airbags": 6, "boot_litres": 382},
       ["IN-MH"], ["Electric sunroof", "Auto headlamps"], {}),
      ("kes-ridge-s-turbo-at", "S Turbo DCT", "petrol", "automatic", 5, 1210000,
       {"engine_cc": 1199, "power_kw": 88, "claimed_efficiency": "16.2 km/l", "airbags": 6, "boot_litres": 382},
       ["IN-MH"], ["Paddle shifters", "Ventilated seats"], {})]),
    ("vanta-city", "Vanta", "City", "hatchback", "private",
     "The City E is a four-seat electric city car with a 26 kWh battery, intended for short urban commutes "
     "with home overnight charging.",
     ["Remote charging schedule via app", "Single-pedal driving mode"],
     "3 years / 1,00,000 km; battery 8 years / 1,20,000 km", "Every 15,000 km or 12 months", ["Mint", "White"],
     {"length_mm": 3600, "width_mm": 1650, "height_mm": 1575, "wheelbase_mm": 2350},
     [("van-city-e", "E", "electric", "automatic", 4, 990000,
       {"battery_kwh": 26, "power_kw": 55, "claimed_range_km": 315, "airbags": 2},
       ["IN-MH", "IN-KA"], ["7.2 kW AC wall-box included"], {})]),
    ("vanta-spark", "Vanta", "Spark EV", "hatchback", "private",
     "The Spark EV is Vanta's lowest-priced five-seat electric hatchback with a 30 kWh battery and support "
     "for 50 kW DC fast charging.",
     ["Connected-car telematics", "Rear parking camera", "Auto climate control"],
     "3 years / 1,00,000 km; battery 8 years / 1,60,000 km", "Every 15,000 km or 12 months",
     ["Electric Blue", "Snow White", "Charcoal"],
     {"length_mm": 3770, "width_mm": 1677, "height_mm": 1536, "wheelbase_mm": 2400},
     [("van-spark-ev-mr", "Medium Range", "electric", "automatic", 5, 790000,
       {"battery_kwh": 25, "power_kw": 45, "claimed_range_km": 250, "airbags": 2, "dc_fast_charge_kw": 50},
       ["IN-MH"], [], {}),
      ("van-spark-ev-lr", "Long Range", "electric", "automatic", 5, 920000,
       {"battery_kwh": 30, "power_kw": 55, "claimed_range_km": 320, "airbags": 6, "dc_fast_charge_kw": 50},
       ["IN-MH", "IN-KA"], ["Six airbags"], {})]),
    ("vanta-prime", "Vanta", "Prime", "sedan", "private",
     "The Prime GT Hybrid is an executive sedan pairing a 2.0-litre petrol engine with an electric motor for "
     "strong economy in city traffic.",
     ["12.3-inch digital cluster", "Adaptive cruise control", "Lane-keep assist", "Premium 10-speaker audio"],
     "3 years / unlimited km; hybrid battery 8 years / 1,60,000 km", "Every 10,000 km or 12 months",
     ["Platinum White", "Attitude Black"],
     {"length_mm": 4885, "width_mm": 1840, "height_mm": 1445, "wheelbase_mm": 2825},
     [("van-prime-gt", "GT Hybrid", "hybrid", "automatic", 5, 3200000,
       {"engine_cc": 1987, "power_kw": 137, "claimed_efficiency": "23.2 km/l", "airbags": 8},
       ["IN-MH"], [], {})]),
    ("vanta-atlas", "Vanta", "Atlas", "mpv", "private",
     "The Atlas is a seven-seat MPV with sliding second-row seats and a flat third row, built for large "
     "families and airport transfers.",
     ["Roof-mounted rear AC", "Captain-style second row", "Rear camera"],
     "2 years / 40,000 km", "Every 10,000 km or 12 months", ["Silky Silver", "Pearl White"],
     {"length_mm": 4395, "width_mm": 1735, "height_mm": 1690, "wheelbase_mm": 2740},
     [("van-atlas-7", "7-Seater", "petrol", "manual", 7, 1550000,
       {"engine_cc": 1462, "power_kw": 75, "claimed_efficiency": "17.5 km/l", "airbags": 4},
       ["IN-MH"], [], {})]),
    ("orion-hauler", "Orion", "Hauler", "van", "commercial",
     "The Hauler Cargo is a two-seat panel van with a 1,000 kg payload for small businesses and last-mile "
     "delivery. It is a commercial vehicle.",
     ["Partition wall", "Sliding side door", "Rear barn doors"],
     "2 years / 72,000 km", "Every 10,000 km or 6 months", ["White"],
     {"length_mm": 4500, "width_mm": 1700, "height_mm": 1940},
     [("ori-hauler-cargo", "Cargo", "diesel", "manual", 2, 1250000,
       {"engine_cc": 1499, "payload_kg": 1000, "airbags": 2}, ["IN-MH"], [], {})]),
    ("orion-metro", "Orion", "Metro", "hatchback", "private",
     "The Metro CNG is a frugal hatchback with a factory CNG kit, one of the cheapest cars to run per "
     "kilometre in the catalogue.",
     ["Dual-fuel switch", "Bluetooth audio", "Rear defogger"],
     "2 years / 40,000 km", "Every 10,000 km or 12 months", ["White", "Grey"],
     {"length_mm": 3700, "width_mm": 1620, "height_mm": 1560},
     [("ori-metro-cng", "CNG", "cng", "manual", 5, 720000,
       {"engine_cc": 998, "power_kw": 42, "claimed_efficiency": "32.7 km/kg", "airbags": 2},
       ["IN-MH"], [], {})]),
    ("orion-pickup", "Orion", "Ridgeback Pickup", "van", "commercial",
     "The Ridgeback is a single-cab pickup with a 1,250 kg payload and a 2,550 mm cargo bed for "
     "agricultural and construction work. It is registered as a commercial vehicle.",
     ["Tow hook", "Rubber floor mats", "Load-sensing rear brakes"],
     "3 years / 1,00,000 km", "Every 10,000 km or 6 months", ["White", "Silver"],
     {"length_mm": 5215, "width_mm": 1775, "height_mm": 1830},
     [("ori-ridgeback", "Single Cab", "diesel", "manual", 2, 1050000,
       {"engine_cc": 2523, "payload_kg": 1250, "airbags": 2}, ["IN-MH"], [], {})]),
    ("lumen-pulse", "Lumen", "Pulse", "suv", "private",
     "The Pulse is a compact crossover. The Standard variant's insurance quote is not yet available and the "
     "Turbo price list is from January 2025, so both must be re-verified with the dealer.",
     ["8-inch touchscreen", "Rear camera"],
     "3 years / 1,00,000 km", "Every 10,000 km or 12 months", ["Ice White", "Copper"],
     {"length_mm": 3990, "width_mm": 1760, "height_mm": 1605},
     [("lum-pulse", "Standard", "petrol", "manual", 5, 980000,
       {"engine_cc": 1199, "power_kw": 66, "claimed_efficiency": "18.6 km/l", "airbags": 6},
       ["IN-MH"], [], {"insurance": None}),
      ("lum-pulse-turbo", "Turbo", "petrol", "automatic", 5, 1210000,
       {"engine_cc": 999, "power_kw": 88, "claimed_efficiency": "17.0 km/l", "airbags": 6},
       ["IN-MH"], [], {"price_date": "2025-01-15"})]),
    ("lumen-glide", "Lumen", "Glide", "sedan", "private",
     "The Glide is a compact sedan offered with petrol and CNG, with a 378-litre boot even in the CNG version "
     "thanks to an underfloor tank.",
     ["7-inch touchscreen", "Rear AC vents", "Steering-mounted controls"],
     "3 years / 1,00,000 km", "Every 10,000 km or 12 months", ["White", "Maroon", "Blue"],
     {"length_mm": 3995, "width_mm": 1735, "height_mm": 1515, "wheelbase_mm": 2450},
     [("lum-glide-s-cng", "S CNG", "cng", "manual", 5, 840000,
       {"engine_cc": 1197, "power_kw": 57, "claimed_efficiency": "31.1 km/kg", "airbags": 6, "boot_litres": 378},
       ["IN-MH"], [], {}),
      ("lum-glide-vx", "VX", "petrol", "manual", 5, 760000,
       {"engine_cc": 1197, "power_kw": 66, "claimed_efficiency": "20.0 km/l", "airbags": 6, "boot_litres": 416},
       ["IN-MH", "IN-KA"], ["Cruise control"], {})]),
    ("zephyr-grand", "Zephyr", "Grand", "suv", "private",
     "The Grand Signature is a full-size luxury SUV with air suspension and seven seats.",
     ["Air suspension", "Panoramic sunroof", "Four-zone climate control", "Massage front seats"],
     "4 years / unlimited km", "Every 20,000 km or 12 months", ["Obsidian Black", "Polar White"],
     {"length_mm": 5060, "width_mm": 2000, "height_mm": 1830, "wheelbase_mm": 3000},
     [("zep-grand", "Signature", "diesel", "automatic", 7, 6200000,
       {"engine_cc": 2993, "power_kw": 195, "claimed_efficiency": "12.4 km/l", "airbags": 9},
       ["IN-MH"], [], {})]),
    ("zephyr-coupe", "Zephyr", "Coupe", "coupe", "private",
     "The Coupe Performance is a four-seat grand tourer with a twin-turbo six-cylinder engine.",
     ["Adaptive dampers", "Launch control", "Carbon-ceramic brakes"],
     "4 years / unlimited km", "Every 15,000 km or 12 months", ["Racing Yellow", "Black"],
     {"length_mm": 4720, "width_mm": 1900, "height_mm": 1370},
     [("zep-coupe", "Performance", "petrol", "automatic", 4, 8500000,
       {"engine_cc": 2998, "power_kw": 285, "claimed_efficiency": "9.8 km/l", "airbags": 8},
       ["IN-MH"], [], {})]),
    ("zephyr-executive", "Zephyr", "Executive", "sedan", "private",
     "The Executive is a long-wheelbase luxury sedan with rear-seat business-class comfort.",
     ["Rear reclining seats", "Ambient lighting", "Burmester-style 15-speaker audio", "Level 2 ADAS"],
     "4 years / unlimited km", "Every 20,000 km or 12 months", ["Selenite Grey", "White"],
     {"length_mm": 5180, "width_mm": 1950, "height_mm": 1470, "wheelbase_mm": 3215},
     [("zep-executive-450", "450 Premium", "petrol", "automatic", 5, 4800000,
       {"engine_cc": 1999, "power_kw": 190, "claimed_efficiency": "13.5 km/l", "airbags": 8},
       ["IN-MH"], [], {})]),
    ("halcyon-terra", "Halcyon", "Terra", "suv", "private",
     "The Terra is a mid-size five-seat SUV with a 1.5-litre diesel and Level 1 driver assistance.",
     ["10.25-inch touchscreen", "Panoramic sunroof", "Forward collision warning", "Powered driver seat"],
     "3 years / 1,00,000 km", "Every 10,000 km or 12 months", ["Abyss Black", "Titan Grey", "Fiery Red"],
     {"length_mm": 4330, "width_mm": 1790, "height_mm": 1635, "wheelbase_mm": 2610, "ground_clearance_mm": 190},
     [("hal-terra-pro", "Pro", "diesel", "manual", 5, 1350000,
       {"engine_cc": 1493, "power_kw": 85, "claimed_efficiency": "21.0 km/l", "airbags": 6, "boot_litres": 433},
       ["IN-MH", "IN-KA"], [], {}),
      ("hal-terra-pro-plus-at", "Pro+ AT", "diesel", "automatic", 5, 1620000,
       {"engine_cc": 1493, "power_kw": 85, "claimed_efficiency": "18.5 km/l", "airbags": 6, "boot_litres": 433},
       ["IN-MH"], ["Level 2 ADAS", "Ventilated seats", "Bose-style 8-speaker audio"], {})]),
    ("halcyon-family", "Halcyon", "Family", "mpv", "private",
     "The Family is a seven-seat MPV with sliding rear doors, aimed at buyers who need easy third-row access.",
     ["Sliding rear doors", "Rear sunshades", "Second-row USB-C ports"],
     "3 years / 1,00,000 km", "Every 10,000 km or 12 months", ["White", "Bronze"],
     {"length_mm": 4500, "width_mm": 1775, "height_mm": 1750, "wheelbase_mm": 2780},
     [("hal-family-7", "7-Seater", "petrol", "manual", 7, 1120000,
       {"engine_cc": 1497, "power_kw": 77, "claimed_efficiency": "16.8 km/l", "airbags": 6, "boot_litres": 216},
       ["IN-MH"], [], {})]),
    ("nimbus-cruze", "Nimbus", "Cruze", "hatchback", "private",
     "The Cruze is a premium hatchback with a large cabin, a 339-litre boot and a strong safety package.",
     ["9-inch touchscreen", "Wireless smartphone mirroring", "Rear camera", "LED DRLs"],
     "3 years / 1,00,000 km", "Every 10,000 km or 12 months", ["Nexa Blue", "Splendid Silver"],
     {"length_mm": 3990, "width_mm": 1745, "height_mm": 1500, "wheelbase_mm": 2520},
     [("nim-cruze-zeta", "Zeta", "petrol", "manual", 5, 840000,
       {"engine_cc": 1197, "power_kw": 66, "claimed_efficiency": "22.4 km/l", "airbags": 6, "boot_litres": 339},
       ["IN-MH", "IN-KA"], [], {}),
      ("nim-cruze-alpha-at", "Alpha AT", "petrol", "automatic", 5, 960000,
       {"engine_cc": 1197, "power_kw": 66, "claimed_efficiency": "22.9 km/l", "airbags": 6, "boot_litres": 339},
       ["IN-MH"], ["Head-up display", "360-degree camera"], {})]),
    ("nimbus-arc", "Nimbus", "Arc", "sedan", "private",
     "The Arc is a compact diesel sedan focused on highway economy and low maintenance cost.",
     ["Cruise control", "Rear AC vents", "Auto-dimming mirror"],
     "3 years / 1,00,000 km", "Every 15,000 km or 12 months", ["White", "Grey"],
     {"length_mm": 3995, "width_mm": 1735, "height_mm": 1505},
     [("nim-arc-d", "D", "diesel", "manual", 5, 960000,
       {"engine_cc": 1498, "power_kw": 74, "claimed_efficiency": "24.7 km/l", "airbags": 6, "boot_litres": 420},
       ["IN-MH"], [], {})]),
    ("solace-hybrid", "Solace", "Hybrid", "sedan", "private",
     "The Solace Hybrid is a mid-size sedan with a self-charging strong-hybrid system and very high claimed "
     "efficiency.",
     ["Electric-only drive mode in traffic", "Head-up display", "Level 2 ADAS"],
     "3 years / 1,00,000 km; hybrid battery 8 years / 1,60,000 km", "Every 10,000 km or 12 months",
     ["Pearl White", "Meteoroid Grey"],
     {"length_mm": 4550, "width_mm": 1748, "height_mm": 1475, "wheelbase_mm": 2650},
     [("sol-hybrid-zx", "ZX e-HEV", "hybrid", "automatic", 5, 1950000,
       {"engine_cc": 1498, "power_kw": 93, "claimed_efficiency": "27.1 km/l", "airbags": 6, "boot_litres": 410},
       ["IN-MH", "IN-KA"], [], {})]),
    ("terra-volt-max", "Terra", "Volt Max", "suv", "private",
     "The Volt Max is a mid-size electric SUV with a 60 kWh battery and 150 kW DC fast charging.",
     ["Panoramic glass roof", "Vehicle-to-load", "Level 2 ADAS", "Over-the-air updates"],
     "3 years / 1,25,000 km; battery 8 years / 1,60,000 km", "Every 15,000 km or 12 months",
     ["Pristine White", "Empowered Oxide"],
     {"length_mm": 4500, "width_mm": 1860, "height_mm": 1640, "wheelbase_mm": 2700},
     [("ter-voltmax-lr", "Long Range", "electric", "automatic", 5, 2400000,
       {"battery_kwh": 60, "power_kw": 150, "claimed_range_km": 520, "airbags": 6, "dc_fast_charge_kw": 150},
       ["IN-MH"], [], {})]),
    ("terra-compact", "Terra", "Compact", "suv", "private",
     "The Compact is an entry SUV with a turbo-petrol engine and a five-star synthetic safety rating.",
     ["Six airbags", "Electronic stability control", "Reverse camera"],
     "3 years / 1,00,000 km", "Every 10,000 km or 12 months", ["Red", "White"],
     {"length_mm": 3995, "width_mm": 1790, "height_mm": 1620, "ground_clearance_mm": 209},
     [("ter-compact-mt", "MT", "petrol", "manual", 5, 820000,
       {"engine_cc": 1199, "power_kw": 88, "claimed_efficiency": "17.0 km/l", "airbags": 6, "boot_litres": 350},
       ["IN-MH"], [], {})]),
]


def _price(ex_showroom: int, region: str, fuel: str, overrides: dict) -> dict:
    reg_rate = 0.01 if fuel == "electric" else REG_RATE[region]  # synthetic EV registration concession
    row = {"region": region, "ex_showroom": str(ex_showroom),
           "registration": str(round(ex_showroom * reg_rate)),
           "insurance": str(round(ex_showroom * 0.04)), "other_charges": "15000", "price_date": PRICE_DATE}
    for key, value in overrides.items():
        row[key] = value
    return row


def build() -> dict:
    vehicles = []
    for key, make, model, body, category, overview, features, warranty, service, colours, dims, variants in MODELS:
        for vid, name, fuel, transmission, seats, price, specs, regions, extra, overrides in variants:
            vehicles.append({
                "id": vid, "model_key": key, "make": make, "model": model, "variant": name, "body_type": body,
                "fuel_type": fuel, "category": category, "transmission": transmission, "seating": seats,
                "specs": {**specs, **dims, "features": features + extra, "warranty": warranty,
                          "service_interval": service, "colours": colours},
                "brochure": f"data/documents/vehicles/{key}.md",
                "prices": [_price(price, r, fuel, overrides) for r in regions],
            })
    return {"_note": "SYNTHETIC catalogue. Makes and models are fictional; prices are illustrative and not market "
                     "data.", "source": SOURCE, "vehicles": vehicles}


def _fmt_inr(value: int) -> str:
    s = str(value)
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + parts + [tail])


def brochure(entry: tuple) -> str:
    key, make, model, body, category, overview, features, warranty, service, colours, dims, variants = entry
    lines = [f"# {make} {model} brochure (synthetic)", "", f"Model key: {key}. Body type: {body}. Use: {category}.",
             "", "## Overview", "", overview, "", "## Variants and prices", ""]
    for vid, name, fuel, transmission, seats, price, specs, regions, extra, overrides in variants:
        eff = specs.get("claimed_efficiency") or (f"{specs['claimed_range_km']} km claimed range"
                                                 if "claimed_range_km" in specs else "not stated")
        engine = (f"{specs['engine_cc']} cc" if "engine_cc" in specs
                  else f"{specs['battery_kwh']} kWh battery" if "battery_kwh" in specs else "not stated")
        power = f"{specs['power_kw']} kW" if "power_kw" in specs else "not stated"
        lines.append(f"- {name} (vehicle id {vid}): {fuel}, {transmission}, {seats} seats, {engine}, {power}, "
                     f"efficiency {eff}, {specs.get('airbags', 'n/a')} airbags. Ex-showroom price in Maharashtra "
                     f"INR {_fmt_inr(price)}." + (f" Adds: {'; '.join(extra)}." if extra else ""))
    lines += ["", "## Key features", ""] + [f"- {f}" for f in features]
    lines += ["", "## Dimensions", ""] + [f"- {k.replace('_', ' ')}: {v}" for k, v in dims.items()]
    lines += ["", "## Warranty and service", "", f"Standard warranty: {warranty}. Scheduled service: {service}.",
              "", "## Colours", "", ", ".join(colours) + ".", "",
              "## Notes", "", "Prices are synthetic and indicative. On-road price adds registration, insurance and "
              "other mandatory charges, which vary by state. Confirm the final quotation with the dealer.", ""]
    return "\n".join(lines)


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    BROCHURES.mkdir(parents=True, exist_ok=True)
    catalogue = build()
    (RAW / "vehicles.json").write_text(json.dumps(catalogue, indent=2, ensure_ascii=False) + "\n", "utf-8")
    with (RAW / "vehicles.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "make", "model", "variant", "body_type", "fuel_type", "category", "transmission",
                         "seating", "region", "ex_showroom", "registration", "insurance", "other_charges",
                         "price_date", "engine_cc", "battery_kwh", "power_kw", "claimed_efficiency",
                         "claimed_range_km", "airbags"])
        for v in catalogue["vehicles"]:
            for p in v["prices"]:
                s = v["specs"]
                writer.writerow([v["id"], v["make"], v["model"], v["variant"], v["body_type"], v["fuel_type"],
                                 v["category"], v["transmission"], v["seating"], p["region"], p["ex_showroom"],
                                 p["registration"], p["insurance"], p["other_charges"], p["price_date"],
                                 s.get("engine_cc"), s.get("battery_kwh"), s.get("power_kw"),
                                 s.get("claimed_efficiency"), s.get("claimed_range_km"), s.get("airbags")])
    for entry in MODELS:
        (BROCHURES / f"{entry[0]}.md").write_text(brochure(entry), "utf-8")
    print(json.dumps({"models": len(MODELS), "variants": len(catalogue["vehicles"]), "brochures": len(MODELS)}))


if __name__ == "__main__":
    main()
