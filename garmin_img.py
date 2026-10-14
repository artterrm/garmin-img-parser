"""
garmin_img — Python library for reading Garmin IMG files.

Features:
  • Single .img files and gmapsupp.img containers with multiple maps
  • Automatic skipping of NT maps
  • Full Garmin type dictionaries (based on GarminTypes.cpp)
  • 28-bit RGN offset (fix from JGarminImgParser)
  • Extra bit for longitude only
  • Export: MP, GeoJSON, GPX, CSV, Shapefile
  • Polygonization of closed lines (polygonize_shapefile)
  • Object deduplication across zoom levels (export_dedup_shapefile)
  • Batch export by map names (extract_all_by_name)

Dependencies: pyshp (only for shapefile methods).
License: MIT.
"""
from __future__ import annotations

import csv
import gc
import json
import logging
import math
import os
import re as _re
import struct
import time
from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple

log = logging.getLogger(__name__)

C_UNIT = 180.0 / (1 << 23)

USE_RGN_EXTENSION = True
EXTRA_BIT_ONLY_X  = True


# ================================================================
# GARMIN TYPES
# ================================================================

POINT_TYPES = {
    0x0100: "Large city (over 10M)",   0x0200: "Large city (5-10M)",
    0x0300: "Large city (2-5M)",       0x0400: "Large city (1-2M)",
    0x0500: "Medium city (0.5-1M)",    0x0600: "Medium city (200-500K)",
    0x0700: "Medium city (100-200K)",  0x0800: "Small city (50-100K)",
    0x0900: "Small city (20-50K)",     0x0A00: "Small city/town (10-20K)",
    0x0B00: "Small city/town (5-10K)", 0x0C00: "Settlement (2-5K)",
    0x0D00: "Settlement (1-2K)",       0x0E00: "Settlement (500-1K)",
    0x0F00: "Settlement (200-500)",    0x1000: "Settlement (100-200)",
    0x1100: "Settlement (less 100)",
    0x1200: "Marina with facilities",  0x1300: "Marine unknown",
    0x1400: "Major country name",      0x1500: "Minor country name",
    0x1E00: "State/province/region name",
    0x1F00: "County/parish name",      0x2800: "Label",
    0x1C00: "Obstruction",             0x1C01: "Wreck",
    0x1C02: "Submerged wreck, dangerous",
    0x1C03: "Submerged wreck, non-dangerous",
    0x1C04: "Wreck, cleared by wire-drag",
    0x1C05: "Obstr., visible at high water",
    0x1C06: "Obstruction, awash",      0x1C07: "Obstruction, submerged",
    0x1C08: "Obstr., cleared by wire-drag",
    0x1C09: "Rock, awash",             0x1C0A: "Rock, submerged at low water",
    0x1C0B: "Possible grounding risk", 0x1D00: "Tide prediction",
    0x2000: "HW Exit",                 0x2100: "HW Exit with facilities",
    0x210F: "HW Exit (service)",       0x2200: "HW Exit (restroom)",
    0x2300: "HW Exit (convenience store)",
    0x2400: "HW Exit (weight station)",
    0x2500: "HW Exit (toll booth)",    0x2600: "HW Exit (information)",
    0x2700: "HW Exit",                 0x2900: "Uncategorized business",
    0x2A00: "Dining",                  0x2A01: "Dining (American)",
    0x2A02: "Dining (Asian)",          0x2A03: "Dining (barbecue)",
    0x2A04: "Dining (Chinese)",        0x2A05: "Dining (Deli/Bakery)",
    0x2A06: "Dining (international)",  0x2A07: "Fast food",
    0x2A08: "Dining (Italian)",        0x2A09: "Dining (Mexican)",
    0x2A0A: "Dining (pizza)",          0x2A0B: "Dining (sea food)",
    0x2A0C: "Dining (steak/grill)",    0x2A0D: "Dining (bagel/donut)",
    0x2A0E: "Dining (cafe/diner)",     0x2A0F: "Dining (French)",
    0x2A10: "Dining (German)",         0x2A11: "Dining (British Isles)",
    0x2A12: "Special food products",
    0x2B00: "Lodging",                 0x2B01: "Hotel/Motel",
    0x2B02: "Bed&Breakfast inn",       0x2B03: "Camping/RV-Park",
    0x2B04: "Resort",
    0x2C00: "Attraction",              0x2C01: "Amusement/Theme park",
    0x2C02: "Museum/History",          0x2C03: "Library",
    0x2C04: "Landmark",                0x2C05: "School",
    0x2C06: "Park/Garden",             0x2C07: "Zoo/Aquarium",
    0x2C08: "Arena/Track",             0x2C09: "Hall/Auditorium",
    0x2C0A: "Winery",                  0x2C0B: "Place of worship",
    0x2D00: "Entertainment",           0x2D01: "Live theatre",
    0x2D02: "Bar/Nightclub",           0x2D03: "Cinema",
    0x2D04: "Casino",                  0x2D05: "Golf course",
    0x2D06: "Skiing center/resort",    0x2D07: "Bowling center",
    0x2D08: "Ice skating",             0x2D09: "Swimming pool",
    0x2D0A: "Sports/Fitness Center",   0x2D0B: "Public sports airport",
    0x2E00: "Shopping",                0x2E01: "Department store",
    0x2E02: "Grocery store",           0x2E03: "General merchandiser",
    0x2E04: "Shopping center",         0x2E05: "Pharmacy",
    0x2E06: "Convenience store",       0x2E07: "Apparel",
    0x2E08: "House and garden",        0x2E09: "Home furnishing",
    0x2E0A: "Speciality retail",       0x2E0B: "Computer/Software",
    0x2F00: "Generic services",        0x2F01: "Auto fuel",
    0x2F02: "Auto rental",             0x2F03: "Auto repair",
    0x2F04: "Air transportation",      0x2F05: "Post office",
    0x2F06: "Bank/ATM",                0x2F07: "Dealer/Auto parts",
    0x2F08: "Ground transportation",   0x2F09: "Marina/Boat repair",
    0x2F0A: "Wrecker service",         0x2F0B: "Parking",
    0x2F0C: "Rest area/Tourist info",  0x2F0D: "Automobile club",
    0x2F0E: "Car wash",                0x2F0F: "Garmin dealer",
    0x2F10: "Personal services",       0x2F11: "Business service",
    0x2F12: "Communication service",   0x2F13: "Repair service",
    0x2F14: "Social service",          0x2F15: "Public utilities",
    0x2F16: "Truck stop",              0x2F17: "Transit service",
    0x3000: "Emergency/Governmental",  0x3001: "Police station",
    0x3002: "Hospital",                0x3003: "City hall",
    0x3004: "Court house",             0x3005: "Community center",
    0x3006: "Border crossing",         0x3007: "Government office",
    0x3008: "Fire department",
    0x4000: "Golf",                    0x4100: "Fishing spot",
    0x4200: "Wreck",                   0x4300: "Marina",
    0x4400: "Gas station",             0x4500: "Restaurant",
    0x4600: "Bar",                     0x4700: "Boat ramp",
    0x4800: "Camping",                 0x4900: "Park",
    0x4A00: "Picnic area",             0x4B00: "First aid station",
    0x4C00: "Information",             0x4D00: "Parking",
    0x4E00: "Restroom",                0x4F00: "Shower",
    0x5000: "Drinking water",          0x5100: "Telephone",
    0x5200: "Scenic area",             0x5300: "Skiing",
    0x5400: "Swimming area",           0x5500: "Dam",
    0x5600: "Controlled area",         0x5700: "Danger area",
    0x5800: "Restricted area",
    0x5900: "Generic airport",         0x5901: "Large airport",
    0x5902: "Medium airport",          0x5903: "Small airport",
    0x5904: "Heliport",                0x5905: "Airport",
    0x5A00: "Mile marker",             0x5B00: "Bell",
    0x5C00: "Diving area",             0x5D00: "Daymark, green square",
    0x5E00: "Daymark, red triangle",   0x6000: "Horn",
    0x6100: "House",                   0x6200: "Depth spot",
    0x6300: "Elevation spot",
    0x6400: "Man-made place",          0x6401: "Bridge",
    0x6402: "Building",                0x6403: "Cemetery",
    0x6404: "Church/mosque/etc",       0x6405: "Civil bulding",
    0x6406: "Crossing",                0x6407: "Dam",
    0x6408: "Hospital",                0x6409: "Levee",
    0x640A: "Locale",                  0x640B: "Military",
    0x640C: "Mine",                    0x640D: "Oil field",
    0x640E: "Park",                    0x640F: "Post office",
    0x6410: "School",                  0x6411: "Tower",
    0x6412: "Trailhead",               0x6413: "Tunnel",
    0x6414: "Well",                    0x6415: "Historical (ghost) town",
    0x6416: "Subdivision of housing",
    0x6500: "Water feature",           0x6501: "Arroyo",
    0x6502: "Sand bar",                0x6503: "Bay",
    0x6504: "Bend",                    0x6505: "Canal",
    0x6506: "Channel",                 0x6507: "Cove",
    0x6508: "Falls",                   0x6509: "Geyser",
    0x650A: "Glacier",                 0x650B: "Harbor",
    0x650C: "Island",                  0x650D: "Lake",
    0x650E: "Rapids",                  0x650F: "Reservoir",
    0x6510: "Sea",                     0x6511: "Spring",
    0x6512: "Stream",                  0x6513: "Swamp",
    0x6600: "Land feature",            0x6601: "Arch",
    0x6602: "Area",                    0x6603: "Basin",
    0x6604: "Beach",                   0x6605: "Bench",
    0x6606: "Cape",                    0x6607: "Cliff",
    0x6608: "Crater",                  0x6609: "Flat",
    0x660A: "Forest",                  0x660B: "Gap",
    0x660C: "Gut",                     0x660D: "Isthmus",
    0x660E: "Lava",                    0x660F: "Pillar",
    0x6610: "Plain",                   0x6611: "Range",
    0x6612: "Reserve",                 0x6613: "Ridge",
    0x6614: "Rock",                    0x6615: "Slope",
    0x6616: "Summit",                  0x6617: "Valley",
    0x6618: "Wooded area",
}

_NAVAID_SUBTYPES = {
    0x00: "Navaid",                    0x01: "Fog horn",
    0x02: "Radio beacon",              0x03: "Racon",
    0x04: "Daybeacon, red triangle",   0x05: "Daybeacon, green square",
    0x06: "Daybeacon, white diamond",  0x07: "Unlit navaid, white",
    0x08: "Unlit navaid, red",         0x09: "Unlit navaid, green",
    0x0A: "Unlit navaid, black",       0x0B: "Unlit navaid, yellow/amber",
    0x0C: "Unlit navaid, orange",      0x0D: "Unlit navaid, multi colored",
    0x0E: "Navaid, unknown",           0x0F: "Navaid, white",
    0x10: "Navaid, red",               0x11: "Navaid, green",
    0x12: "Navaid, yellow/amber",      0x13: "Navaid, orange",
    0x14: "Navaid, violet",            0x15: "Navaid, blue",
    0x16: "Navaid, multi colored",
}
for _hi in (0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B):
    for _sub, _name in _NAVAID_SUBTYPES.items():
        POINT_TYPES[(_hi << 8) | _sub] = _name


