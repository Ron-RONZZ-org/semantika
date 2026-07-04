"""Seed data for unit ontology type hierarchy and default SI units.

Ported from A-semantika's ``_unit_seed_data.py`` with EO→EN migration.
"""

from __future__ import annotations

# ── Unit type hierarchy ─────────────────────────────────────────────────

UNIT_TYPE_NODES: list[dict] = [
    {
        "node_id": ":UnitType",
        "labels": {"en": "Unit type", "eo": "Unuotipo"},
        "parent_type": None,
    },
    {
        "node_id": ":SingularUnit",
        "labels": {"en": "Singular unit", "eo": "Baza unuo"},
        "parent_type": ":UnitType",
    },
    {
        "node_id": ":PrefixedUnit",
        "labels": {"en": "Prefixed unit", "eo": "Prefiksita unuo"},
        "parent_type": ":UnitType",
        "also_type": ":SingularUnit",
    },
    {
        "node_id": ":CompoundUnit",
        "labels": {"en": "Compound unit", "eo": "Kombinita unuo"},
        "parent_type": ":UnitType",
    },
    {
        "node_id": ":UnitProduct",
        "labels": {"en": "Unit product", "eo": "Unuoprodukto"},
        "parent_type": ":CompoundUnit",
    },
    {
        "node_id": ":UnitPower",
        "labels": {"en": "Unit power", "eo": "Unuopotenco"},
        "parent_type": ":CompoundUnit",
    },
]

# ── SI base units ────────────────────────────────────────────────────────

SI_BASE_UNITS: list[dict] = [
    {"node_id": "unit:METER",  "labels": {"en": "meter", "eo": "metro"},  "symbol": "m",  "ucum": "m"},
    {"node_id": "unit:KILOGRAM", "labels": {"en": "kilogram", "eo": "kilogramo"}, "symbol": "kg", "ucum": "kg"},
    {"node_id": "unit:SECOND", "labels": {"en": "second", "eo": "sekundo"}, "symbol": "s",  "ucum": "s"},
    {"node_id": "unit:AMPERE", "labels": {"en": "ampere", "eo": "ampero"}, "symbol": "A",  "ucum": "A"},
    {"node_id": "unit:KELVIN", "labels": {"en": "kelvin", "eo": "kelvino"}, "symbol": "K",  "ucum": "K"},
    {"node_id": "unit:MOLE",   "labels": {"en": "mole", "eo": "molo"}, "symbol": "mol", "ucum": "mol"},
    {"node_id": "unit:CANDELA","labels": {"en": "candela", "eo": "kandelo"}, "symbol": "cd", "ucum": "cd"},
]

# ── Named derived SI units ──────────────────────────────────────────────

DERIVED_UNITS: list[dict] = [
    {"node_id": "unit:RADIAN",         "labels": {"en": "radian", "eo": "radiano"},         "symbol": "rad", "ucum": "rad"},
    {"node_id": "unit:STERADIAN",      "labels": {"en": "steradian", "eo": "steradiano"},   "symbol": "sr",  "ucum": "sr"},
    {"node_id": "unit:HERTZ",          "labels": {"en": "hertz", "eo": "herco"},            "symbol": "Hz",  "ucum": "Hz"},
    {"node_id": "unit:NEWTON",         "labels": {"en": "newton", "eo": "neŭtono"},         "symbol": "N",   "ucum": "N"},
    {"node_id": "unit:PASCAL",         "labels": {"en": "pascal", "eo": "paskalo"},         "symbol": "Pa",  "ucum": "Pa"},
    {"node_id": "unit:JOULE",          "labels": {"en": "joule", "eo": "ĵulo"},             "symbol": "J",   "ucum": "J"},
    {"node_id": "unit:WATT",           "labels": {"en": "watt", "eo": "vato"},              "symbol": "W",   "ucum": "W"},
    {"node_id": "unit:COULOMB",        "labels": {"en": "coulomb", "eo": "kulombo"},        "symbol": "C",   "ucum": "C"},
    {"node_id": "unit:VOLT",           "labels": {"en": "volt", "eo": "volto"},             "symbol": "V",   "ucum": "V"},
    {"node_id": "unit:FARAD",          "labels": {"en": "farad", "eo": "farado"},           "symbol": "F",   "ucum": "F"},
    {"node_id": "unit:OHM",            "labels": {"en": "ohm", "eo": "omo"},                "symbol": "Ω",   "ucum": "Ohm"},
    {"node_id": "unit:SIEMENS",        "labels": {"en": "siemens", "eo": "simenso"},        "symbol": "S",   "ucum": "S"},
    {"node_id": "unit:WEBER",          "labels": {"en": "weber", "eo": "vebero"},           "symbol": "Wb",  "ucum": "Wb"},
    {"node_id": "unit:TESLA",          "labels": {"en": "tesla", "eo": "teslo"},            "symbol": "T",   "ucum": "T"},
    {"node_id": "unit:HENRY",          "labels": {"en": "henry", "eo": "henro"},            "symbol": "H",   "ucum": "H"},
    {"node_id": "unit:LUMEN",          "labels": {"en": "lumen", "eo": "lumeno"},           "symbol": "lm",  "ucum": "lm"},
    {"node_id": "unit:LUX",            "labels": {"en": "lux", "eo": "lukso"},              "symbol": "lx",  "ucum": "lx"},
    {"node_id": "unit:BECQUEREL",      "labels": {"en": "becquerel", "eo": "bekero"},       "symbol": "Bq",  "ucum": "Bq"},
    {"node_id": "unit:GRAY",           "labels": {"en": "gray", "eo": "grajo"},             "symbol": "Gy",  "ucum": "Gy"},
    {"node_id": "unit:SIEVERT",        "labels": {"en": "sievert", "eo": "siverto"},        "symbol": "Sv",  "ucum": "Sv"},
    {"node_id": "unit:KATAL",          "labels": {"en": "katal", "eo": "katalo"},           "symbol": "kat", "ucum": "kat"},
    {"node_id": "unit:DEGREE_CELSIUS", "labels": {"en": "degree Celsius", "eo": "gradoj celsiaj"}, "symbol": "°C", "ucum": "Cel", "multiplier": 1.0, "offset": -273.15},
]

