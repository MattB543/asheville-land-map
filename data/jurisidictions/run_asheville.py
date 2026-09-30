#!/usr/bin/env python3
"""
Build the City of Asheville, NC canonical parcel parquet.

Asheville is the seat of Buncombe County. Parcels AND values come from the county, so the
countywide layer is restricted to the city (see "City restriction" below).

Source (Buncombe County GIS open data, public, no token):
- opendata MapServer layer 1 ("Property"):
  https://gis.buncombecounty.org/arcgis/rest/services/opendata/MapServer/1
  ~135k parcels countywide. One-stop layer: geometry + current assessor LandValue /
  BuildingValue / TotalMarketValue + property Class + Exempt code + Acreage + a per-parcel
  property-record-card URL (PropCard), all in one place. No joins, no manual downloads.
  TaxYear = 26 (the 2026 reappraisal roll, "MyValueBC 2026").
- opendata MapServer layer 4 ("Incorporated Areas"), DistCode='CAS' = CITY OF ASHEVILLE.
- Class code lookup: Buncombe County "Parcel Class Codes" table (AGOL item
  926a714867ef4e0f9147c486516614d5) — exported as use_desc; categorize() quotes it.

Outputs:
- data/jurisidictions/data/asheville/asheville-nc-parcels.parquet
- data/jurisidictions/data/asheville/asheville-nc-parcels_YYYY_MM_DD.parquet
Then bake tiles (the browser GeoParquet path froze Chrome's renderer for ~30 s building 34k
3D extrusions, which the playbook says calls for PMTiles even below ~100k parcels):
  python data/scripts/parquet_to_pmtiles.py --city asheville --drop-remnants --wsl

Notes:
- City restriction: the layer's `City` field is the assessor's municipal TAX-DISTRICT code
  (CAS = City of Asheville), not a mailing-address city (that is `CityName`). It is the filter,
  cross-checked SYMMETRICALLY against a representative-point-within test on the Incorporated
  Areas polygon (intersection / union of the two sets): on 2026-09-29 39,813 records were in
  both, 7 CAS records sit just outside and 1 non-CAS record inside (IoU 99.98%). The ETL fails
  below 99.5%.
- VALUES: TotalMarketValue = LandValue + BuildingValue + the county's "Features" value (paving,
  outbuildings, pools — the property card's third line; $57.7M over 7,027 city records). It is
  never below land + building (asserted). improvement_value = Total − Land (building AND
  features); counting only BuildingValue called e.g. a $1.1M service station "Vacant".
- NON-MAPPED PARCELS (NMP) — the condo/leasehold trap. Buncombe does not draw condo units or
  leasehold improvements. Each is a record with NmpType set (0 = condo unit, PIN = 10-digit
  parent root + 'C' + unit; 3 = leasehold, root + 'L' + id) whose geometry is an exact COPY of
  the parent parcel's polygon (asserted) — stacks up to 226 deep on one footprint. Each root is
  collapsed to ONE parcel on the parent's footprint. Only TAXABLE member accounts are summed
  (units and leaseholds are separate accounts, so summing is correct — not the Dallas N-x
  broadcast case): exempt members such as a City-owned unit in a private condo ($13.8M) or an
  AB Tech leasehold stay out, and so do zero-value records when picking the group's category.
- CONDO LAND IS $0 BY ASSESSOR DESIGN (skill §6d): Buncombe puts a condo unit's whole value in
  BuildingValue (3,319 of 3,328 class-120 units have LandValue 0) and the development's land is
  a class-317 COMMON AREA parcel, also $0. Citywide that is only ~7% of value, but it is
  concentrated downtown (~15% of shipped parcel area within 500 m of the city center), where
  $0-land condos rendered as the CHEAPEST land in the city — and $0 land does not trip the
  gp-error outline in the default land-value view. So, like run_boston.py, the land of a lot
  whose value is mostly unsplit condo units (stacked NMP units, or a condo unit the county draws
  as its own polygon) is ESTIMATED: lot area x median land $/sqft of the
  15 nearest non-condo taxable parcels (assessor-valued land, >=500 sqft), capped at 70% of the
  lot's total value; improvement = total − land. Such lots carry condo_land_imputed = 1 and keep
  the county's figure in assessor_land_value, and are never labelled "Underdeveloped" (their land
  share is our estimate). --no-condo-impute ships the assessor's $0 instead.
- EXEMPT: the `Exempt` field mixes institutional exemptions with owner-level relief.
  Excluded (exemption_flag=1): EXM (government: city/county/state/DOT/housing authority/UNCA/
  AB Tech), RXM (religious), EXC/EXA/EXE/EXH/EXL/EXO/EXP/EXR/EXS/EX1/EX3/EX4/EX5 (charitable,
  educational, hospital, low-income housing, cemeteries, fraternal, CCRCs, other nonprofit),
  the government-owned classes (365 GVMT/EXMT/VAC, 61x public schools/college/library, 65x-67x
  government, 682 gov park, 93x public parks) where no code is set but a government body owns
  the record or it carries no value (a valued private owner means the class is stale), and records
  owned by an exact-named government body (GOV_OWNERS) with a blank code — 33 on 2026-09-29, nearly all
  deeded in 2025-26 (I-26 Connector NCDOT acquisitions, UNC Health Care System, new County/City
  purchases) whose exemption code has not been applied yet. Exact names only: "BUNCOMBE COUNTY
  FARM BUREAU" and "BUNCOMBE COUNTY DEMOCRATIC PARTY" are private.
  KEPT (owner relief on ordinary taxable property): ELD (elderly/disabled homestead
  exclusion), VET (disabled veteran), DIS (disabled), HIS (historic 50% deferral), BLD
  (builder inventory), BRF (brownfield), and EX2 (pollution-abatement/recycling-equipment
  exclusion on otherwise taxable industrial sites — New Belgium Brewing, two scrap yards).
  UNRESOLVED: EX1 (Givens Estates, 5 parcels, $192.5M) and EX4 (Deerfield, 28 parcels, $142.2M)
  are CCRCs, which G.S. 105-278.6A lets be excluded in part (20/40/60/80%) as well as in full;
  the public layer has no exempt amount, so they are treated as fully exempt.
  TaxValue can NOT be used as an exemption signal: in this layer it equals TotalMarketValue
  even on fully exempt parcels. A merged NMP group is exempt iff its parent LAND is (so the
  airport's taxable hangar leaseholds do not drag the 567-acre exempt airfield into the map);
  the taxable leaseholds dropped that way (airport hangars, a hotel over a city parking deck,
  Community Land Trust homes — ~$10.6M of buildings) are logged.
- Also excluded: state-assessed utility networks (800 STATE ASSESSED, 81x electric/gas, 82x
  water, 831 telephone, 836 cable, 853 sewer — valued by the NC Department of Revenue, ~$0
  local value) and right-of-way (305 road, 842 railroad). Not every 8xx class is a utility:
  830 cell-tower sites (Commercial) and 850/852 waste disposal / landfill (Industrial, incl.
  the EX2 scrap yards) are ordinary taxable property and are kept.
- Vacant: the shared classifier forces "Vacant" onto every vacant-CLASS parcel. Here a stale
  vacant class does not beat building evidence (a $441,600 house on a class-311 "residential
  building lot"): vacant-class parcels with improvement value are re-judged by the land-share
  rule, those flagged Improved=Y with no improvement value yet are left unclassified, and
  parcels with no valuation at all are unknown rather than vacant — except assessor-designated
  vacant land, which stays Vacant.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import numpy as np
import pandas as pd
import geopandas as gpd
import requests
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "data"))
from parcel_calculations import (add_improvement_ratio_fields, check_area_agreement,  # noqa: E402
                                 classify_property_refined, gis_area_sqft, impute_condo_land)

DATA_DIR = ROOT / "data" / "jurisidictions" / "data" / "asheville"
DATA_DIR.mkdir(parents=True, exist_ok=True)
GEOM_CACHE = DATA_DIR / "asheville-nc-geometry.parquet"
BOUNDARY_CACHE = DATA_DIR / "asheville-nc-boundary.parquet"
CLASS_CACHE = DATA_DIR / "buncombe-class-codes.json"

BASE = "https://gis.buncombecounty.org/arcgis/rest/services/opendata/MapServer"
PARCELS_URL = f"{BASE}/1/query"
INCORPORATED_URL = f"{BASE}/4/query"
CLASS_CODES_URL = ("https://services6.arcgis.com/VLA0ImJ33zhtGEaP/arcgis/rest/services/"
                   "Buncombe_County_Parcel_Class_Codes/FeatureServer/0/query")
CITY_CODE = "CAS"
# Owner is fetched ONLY for the exemption logic/diagnostics below; it is never exported.
OUT_FIELDS = ("objectid,PIN,Owner,NmpType,CondoUnit,CondoBuilding,SubName,SubLot,Acreage,City,Class,"
              "Improved,Exempt,TotalMarketValue,AppraisedValue,TaxValue,LandUse,LandValue,"
              "BuildingValue,Address,PropCard")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36",
           "Accept": "application/json, text/plain, */*"}
SQFT_PER_ACRE = 43560.0
PAGE = 2000
UTM = "EPSG:32617"
CONDO_K = 15             # nearest donor parcels for the condo land estimate
CONDO_CAP = 0.70         # estimated land never exceeds this share of the lot's total value
UNSPLIT_MIN_SHARE = 0.5  # a condo lot = most of its value sits in $0-land condo unit records
SF_CUTOFF, OTHER_CUTOFF = 0.67, 0.50

# Institutional exemptions -> excluded. ELD/VET/DIS/HIS/BLD/BRF/EX2 are deliberately absent
# (owner-level relief on ordinary taxable property — see the module docstring).
EXEMPT_CODES = {"EXM", "RXM", "EXC", "EXA", "EXE", "EXH", "EXL", "EXO", "EXP", "EXR", "EXS",
                "EX1", "EX3", "EX4", "EX5"}
# Government-owned classes: exempt even when the Exempt code is blank — if a government body owns
# the record or it carries no value. A valued, privately owned record in one of these classes is a
# sale out of government ownership the class has not caught up with (Pulliam Arden Developers LLC,
# class 654, $1.18M) and stays taxable.
GOV_CLASSES = {"365", "611", "612", "613", "617", "650", "651", "652", "653", "654", "656", "658",
               "660", "661", "662", "670", "682", "931", "932", "933", "934"}
# Government bodies, by EXACT owner name (every spelling below also appears on EXM-coded records
# or is a state agency). Property of the State, counties and cities is exempt (N.C. Const. art. V
# §2(3)); a blank code on these is an acquisition the assessor has not coded yet. Never a regex.
GOV_OWNERS = {
    "CITY OF ASHEVILLE", "BUNCOMBE COUNTY", "COUNTY OF BUNCOMBE", "STATE OF NORTH CAROLINA",
    "THE STATE OF NORTH CAROLINA", "DEPARTMENT OF TRANSPORTATION", "N C DEPARTMENT OF TRANSPORTATION",
    "NC DEPT OF TRANSPORTATION", "N C DEPTARTMENT OF TRANSPORTATION", "N C STATE HIGHWAY COMMISSION",
    "NC DEPT OF TRANSPORATION", "NC DEPT OF TRANSPORATION ROW DIV",
    "UNITED STATES OF AMERICA", "UNITED STATES POSTAL SERV", "UNITED STATES POSTAL SERVICES",
    "ASHEVILLE BOARD ALCOHOLIC CONTROL", "ASHEVILLE BOARD ALCHOLIC CONTROL",
    "BUNCOMBE COUNTY BOARD OF EDUCATION", "ASHEVILLE CITY BOARD OF EDUCATION",
    "GREATER ASHEVILLE REGIONAL AIRPORT AUTHORITY",
    "UNIVERSITY OF NORTH CAROLINA HEALTH CARE SYSTEM",  # state agency (G.S. 116-37)
}

ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
ap.add_argument("--no-condo-impute", action="store_true",
                help="Ship the assessor's $0 condo land instead of the neighbour estimate.")
ARGS = ap.parse_args()


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


# ── fetch (cached) ─────────────────────────────────────────────────────────────
def _get_json(url, params, what):
    for attempt in range(5):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=240)
            r.raise_for_status()
            # Parse directly: gpd.read_file(BytesIO) trips pyogrio's URL sniffing (run_lynchburg.py).
            payload = json.loads(r.content)
            # ArcGIS reports failures as HTTP 200 + {"error": ...}. Treating that as an empty page
            # ended pagination early and cached a partial download — retry it like any failure.
            if "error" in payload:
                raise RuntimeError(f"ArcGIS error: {str(payload['error'])[:200]}")
            return payload
        except Exception as e:  # noqa: BLE001
            log(f"  retry {attempt + 1} ({what}): {type(e).__name__}: {e}")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Fetch failed: {what}")


def _get_geojson(url, params, what):
    feats = _get_json(url, {**params, "f": "geojson", "outSR": 4326}, what).get("features")
    if feats is None:
        raise RuntimeError(f"No 'features' in the response ({what})")
    return (gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326")
            if feats else gpd.GeoDataFrame(geometry=[], crs="EPSG:4326"))


def fetch_boundary():
    if BOUNDARY_CACHE.exists():
        return gpd.read_parquet(BOUNDARY_CACHE)
    b = _get_geojson(INCORPORATED_URL, {"where": f"DistCode='{CITY_CODE}'",
                                        "outFields": "DistCode,Description",
                                        "returnGeometry": "true"}, "boundary")
    if len(b) != 1:
        raise RuntimeError(f"Expected 1 CITY OF ASHEVILLE polygon, got {len(b)}")
    b.to_parquet(BOUNDARY_CACHE, index=False)
    return b


def fetch_parcels(boundary):
    if GEOM_CACHE.exists():
        log(f"Using cached geometry: {GEOM_CACHE.name}")
        return gpd.read_parquet(GEOM_CACHE)
    # Every parcel in the city's bounding envelope — a superset of the city, so the tax-district
    # filter can be cross-checked against a spatial clip on the incorporated-area polygon.
    x0, y0, x1, y1 = boundary.total_bounds
    spatial = {"geometry": f"{x0},{y0},{x1},{y1}", "geometryType": "esriGeometryEnvelope",
               "inSR": 4326, "spatialRel": "esriSpatialRelIntersects", "where": "1=1"}
    total = _get_json(PARCELS_URL, {**spatial, "returnCountOnly": "true", "f": "json"}, "count")["count"]
    log(f"Pulling {total:,} Buncombe parcels in the Asheville envelope (paginated GeoJSON)...")
    pages, off = [], 0
    while off < total:
        gdf = _get_geojson(PARCELS_URL, {**spatial, "outFields": OUT_FIELDS, "returnGeometry": "true",
                                         "resultOffset": off, "resultRecordCount": PAGE,
                                         "orderByFields": "objectid"}, f"parcels @{off}")
        if not len(gdf):
            raise RuntimeError(f"Empty page at offset {off:,} of {total:,} — refusing to cache a partial pull")
        pages.append(gdf)
        off += len(gdf)
        if off % 10000 < PAGE:
            log(f"  fetched {off:,}/{total:,}")
    geom = gpd.GeoDataFrame(pd.concat(pages, ignore_index=True), crs="EPSG:4326")
    # The cache is only written once the pull is provably complete.
    if len(geom) != total or geom["objectid"].duplicated().any():
        raise RuntimeError(f"Pulled {len(geom):,} rows ({int(geom['objectid'].duplicated().sum())} duplicate "
                           f"objectids) but the layer reported {total:,} — not caching")
    geom.to_parquet(GEOM_CACHE, index=False)
    log(f"  cached geometry -> {GEOM_CACHE.name} ({len(geom):,} rows)")
    return geom


def fetch_class_descriptions():
    if not CLASS_CACHE.exists():
        rows = _get_json(CLASS_CODES_URL, {"where": "1=1", "outFields": "Code,Description",
                                           "resultRecordCount": 1000, "f": "json"}, "class codes")["features"]
        CLASS_CACHE.write_text(json.dumps({r["attributes"]["Code"].strip(): r["attributes"]["Description"].strip()
                                           for r in rows}, indent=1))
    return json.loads(CLASS_CACHE.read_text())


boundary = fetch_boundary()
raw = fetch_parcels(boundary)
CLASS_DESC = fetch_class_descriptions()
log(f"{len(raw):,} parcels in the Asheville envelope; {len(CLASS_DESC)} class codes")

# ── city restriction: tax-district code, cross-checked spatially (symmetric) ──
is_cas = raw["City"].fillna("").str.strip().eq(CITY_CODE)
inside = raw.geometry.representative_point().within(boundary.geometry.union_all())
iou = int((is_cas & inside).sum()) / max(int((is_cas | inside).sum()), 1)
log(f"City='{CITY_CODE}': {int(is_cas.sum()):,} | rep-point-in-boundary: {int(inside.sum()):,} | "
    f"both: {int((is_cas & inside).sum()):,} (IoU {iou:.3%}) | CAS-outside: {int((is_cas & ~inside).sum())} | "
    f"inside-not-CAS: {int((inside & ~is_cas).sum())}")
if iou < 0.995:
    raise RuntimeError("Tax-district filter and city boundary disagree by >0.5% — investigate before shipping")
parcel = raw[is_cas].copy()

parcel["PIN"] = parcel["PIN"].astype(str).str.strip()
for c in ["LandValue", "BuildingValue", "TotalMarketValue", "Acreage"]:
    parcel[c] = pd.to_numeric(parcel[c], errors="coerce")
for c in ["Class", "Exempt", "Improved", "PropCard", "Owner"]:
    parcel[c] = parcel[c].fillna("").astype(str).str.strip()
parcel["land_val"] = parcel["LandValue"].fillna(0)
parcel["bld_val"] = parcel["BuildingValue"].fillna(0)
parcel["tot_appr_val"] = parcel["TotalMarketValue"].fillna(parcel["land_val"] + parcel["bld_val"])
features = parcel["tot_appr_val"] - parcel["land_val"] - parcel["bld_val"]
if (features < -1).any():
    raise RuntimeError(f"{int((features < -1).sum())} records have total < land + building — schema changed?")
# Improvements = building + the county's "Features" (paving, outbuildings...): everything but land.
parcel["impr_val"] = parcel["tot_appr_val"] - parcel["land_val"]
log(f"Features value (total − land − building): ${features.sum() / 1e6:.1f}M on {int((features > 0).sum()):,} "
    f"records -> counted as improvements")
parcel["geometry"] = parcel["geometry"].apply(lambda x: x if x is None or x.is_valid else x.buffer(0))
parcel = parcel[parcel["geometry"].notnull() & ~parcel["geometry"].is_empty].copy()
dup = int(parcel["PIN"].duplicated().sum())
if dup:
    raise RuntimeError(f"{dup} duplicate PINs — the multi-polygon dedup assumed absent is needed")
log(f"City parcels with valid geometry: {len(parcel):,}")

# ── exemption flag (per record, before the NMP collapse) ─────────────────────
by_code = parcel["Exempt"].isin(EXEMPT_CODES)
gov_owner = parcel["Owner"].isin(GOV_OWNERS)
gov_class = parcel["Class"].isin(GOV_CLASSES) & ~by_code
by_class = gov_class & (gov_owner | parcel["tot_appr_val"].le(0))
by_owner = gov_owner & ~by_code & ~by_class
parcel["exempt_rec"] = (by_code | by_class | by_owner).astype(int)
log(f"Exempt records: {int(parcel['exempt_rec'].sum()):,} — {int(by_code.sum()):,} by code, "
    f"{int(by_class.sum())} by government class ({parcel.loc[by_class, 'Owner'].value_counts().head(4).to_dict()}), "
    f"{int(by_owner.sum())} by government owner with no code (${parcel.loc[by_owner, 'tot_appr_val'].sum() / 1e6:.1f}M: "
    f"{parcel.loc[by_owner, 'Owner'].value_counts().to_dict()}); kept taxable despite a government class "
    f"(private owner, valued): {parcel.loc[gov_class & ~by_class, ['Owner', 'Class', 'tot_appr_val']].values.tolist()}")


# ── categorization (Buncombe class codes) ────────────────────────────────────
def categorize(cls):
    """Map a Buncombe property Class code -> app property category."""
    c = str(cls or "").strip()
    if c in ("100", "101", "105"):          # RES 0-3 AC / RES >3 AC / RES LEASEHOLD
        return "Single Family"
    if c == "121":                          # TOWNHOME (fee-simple lot, real land value)
        return "Townhome"
    if c in ("120", "122"):                 # CONDO / CONDO STRG
        return "Condominium"
    if c in ("466", "467"):                 # COMM CONDO / COMM-OFFICE CONDO
        return "Commercial Condominium"
    if c in ("170", "173"):                 # MFG HOME SITE / PP MH(S) OR SITE
        return "Mobile Home"
    if c in ("180", "411", "442"):          # MULTIPLE RES / APT / SECT. 42 APARTMENT
        return "Multifamily"
    if c in ("300", "301", "311", "320", "340", "365"):  # VAC LAND / SUBSTD LOT / RES BLDG LOT / UNDEV TRACT / COMM VAC
        return "Vacant Land"
    if c in ("312", "341"):                 # NON-DWG IMPV / COMM-SMALL IMP (shed/garage only)
        return "Minor Improvement"
    if c in ("307", "438"):                 # PARKING / COMM PKG LOT (surface)
        return "Parking"
    if c == "437":                          # COMM PKG GARAGE — a structure, judged by ratio
        return "Parking Garage"
    if c in ("306", "317"):                 # PRK/RSVD AREA / COMMON AREA (HOA land)
        return "Common Area"
    if c in ("315", "900", "910", "930", "942") or c.startswith("93"):
        return "Park / Open Space"
    if c == "416":                          # MFGHOME PARK
        return "Mobile Home Park"
    if c in ("414", "415", "417", "418"):   # HOTEL / MOTEL / CAMPS-RV / INN-B&B
        return "Hotel / Lodging"
    if c == "405":                          # COMM LEASEHOLD (land under a ground lease)
        return "Commercial"
    if c in ("440", "444", "445", "446", "447") or c.startswith("7"):
        return "Industrial"
    if c.startswith("4"):
        return "Commercial"
    if c.startswith("5"):
        return "Recreation"
    if c.startswith("6"):
        return "Institutional"
    if c in ("305", "842"):                 # ROAD/STREET / RAILROAD corridor
        return "Right of Way"
    if c in ("850", "852"):                 # WASTE DISPOSAL / LANDFILL — scrap yards, recyclers
        return "Industrial"
    if c == "830":                          # CELL TOWER site (taxable ground lease)
        return "Commercial"
    if c in ("840", "841", "844"):          # TRANSPORTATION / BUS TERMINAL / AIRPORT
        return "Transportation"
    if c.startswith("8"):                   # 800 STATE ASSESSED, 81x/82x/831/836/853 networks
        return "Utility"
    return "Other"


parcel["cat_rec"] = parcel["Class"].map(categorize)

# ── NMP collapse: condo units + leaseholds -> their mapped parent parcel ──────
# NMP records (NmpType 0/3) carry a copy of the parent's polygon; group by the 10-digit root.
parcel["is_nmp"] = parcel["NmpType"].notna()
parcel["root"] = parcel["PIN"].str[:10]
std = parcel[~parcel["is_nmp"]].copy()
nmp = parcel[parcel["is_nmp"]].copy()
# The grouping key relies on the PIN shape: 15 chars; mapped = root + '00000'; unit = root + 'C…'
# (NmpType 0); leasehold = root + 'L…' (NmpType 3). Anything else means the scheme changed.
_kind = nmp["NmpType"].map({0: "C", 3: "L"})
bad_pin = (~parcel["PIN"].str.len().eq(15)).sum() + (~std["PIN"].str[10:].eq("00000")).sum() \
    + (nmp["PIN"].str[10] != _kind).sum()
if bad_pin:
    raise RuntimeError(f"{bad_pin} PINs/NmpTypes outside the known scheme "
                       f"(NmpType values: {nmp['NmpType'].value_counts(dropna=False).to_dict()})")
std_by_root = std.set_index("root")
orphans = ~nmp["root"].isin(std_by_root.index)
if orphans.any():
    raise RuntimeError(f"{int(orphans.sum())} NMP records have no mapped parent parcel")
if std["root"].duplicated().any():
    raise RuntimeError("Mapped parcels share a 10-digit root — the NMP grouping key is ambiguous")
# The collapse keeps the PARENT footprint, which is only right if every NMP polygon IS that
# footprint: require a negligible symmetric difference (<=1 m² or 0.1% of the parent).
_par_g = gpd.GeoSeries(std_by_root.loc[nmp["root"]].geometry.values, crs="EPSG:4326").to_crs(UTM)
_nmp_g = gpd.GeoSeries(nmp.geometry.values, crs="EPSG:4326").to_crs(UTM)
_diff = _nmp_g.symmetric_difference(_par_g).area.to_numpy()
_off = _diff > np.maximum(1.0, 0.001 * _par_g.area.to_numpy())
if _off.any():
    raise RuntimeError(f"{int(_off.sum())} NMP polygons differ from their parent footprint "
                       f"(e.g. {nmp['PIN'].iloc[np.flatnonzero(_off)[:3]].tolist()})")
log(f"NMP records: {len(nmp):,} (condo units {int(nmp['NmpType'].eq(0).sum()):,}, leaseholds "
    f"{int(nmp['NmpType'].eq(3).sum())}) on {nmp['root'].nunique()} parents; all footprints == parent")

# Parent classes that describe the LAND under the development (common area, ground-leased
# land, vacant/parking lots) rather than what is built on it — they never pick the category.
CONDO_CLASSES = {"120", "122", "466", "467"}
LAND_ONLY_CLASSES = {"317", "306", "405", "105", "300", "301", "311", "320", "340", "312", "341",
                     "307", "438", ""}
VALUE_COLS = ("land_val", "bld_val", "impr_val", "tot_appr_val")
rows = []
for root, grp_nmp in nmp.groupby("root"):
    par = std_by_root.loc[root]
    members = pd.concat([par.to_frame().T, grp_nmp])
    # Only taxable accounts count toward the lot's value and use. Footprint and exemption still
    # follow the parent LAND (below), so an exempt unit in a private condo neither inflates the
    # taxable total nor relabels the lot.
    taxable = members[members["exempt_rec"].astype(int).eq(0)]
    row = par.to_dict()
    row["root"] = root
    for c in VALUE_COLS:
        row[c] = float(pd.to_numeric(taxable[c], errors="coerce").fillna(0).sum())
    v = pd.to_numeric(taxable["tot_appr_val"], errors="coerce").fillna(0)
    # Category = the category holding the most value among taxable members that describe a USE.
    # Zero-value records (unvalued new units, $0 leaseholds) can't win.
    use = taxable.assign(v=v)
    use = use[(use["is_nmp"].astype(bool) | ~use["Class"].isin(LAND_ONLY_CLASSES))
              & use["Class"].ne("") & use["v"].gt(0)]
    row["cat_rec"] = (use.groupby("cat_rec")["v"].sum().idxmax() if len(use) else par["cat_rec"])
    # Exemption follows the parent LAND. Taxable leaseholds on exempt ground exist (hangars on
    # the 567-acre airport, a hotel over a city parking deck, Community Land Trust homes on
    # trust-owned lots), but keeping them would ship the exempt land under them too: the whole
    # airport rendered as a taxable parcel. The map is about land, so the group goes with its land.
    row["exempt_rec"] = int(par["exempt_rec"])
    row["Improved"] = "Y" if taxable["Improved"].eq("Y").any() else par["Improved"]
    row["n_accounts"] = len(taxable)
    row["n_condo_units"] = int(pd.to_numeric(taxable["NmpType"], errors="coerce").eq(0).sum())
    row["condo_regime"] = int(grp_nmp["NmpType"].eq(0).any())
    # Value held by condo-unit accounts the assessor gave no land (the §6d "unsplit" share).
    unsplit = taxable[pd.to_numeric(taxable["NmpType"], errors="coerce").eq(0)
                      & pd.to_numeric(taxable["land_val"], errors="coerce").fillna(0).le(0)]
    row["unsplit_val"] = float(pd.to_numeric(unsplit["tot_appr_val"], errors="coerce").fillna(0).sum())
    row["exempt_member_val"] = float(pd.to_numeric(members.loc[members["exempt_rec"].astype(int).eq(1),
                                                               "tot_appr_val"], errors="coerce").fillna(0).sum())
    rows.append(row)
merged = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
total_in = float(parcel["tot_appr_val"].sum())
parcel = gpd.GeoDataFrame(pd.concat([std[~std["root"].isin(merged["root"])], merged], ignore_index=True),
                          geometry="geometry", crs="EPSG:4326")
# A condo unit the county draws as its OWN polygon (24 commercial condos, a few residential) is a
# one-unit condo regime: same $0-land treatment, so it gets the same estimate.
_solo = parcel["n_accounts"].isna()
_solo_condo = _solo & parcel["Class"].isin(CONDO_CLASSES)
parcel.loc[_solo, "n_accounts"] = 1
parcel.loc[_solo, "n_condo_units"] = _solo_condo[_solo].astype(int)
parcel.loc[_solo, "condo_regime"] = _solo_condo[_solo].astype(int)
parcel.loc[_solo, "unsplit_val"] = np.where(_solo_condo[_solo] & parcel.loc[_solo, "land_val"].le(0),
                                            parcel.loc[_solo, "tot_appr_val"], 0.0)
parcel["exempt_member_val"] = parcel["exempt_member_val"].fillna(0.0)
for c in ("n_accounts", "n_condo_units", "condo_regime"):
    parcel[c] = parcel[c].astype(int)
# Value conservation: every record's value is either on a collapsed parcel or an exempt member left out.
_left_out = float(merged["exempt_member_val"].where(merged["exempt_rec"].eq(0), 0).sum())
_exempt_in_exempt_groups = float(merged.loc[merged["exempt_rec"].eq(1), "exempt_member_val"].sum())
if abs(total_in - (parcel["tot_appr_val"].sum() + _left_out + _exempt_in_exempt_groups)) > 1:
    raise RuntimeError("NMP collapse does not conserve value")
log(f"After NMP collapse -> {len(parcel):,} parcels ({len(merged)} developments/leaseholds: "
    f"{merged['cat_rec'].value_counts().to_dict()})")
log(f"  exempt member accounts left out of taxable groups: ${_left_out / 1e6:.1f}M "
    f"({int(((merged['exempt_member_val'] > 0) & merged['exempt_rec'].eq(0)).sum())} groups)")
_on_exempt = nmp[nmp["root"].map(std_by_root["exempt_rec"]).eq(1) & nmp["exempt_rec"].eq(0)]
log(f"  taxable NMP records dropped with their exempt parent land: {len(_on_exempt)} "
    f"(${_on_exempt['impr_val'].sum() / 1e6:.1f}M of improvements)")

# Defensive: any remaining same-footprint stacks among mapped parcels?
rp = parcel.geometry.representative_point()
vc = (rp.x.round(5).astype(str) + "," + rp.y.round(5).astype(str)).value_counts()
log(f"Remaining stacked footprints: {int((vc > 1).sum())} (max stack {int(vc.max())})")

# ── exemption / exclusion ─────────────────────────────────────────────────────
parcel["exemption_flag"] = parcel["exempt_rec"].astype(int)
parcel["PROPERTY_CATEGORY"] = parcel["cat_rec"]
drop_cat = parcel["PROPERTY_CATEGORY"].isin(["Utility", "Right of Way"])
dropped = parcel[(parcel["exemption_flag"] == 1) | drop_cat]
log(f"Excluding {int(parcel['exemption_flag'].sum()):,} exempt + {int((drop_cat & parcel['exemption_flag'].eq(0)).sum())} "
    f"utility/right-of-way parcels ({parcel.loc[drop_cat, 'PROPERTY_CATEGORY'].value_counts().to_dict()}; "
    f"${dropped['tot_appr_val'].sum() / 1e6:,.1f}M)")
ex = parcel[(parcel["exemption_flag"] == 0) & ~drop_cat].copy()
if abs(parcel["tot_appr_val"].sum() - ex["tot_appr_val"].sum() - dropped["tot_appr_val"].sum()) > 1:
    raise RuntimeError("Exemption filter does not conserve value")
log(f"After exempt/utility filter -> {len(ex):,}")

ex["property_land_use_category"] = ex["PROPERTY_CATEGORY"]
ex["land_value"] = pd.to_numeric(ex["land_val"], errors="coerce")
ex["improvement_value"] = pd.to_numeric(ex["impr_val"], errors="coerce")
ex["full_market_value"] = pd.to_numeric(ex["tot_appr_val"], errors="coerce")

# ── land area — geodesic polygon, Acreage only a cross-check / fallback ──────
log("Computing GIS areas...")
ex["geom_area_sqft"] = ex["geometry"].apply(gis_area_sqft)
ex.loc[ex["geom_area_sqft"] < 1, "geom_area_sqft"] = np.nan
# The GEODESIC POLYGON area is the denominator, not the source's Acreage: Acreage is stored on a
# 0.01-acre grid (99.99% of values), i.e. +/-218 sqft of rounding — up to ~10% on the city's
# many sub-0.1-acre lots — and on larger tracts it is the deeded figure, which differs from
# the drawn polygon by >5% on ~20% of 1+ acre parcels. The polygon is what the map renders, so
# $/sqft stays consistent with what the user sees. Acreage is kept as a median cross-check
# (it should agree to ~1.0) and as the fallback where no usable polygon area exists.
rep = pd.to_numeric(ex["Acreage"], errors="coerce") * SQFT_PER_ACRE
rep[rep < 1] = np.nan
med = check_area_agreement(ex["geom_area_sqft"], rep, label="source Acreage (0.01-acre grid)", log=log)
if not 0.98 < med < 1.02:
    raise RuntimeError("Polygon area disagrees systematically with source Acreage — check the area computation")
use_reported = ex["geom_area_sqft"].isna() & rep.gt(0)
ex["land_area_sqft"] = np.where(use_reported, rep, ex["geom_area_sqft"])
ex["area_source"] = np.where(use_reported, "reported", "gis")
ex["land_area_acres"] = ex["land_area_sqft"] / SQFT_PER_ACRE
ex["likely_remnant"] = (ex["land_area_sqft"] < 500).astype(int)

# ── condo land estimate (skill §6d; see docstring) ────────────────────────────
ex["assessor_land_value"] = ex["land_value"]
ex["condo_land_imputed"] = 0
share = ex["unsplit_val"] / ex["full_market_value"].where(ex["full_market_value"] > 0)
condo_lot = ex["condo_regime"].eq(1) & share.ge(UNSPLIT_MIN_SHARE)  # stacked units or a drawn unit
donor = (ex["land_value"].gt(0) & ex["condo_regime"].eq(0) & ex["land_area_sqft"].ge(500)
         & ex["likely_remnant"].eq(0) & ~ex["property_land_use_category"].isin(["Common Area"]))
est = impute_condo_land(ex, eligible=condo_lot.to_numpy(), donor=donor.to_numpy(), land_col="land_value",
                        total_col="full_market_value", area_col="land_area_sqft", k=CONDO_K, cap=CONDO_CAP,
                        metric_crs=UTM)
apply = condo_lot & est["new_land"].notna() & est["new_land"].gt(ex["land_value"])
log(f"Condo lots (unsplit condo units >= {UNSPLIT_MIN_SHARE:.0%} of value): {int(condo_lot.sum())}; estimate "
    f"{'NOT applied (--no-condo-impute)' if ARGS.no_condo_impute else 'applied'} to {int(apply.sum())} "
    f"(+${(est['new_land'] - ex['land_value'])[apply].sum() / 1e6:,.1f}M land, cap binding "
    f"{int((apply & est['cap_binding']).sum())})")
if not ARGS.no_condo_impute:
    ex.loc[apply, "land_value"] = est.loc[apply, "new_land"]
    ex.loc[apply, "improvement_value"] = ex.loc[apply, "full_market_value"] - ex.loc[apply, "land_value"]
    ex.loc[apply, "condo_land_imputed"] = 1
    # Calibration: estimated condo land should sit inside its neighbours' range, not above it.
    _psf = ex["land_value"] / ex["land_area_sqft"]
    _near = ex.to_crs(UTM).geometry.representative_point().distance(
        gpd.GeoSeries.from_xy([-82.5515], [35.5951], crs="EPSG:4326").to_crs(UTM).iloc[0]) <= 300
    log(f"  land $/sqft — estimated condo lots p50 ${_psf[apply].median():,.2f} vs donors p50 "
        f"${_psf[donor].median():,.2f}; downtown core (300 m): estimated p50 "
        f"${_psf[apply & _near].median():,.2f} (n={int((apply & _near).sum())}) vs donors p50 "
        f"${_psf[donor & _near].median():,.2f} (n={int((donor & _near).sum())})")

# ── refined (underused) classification ────────────────────────────────────────
# Improved=Y is the assessor's own "a structure is here" flag -> used as the building signal so
# a built-but-unvalued parcel is never called Vacant (Overture footprint lookup not needed).
ex["bld_ar"] = ex["Improved"].eq("Y").astype(int)
# Townhomes are single-family dwellings on small fee-simple lots: judge them with the
# single-family land-share cutoff, not the stricter 'other' one.
_cls_cat = ex["property_land_use_category"].replace({"Townhome": "Single Family"})
refined = classify_property_refined(
    ex.assign(_cls_cat=_cls_cat), sf_cutoff=SF_CUTOFF, other_cutoff=OTHER_CUTOFF,
    exclude_categories=("Other", "Common Area", "Park / Open Space", "Transportation"),
    category_col="_cls_cat", land_col="land_value", improvement_col="improvement_value",
    bld_ar_col="bld_ar", fetch_footprints=False)
land, impr = ex["land_value"].fillna(0), ex["improvement_value"].fillna(0)
vacant_class = ex["property_land_use_category"].eq("Vacant Land")
# The shared helper stamps "Vacant" on every vacant-CLASS parcel last, over any building
# evidence. A stale class (a house on a "residential building lot") must not win: with
# improvement value, re-judge by the land-share rule (these are houses in practice -> SF cutoff);
# flagged Improved=Y but not yet valued -> unknown.
stale = refined.eq("Vacant") & vacant_class & (impr.gt(0) | ex["bld_ar"].eq(1))
share_land = land / (land + impr).where(lambda s: s > 0)
refined[stale] = np.where(impr[stale].gt(0) & share_land[stale].ge(SF_CUTOFF), "Underdeveloped", None)
# No valuation at all is not evidence of vacancy (new splits, unvalued new construction) —
# except where the assessor itself designates the lot vacant.
unvalued = ex["full_market_value"].fillna(0).le(0)
refined[unvalued & ~vacant_class] = None
# The land share of an estimated condo lot is our estimate, not the assessor's.
refined[ex["condo_land_imputed"].eq(1) & refined.eq("Underdeveloped")] = None
ex["property_land_use_refined"] = refined
log(f"Vacant-class overrides: {int(stale.sum())} stale vacant classes with building evidence; "
    f"{int((unvalued & ~vacant_class).sum())} unvalued non-vacant parcels left unclassified")

# ── canonical fields ──────────────────────────────────────────────────────────
den = ex["land_area_sqft"].replace(0, np.nan)
ex["full_market_value_per_sqft"] = ex["full_market_value"] / den
ex["land_value_per_sqft"] = ex["land_value"] / den
ex["improvement_value_per_sqft"] = ex["improvement_value"] / den
ex = add_improvement_ratio_fields(ex, land_col="land_value", improvement_col="improvement_value")

# Buncombe's Spatialest property record card — a real per-parcel deep link, provided by the
# source layer itself. A merged group links to its PARENT lot, whose card shows only the lot's
# own value — record_note says so, since the map shows the sum of the unit accounts.
ex["link"] = ex["PropCard"].where(ex["PropCard"].str.startswith("http"),
                                  "https://prc-buncombe.spatialest.com/#/property/" + ex["PIN"])
ex["parcel_id"] = ex["PIN"]
ex["use_code"] = ex["Class"]
ex["use_desc"] = ex["Class"].map(CLASS_DESC)
note = pd.Series("", index=ex.index, dtype=object)
_combined = ex["n_accounts"].gt(1)
note[_combined] = ("Sum of " + ex.loc[_combined, "n_accounts"].astype(str) + " tax accounts on this lot "
                   "(condo units / leaseholds); the record card is the parent lot, which shows only its own value.")
_imp = ex["condo_land_imputed"].eq(1)
note[_imp] = (note[_imp] + " Land value is estimated from neighbouring parcels (the county assigns "
              "condo land $0).").str.strip()
ex["record_note"] = note.where(note.ne(""), None)

# ── export ────────────────────────────────────────────────────────────────────
# Canonical column set (run_lynchburg.py) + non-personal provenance (run_boston.py). Owner,
# mailing address and the owner-relief exemption codes (elderly / disabled / veteran) are
# deliberately NOT exported.
COLUMNS = ["geometry", "parcel_id", "use_code", "use_desc", "exemption_flag", "property_land_use_category",
           "property_land_use_refined", "full_market_value", "full_market_value_per_sqft", "land_value",
           "land_value_per_sqft", "improvement_value", "improvement_value_per_sqft", "assessor_land_value",
           "condo_land_imputed", "n_accounts", "n_condo_units", "record_note", "TLLDIMPROV",
           "IMPR_LAND_RATIO", "IMPR_LAND_PCT", "IMPR_PCT_TOTAL", "link", "land_area_acres", "area_source",
           "likely_remnant"]
missing = [c for c in COLUMNS if c not in ex.columns]
if missing:
    raise RuntimeError(f"Output columns missing: {missing}")
final = gpd.GeoDataFrame(ex[COLUMNS].rename(columns={"land_value": "current_full_land_value"}).reset_index(drop=True),
                         geometry="geometry", crs="EPSG:4326")
for c in ("condo_land_imputed", "n_accounts", "n_condo_units", "likely_remnant", "exemption_flag"):
    final[c] = final[c].astype("int32")
# Invariants on what ships.
if not final.geometry.is_valid.all():
    raise RuntimeError(f"{int((~final.geometry.is_valid).sum())} invalid geometries in the output")
_v = final[["current_full_land_value", "improvement_value", "full_market_value"]]
if _v.isna().any().any() or (_v < 0).any().any():
    raise RuntimeError("Missing or negative values in the output")
if (final["TLLDIMPROV"] - final["full_market_value"]).abs().max() > 1:
    raise RuntimeError("land + improvements != total market value")
out = DATA_DIR / "asheville-nc-parcels.parquet"
final.to_parquet(out, index=False)
final.to_parquet(DATA_DIR / f"asheville-nc-parcels_{datetime.now().strftime('%Y_%m_%d')}.parquet",
                 index=False)
log(f"SAVED {out} | rows {len(final):,}")
log(f"land ${final['current_full_land_value'].sum() / 1e9:.3f}B (assessor ${final['assessor_land_value'].sum() / 1e9:.3f}B "
    f"+ condo estimate) | improvements ${final['improvement_value'].sum() / 1e9:.3f}B | market "
    f"${final['full_market_value'].sum() / 1e9:.3f}B")
log(f"category: {final['property_land_use_category'].value_counts().to_dict()}")
log(f"refined: {final['property_land_use_refined'].value_counts(dropna=False).to_dict()}")
log(f"area_source: {final['area_source'].value_counts().to_dict()}")
log(f"likely_remnant: {int(final['likely_remnant'].sum()):,}")

# ── §6a smoke alarms ──────────────────────────────────────────────────────────
log("--- condo/stub smoke alarms (skill §6a) ---")
a = ex["geom_area_sqft"].reset_index(drop=True)
lv = pd.to_numeric(final["land_value_per_sqft"], errors="coerce")
shown = lv[final["likely_remnant"] == 0]
log(f"  footprint sqft p1/p5/p10: {[round(a.quantile(q)) for q in (.01, .05, .10)]}")
log(f"  sub-500 / sub-1000 sqft footprints: {int((a < 500).sum()):,} / {int((a < 1000).sum()):,}")
log(f"  land $/sqft ALL ROWS    p50/p95/p99/max: ${lv.median():,.2f} / ${lv.quantile(.95):,.2f} / "
    f"${lv.quantile(.99):,.2f} / ${lv.max():,.2f}")
log(f"  land $/sqft AS RENDERED p50/p95/p99/max: ${shown.median():,.2f} / ${shown.quantile(.95):,.2f} / "
    f"${shown.quantile(.99):,.2f} / ${shown.max():,.2f}  (likely_remnant excluded, hideRemnants=true)")
rp = final.geometry.representative_point()
vc = (rp.x.round(5).astype(str) + "," + rp.y.round(5).astype(str)).value_counts()
log(f"  stacked footprints in output: {int((vc > 1).sum())} (max {int(vc.max())})")
holes = final.geometry.apply(lambda g: 0 if g is None else sum(
    len(p.interiors) for p in (g.geoms if g.geom_type == "MultiPolygon" else [g])))
log(f"  parcels with interior rings (holes): {int((holes > 0).sum()):,}")
zero = pd.to_numeric(final["current_full_land_value"], errors="coerce").fillna(0) <= 0
log(f"  zero land value (renders as the cheapest land): {int(zero.sum()):,} "
    f"{final.loc[zero, 'property_land_use_category'].value_counts().head(6).to_dict()}")
log(f"  bounds: {[round(v, 4) for v in final.total_bounds]}")
log("DONE")