POLYLINE_TYPES = {
    0x00: "Road", 0x01: "Major highway", 0x02: "Principal highway",
    0x03: "Other highway road", 0x04: "Arterial road", 0x05: "Collector road",
    0x06: "Residential street", 0x07: "Alleyway/private driveway",
    0x08: "Highway ramp, low-speed", 0x09: "Highway ramp, high-speed",
    0x0A: "Unpaved road", 0x0B: "Major highway connector", 0x0C: "Roundabout",
    0x14: "Railroad", 0x15: "Shoreline of water body", 0x16: "Walkway/trail",
    0x18: "Stream", 0x19: "Time-zone",
    0x1A: "Water or rail ferry", 0x1B: "Water or rail ferry",
    0x1C: "State/province boundary", 0x1D: "County/parish boundary",
    0x1E: "International boundary", 0x1F: "River",
    0x20: "Minor land contour (1/10)", 0x21: "Interm. land contour (1/2)",
    0x22: "Major land contour (1/1)", 0x23: "Minor depth contour (1/10)",
    0x24: "Interm. depth contour (1/2)", 0x25: "Major depth contour (1/1)",
    0x26: "Intermittent stream/ditch", 0x27: "Airport runway centerline",
    0x28: "Oil or water pipeline", 0x29: "Power line",
    0x2A: "Marine boundary (no line)", 0x2B: "Marine hazard (no line)",
}

POLYGON_TYPES = {
    0x01: "Large urban area (>200K)", 0x02: "Small urban area (<200K)",
    0x03: "Rural housing area", 0x04: "Military base", 0x05: "Parking lot",
    0x06: "Parking garage", 0x07: "Airport", 0x08: "Shopping center",
    0x09: "Marina", 0x0A: "University/College", 0x0B: "Hospital",
    0x0C: "Industrial complex", 0x0D: "Reservation", 0x0E: "Airport runway",
    0x13: "Building/Man-made area",
    0x14: "National park", 0x15: "National park", 0x16: "National park",
    0x17: "City park", 0x18: "Golf course", 0x19: "Sports complex",
    0x1A: "Cemetery", 0x1E: "State park", 0x1F: "State park", 0x20: "State park",
    0x28: "Sea/Ocean", 0x29: "Blue-Unknown", 0x32: "Sea", 0x3B: "Blue-Unknown",
    0x3C: "Large lake (250-600 km2)", 0x3D: "Large lake (77-250 km2)",
    0x3E: "Medium lake (25-77 km2)", 0x3F: "Medium lake (11-25 km2)",
    0x40: "Small lake (0.25-11 km2)", 0x41: "Small lake (<0.25 km2)",
    0x42: "Major lake (>3.3 tkm2)", 0x43: "Major lake (1.1-3.3 tkm2)",
    0x44: "Large lake (0.6-1.1 tkm2)", 0x45: "Blue-Unknown",
    0x46: "Major river (>1 km)", 0x47: "Large river (200 m-1 km)",
    0x48: "Medium river (40-200 m)", 0x49: "Small river (<40 m)",
    0x4A: "Map selection area", 0x4B: "Map coverage area",
    0x4C: "Intermittent water", 0x4D: "Glacier", 0x4E: "Orchard/plantation",
    0x4F: "Scrub", 0x50: "Forest", 0x51: "Wetland/swamp", 0x52: "Tundra",
    0x53: "Sand/tidal/mud flat",
}

POLYLINE_GROUPS = {
    0x00: "road", 0x01: "road", 0x02: "road", 0x03: "road",
    0x04: "road", 0x05: "road", 0x06: "road", 0x07: "road",
    0x08: "road", 0x09: "road", 0x0A: "road", 0x0B: "road", 0x0C: "road",
    0x14: "rail",
    0x15: "water", 0x18: "water", 0x1F: "water", 0x26: "water",
    0x16: "trail", 0x19: "boundary",
    0x1A: "ferry", 0x1B: "ferry",
    0x1C: "boundary", 0x1D: "boundary", 0x1E: "boundary",
    0x20: "contour", 0x21: "contour", 0x22: "contour",
    0x23: "contour", 0x24: "contour", 0x25: "contour",
    0x27: "infra", 0x28: "infra", 0x29: "infra",
    0x2A: "boundary", 0x2B: "boundary",
}

_SERVICE_SUBFILES = {'MPS', 'TDB', 'MDR', 'SRT', 'MDX',
                     'TYP', 'MD2', 'JCV', 'SID', 'SQL'}


# ================================================================
# Predicates
# ================================================================

def is_city_point(t):    return 0x0100 <= (t & 0xFFFF00) <= 0x1100
def is_hw_exit_point(t): return 0x2000 <= (t & 0xFFFF00) <= 0x2700
def is_height_point(t):  return (t & 0xFFFF00) in (0x6200, 0x6300)
def is_feature_point(t): return 0x6400 <= (t & 0xFFFF00) <= 0x6600
def has_address_point(t):
    x = t & 0xFFFF00
    return (0x2900 <= x <= 0x3000) or x == 0x1200
def is_navaid_point(t):  return 0x1600 <= (t & 0xFF00) <= 0x1B00
def is_road_line(t):
    if 0x00 <= t <= 0x13: return True
    return t in (0x16, 0x1A, 0x1B)
def is_unpaved_road(t):  return t == 0x0A
def is_roundabout(t):    return t == 0x0C
def is_height_line(t):   return 0x20 <= t <= 0x25
def is_background_polygon(t): return t == 0x4B
def is_water_line(t):    return t in (0x15, 0x18, 0x1F, 0x26)
def is_rail_line(t):     return t == 0x14
def is_border_line(t):   return t in (0x1C, 0x1D, 0x1E)
def is_water_polygon(t):
    return t in (0x28, 0x29, 0x32, 0x3B, 0x3C, 0x3D, 0x3E, 0x3F,
                 0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47,
                 0x48, 0x49, 0x4C, 0x51, 0x53)
def is_land_polygon(t):
    return t in (0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A,
                 0x1E, 0x1F, 0x20, 0x4D, 0x4E, 0x4F, 0x50, 0x52)


# ================================================================
# Type registration
# ================================================================

def register_point_type(code, name):    POINT_TYPES[int(code)] = str(name)
def register_line_type(code, name, group=None):
    code = int(code); POLYLINE_TYPES[code] = str(name)
    if group is not None: POLYLINE_GROUPS[code] = str(group)
def register_polygon_type(code, name):  POLYGON_TYPES[int(code)] = str(name)
def register_line_group(code, group):   POLYLINE_GROUPS[int(code)] = str(group)


def _read_text(path):
    for enc in ('utf-8-sig', 'utf-8', 'cp1251', 'latin-1'):
        try:
            with open(path, 'r', encoding=enc) as f: return f.read()
        except UnicodeDecodeError: continue
    with open(path, 'r', encoding='latin-1', errors='replace') as f:
        return f.read()


def _parse_code(s):
    s = s.strip()
    try:
        if s.lower().startswith('0x'): return int(s, 16)
        if _re.fullmatch(r'[0-9A-Fa-f]+', s): return int(s, 16)
        return int(s)
    except ValueError:
        return None


def _parse_name_group(s):
    m = _re.match(r'^(.*?)\s+@(\w+)\s*$', s)
    if m: return m.group(1).strip(), m.group(2).strip()
    return s.strip(), None


def _parse_type_line(line):
    line = _re.split(r'\s*[#;]', line, maxsplit=1)[0].strip()
    if not line: return None, None, None
    if '=' in line:
        left, right = line.split('=', 1)
        return _parse_code(left.strip()), *_parse_name_group(right.strip())
    parts = line.split(None, 1)
    if len(parts) < 2: return None, None, None
    return _parse_code(parts[0]), *_parse_name_group(parts[1])


def _guess_kind_by_code(code):
    if code >= 0x100: return 'point'
    if code >= 0x40: return 'polygon'
    return 'line'


def load_types_from_file(path, *, kind=None, verbose=False):
    text = _read_text(path); loaded = 0; section = kind
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or line.startswith(';'): continue
        m = _re.match(r'^\[(\w+)\]$', line)
        if m:
            s = m.group(1).lower()
            if s in ('point', 'points', 'poi'): section = 'point'
            elif s in ('line', 'lines', 'polyline', 'polylines'): section = 'line'
            elif s in ('polygon', 'polygons'): section = 'polygon'
            continue
        code, name, group = _parse_type_line(line)
        if code is None or not name: continue
        k = section or _guess_kind_by_code(code)
        if k == 'point': register_point_type(code, name)
        elif k == 'line': register_line_type(code, name, group=group)
        elif k == 'polygon': register_polygon_type(code, name)
        else: continue
        loaded += 1
        if verbose:
            print(f"  {k:<8} 0x{code:04X}  {name}"
                  + (f"  [{group}]" if group else ""))
    return loaded


def save_types_to_file(path):
    with open(path, 'w', encoding='utf-8') as f:
        f.write("# Garmin IMG types\n\n[POINT]\n")
        for t in sorted(POINT_TYPES): f.write(f"0x{t:04X} = {POINT_TYPES[t]}\n")
        f.write("\n[LINE]\n")
        for t in sorted(POLYLINE_TYPES):
            g = POLYLINE_GROUPS.get(t)
            f.write(f"0x{t:04X} = {POLYLINE_TYPES[t]}"
                    + (f" @{g}" if g else "") + "\n")
        f.write("\n[POLYGON]\n")
        for t in sorted(POLYGON_TYPES): f.write(f"0x{t:04X} = {POLYGON_TYPES[t]}\n")


def guess_point_type(code):
    code = int(code)
    if code in POINT_TYPES: return POINT_TYPES[code]
    hi = (code >> 8) & 0xFF
    for lo, hi_b, name in [
        (0x01, 0x11, "City"), (0x12, 0x13, "Marine"),
        (0x14, 0x15, "Country name"), (0x16, 0x1B, "Navaid"),
        (0x1C, 0x1C, "Obstruction"), (0x1D, 0x1D, "Tide prediction"),
        (0x1E, 0x1E, "State/province/region"),
        (0x1F, 0x1F, "County/parish"),
        (0x20, 0x27, "HW Exit"), (0x28, 0x28, "Label"),
        (0x29, 0x30, "POI"), (0x40, 0x58, "Recreation"),
        (0x59, 0x59, "Airport"), (0x5A, 0x61, "Misc"),
        (0x62, 0x63, "Depth/Elevation"), (0x64, 0x64, "Man-made"),
        (0x65, 0x65, "Water feature"), (0x66, 0x66, "Land feature")]:
        if lo <= hi <= hi_b: return f"{name} (0x{code:04X})"
    return f"Unknown (0x{code:04X})"

def guess_line_type(code):
    return POLYLINE_TYPES.get(int(code), f"Unknown line (0x{int(code):02X})")
def guess_polygon_type(code):
    return POLYGON_TYPES.get(int(code), f"Unknown polygon (0x{int(code):02X})")


# ================================================================
# Reader / exceptions
# ================================================================

class GarminImgError(Exception): pass