# ── SI Prefixes ─────────────────────────────────────────────────────────

SI_PREFIXES: list[dict] = [
    {"node_id": "unit:YOTTA", "labels": {"en": "yotta"}, "symbol": "Y", "multiplier": 1e24},
    {"node_id": "unit:ZETTA", "labels": {"en": "zetta"}, "symbol": "Z", "multiplier": 1e21},
    {"node_id": "unit:EXA",   "labels": {"en": "exa"},   "symbol": "E", "multiplier": 1e18},
    {"node_id": "unit:PETA",  "labels": {"en": "peta"},  "symbol": "P", "multiplier": 1e15},
    {"node_id": "unit:TERA",  "labels": {"en": "tera"},  "symbol": "T", "multiplier": 1e12},
    {"node_id": "unit:GIGA",  "labels": {"en": "giga"},  "symbol": "G", "multiplier": 1e9},
    {"node_id": "unit:MEGA",  "labels": {"en": "mega"},  "symbol": "M", "multiplier": 1e6},
    {"node_id": "unit:KILO",  "labels": {"en": "kilo"},  "symbol": "k", "multiplier": 1e3},
    {"node_id": "unit:HECTO", "labels": {"en": "hecto"}, "symbol": "h", "multiplier": 1e2},
    {"node_id": "unit:DEKA",  "labels": {"en": "deka"},  "symbol": "da","multiplier": 1e1},
    {"node_id": "unit:DECI",  "labels": {"en": "deci"},  "symbol": "d", "multiplier": 1e-1},
    {"node_id": "unit:CENTI", "labels": {"en": "centi"}, "symbol": "c", "multiplier": 1e-2},
    {"node_id": "unit:MILLI", "labels": {"en": "milli"}, "symbol": "m", "multiplier": 1e-3},
    {"node_id": "unit:MICRO", "labels": {"en": "micro"}, "symbol": "µ", "multiplier": 1e-6},
    {"node_id": "unit:NANO",  "labels": {"en": "nano"},  "symbol": "n", "multiplier": 1e-9},
    {"node_id": "unit:PICO",  "labels": {"en": "pico"},  "symbol": "p", "multiplier": 1e-12},
    {"node_id": "unit:FEMTO", "labels": {"en": "femto"}, "symbol": "f", "multiplier": 1e-15},
    {"node_id": "unit:ATTO",  "labels": {"en": "atto"},  "symbol": "a", "multiplier": 1e-18},
    {"node_id": "unit:ZEPTO", "labels": {"en": "zepto"}, "symbol": "z", "multiplier": 1e-21},
    {"node_id": "unit:YOCTO", "labels": {"en": "yocto"}, "symbol": "y", "multiplier": 1e-24},
]

BASE_AND_DERIVED: list[dict] = SI_BASE_UNITS + DERIVED_UNITS
ALL_UNITS: list[dict] = BASE_AND_DERIVED + SI_PREFIXES