class _Reader:
    __slots__ = ('d','p','n')
    def __init__(self, d, p=0): self.d, self.p, self.n = d, p, len(d)
    def u8(self): v=self.d[self.p]; self.p+=1; return v
    def u16(self): v=self.d[self.p]|(self.d[self.p+1]<<8); self.p+=2; return v
    def i16(self): v=self.u16(); return v-0x10000 if v&0x8000 else v
    def u24(self):
        p=self.p; v=self.d[p]|(self.d[p+1]<<8)|(self.d[p+2]<<16)
        self.p+=3; return v
    def i24(self): v=self.u24(); return v-0x1000000 if v&0x800000 else v
    def u32(self):
        v=struct.unpack_from('<I', self.d, self.p)[0]; self.p+=4; return v
    def fixed(self, n):
        v=self.d[self.p:self.p+n]; self.p+=n
        i=v.find(b'\x00')
        if i>=0: v=v[:i]
        return v.decode('latin-1', 'replace')


# ================================================================
# Data classes
# ================================================================

@dataclass
class ZoomLevel:
    zoom: int; bits: int; subdivisions: int; inherited: bool

@dataclass
class Subdivision:
    zoom: int; shift: int
    rgn_start: int; rgn_end: int
    elems: int; lon: int; lat: int
    width: int; height: int
    terminating: bool
    next_level: int = 0

@dataclass
class Point:
    kind: str; type: int; subtype: Optional[int]
    label: str; lat: float; lon: float; level: int
    @property
    def type_name(self): return guess_point_type(self.type)

@dataclass
class Polyline:
    type: int; label: str; level: int
    points: List[Tuple[float, float]]
    direction: bool = False; in_net: bool = False
    @property
    def type_name(self): return guess_line_type(self.type)
    @property
    def type_group(self): return POLYLINE_GROUPS.get(self.type, "other")

@dataclass
class Polygon:
    type: int; label: str; level: int
    points: List[Tuple[float, float]]
    @property
    def type_name(self): return guess_polygon_type(self.type)

@dataclass
class Metadata:
    name: str; map_id: int; codepage: int; encoding: int
    north: float; east: float; south: float; west: float
    locked: bool; size_bytes: int
    submap_id: Optional[str] = None
    submap_name: Optional[str] = None   # name from MPS (for submaps)


# ================================================================
# LBL
# ================================================================

_ENC6       = " ABCDEFGHIJKLMNOPQRSTUVWXYZ~~~~~0123456789~~~~~~"
_ENC6_SHIFT = "@!\"#$%&'()*+,-./" + "~"*10 + ":;<=>?" + "~"*11 + "[\\]^_"
_ENC6_SPEC  = "`" + "abcdefghijklmnopqrstuvwxyz" + "~"*5 + "0123456789" + "~"*6


class LBL:
    def __init__(self, data, sub_off):
        self._data = data
        r = _Reader(data, sub_off)
        self.hlen = r.u16()
        r.fixed(10); r.u8()
        self.locked = (r.u8() & 0x80) != 0
        r.u16(); r.u8(); r.u8(); r.u8(); r.u8(); r.u8()
        self.data_off = r.u32() + sub_off
        self.data_len = r.u32()
        self.mult = 1 << r.u8()
        self.encoding = r.u8()
        r.u32(); r.u32(); r.u16(); r.u32()
        r.u32(); r.u32(); r.u16(); r.u32()
        r.u32(); r.u32(); r.u16(); r.u32()
        r.u32(); r.u32(); r.u16(); r.u32()
        self.poi_off = r.u32() + sub_off
        self.poi_len = r.u32()
        self.poi_mult = 1 << r.u8()
        self.poi_global = r.u8()
        r.u16(); r.u8()
        self._cache = {}; self._poi_cache = {}
        self.codepage = 1252
        if self.hlen >= 0xAC and sub_off + 0xAA + 2 <= len(data):
            cp = struct.unpack_from('<H', data, sub_off + 0xAA)[0]
            if cp in (1250,1251,1252,1253,1254,1255,1256,1257):
                self.codepage = cp
            elif cp == 65001:
                self.codepage = 65001

    def read(self, offset):
        if offset in self._cache: return self._cache[offset]
        real = self.data_off + offset * self.mult
        if real < 0 or real >= len(self._data):
            self._cache[offset] = ""; return ""
        if self.encoding == 6: s = self._dec6(real)
        elif self.encoding in (9, 10): s = self._dec8(real)
        else: s = ""
        self._cache[offset] = s
        return s

    def read_poi(self, offset, extra):
        if not extra: return self.read(offset)
        key = ('p', offset)
        if key in self._poi_cache: return self._poi_cache[key]
        real = self.poi_off + offset * self.poi_mult
        if real < 0 or real + 3 > len(self._data):
            self._poi_cache[key] = ""; return ""
        b = self._data[real:real+3]
        inner = b[0] | (b[1] << 8) | (b[2] << 16)
        s = self.read(inner & 0x3FFFFF)
        self._poi_cache[key] = s
        return s

    def clear_cache(self):
        self._cache.clear(); self._poi_cache.clear()

    def _dec6(self, pos):
        d = self._data; out = []; chset = 0; lcont = False
        while pos + 3 <= len(d):
            b0,b1,b2 = d[pos],d[pos+1],d[pos+2]
            for i, c in enumerate((b0>>2, ((b0&3)<<4)|(b1>>4),
                                   ((b1&0x0F)<<2)|(b2>>6), b2&0x3F)):
                if c > 0x2F or (c == 0 and i == 0 and not lcont):
                    return ''.join(out)
                if chset == 0:
                    if c == 0x1C: chset = 1; continue
                    if c == 0x1B: chset = 2; continue
                    ch = _ENC6[c]
                elif chset == 1: ch = _ENC6_SHIFT[c]; chset = 0
                else:           ch = _ENC6_SPEC[c]; chset = 0
                out.append(ch if ch != '~' else f"~[0x{c:02x}]")
            lcont = True; pos += 3
        return ''.join(out)

    def _dec8(self, pos):
        cp = self.codepage
        if cp == 65001:
            enc = 'utf-8'
        elif cp in (1250, 1251, 1252, 1253, 1254, 1255, 1256, 1257,
                    932, 949, 950, 874):
            enc = f'cp{cp}'
        else:
            enc = 'cp1252'
        d = self._data; out = []
        while pos < len(d):
            b = d[pos]
            if b == 0: break
            if b < 0x20: out.append(f"~[0x{b:02x}]")
            else: out.append(bytes([b]).decode(enc, errors='replace'))
            pos += 1
        return ''.join(out)


# ================================================================
# Bitstream (extra bit for X only)
# ================================================================

def decode_bitstream(bs, shift, bitdef, extra_bit, x0, y0):
    if not bs: return [(x0, y0)]
    bits = []
    for byte in bs:
        for i in range(8): bits.append((byte >> i) & 1)
    n = 0; total = len(bits)

    if bits[n] == 0:
        sign_x = 0; cbits_x = 1; n += 1
    else:
        n += 1
        sign_x = 1 if bits[n] == 0 else -1
        cbits_x = 0; n += 1
    bpx = bitdef & 0x0F
    if bpx > 9: bpx = 2*bpx - 9
    cbits_x += bpx + 2

    if bits[n] == 0:
        sign_y = 0; cbits_y = 1; n += 1
    else:
        n += 1
        sign_y = 1 if bits[n] == 0 else -1
        cbits_y = 0; n += 1
    bpy = (bitdef >> 4) & 0x0F
    if bpy > 9: bpy = 2*bpy - 9
    cbits_y += bpy + 2

    # Extra bit is a separate bit before the coordinate pair.
    if extra_bit:
        if EXTRA_BIT_ONLY_X:
            cbits_point = cbits_x + cbits_y + 1
        else:
            cbits_point = cbits_x + cbits_y + 2
    else:
        cbits_point = cbits_x + cbits_y

    x_special = 1 << (cbits_x - 1)
    y_special = 1 << (cbits_y - 1)
    x, y = x0, y0
    pts = [(x, y)]

    def read_delta(special, nb, sign_mode):
        nonlocal n
        if sign_mode == 0:
            acc = 0
            while True:
                d = 0
                for i in range(nb):
                    if n + i < total: d |= bits[n+i] << i
                n += nb
                if d != special: break
                acc += (1 << (nb - 1)) - 1
            if d < special: return acc + d
            return (d - 2*special) - acc
        else:
            d = 0
            for i in range(nb):
                if n + i < total: d |= bits[n+i] << i
            n += nb
            return -d if sign_mode < 0 else d

    while n + cbits_point <= total:
        if extra_bit: n += 1
        dx = read_delta(x_special, cbits_x, sign_x)
        dy = read_delta(y_special, cbits_y, sign_y)
        dx <<= shift; dy <<= shift
        if dx >= 0x800000: dx -= 0x1000000
        if dy >= 0x800000: dy -= 0x1000000
        x += dx; y += dy
        pts.append((x, y))
    return pts


# ================================================================
# XOR / subfile lookup / FAT / MPS
# ================================================================

def _find_subfiles(data):
    res = {}
    for kind in (b'RGN', b'TRE', b'LBL', b'NET', b'NOD'):
        marker = b'GARMIN ' + kind
        pos = 0
        while True:
            pos = data.find(marker, pos)
            if pos < 0: break
            hdr = pos - 2
            if hdr < 0: pos += 1; continue
            hlen = struct.unpack_from('<H', data, hdr)[0]
            if 20 <= hlen <= 700 and hdr + 0x16 < len(data):
                yr = struct.unpack_from('<H', data, hdr + 0x0E)[0]
                if 1990 <= yr <= 2030 or yr < 100:
                    nm = kind.decode()
                    if nm not in res or hdr < res[nm]:
                        res[nm] = hdr
            pos += 1
    return res


def _xor_bytes(data, key):
    if key == 0: return data
    trans = bytes.maketrans(bytes(range(256)),
                            bytes(i ^ key for i in range(256)))
    return data.translate(trans)


def _decode_xor(raw):
    if len(raw) > 0x16:
        key = raw[0x10] ^ ord('D')
        if key == 0:
            if b'GARMIN TRE' in raw or b'GARMIN RGN' in raw:
                return raw, 0
        dec = _xor_bytes(raw, key)
        if b'GARMIN TRE' in dec or b'GARMIN RGN' in dec:
            return dec, key
    if len(raw) > 20 * 1024 * 1024:
        raise GarminImgError(f"File is {len(raw)//1024//1024} MB, "
                             f"signatures not found. Possibly NT.")
    for key in range(1, 256):
        dec = _xor_bytes(raw, key)
        if b'GARMIN TRE' in dec or b'GARMIN RGN' in dec:
            return dec, key
    return raw, 0


@dataclass
class _FATEntry:
    name: str; stype: str; size: int; part: int; blocks: List[int]


def _parse_fat_entries(data):
    block_size = 1 << (data[0x61] + data[0x62])
    data_offset = struct.unpack_from('<I', data, 0x40C)[0]
    entries = []; o = 0x600; seen_valid = False
    while o + 512 <= len(data):
        valid = data[o]
        name = data[o+1:o+9].decode('ascii','replace').rstrip('\x00 ')
        stype = data[o+9:o+12].decode('ascii','replace').rstrip('\x00 ')
        if valid == 0 and not name and not stype:
            if seen_valid: break
            o += 512; continue
        if valid != 1: break
        size = struct.unpack_from('<I', data, o+0x0C)[0]
        part = data[o+0x11]
        blocks = []
        for i in range(240):
            w = struct.unpack_from('<H', data, o+0x20+i*2)[0]
            if w == 0xFFFF: break
            blocks.append(w)
        entries.append(_FATEntry(name, stype, size, part, blocks))
        seen_valid = True; o += 512
        if data_offset > 0 and o >= data_offset: break
    return entries, block_size


def _fat_groups(data):
    entries, _ = _parse_fat_entries(data)
    groups = {}
    for e in entries:
        if not e.name or not e.stype: continue
        groups.setdefault(e.name, {}).setdefault(e.stype, []).append(e)
    return groups


def _hex_id_to_int(sid):
    s = sid.strip()
    if not s: return None
    if s.startswith('I'):
        try: return int(s[1:], 16)
        except ValueError: return None
    try: return int(s, 10)
    except ValueError: return None


def _parse_mps(data, sub_off):
    result = {}; p = sub_off; end = len(data)
    while p + 3 <= end:
        rectype = chr(data[p])
        reclen = struct.unpack_from('<H', data, p+1)[0]
        body = data[p+3:p+3+reclen]; p += 3 + reclen
        if rectype == 'L' and len(body) >= 8:
            pid = struct.unpack_from('<H', body, 0)[0]
            fid = struct.unpack_from('<H', body, 2)[0]
            seg = struct.unpack_from('<I', body, 4)[0]
            strings = []; rest = body[8:]
            while rest and len(strings) < 3:
                i = rest.find(b'\x00')
                if i < 0: break
                raw = rest[:i]
                if raw:
                    try: strings.append(raw.decode('cp1251'))
                    except Exception: strings.append(raw.decode('latin-1','replace'))
                else: strings.append('')
                rest = rest[i+1:]
            result[seg] = {'pid': pid, 'fid': fid,
                'name':    strings[0] if len(strings) > 0 else '',
                'segment': strings[1] if len(strings) > 1 else '',
                'area':    strings[2] if len(strings) > 2 else ''}
    return result


def _is_classic_img(t): return 'RGN' in t and 'TRE' in t
def _is_nt_img(t):
    if _is_classic_img(t): return False
    return any(x in t for x in ('NT', 'MPC', 'GMP'))
def _is_service_only(t):
    return not any(x in t for x in ('RGN', 'TRE', 'NT', 'MPC', 'GMP'))


# ================================================================
# TRE
# ================================================================

def _parse_tre(data, sub_off, rgn_data_len):
    r = _Reader(data, sub_off)
    hlen = r.u16()
    r.fixed(10); r.u8()
    locked = (r.u8() & 0x80) != 0
    r.u16(); r.u8(); r.u8(); r.u8(); r.u8(); r.u8()
    north = r.i24() * C_UNIT
    east  = r.i24() * C_UNIT
    south = r.i24() * C_UNIT
    west  = r.i24() * C_UNIT
    lvl_off = r.u32(); lvl_len = r.u32()
    sub_off_ = r.u32(); sub_len = r.u32()

    lr = _Reader(data, sub_off + lvl_off)
    levels = []
    for _ in range(lvl_len // 4):
        b = lr.u8(); zoom = b & 0x0F
        inherited = (b & 0x80) != 0
        bits = lr.u8(); nsub = lr.u16()
        levels.append(ZoomLevel(zoom, bits, nsub, inherited))

    sr = _Reader(data, sub_off + sub_off_)
    sub_end = sub_off + sub_off_ + sub_len
    subdivisions = []
    min_zoom = min(l.zoom for l in levels) if levels else 0

    for lvl in levels:
        recsz = 14 if lvl.zoom == min_zoom else 16
        for _ in range(lvl.subdivisions):
            rgn_off_low = sr.u24()
            elems = sr.u8()
            if USE_RGN_EXTENSION:
                rgn_start = rgn_off_low | ((elems & 0x0F) << 24)
                kinds = elems & 0xF0
            else:
                rgn_start = rgn_off_low
                kinds = elems
            clon = sr.i24(); clat = sr.i24()
            w = sr.u16()
            term = (w & 0x8000) != 0
            w &= 0x7FFF
            h = sr.u16()
            nl = sr.u16() if recsz == 16 else 0
            subdivisions.append(Subdivision(
                zoom=lvl.zoom, shift=24 - lvl.bits,
                rgn_start=rgn_start, rgn_end=rgn_start,
                elems=kinds, lon=clon, lat=clat,
                width=w, height=h, terminating=term,
                next_level=nl))
            if sr.p >= sub_end: break
        if sr.p >= sub_end: break

    for i in range(len(subdivisions) - 1):
        subdivisions[i].rgn_end = subdivisions[i+1].rgn_start
    if subdivisions:
        subdivisions[-1].rgn_end = rgn_data_len

    map_id = 0
    if hlen >= 120 and sub_off + 0x74 + 4 <= len(data):
        map_id = struct.unpack_from('<I', data, sub_off + 0x74)[0]

    return (levels, subdivisions, north, east, south, west, locked, map_id)


# ================================================================
# RGN
# ================================================================

def _parse_points(data, s, e, sd, lbl):
    p = s; shift = sd.shift
    while p + 8 <= e:
        d = struct.unpack_from('<I', data, p)[0]
        btype = d & 0xFF
        lbl_off = (d >> 8) & 0x3FFFFF
        extra = (d >> 30) & 1
        has_sub = (d >> 31) & 1
        x = struct.unpack_from('<H', data, p+4)[0]
        y = struct.unpack_from('<H', data, p+6)[0]
        p += 8
        sub = None
        if has_sub:
            if p >= e: break
            sub = data[p]; p += 1
        sx = x - 0x10000 if x & 0x8000 else x
        sy = y - 0x10000 if y & 0x8000 else y
        gu_x = sd.lon + (sx << shift)
        gu_y = sd.lat + (sy << shift)
        full_type = (btype << 8) | (sub if sub is not None else 0)
        label = lbl.read_poi(lbl_off, bool(extra)) if (lbl and lbl_off) else ""
        yield Point(
            kind='point',
            type=full_type if sub is not None else (btype << 8),
            subtype=sub, label=label,
            lat=gu_y * C_UNIT, lon=gu_x * C_UNIT,
            level=sd.zoom)


def _parse_polys(data, s, e, sd, lbl, is_polygon):
    p = s; shift = sd.shift
    while p + 9 <= e:
        type_byte = data[p]; p += 1
        two_byte_len = (type_byte & 0x80) != 0
        if is_polygon:
            ptype = type_byte & 0x7F; direction = False
        else:
            ptype = type_byte & 0x3F
            direction = (type_byte & 0x40) != 0
        if p + 3 > e: break
        lbl_info = data[p] | (data[p+1] << 8) | (data[p+2] << 16); p += 3
        lbl_off = lbl_info & 0x3FFFFF
        extra_bit = bool(lbl_info & 0x400000)
        in_net = bool(lbl_info & 0x800000)
        if p + 4 > e: break
        dx = struct.unpack_from('<h', data, p)[0]; p += 2
        dy = struct.unpack_from('<h', data, p)[0]; p += 2
        if two_byte_len:
            if p + 2 > e: break
            blen = struct.unpack_from('<H', data, p)[0]; p += 2
        else:
            if p + 1 > e: break
            blen = data[p]; p += 1
        if p + 1 > e: break
        bitdef = data[p]; p += 1
        if p + blen > e: break
        bitstream = data[p:p+blen]; p += blen
        gu_x = sd.lon + (dx << shift)
        gu_y = sd.lat + (dy << shift)
        pts_gu = decode_bitstream(bitstream, shift, bitdef, extra_bit, gu_x, gu_y)
        pts_deg = [(x * C_UNIT, y * C_UNIT) for (x, y) in pts_gu]
        label = lbl.read(lbl_off) if (lbl and lbl_off) else ""
        if is_polygon:
            yield Polygon(ptype, label, sd.zoom, pts_deg)
        else:
            yield Polyline(ptype, label, sd.zoom, pts_deg, direction, in_net)


# ================================================================
# Utilities
# ================================================================

def line_length_m(points):
    if len(points) < 2: return 0.0
    R = 6371000.0; total = 0.0
    for i in range(len(points) - 1):
        lon1, lat1 = points[i]; lon2, lat2 = points[i+1]
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat/2)**2 + math.cos(math.radians(lat1))
             * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2)
        total += 2 * R * math.asin(math.sqrt(a))
    return total

def bbox(points):
    if not points: return (0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in points]; ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))

def _xml_escape(s):
    return (s.replace('&','&amp;').replace('<','&lt;')
             .replace('>','&gt;').replace('"','&quot;'))

def _safe_folder_name(name, sid=None):
    """Sanitizes a folder name from invalid Windows characters."""
    base = (name or sid or "unnamed").strip()
    if not base:
        base = sid or "unnamed"
    bad = '<>:"/\\|?*'
    for ch in bad:
        base = base.replace(ch, "_")
    base = base.rstrip(". ")
    return base[:80] or (sid or "unnamed")


# ================================================================
# GarminIMG
# ================================================================

class GarminIMG:
    def __init__(self, path, *, subfile_offsets=None, submap_id=None,
                 submap_name=None,
                 _shared_data=None, _shared_xor=None):
        self.path = path
        if _shared_data is not None:
            self._data = _shared_data
            self._xor_key = _shared_xor or 0
            self._raw_size = len(_shared_data)
        else:
            with open(path, 'rb') as f: raw = f.read()
            self._raw_size = len(raw)
            self._data, self._xor_key = _decode_xor(raw)

        if subfile_offsets is not None:
            self._subfiles = dict(subfile_offsets)
        else:
            self._subfiles = _find_subfiles(self._data)
        self.submap_id = submap_id

        if 'TRE' not in self._subfiles or 'RGN' not in self._subfiles:
            raise GarminImgError(f"TRE or RGN not found in {path}. "
                                 f"Found: {list(self._subfiles.keys())}")

        rgn_off = self._subfiles['RGN']
        rr = _Reader(self._data, rgn_off)
        rr.u16(); rr.fixed(10); rr.u8(); rr.u8()
        rr.u16(); rr.u8(); rr.u8(); rr.u8(); rr.u8(); rr.u8()
        rr.u32()
        rgn_data_len = rr.u32()

        (self._levels, self._subdivisions,
         n, e, s, w, locked, map_id) = _parse_tre(
            self._data, self._subfiles['TRE'], rgn_data_len)

        self._lbl = (LBL(self._data, self._subfiles['LBL'])
                     if 'LBL' in self._subfiles else None)

        raw_name = self._data[0x2C:0x2C+20]
        i = raw_name.find(b'\x00')
        name = (raw_name[:i].decode('latin-1','replace').strip()
                if i > 0 else "")

        self.metadata = Metadata(
            name=name or os.path.basename(path),
            map_id=map_id,
            codepage=self._lbl.codepage if self._lbl else 1252,
            encoding=self._lbl.encoding if self._lbl else 0,
            north=n, east=e, south=s, west=w,
            locked=locked, size_bytes=self._raw_size,
            submap_id=submap_id,
            submap_name=submap_name)

        self._points = None
        self._polylines = None
        self._polygons = None

    def get_display_name(self):
        """
        Human-readable map name.

        Priority:
          1. submap_name from MPS (for container submaps)
          2. name from IMG header (for single files)
          3. file name without path
        """
        if self.metadata.submap_name:
            return self.metadata.submap_name
        if self.metadata.name:
            return self.metadata.name
        return os.path.basename(self.path)

    def _iter_objects(self, kinds):
        rgn_off = self._subfiles['RGN']
        r = _Reader(self._data, rgn_off)
        r.u16(); r.fixed(10); r.u8(); r.u8()
        r.u16(); r.u8(); r.u8(); r.u8(); r.u8(); r.u8()
        rgn_data_start = rgn_off + r.u32()

        for sd in self._subdivisions:
            if sd.elems == 0 or sd.rgn_end <= sd.rgn_start: continue
            abs_start = rgn_data_start + sd.rgn_start
            abs_end   = rgn_data_start + sd.rgn_end
            if abs_start >= len(self._data) or abs_start >= abs_end: continue

            order = []
            if sd.elems & 0x10: order.append('pts')
            if sd.elems & 0x20: order.append('idx')
            if sd.elems & 0x40: order.append('pln')
            if sd.elems & 0x80: order.append('pgn')
            if not order: continue

            n_ptrs = len(order) - 1
            olast = abs_start + 2 * n_ptrs
            starts = {}; pp = abs_start
            for i, t in enumerate(order):
                if i == 0: starts[t] = olast
                else:
                    off = struct.unpack_from('<H', self._data, pp)[0]; pp += 2
                    starts[t] = abs_start + off
            ends = {}
            for i, t in enumerate(order):
                ends[t] = (starts[order[i+1]]
                           if i+1 < len(order) else abs_end)

            if 'pts' in kinds and 'pts' in starts:
                yield from _parse_points(self._data, starts['pts'],
                                         ends['pts'], sd, self._lbl)
            if 'idx' in kinds and 'idx' in starts:
                yield from _parse_points(self._data, starts['idx'],
                                         ends['idx'], sd, self._lbl)
            if 'pln' in kinds and 'pln' in starts:
                yield from _parse_polys(self._data, starts['pln'],
                                        ends['pln'], sd, self._lbl, False)
            if 'pgn' in kinds and 'pgn' in starts:
                yield from _parse_polys(self._data, starts['pgn'],
                                        ends['pgn'], sd, self._lbl, True)

    def iter_points(self):    yield from self._iter_objects({'pts','idx'})
    def iter_polylines(self): yield from self._iter_objects({'pln'})
    def iter_polygons(self):  yield from self._iter_objects({'pgn'})

    def iter_all(self, kinds=('point','line','polygon')):
        if 'point'   in kinds: yield from self.points
        if 'line'    in kinds: yield from self.polylines
        if 'polygon' in kinds: yield from self.polygons

    @property
    def points(self):
        if self._points is None: self._points = list(self.iter_points())
        return self._points
    @property
    def polylines(self):
        if self._polylines is None: self._polylines = list(self.iter_polylines())
        return self._polylines
    @property
    def polygons(self):
        if self._polygons is None: self._polygons = list(self.iter_polygons())
        return self._polygons
    @property
    def levels(self): return self._levels
    @property
    def subdivisions(self): return self._subdivisions

    def clear_cache(self):
        self._points = None; self._polylines = None; self._polygons = None
        if self._lbl is not None: self._lbl.clear_cache()

    def has_type(self, ptype, kind='any'):
        ptype = int(ptype)
        if kind in ('point','any') and any(p.type == ptype for p in self.points): return True
        if kind in ('line','any')  and any(pl.type == ptype for pl in self.polylines): return True
        if kind in ('polygon','any') and any(pg.type == ptype for pg in self.polygons): return True
        return False

    def count_type(self, ptype, kind='any'):
        ptype = int(ptype); n = 0
        if kind in ('point','any'):   n += sum(1 for p in self.points if p.type == ptype)
        if kind in ('line','any'):    n += sum(1 for pl in self.polylines if pl.type == ptype)
        if kind in ('polygon','any'): n += sum(1 for pg in self.polygons if pg.type == ptype)
        return n

    def types_present(self):
        from collections import Counter
        return {'point':   dict(Counter(p.type  for p  in self.points)),
                'line':    dict(Counter(pl.type for pl in self.polylines)),
                'polygon': dict(Counter(pg.type for pg in self.polygons))}

    def filter(self, *, type=None, types=None, kind=None,
               level=None, group=None, predicate=None):
        wanted = (kind,) if kind and kind != 'any' else ('point','line','polygon')
        if types is not None: types = set(int(t) for t in types)
        if type  is not None: types = {int(type)}
        result = []
        for obj in self.iter_all(wanted):
            if types is not None and obj.type not in types: continue
            if level is not None and obj.level != level: continue
            if group is not None:
                if getattr(obj, 'type_group', None) != group: continue
            if predicate is not None and not predicate(obj): continue
            result.append(obj)
        return result

    def points_by_type(self, ptype):
        return [p for p in self.points if p.type == int(ptype)]

    def polylines_by_type(self, *types):
        s = set(int(t) for t in types)
        return [p for p in self.polylines if p.type in s]

    def polylines_by_level(self, level):
        return [p for p in self.polylines if p.level == level]

    def polylines_by_group(self, group):
        return [p for p in self.polylines if p.type_group == group]

    def polygons_by_type(self, *types):
        s = set(int(t) for t in types)
        return [p for p in self.polygons if p.type in s]

    def near(self, lat, lon, radius_km, kind='any', limit=None):
        R = 6371.0
        def d(lo1, la1, lo2, la2):
            dlat = math.radians(la2-la1); dlon = math.radians(lo2-lo1)
            a = (math.sin(dlat/2)**2 + math.cos(math.radians(la1))
                 * math.cos(math.radians(la2)) * math.sin(dlon/2)**2)
            return 2 * R * math.asin(math.sqrt(a))
        result = []
        wanted = (kind,) if kind != 'any' else ('point','line','polygon')
        if 'point' in wanted:
            for p in self.points:
                dd = d(lon, lat, p.lon, p.lat)
                if dd <= radius_km: result.append((dd, p))
        if 'line' in wanted:
            for pl in self.polylines:
                dd = min(d(lon, lat, x, y) for x, y in pl.points)
                if dd <= radius_km: result.append((dd, pl))
        if 'polygon' in wanted:
            for pg in self.polygons:
                dd = min(d(lon, lat, x, y) for x, y in pg.points)
                if dd <= radius_km: result.append((dd, pg))
        result.sort(key=lambda t: t[0])
        if limit: result = result[:limit]
        return result

    def search_labels(self, pattern, kind='any', regex=False, ignore_case=True):
        flags = _re.IGNORECASE if ignore_case else 0
        if regex:
            rx = _re.compile(pattern, flags)
            def m(s): return bool(rx.search(s))
        else:
            if ignore_case:
                low = pattern.lower()
                def m(s): return low in s.lower()
            else:
                def m(s): return pattern in s
        wanted = (kind,) if kind != 'any' else ('point','line','polygon')
        return [o for o in self.iter_all(wanted) if o.label and m(o.label)]

    def longest(self, n=10, kind='line', group=None, level=None):
        items = self.filter(kind=kind, group=group, level=level)
        scored = [(line_length_m(o.points), o) for o in items]
        scored.sort(key=lambda t: t[0], reverse=True)
        return scored[:n]

    def total_length_m(self, group=None, kind='line'):
        return sum(line_length_m(o.points)
                   for o in self.filter(kind=kind, group=group))

    def bbox_of(self, type=None, kind=None):
        objs = self.filter(type=type, kind=kind)
        pts = []
        for o in objs:
            if hasattr(o, 'points'): pts.extend(o.points)
            else: pts.append((o.lon, o.lat))
        return bbox(pts) if pts else None

    def summary(self):
        out = [f"Map: {self.get_display_name()!r} "
               f"(id={self.metadata.map_id}, "
               f"{self.metadata.size_bytes/1024:.1f} KB)"]
        out.append(f"Bounds: N={self.metadata.north:.4f} "
                   f"S={self.metadata.south:.4f} "
                   f"W={self.metadata.west:.4f} "
                   f"E={self.metadata.east:.4f}")
        out.append(f"Encoding: cp{self.metadata.codepage}, "
                   f"{self.metadata.encoding}-bit")
        out.append(f"Levels: {len(self.levels)}, "
                   f"subdivisions: {len(self.subdivisions)}")
        out.append(f"Points:   {len(self.points)}")
        out.append(f"Lines:    {len(self.polylines)}")
        out.append(f"Polygons: {len(self.polygons)}")
        present = self.types_present()
        for kind in ('point', 'line', 'polygon'):
            d = present[kind]
            if not d: continue
            out.append(f"\n{kind.upper()} by type:")
            for t, n in sorted(d.items(), key=lambda kv: -kv[1]):
                if kind == 'point':   name = guess_point_type(t)
                elif kind == 'line':  name = guess_line_type(t)
                else:                 name = guess_polygon_type(t)
                out.append(f"  0x{t:04X}  {n:>5}  {name}")
        return "\n".join(out)

    def __repr__(self):
        sid = f", submap_id={self.submap_id!r}" if self.submap_id else ""
        return (f"GarminIMG({self.path!r}, "
                f"name={self.get_display_name()!r}{sid})")

    # ------------------------------------------------------------
    # Export to MP
    # ------------------------------------------------------------
    def export_mp(self, path, *, levels=None, snap_to_grid=False):
        """
        Export to Polish Format.

        snap_to_grid=True — coordinates are rounded to the Garmin grid
        (step 360 / 2^bits_per_coord for each level) before writing.
        This makes the MP file compatible with GPSMapEdit: coordinates
        won't be shifted on load (the "Snap to grid" checkbox in Settings).

        snap_to_grid=False — coordinates are written with normal rounding
        to 5-6 decimal places (as before).
        """
        level_bits = {lvl.zoom: lvl.bits for lvl in self.levels}

        max_bits = max(l.bits for l in self.levels) if self.levels else 24
        if snap_to_grid:
            prec = 7
        else:
            prec = 6 if max_bits >= 25 else 5
        fmt = f"{{:.{prec}f}}"

        def snap_value(value, level):
            """
            Round coordinate to the Garmin grid for the given level.

            Grid step = 360 / 2^bits_per_coord.
            Uses round-half-away-from-zero (same as C++ round() and
            GPSMapEdit), which gives identical results for positive
            and negative coordinates — important for maps in the
            southern hemisphere and western longitudes.
            """
            if not snap_to_grid:
                return value
            bits = level_bits.get(level)
            if not bits:
                return value
            step = 360.0 / (1 << bits)
            scaled = value / step
            if scaled >= 0:
                snapped = math.floor(scaled + 0.5)
            else:
                snapped = math.ceil(scaled - 0.5)
            return snapped * step

        def ok(lvl):
            return levels is None or lvl in levels

        def rnd(p):
            return (round(p[0], 5), round(p[1], 5))

        with open(path, 'w', encoding='cp1251',
                  errors='replace', newline='') as f:
            f.write("; Exported by garmin_img\r\n")
            f.write(f"; Source: {os.path.basename(self.path)}\r\n")
            f.write(f"; Name: {self.get_display_name()}\r\n")
            if self.submap_id:
                f.write(f"; Submap: {self.submap_id}\r\n")
            if snap_to_grid:
                f.write("; Coordinates snapped to Garmin grid\r\n")
            f.write("\r\n[IMG ID]\r\n")
            f.write(f"CodePage={self.metadata.codepage}\r\n")
            f.write(f"LblCoding={self.metadata.encoding}\r\n")
            f.write(f"ID={self.metadata.map_id}\r\n")
            f.write(f"Name={self.get_display_name()}\r\n")
            f.write("TreSize=1253\r\nRgnLimit=127\r\nTransparent=Y\r\n")
            f.write("POIIndex=Y\r\nPOINumberFirst=Y\r\nPOIZipFirst=Y\r\n")
            ls = sorted(self.levels, key=lambda x: x.zoom)
            f.write(f"Levels={len(ls)}\r\n")
            for i, lvl in enumerate(ls):
                f.write(f"Level{i}={lvl.bits}\r\n")
            for i, lvl in enumerate(ls):
                f.write(f"Zoom{i}={lvl.zoom}\r\n")
            f.write("[END-IMG ID]\r\n\r\n")

            # --- POI ---
            poi_groups = {}
            for p in self.points:
                if not ok(p.level): continue
                key = (p.type, p.label, p.subtype,
                       round(p.lat, 5), round(p.lon, 5))
                poi_groups.setdefault(key, []).append(p)
            for key, group in poi_groups.items():
                ptype, label, sub, _la, _lo = key
                by_level = {}
                for p in group:
                    by_level.setdefault(p.level, []).append(p)
                if all(len(v) == 1 for v in by_level.values()):
                    f.write("[POI]\r\n")
                    f.write(f"Type=0x{ptype:x}\r\n")
                    if sub is not None:
                        f.write(f"SubType=0x{sub:x}\r\n")
                    if label:
                        f.write(f"Label={label}\r\n")
                    for lvl in sorted(by_level):
                        p = by_level[lvl][0]
                        lat = snap_value(p.lat, p.level)
                        lon = snap_value(p.lon, p.level)
                        f.write(f"Data{lvl}="
                                f"({fmt.format(lat)},{fmt.format(lon)})\r\n")
                    f.write("[END]\r\n\r\n")
                else:
                    for p in group:
                        lat = snap_value(p.lat, p.level)
                        lon = snap_value(p.lon, p.level)
                        f.write("[POI]\r\n")
                        f.write(f"Type=0x{ptype:x}\r\n")
                        if sub is not None:
                            f.write(f"SubType=0x{sub:x}\r\n")
                        if label:
                            f.write(f"Label={label}\r\n")
                        f.write(f"Data{p.level}="
                                f"({fmt.format(lat)},{fmt.format(lon)})\r\n")
                        f.write("[END]\r\n\r\n")

            # --- Polylines ---
            line_groups = {}
            for pl in self.polylines:
                if not ok(pl.level) or not pl.points: continue
                first = rnd(pl.points[0])
                key = (pl.type, pl.label, first, pl.direction, pl.in_net)
                line_groups.setdefault(key, []).append(pl)
            for key, group in line_groups.items():
                t, lbl, _first, dir_, in_net = key
                by_level = {}
                for pl in group:
                    by_level.setdefault(pl.level, []).append(pl)

                def write_line_block(pl):
                    return ",".join(
                        f"({fmt.format(snap_value(y, pl.level))},"
                        f"{fmt.format(snap_value(x, pl.level))})"
                        for (x, y) in pl.points)

                if all(len(v) == 1 for v in by_level.values()):
                    f.write("[POLYLINE]\r\n")
                    f.write(f"Type=0x{t:x}\r\n")
                    if lbl: f.write(f"Label={lbl}\r\n")
                    if dir_: f.write("DirIndicator=1\r\n")
                    for lvl in sorted(by_level):
                        pl = by_level[lvl][0]
                        f.write(f"Data{lvl}={write_line_block(pl)}\r\n")
                    f.write("[END]\r\n\r\n")
                else:
                    for pl in group:
                        f.write("[POLYLINE]\r\n")
                        f.write(f"Type=0x{t:x}\r\n")
                        if lbl: f.write(f"Label={lbl}\r\n")
                        if dir_: f.write("DirIndicator=1\r\n")
                        f.write(f"Data{pl.level}={write_line_block(pl)}\r\n")
                        f.write("[END]\r\n\r\n")

            # --- Polygons ---
            poly_groups = {}
            for pg in self.polygons:
                if not ok(pg.level) or not pg.points: continue
                first = rnd(pg.points[0])
                key = (pg.type, pg.label, first)
                poly_groups.setdefault(key, []).append(pg)
            for key, group in poly_groups.items():
                t, lbl, _first = key
                by_level = {}
                for pg in group:
                    by_level.setdefault(pg.level, []).append(pg)

                def write_poly_block(pg):
                    return ",".join(
                        f"({fmt.format(snap_value(y, pg.level))},"
                        f"{fmt.format(snap_value(x, pg.level))})"
                        for (x, y) in pg.points)

                if all(len(v) == 1 for v in by_level.values()):
                    f.write("[POLYGON]\r\n")
                    f.write(f"Type=0x{t:x}\r\n")
                    if lbl: f.write(f"Label={lbl}\r\n")
                    for lvl in sorted(by_level):
                        pg = by_level[lvl][0]
                        f.write(f"Data{lvl}={write_poly_block(pg)}\r\n")
                    f.write("[END]\r\n\r\n")
                else:
                    for pg in group:
                        f.write("[POLYGON]\r\n")
                        f.write(f"Type=0x{t:x}\r\n")
                        if lbl: f.write(f"Label={lbl}\r\n")
                        f.write(f"Data{pg.level}={write_poly_block(pg)}\r\n")
                        f.write("[END]\r\n\r\n")

    def export_geojson(self, path):
        features = []
        for p in self.points:
            features.append({"type": "Feature",
                "geometry": {"type": "Point", "coordinates": [p.lon, p.lat]},
                "properties": {"kind": p.kind, "type_hex": f"0x{p.type:04X}",
                    "type_name": p.type_name, "subtype": p.subtype,
                    "label": p.label, "level": p.level}})
        for pl in self.polylines:
            features.append({"type": "Feature",
                "geometry": {"type": "LineString",
                             "coordinates": [[x, y] for (x, y) in pl.points]},
                "properties": {"type_hex": f"0x{pl.type:02X}",
                    "type_name": pl.type_name, "type_group": pl.type_group,
                    "label": pl.label, "level": pl.level,
                    "direction": pl.direction, "in_net": pl.in_net,
                    "length_m": round(line_length_m(pl.points), 1)}})
        for pg in self.polygons:
            features.append({"type": "Feature",
                "geometry": {"type": "Polygon",
                             "coordinates": [[[x, y] for (x, y) in pg.points]]},
                "properties": {"type_hex": f"0x{pg.type:02X}",
                    "type_name": pg.type_name, "label": pg.label,
                    "level": pg.level}})
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({"type": "FeatureCollection", "features": features},
                      f, ensure_ascii=False)

    def export_gpx(self, path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write('<gpx version="1.1" creator="garmin_img"\n')
            f.write('     xmlns="http://www.topografix.com/GPX/1/1">\n')
            for p in self.points:
                f.write(f'  <wpt lat="{p.lat:.7f}" lon="{p.lon:.7f}">\n')
                if p.label:
                    f.write(f'    <name>{_xml_escape(p.label)}</name>\n')
                f.write(f'    <type>{p.type:04X}</type>\n  </wpt>\n')
            for pl in self.polylines:
                f.write('  <trk>\n    <trkseg>\n')
                for (x, y) in pl.points:
                    f.write(f'      <trkpt lat="{y:.7f}" lon="{x:.7f}"/>\n')
                f.write('    </trkseg>\n  </trk>\n')
            f.write('</gpx>\n')

    def export_csv(self, path):
        with open(path, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            w.writerow(['label','lat','lon','type_hex','type_name',
                        'subtype','level'])
            for p in self.points:
                w.writerow([p.label, f"{p.lat:.7f}", f"{p.lon:.7f}",
                            f"0x{p.type:04X}", p.type_name,
                            f"0x{p.subtype:02X}" if p.subtype is not None else "",
                            p.level])

    def export_shapefile(self, base_path, *, kinds=('lines',),
                         filter_types=None, filter_group=None,
                         filter_level=None):
        try:
            import shapefile
        except ImportError:
            raise GarminImgError("pyshp is required. Install: pip install pyshp")
        if 'lines' in kinds:      shp_type = shapefile.POLYLINE
        elif 'points' in kinds:   shp_type = shapefile.POINT
        elif 'polygons' in kinds: shp_type = shapefile.POLYGON
        else: raise GarminImgError(f"Unknown kinds={kinds}")

        w = shapefile.Writer(base_path, shapeType=shp_type)
        w.encoding = 'utf-8'
        w.field('ID',         'N', 10, 0)
        w.field('TYPE_HEX',   'C', 8)
        w.field('TYPE_NAME',  'C', 64)
        w.field('TYPE_GROUP', 'C', 20)
        w.field('ZOOM',       'N', 2, 0)
        w.field('N_POINTS',   'N', 6, 0)
        w.field('LENGTH_M',   'N', 12, 1)
        w.field('ONEWAY',     'N', 1, 0)
        w.field('ROUTABLE',   'N', 1, 0)
        w.field('SUBTYPE',    'N', 3, 0)
        w.field('MINLON',     'N', 12, 7)
        w.field('MINLAT',     'N', 12, 7)
        w.field('MAXLON',     'N', 12, 7)
        w.field('MAXLAT',     'N', 12, 7)
        w.field('LABEL',      'C', 254)

        n = 0
        def ok(p, g, l):
            if filter_types is not None and p not in filter_types: return False
            if filter_group is not None and g != filter_group: return False
            if filter_level is not None and l != filter_level: return False
            return True

        if 'lines' in kinds:
            for pl in self.polylines:
                if not ok(pl.type, pl.type_group, pl.level): continue
                w.line([[(lon, lat) for (lon, lat) in pl.points]])
                bb = bbox(pl.points)
                w.record(ID=n, TYPE_HEX=f"0x{pl.type:02X}",
                    TYPE_NAME=pl.type_name, TYPE_GROUP=pl.type_group,
                    ZOOM=pl.level, N_POINTS=len(pl.points),
                    LENGTH_M=round(line_length_m(pl.points), 1),
                    ONEWAY=1 if pl.direction else 0,
                    ROUTABLE=1 if pl.in_net else 0, SUBTYPE=0,
                    MINLON=bb[0], MINLAT=bb[1], MAXLON=bb[2], MAXLAT=bb[3],
                    LABEL=pl.label or "")
                n += 1
        if 'points' in kinds:
            for p in self.points:
                if not ok(p.type, "", p.level): continue
                w.point(p.lon, p.lat)
                w.record(ID=n, TYPE_HEX=f"0x{p.type:04X}",
                    TYPE_NAME=p.type_name, TYPE_GROUP="",
                    ZOOM=p.level, N_POINTS=1, LENGTH_M=0.0,
                    ONEWAY=0, ROUTABLE=0,
                    SUBTYPE=p.subtype if p.subtype is not None else 0,
                    MINLON=p.lon, MINLAT=p.lat, MAXLON=p.lon, MAXLAT=p.lat,
                    LABEL=p.label or "")
                n += 1
        if 'polygons' in kinds:
            for pg in self.polygons:
                if not ok(pg.type, "", pg.level): continue
                w.poly([[(lon, lat) for (lon, lat) in pg.points]])
                bb = bbox(pg.points)
                w.record(ID=n, TYPE_HEX=f"0x{pg.type:02X}",
                    TYPE_NAME=pg.type_name, TYPE_GROUP="",
                    ZOOM=pg.level, N_POINTS=len(pg.points),
                    LENGTH_M=0.0, ONEWAY=0, ROUTABLE=0, SUBTYPE=0,
                    MINLON=bb[0], MINLAT=bb[1], MAXLON=bb[2], MAXLAT=bb[3],
                    LABEL=pg.label or "")
                n += 1

        w.close()
        with open(f"{base_path}.prj", 'w') as f:
            f.write('GEOGCS["GCS_WGS_1984",'
                    'DATUM["D_WGS_1984",'
                    'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
                    'PRIMEM["Greenwich",0.0],'
                    'UNIT["Degree",0.0174532925199433]]')
        with open(f"{base_path}.cpg", 'w') as f:
            f.write("UTF-8")
        log.info("Shapefile: %s.shp (%d objects)", base_path, n)

    def export_all_shapefiles(self, out_dir, *, level=None,
                              kinds=('points', 'lines', 'polygons')):
        """
        Export all layers (points/lines/polygons) with a single call.

        Creates points.shp, lines.shp, polygons.shp in out_dir (only
        those layers that contain objects).

        Returns a dict {'points': N, 'lines': N, 'polygons': N}.
        """
        os.makedirs(out_dir, exist_ok=True)

        result = {}
        counter = {
            'points':   lambda: sum(1 for p in self.iter_points()
                                    if level is None or p.level == level),
            'lines':    lambda: sum(1 for pl in self.iter_polylines()
                                    if level is None or pl.level == level),
            'polygons': lambda: sum(1 for pg in self.iter_polygons()
                                    if level is None or pg.level == level),
        }
        for kind in kinds:
            n = counter[kind]()
            if n > 0:
                self.export_shapefile(
                    os.path.join(out_dir, kind),
                    kinds=(kind,), filter_level=level)
            result[kind] = n
        return result

    def export_by_types_shapefiles(self, out_dir, *, level=None,
                                    kinds=('points', 'lines', 'polygons')):
        """
        Export with per-type split.

        File name: <prefix>_<hex>.shp
            points_1400.shp     — points of type 0x1400
            points_1E00.shp     — points of type 0x1E00
            lines_06.shp        — lines of type 0x06
            polygons_50.shp     — polygons of type 0x50

        All files in a single out_dir.
        """
        from collections import Counter
        os.makedirs(out_dir, exist_ok=True)
        result = {}

        for kind in kinds:
            if kind == 'points':
                counter = Counter(p.type for p in self.iter_points()
                                  if level is None or p.level == level)
                fmt = lambda t: f"{t:04X}"
                prefix = "points"
            elif kind == 'lines':
                counter = Counter(pl.type for pl in self.iter_polylines()
                                  if level is None or pl.level == level)
                fmt = lambda t: f"{t:02X}"
                prefix = "lines"
            elif kind == 'polygons':
                counter = Counter(pg.type for pg in self.iter_polygons()
                                  if level is None or pg.level == level)
                fmt = lambda t: f"{t:02X}"
                prefix = "polygons"
            else:
                continue

            if not counter:
                continue

            result[kind] = {}
            for t in sorted(counter):
                fname = f"{prefix}_{fmt(t)}"
                base = os.path.join(out_dir, fname)
                self.export_shapefile(base, kinds=(kind,),
                                      filter_types={t},
                                      filter_level=level)
                result[kind][t] = base + ".shp"
                log.info("%s.shp: %d objects", fname, counter[t])

        return result

    def polygonize_shapefile(self, base_path, *,
                             types=(0x1D,),
                             tolerance=1e-6,
                             filter_level=None):
        """Export closed lines of the given types as polygons."""
        try:
            import shapefile
        except ImportError:
            raise GarminImgError("pyshp is required. Install: pip install pyshp")

        types = set(int(t) for t in types)

        w = shapefile.Writer(base_path, shapeType=shapefile.POLYGON)
        w.encoding = 'utf-8'
        w.field('ID',         'N', 10, 0)
        w.field('SRC_TYPE',   'C', 8)
        w.field('SRC_NAME',   'C', 64)
        w.field('TYPE_GROUP', 'C', 20)
        w.field('ZOOM',       'N', 2, 0)
        w.field('N_POINTS',   'N', 6, 0)
        w.field('LENGTH_M',   'N', 12, 1)
        w.field('LABEL',      'C', 254)
        w.field('MINLON',     'N', 12, 7)
        w.field('MINLAT',     'N', 12, 7)
        w.field('MAXLON',     'N', 12, 7)
        w.field('MAXLAT',     'N', 12, 7)

        n_closed = 0
        n_open = 0
        for pl in self.iter_polylines():
            if pl.type not in types: continue
            if filter_level is not None and pl.level != filter_level: continue
            if len(pl.points) < 3: continue

            first = pl.points[0]
            last = pl.points[-1]
            d = abs(first[0] - last[0]) + abs(first[1] - last[1])
            if d > tolerance:
                n_open += 1
                continue

            pts = list(pl.points)
            bb = bbox(pts)
            w.poly([pts])
            w.record(
                ID=n_closed,
                SRC_TYPE=f"0x{pl.type:02X}",
                SRC_NAME=pl.type_name,
                TYPE_GROUP=pl.type_group,
                ZOOM=pl.level,
                N_POINTS=len(pts),
                LENGTH_M=round(line_length_m(pts), 1),
                LABEL=pl.label or "",
                MINLON=bb[0], MINLAT=bb[1],
                MAXLON=bb[2], MAXLAT=bb[3])
            n_closed += 1

        w.close()
        with open(f"{base_path}.prj", 'w') as f:
            f.write('GEOGCS["GCS_WGS_1984",'
                    'DATUM["D_WGS_1984",'
                    'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
                    'PRIMEM["Greenwich",0.0],'
                    'UNIT["Degree",0.0174532925199433]]')
        with open(f"{base_path}.cpg", 'w') as f:
            f.write("UTF-8")
        log.info("Polygonize %s: %d polygons, %d unclosed dropped",
                 base_path, n_closed, n_open)
        return n_closed, n_open

    def export_dedup_shapefile(self, base_path, *, kind='points',
                                filter_types=None, filter_level=None):
        """Export with deduplication of objects across zoom levels."""
        try:
            import shapefile as shp
        except ImportError:
            raise GarminImgError("pyshp is required. Install: pip install pyshp")

        shp_type = {'points': shp.POINT,
                    'lines': shp.POLYLINE,
                    'polygons': shp.POLYGON}[kind]

        w = shp.Writer(base_path, shapeType=shp_type)
        w.encoding = 'utf-8'
        w.field('ID',         'N', 10, 0)
        w.field('TYPE_HEX',   'C', 8)
        w.field('TYPE_NAME',  'C', 64)
        w.field('TYPE_GROUP', 'C', 20)
        w.field('MIN_LEVEL',  'N', 2, 0)
        w.field('N_LEVELS',   'N', 2, 0)
        w.field('LABEL',      'C', 254)

        obj_kind = {'points': 'point', 'lines': 'line',
                    'polygons': 'polygon'}[kind]

        groups = {}
        for o in self.iter_all((obj_kind,)):
            if filter_types is not None and o.type not in filter_types:
                continue
            if filter_level is not None and o.level != filter_level:
                continue
            if kind == 'points':
                key = (o.type, o.label, round(o.lat, 5), round(o.lon, 5))
            else:
                key = (o.type, o.label, tuple(o.points[:3]))
            groups.setdefault(key, []).append(o)

        n = 0
        for key, objs in groups.items():
            obj = objs[0]
            levels = sorted(set(o.level for o in objs))
            if kind == 'points':
                w.point(obj.lon, obj.lat)
                w.record(ID=n, TYPE_HEX=f"0x{obj.type:04X}",
                         TYPE_NAME=obj.type_name, TYPE_GROUP="",
                         MIN_LEVEL=levels[0], N_LEVELS=len(levels),
                         LABEL=obj.label or "")
            else:
                pts = list(obj.points)
                if kind == 'lines': w.line([pts])
                else:               w.poly([pts])
                w.record(ID=n, TYPE_HEX=f"0x{obj.type:02X}",
                         TYPE_NAME=obj.type_name,
                         TYPE_GROUP=getattr(obj, 'type_group', ''),
                         MIN_LEVEL=levels[0], N_LEVELS=len(levels),
                         LABEL=obj.label or "")
            n += 1
        w.close()

        with open(f"{base_path}.prj", 'w') as f:
            f.write('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
                    'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
                    'PRIMEM["Greenwich",0.0],'
                    'UNIT["Degree",0.0174532925199433]]')
        with open(f"{base_path}.cpg", 'w') as f:
            f.write("UTF-8")
        log.info("%s: %d unique out of %d", base_path, n,
                 sum(len(v) for v in groups.values()))
        return n

    def extract_shape(self, ptype, base_path, kind='any'):
        ptype = int(ptype)
        if kind == 'any':
            if any(pl.type == ptype for pl in self.polylines): kind = 'line'
            elif any(p.type == ptype for p in self.points): kind = 'point'
            elif any(pg.type == ptype for pg in self.polygons): kind = 'polygon'
            else: return 0
        if kind == 'line':
            n = sum(1 for pl in self.polylines if pl.type == ptype)
            if n: self.export_shapefile(base_path, kinds=('lines',),
                                        filter_types={ptype})
            return n
        if kind == 'point':
            n = sum(1 for p in self.points if p.type == ptype)
            if n: self.export_shapefile(base_path, kinds=('points',),
                                        filter_types={ptype})
            return n
        if kind == 'polygon':
            n = sum(1 for pg in self.polygons if pg.type == ptype)
            if n: self.export_shapefile(base_path, kinds=('polygons',),
                                        filter_types={ptype})
            return n
        raise ValueError(f"kind must be line/point/polygon, not {kind!r}")

    def export_roads_shapefile(self, base_path, level=None):
        self.export_shapefile(base_path, kinds=('lines',),
                              filter_group="road", filter_level=level)

    def export_water_shapefile(self, base_path):
        self.export_shapefile(base_path, kinds=('lines',),
                              filter_group="water")


# ================================================================
# Container
# ================================================================

class GarminIMGContainer:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f: raw = f.read()
        self._raw_size = len(raw)
        self._data, self._xor_key = _decode_xor(raw)
        if self._data[0x10:0x16] != b'DSKIMG':
            raise GarminImgError(f"Not an IMG file: {path}")
        self._groups = _fat_groups(self._data)
        self._block_size = 1 << (self._data[0x61] + self._data[0x62])
        self._mps = None
        self._submaps = []
        self.n_nt_skipped = 0
        self.n_service_skipped = 0
        self._build_submaps()

    def _get_mps(self):
        if self._mps is not None: return self._mps
        self._mps = {}
        for name, types in self._groups.items():
            if 'MPS' in types:
                first = sorted(types['MPS'], key=lambda e: e.part)[0]
                if first.blocks:
                    try:
                        self._mps = _parse_mps(
                            self._data, first.blocks[0] * self._block_size)
                    except Exception as e:
                        log.warning("MPS parse error: %s", e)
                break
        return self._mps

    def _build_submaps(self):
        skipped_nt = []; skipped_srv = []
        mps = self._get_mps()

        for submap_id, types in self._groups.items():
            if _is_service_only(types):
                skipped_srv.append(submap_id); continue
            if _is_nt_img(types):
                skipped_nt.append(submap_id); continue
            if not _is_classic_img(types): continue
            offsets = {}
            for stype, entries in types.items():
                if stype in _SERVICE_SUBFILES: continue
                first = sorted(entries, key=lambda e: e.part)[0]
                if first.blocks:
                    offsets[stype] = first.blocks[0] * self._block_size
            if 'TRE' not in offsets or 'RGN' not in offsets: continue

            sid_int = _hex_id_to_int(submap_id)
            info = mps.get(sid_int, {}) if sid_int is not None else {}
            submap_name = (info.get('segment')
                           or info.get('name')
                           or info.get('area')
                           or None)

            try:
                img = GarminIMG(self.path, subfile_offsets=offsets,
                                submap_id=submap_id,
                                submap_name=submap_name,
                                _shared_data=self._data,
                                _shared_xor=self._xor_key)
                self._submaps.append(img)
            except Exception as e:
                log.warning("Failed to read %s: %s", submap_id, e)
        self.n_nt_skipped = len(skipped_nt)
        self.n_service_skipped = len(skipped_srv)
        if skipped_nt:
            log.info("[NT] Skipped NT maps: %d", len(skipped_nt))
        if skipped_srv:
            log.info("[service] Skipped: %d: %s",
                     len(skipped_srv), ", ".join(skipped_srv))
        log.info("[classic] Maps loaded: %d", len(self._submaps))

    def __len__(self): return len(self._submaps)
    def __iter__(self): return iter(self._submaps)
    def __getitem__(self, idx): return self._submaps[idx]
    @property
    def submaps(self): return list(self._submaps)

    def list_light(self):
        mps = self._get_mps()
        out = []
        for submap_id, types in self._groups.items():
            if _is_service_only(types): continue
            total_size = sum(e.size for et in types.values() for e in et)
            sections = ','.join(sorted(types.keys()))
            if _is_classic_img(types): kind = 'classic'
            elif _is_nt_img(types):   kind = 'NT'
            else:                     kind = '?'
            seg_int = _hex_id_to_int(submap_id)
            info = mps.get(seg_int, {}) if seg_int is not None else {}
            name = (info.get('segment') or info.get('name')
                    or info.get('area') or '')
            out.append({'id': submap_id, 'kind': kind, 'size': total_size,
                        'sections': sections, 'name': name,
                        'pid': info.get('pid'), 'fid': info.get('fid')})
        return out

    def list_submaps(self):
        out = []
        for img in self._submaps:
            out.append({
                "id": img.submap_id, "name": img.get_display_name(),
                "map_id": img.metadata.map_id,
                "points":   sum(1 for _ in img.iter_points()),
                "polylines":sum(1 for _ in img.iter_polylines()),
                "polygons": sum(1 for _ in img.iter_polygons()),
                "levels": len(img.levels),
                "bounds": {"north": img.metadata.north,
                           "east":  img.metadata.east,
                           "south": img.metadata.south,
                           "west":  img.metadata.west},
                "locked": img.metadata.locked})
            img.clear_cache()
        return out

    def find(self, submap_id):
        for img in self._submaps:
            if img.submap_id == submap_id: return img
        return None

    def extract_all(self, out_dir, *, export='shapefile',
                    kinds=('lines',), filter_group=None, clear_after=True):
        os.makedirs(out_dir, exist_ok=True)
        created = []
        for img in self._submaps:
            sid = img.submap_id or f"submap_{img.metadata.map_id}"
            safe = _safe_folder_name(img.get_display_name(), sid)
            if export == 'shapefile':
                base = os.path.join(out_dir, safe)
                img.export_shapefile(base, kinds=kinds,
                                     filter_group=filter_group)
                created.append(f"{base}.shp")
            elif export == 'geojson':
                p = os.path.join(out_dir, f"{safe}.geojson")
                img.export_geojson(p); created.append(p)
            elif export == 'mp':
                p = os.path.join(out_dir, f"{safe}.mp")
                img.export_mp(p); created.append(p)
            elif export == 'gpx':
                p = os.path.join(out_dir, f"{safe}.gpx")
                img.export_gpx(p); created.append(p)
            elif export == 'csv':
                p = os.path.join(out_dir, f"{safe}.csv")
                img.export_csv(p); created.append(p)
            else:
                raise GarminImgError(f"Unknown format: {export}")
            if clear_after:
                img.clear_cache(); gc.collect()
        return created

    def extract_all_by_name(self, out_dir, *, level=0,
                            kinds=('points', 'lines', 'polygons'),
                            by_types=True,
                            verbose=True):
        """
        Batch export of all classic maps from the container into separate
        folders named after the map name from MPS.

        by_types=True  — per-type files inside each folder:
                         points_1400.shp, lines_06.shp, polygons_50.shp
        by_types=False — common files points.shp, lines.shp, polygons.shp.
        """
        os.makedirs(out_dir, exist_ok=True)

        summary = {}
        errors = []
        t0 = time.time()

        for i, img in enumerate(self._submaps, 1):
            sid = img.submap_id or f"sub_{img.metadata.map_id}"
            name = img.get_display_name()
            folder_name = _safe_folder_name(name, sid)

            base = folder_name
            k = 1
            while os.path.exists(os.path.join(out_dir, folder_name, ".done")):
                folder_name = f"{base}_{k}"
                k += 1

            folder = os.path.join(out_dir, folder_name)
            try:
                if by_types:
                    res = img.export_by_types_shapefiles(
                        folder, level=level, kinds=kinds)
                    n_types = sum(len(v) for v in res.values())
                    n_total = 0
                    for kind in kinds:
                        if kind == 'points':
                            n_total += sum(1 for p in img.iter_points()
                                           if level is None or p.level == level)
                        elif kind == 'lines':
                            n_total += sum(1 for pl in img.iter_polylines()
                                           if level is None or pl.level == level)
                        elif kind == 'polygons':
                            n_total += sum(1 for pg in img.iter_polygons()
                                           if level is None or pg.level == level)
                    summary[folder_name] = {'types': n_types, 'total': n_total}
                    if verbose:
                        print(f"{i:>3}  {sid:<10} {folder_name:<28}  "
                              f"{n_types:>4} types, {n_total:>8} objects")
                else:
                    res = img.export_all_shapefiles(folder, level=level,
                                                     kinds=kinds)
                    summary[folder_name] = res
                    if verbose:
                        print(f"{i:>3}  {sid:<10} {folder_name:<28}  "
                              f"{sum(res.values()):>8} objects")

                with open(os.path.join(folder, ".done"), "w") as f:
                    f.write(f"submap_id={sid}\nname={name}\n"
                            f"level={level}\nby_types={by_types}\n")
            except Exception as e:
                errors.append((sid, name, str(e)))
                if verbose:
                    print(f"{i:>3}  {sid:<10} {folder_name:<28}  ERROR: {e}")
            finally:
                img.clear_cache()

        if verbose:
            dt = time.time() - t0
            print()
            print("=" * 70)
            print(f"Done in {dt:.1f} sec ({dt/60:.1f} min)")
            print(f"Maps: {len(summary)}")
            print(f"Errors: {len(errors)}")

        return summary, errors

    def __repr__(self):
        return (f"GarminIMGContainer({self.path!r}, "
                f"submaps={len(self._submaps)}, "
                f"nt_skipped={self.n_nt_skipped})")


# ================================================================
# open_img / CLI
# ================================================================

def open_img(path):
    with open(path, 'rb') as f: raw = f.read()
    data, _ = _decode_xor(raw)
    if data[0x10:0x16] != b'DSKIMG':
        raise GarminImgError(f"Not an IMG file: {path}")
    groups = _fat_groups(data)
    n_classic = sum(1 for types in groups.values()
                    if _is_classic_img(types) and not _is_service_only(types))
    if n_classic > 1:
        return GarminIMGContainer(path)
    if n_classic == 1:
        for sid, types in groups.items():
            if _is_classic_img(types) and not _is_service_only(types):
                bs = 1 << (data[0x61] + data[0x62])
                offsets = {}
                for stype, entries in types.items():
                    if stype in _SERVICE_SUBFILES: continue
                    first = sorted(entries, key=lambda e: e.part)[0]
                    if first.blocks:
                        offsets[stype] = first.blocks[0] * bs
                return GarminIMG(path, subfile_offsets=offsets, submap_id=sid)
    try: return GarminIMG(path)
    except GarminImgError: pass
    raise GarminImgError(
        f"No classic IMG maps in {path}. "
        f"Possibly an NT container.")


def _cli():
    import sys
    if len(sys.argv) < 2:
        print("usage:")
        print("  python garmin_img.py info     <file.img>")
        print("  python garmin_img.py list     <gmapsupp.img>")
        print("  python garmin_img.py export   <file.img> <out_prefix>")
        print("  python garmin_img.py extract  <gmapsupp.img> <out_dir>")
        print("  python garmin_img.py extract-by-name <gmapsupp.img> <out_dir> [level]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == 'info':
        obj = open_img(sys.argv[2])
        if isinstance(obj, GarminIMGContainer):
            print(f"Container: {sys.argv[2]}")
            print(f"Maps inside: {len(obj)}")
            for r in obj.list_light():
                print(f"  {r['id']:<10} {r['kind']:<8} "
                      f"{r['size']//1024:>8} KB  {r['name']}")
        else:
            print(obj.summary())
    elif cmd == 'list':
        cont = GarminIMGContainer(sys.argv[2])
        print(f"{'ID':<10} {'Kind':<8} {'Size, KB':>10}  Name")
        print("-" * 60)
        for r in cont.list_light():
            print(f"{r['id']:<10} {r['kind']:<8} "
                  f"{r['size']//1024:>10}  {r['name']}")
    elif cmd == 'export':
        obj = open_img(sys.argv[2])
        if isinstance(obj, GarminIMGContainer):
            print("This is a container. Use 'extract'."); sys.exit(1)
        prefix = sys.argv[3]
        obj.export_mp(prefix + ".mp")
        obj.export_geojson(prefix + ".geojson")
        try:
            obj.export_shapefile(prefix + "_roads.shp", filter_group="road")
        except GarminImgError as e:
            print(f"Shapefile skipped: {e}")
        print(f"Done: {prefix}.*")
    elif cmd == 'extract':
        cont = GarminIMGContainer(sys.argv[2])
        files = cont.extract_all(sys.argv[3], export='shapefile',
                                 kinds=('lines',))
        print(f"Extracted {len(files)} maps to {sys.argv[3]}")
    elif cmd == 'extract-by-name':
        cont = GarminIMGContainer(sys.argv[2])
        out_dir = sys.argv[3] if len(sys.argv) > 3 else "extracted"
        level = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        print(f"{'#':>3}  {'ID':<10} {'Map name':<28}  "
              f"{'Points':>7}  {'Lines':>8}  {'Polygons':>9}")
        print("-" * 90)
        cont.extract_all_by_name(out_dir, level=level)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == '__main__':
    _cli()