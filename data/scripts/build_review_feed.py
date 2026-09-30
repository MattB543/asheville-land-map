#!/usr/bin/env python3
"""
Build the parcel review feed for one city: a small JSON the viz/review.html page lists as cards.

Two ranked lists (tabs), from any city's canonical parcel parquet (docs/parcel-parquet-format.md;
Asheville-only columns such as condo_land_imputed / record_note / likely_remnant / use_code /
n_accounts are optional):

1. "Likely data issues": parcels whose record is probably wrong (assessor or pipeline error) or
   would mislead on the map. Scored as below.
2. "Biggest opportunities": parcels the refined classifier calls Vacant / Underdeveloped /
   Parking Lot (the top N by land value), PLUS every parcel the assessor values as land with a
   token building, or whose building was written off after a storm (see TOKEN BUILDINGS), all
   ranked by land value (largest first).

Usage (from the repo root):
    python data/scripts/build_review_feed.py --city asheville
    python data/scripts/build_review_feed.py --file path/to/x-parcels.parquet --out viz/public/x-review.json
Default output: next to the parquet, as <prefix>-review.json (e.g. asheville-nc-review.json).
Upload it next to the parcel parquet and set reviewFilename / reviewVersion in viz/src/cities/<key>.json.

PER-CITY RULES
--------------
Assessor-specific knowledge (class codes, the previous roll's service, a storm-damage layer) lives
in CITY_RULES below, keyed by city (or matched by the parquet prefix); every other city gets
DEFAULT_RULES, which work from the canonical category / use_desc text alone. Optional sources are
fetched once (<= 1 request/s), cached next to the parquet as <prefix>-prior-values.parquet /
<prefix>-damage-points.parquet, and skipped with a warning when unreachable (--sources off|cache).
A damage point tags the parcels within 15 m of it (points often sit on the street frontage).
--explain ID ... prints every baseline, z-score, signal and state of those parcels.

THE LAND $/SQFT BASELINE (signals land_psf_high / land_psf_low / estimate_off)
-----------------------------------------------------------------------------
Donors = parcels with land > 0 and a real lot area, excluding `likely_remnant` slivers, parcels
whose land is estimated (`condo_land_imputed` = 1), footprint pads (townhome / condo unit lots
under ~2,500 sqft: their land is a per-unit share drawn on the footprint) and classes the
assessor values nominally by design (substandard lots, common areas, cemeteries, ...).
Footprint pads (also house-class lots under 1,500 sqft in Asheville) are only compared with
other pads, and never flagged by land_psf_* or sliver: $/sqft of a per-unit share is no rate.
Each parcel belongs to a same-use family: residential or non-residential, with vacant classes
joining the family of their use (a residential building lot is compared with houses, a
commercial-vacant lot with commercial land). For each parcel i (the parcel never counts itself):
  raw_i  = ln(psf_i) - median ln(psf) of the K=15 nearest donors               ("neighbours")
  peer_i = ln(psf_i) - median ln(psf) of the K nearest same-family donors within 1.5 km (>= 8),
           else raw_i.
  size_i = ln(psf_i) - [median over those peers of (ln psf_j - b ln area_j) + b ln area_i]
           i.e. the peers' rate adjusted for lot size with the city's size elasticity b (trimmed
           OLS of the neighbour-demeaned ln psf on ln area; Asheville b ~ -0.63).
  sim_i  = lots over 1 acre only: as size_i, but over same-family donors of SIMILAR size (1/3x-3x
           the lot) within 3 km (>= 6), so a 6-acre tract is judged against acreage, not against
           the quarter-acre subdivision next door.
  z_b,i  = (b_i - median b) / (1.4826 * MAD b) for each baseline b, with median/MAD over donors
           IN THE SAME LOT-SIZE BAND (< 1/4 acre, < 1, < 5, larger): the spread widens with lot
           size, so one citywide sigma turned a 2x gap on a 10-acre tract into z = -9.
  z_i    = the least extreme of the available z's, or 0 if they disagree in sign; capped at +/-12.
  lr_i   = the least extreme of the log-ratios (the smallest gap any baseline implies).
Reason text quotes the plain neighbours' median; when a fairer baseline shrinks the gap a lot it
adds "still ~Nx after allowing for lot size and use".

SIGNALS (each gives a severity sev in [0,1] and a dollar stake: the value that is at issue)
------------------------------------------------------------------------------------------
land_psf_high     z >= Z_FLAG (4).  sev = (|z| - 4) / (12 - 4), clipped.  stake = land - land / e^lr.
                  Weight x 0.3 on a storm write-down that moved building value onto the land.
land_psf_low      z <= -4.  Same sev.  stake = min(land / e^lr - land, the parcel's total value):
                  never an invented neighbours'-rate x area figure bigger than the parcel itself.
                  Never on nominal-by-design classes. Weight 0.7 (0.5 on vacant parcels); x 0.3
                  when other parcels surround it (>= 95% of its boundary: no street frontage,
                  i.e. landlocked or backland); x 0.3 when a tagged storm wrote the land down.
zero_land         land <= 0 under improvements > 0 (sev 1), or land < 1% of total under
                  improvements >= $25k (sev 0.6, or 0.3 when the land $/sqft is within |z| < 4:
                  a PUD / office-park pad whose land sits in a shared parcel).  stake = total value.
sliver            lot < 5,000 sqft AND <= 1/4 of the neighbours' median lot, land >= $25k, and the
                  land would buy >= 10 such lots at the neighbours' $/sqft.  sev = (log10(x) - 0.7)
                  / 1.3.  stake = land.  Never on footprint pads.
label_vacant_built   vacant category / refined Vacant, improvements >= $25k and >= 20% of total.
label_parking_built  surface-parking category / refined Parking Lot (not a garage / deck),
                  improvements >= $250k and >= 50% of total.
                  Both: sev = 0.5 + 0.5 * (share - 0.2) / 0.6, clipped.  stake = improvements.
building_dropped  a building class valued at ~$0 now whose building the PREVIOUS roll valued
                  (> max($1k, 1% of its total)), with no storm-damage record and the land not
                  absorbing the value.  sev 0.8 (0.3 on house classes: most are demolitions).
                  stake = the previous roll's improvements (the missing building).
label_built_empty a building class whose improvements are <= 1% of total (land >= $50k) and that
                  the previous roll does NOT explain as a token value:
                    - a new parcel (split / recombination) on a non-house class: sev 0.8, stake =
                      the missing building estimated as land x the class's median impr/land;
                    - reclassed from vacant since the previous roll, non-house: sev 0.25;
                    - a house class valued at $0 in both rolls (lapsed permit, stale flag, missing
                      house): sev 0.2;  - the map already shows it Vacant (stale class): sev 0.2;
                    - no previous roll available: sev 0.2 (house) / 0.25 (other).
                  stake = land unless stated.  House classes (Asheville: 1xx) that were vacant or
                  did not exist in the previous roll are new construction not yet valued: never
                  flagged. Skipped when record_note says the building is on another (exempt)
                  account, and for inventory classes (Asheville: 458 manufactured-home sales).
estimate_off      estimated land (condo_land_imputed = 1) with |z| >= 4.  sev as land_psf_*.
estimate_floor    record_note says the estimate is a conservative floor.  sev 0.6, stake = land.

TOKEN BUILDINGS (Opportunities, not issues)
-------------------------------------------
A building class with improvements <= 1% of total and land >= $50k is the assessor saying the
building adds nothing over the land (Buncombe's 2021 reappraisal set $0-$400 on empty big boxes,
motels, a bank branch...). When the previous roll shows the same token value (or the value moved
from the building to the land), the parcel scores nothing as an issue and is listed under
Opportunities ("The county values the building at $100 and the land at $1.5M ..."). A building
written off after a tagged storm (previous roll valued, a damage-assessment point on the parcel)
is listed there too, with the storm named, and so is a parcel the map already shows as Vacant
whose class still names a building. Without a previous roll, non-house token buildings go to
Opportunities and keep only a weak issue flag.

SCORE
-----
  V(stake) = min(1, log10(1 + stake / $10k) / log10(1 + $100M / $10k))    (value at stake, 0..1)
  p_s      = w_s * sev_s * V(stake_s)
             w: land_psf_high 1.0; land_psf_low 0.7 (0.5 on vacant parcels); zero_land 1.0;
                sliver 1.0; label_vacant_built / label_parking_built 0.8; building_dropped 0.9;
                label_built_empty 0.6; estimate_off 0.8; estimate_floor 0.1 (a disclosure)
  score    = 100 * (1 - prod_s (1 - p_s))  (noisy-OR: more signals raise it, never past 100)

`likely_remnant` parcels are left out of both lists when the city's config has hideRemnants
(they are hidden on the map too); the output metadata records how many. --csv writes every
flagged parcel with its per-signal severity / stake / z-scores, for auditing the scoring.

JSON: top-level metadata (city, generated, method, per-signal counts, city medians,
link_template) plus issues.items / opportunities.items. Per item: rank, score (issues),
parcel_id, category, refined, use_desc, use_code, land / impr / total, land_psf, nbr_psf,
psf_ratio, z, lot_sqft, lot_acres, impr_share, signals + reasons (aligned lists), note
(record_note), link (omitted when link_template covers it), center [lng, lat] (a point inside
the parcel), outline (<= ~40 vertices, metres east/north of center, flat rings [x0, y0, ...]),
and when known prior_land / prior_impr (previous roll) and damage_event. Opportunity items add
opportunity_type (vacant / parking / underdeveloped / token_building / storm_writedown).

CHANGELOG
---------
2026-09-30b  Retuned against 250 hand-labelled parcels (claude/artifacts/review-batches):
             token buildings and storm write-downs move to Opportunities; house classes under
             construction are no longer flagged; building_dropped (new) stakes the missing
             building; land_psf_low skips nominal-by-design classes, caps its stake at the
             parcel's value, compares vacant land with same-use neighbours and acreage with
             acreage, z-scores per lot-size band, discounts enclosed (landlocked) lots, and
             leaves footprint pads out of the donors and the $/sqft signals; zero_land's
             nominal branch and estimate_floor weigh less; per-city rules block; optional
             previous-roll and storm-damage sources (cached); --explain. Against the labels:
             FALSE_ALARM share of the top 250 41% -> 7%; SOURCE_DATA_ERRORs in the top 25
             11 -> 16; 77 of 78 labelled token-building / storm findings now in Opportunities.
2026-09-30a  First version.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import warnings
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from data.parquet_registry import CITY_PARQUETS, resolve_city  # noqa: E402

SQFT_PER_ACRE = 43560.0
SQFT_PER_M2 = 10.763910417

# ── tuning ────────────────────────────────────────────────────────────────────
K = 15                     # nearest donors for the neighbour median
PEER_RADIUS_M = 1500.0     # same-use peers must be this close ...
PEER_MIN = 8               # ... and at least this many, else fall back to plain neighbours
BIG_LOT_SQFT = SQFT_PER_ACRE   # lots this big also get the similar-size baseline
SIM_BAND = 3.0             # similar size = within this factor of the lot's area
SIM_RADIUS_M = 3000.0
SIM_MIN = 6
SIM_POOL = 400             # nearest candidate donors searched for similar-size ones
SIZE_BANDS_ACRES = (0.25, 1.0, 5.0)   # z-score spread is measured per lot-size band
BAND_MIN_DONORS = 100
Z_FLAG = 4.0               # |z| where the $/sqft signals start (~3.5x off the neighbours)
Z_CAP = 12.0               # |z| where they saturate (extreme z-scores are capped here)
STAKE_REF = 10_000.0       # V(stake) = log10(1 + stake/STAKE_REF) / log10(1 + STAKE_NORM/STAKE_REF)
STAKE_NORM = 100_000_000.0
SLIVER_MAX_SQFT = 5000.0
SLIVER_MAX_REL = 0.25      # lot <= this share of the neighbours' median lot
SLIVER_MIN_LAND = 25_000.0
SLIVER_MIN_X = 10.0        # land buys >= this many lots at the neighbours' rate
NOMINAL_LAND_SHARE = 0.01
NOMINAL_MIN_IMPR = 25_000.0
VACANT_MIN_IMPR = 25_000.0
PARKING_MIN_IMPR = 250_000.0
BUILT_EMPTY_MAX_SHARE = 0.01
BUILT_EMPTY_MIN_LAND = 50_000.0
TOKEN_MAX = 1_000.0        # a building value <= max(this, 1% of total) is a token / nominal value
W_LOW_VACANT = 0.5         # land_psf_low weight on vacant-category parcels (0.7 elsewhere)
DAMAGE_SNAP_M = 15.0       # a damage point tags the nearest parcel within this distance
STORM_LOW_WEIGHT = 0.3     # land_psf_low weight factor when a tagged storm wrote the land down
ENCLOSED_SHARE = 0.95      # boundary share touching other parcels above which a lot has no frontage
ENCLOSED_TOL_M = 1.5
ENCLOSED_WEIGHT = 0.3      # land_psf_low weight factor on enclosed (landlocked / backland) lots
LAND_MOVED_MIN = 1.2       # "value moved to the land": land >= 1.2x the previous roll's ...
TOTAL_KEPT_MIN = 0.7       # ... and the total >= 0.7x the previous roll's

SIGNALS: dict[str, dict] = {
    "land_psf_high": {"weight": 1.0, "label": "Land $/sqft far above neighbours",
                      "description": "Land value per sqft is far above nearby parcels', even allowing for lot "
                                     "size and use."},
    "land_psf_low": {"weight": 0.7, "label": "Land $/sqft far below neighbours",
                     "description": "Land value per sqft is far below nearby parcels', even allowing for lot "
                                    "size and use."},
    "zero_land": {"weight": 1.0, "label": "Land value missing",
                  "description": "The land is valued at $0 (or next to nothing) but the improvements are "
                                 "valued: the land value is probably missing."},
    "sliver": {"weight": 1.0, "label": "Small lot, big land value",
               "description": "A small lot carries the land value of a much bigger holding, so its $/sqft "
                              "is meaningless."},
    "label_vacant_built": {"weight": 0.8, "label": "Vacant label, valued building",
                           "description": "Classed as vacant land but carries sizeable improvements."},
    "label_parking_built": {"weight": 0.8, "label": "Parking label, big building",
                            "description": "Classed as a surface parking lot but most of its value is "
                                           "improvements."},
    "building_dropped": {"weight": 0.9, "label": "Building value vanished",
                         "description": "The previous roll valued a building here; now it is valued at "
                                        "~$0, with no storm-damage record to explain it."},
    "label_built_empty": {"weight": 0.6, "label": "Building class, no building value",
                          "description": "A building use class with ~$0 of improvements that the previous "
                                         "roll doesn't explain: a new parcel that lost its building value, "
                                         "or a class or flag the county never updated. Deliberate token "
                                         "values are listed under Opportunities instead."},
    "estimate_off": {"weight": 0.8, "label": "Estimated land off-pattern",
                     "description": "Land is our estimate (the assessor gave $0) and sits far from its "
                                    "neighbours' rate."},
    "estimate_floor": {"weight": 0.1, "label": "Land estimate is a floor",
                       "description": "Land is a conservative floor estimate: few similar parcels nearby."},
}

OPPORTUNITY_LABELS = ("Vacant", "Underdeveloped", "Parking Lot")

# ── per-city rules ────────────────────────────────────────────────────────────
# Everything assessor-specific. A city without an entry gets DEFAULT_RULES (category / use_desc
# text only). Codes are matched against the parquet's use_code column when it has one.
DEFAULT_RULES: dict = {
    # land_psf_low never fires on these (and they are not $/sqft donors): the assessor values
    # them nominally by design.
    "no_low_psf_desc": r"substandard|common area|cemeter|lake|pond|right.of.way",
    "no_low_psf_codes": (),
    # land $/sqft is a method artefact here (neither direction fires; not donors).
    "no_psf_codes": (),
    # house classes: "improved, $0 building" usually means a house not valued yet.
    "house_codes": None,  # regex on use_code; None -> house_categories
    "house_categories": ("Single Family", "Townhome", "Mobile Home", "Condominium"),
    # vacant parcels join the non-residential family when use_desc matches, else residential.
    "vacant_nonres_desc": r"\bcomm|indus|office|retail|business",
    "family_by_code": {},  # use_code -> "res" / "nonres" (wins over the category)
    # footprint pads: their land is a per-unit share drawn on the unit's footprint.
    "pad_codes": (),
    "pad_categories": ("Townhome", "Condominium", "Commercial Condominium"),
    "pad_max_sqft": 2500.0,
    "pad_house_max_sqft": None,   # house-class lots smaller than this are footprint lots too
    # building classes whose "buildings" aren't real property (e.g. dealer inventory).
    "built_empty_skip_codes": (),
    # record_note pattern saying the building is on another (e.g. exempt) account: not a gap.
    "building_elsewhere_note": None,
    # Optional previous roll (ArcGIS layer): see load_prior_values.
    "prior_values": None,
    # Optional storm-damage assessment points (ArcGIS point layer): see load_damage_points.
    "damage_points": None,
}

CITY_RULES: dict[str, dict] = {
    # Buncombe County, NC (class codes: claude/artifacts/buncombe-class-codes.csv).
    "asheville": {
        "prefixes": ("asheville-nc",),
        # 301 SUBSTANDARD LOT, 305 ROAD/STREET, 315 LAKE/POND, 317 COMMON AREA, 695 CEMETERIES
        "no_low_psf_codes": ("301", "305", "315", "317", "695"),
        # 418 INN-B&B: income approach, a flat ~$84-98k land figure whatever the lot size.
        "no_psf_codes": ("418",),
        "house_codes": r"^1\d\d$",
        "family_by_code": {
            "300": "res", "301": "res", "311": "res", "312": "res", "320": "res",   # vacant / accessory
            "340": "nonres", "341": "nonres",                                        # commercial vacant
            "635": "res",                                    # LIHTC housing (category Institutional)
        },
        "pad_codes": ("120", "121", "466"),  # CONDO, TOWNHOME, COMM CONDO
        "pad_house_max_sqft": 1500.0,        # 1xx cottage-court lots drawn as footprints (31 parcels)
        "built_empty_skip_codes": ("458",),  # MH/MODULAR SALES: display homes are inventory
        "building_elsewhere_note": r"tax-exempt accounts",   # run_asheville.py: exempt members left out
        # opendata_2 "Property_YYYY" holds the roll billed in YYYY-1: Property_2025 = the 2024 roll
        # (TaxYear 24, pre-Helene). The shipped map is the 2026 roll.
        "prior_values": {
            "label": "2024 roll",
            "url": "https://gis.buncombecounty.org/arcgis/rest/services/opendata_2/MapServer/17",
            "where": "City='CAS'",
            "fields": {"id": "PIN", "class": "Class", "improved": "Improved", "land": "LandValue",
                       "building": "BuildingValue", "total": "TotalMarketValue"},
        },
        # County Helene damage assessments (NEMAC / SAR / Red Cross ...), Oct-Dec 2024.
        "damage_points": {
            "label": "Hurricane Helene",
            "url": ("https://services6.arcgis.com/VLA0ImJ33zhtGEaP/ArcGIS/rest/services/"
                    "HeleneCombinedDamageAssessmentResults_Clipped/FeatureServer/0"),
            "where": "1=1",
            "id_field": "pinnum",
        },
    },
}


def resolve_rules(city: str | None, prefix: str) -> tuple[dict, str | None]:
    key = city if city in CITY_RULES else next(
        (k for k, r in CITY_RULES.items() if prefix in r.get("prefixes", ())), None)
    return {**DEFAULT_RULES, **(CITY_RULES.get(key) or {})}, key


# ── column resolution ────────────────────────────────────────────────────────
def pick(df: pd.DataFrame, *cands: str) -> str | None:
    for c in cands:
        if c in df.columns:
            return c
    return None


def num(df: pd.DataFrame, col: str | None, default=np.nan) -> np.ndarray:
    if col is None:
        return np.full(len(df), default, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").to_numpy(float)


def text(df: pd.DataFrame, col: str | None) -> np.ndarray:
    if col is None:
        return np.full(len(df), None, dtype=object)
    s = df[col].astype(object).where(df[col].notna(), None)
    return np.array([None if (v is None or str(v).strip() in ("", "nan", "None")) else str(v).strip()
                     for v in s], dtype=object)


def use_family(cat: np.ndarray) -> np.ndarray:
    """Broad use family from the canonical category label: res / nonres / vacant / other."""
    out = np.full(len(cat), "other", dtype=object)
    for i, c in enumerate(cat):
        s = (c or "").lower()
        if "vacant" in s:
            out[i] = "vacant"
        elif re.search(r"commercial|industrial|office|retail|hotel|lodging|parking|institution|"
                       r"recreation|mixed|warehouse|utility", s):
            out[i] = "nonres"
        elif re.search(r"single|family|townho|duplex|triplex|residential|mobile|manufactured|"
                       r"apartment|condo|row ?house", s):
            out[i] = "res"
    return out


def peer_family(fam: np.ndarray, code: np.ndarray, desc: np.ndarray, rules: dict) -> np.ndarray:
    """The family a parcel is compared within: vacant land joins the family of its use."""
    out = fam.copy()
    nonres = re.compile(rules["vacant_nonres_desc"], re.I) if rules.get("vacant_nonres_desc") else None
    for i in np.flatnonzero(fam == "vacant"):
        out[i] = "nonres" if nonres and nonres.search(desc[i] or "") else "res"
    by_code = rules.get("family_by_code") or {}
    for i, c in enumerate(code):
        if c in by_code:
            out[i] = by_code[c]
    return out


def code_in(code: np.ndarray, codes) -> np.ndarray:
    return np.isin(code, list(codes)) if codes else np.zeros(len(code), bool)


def desc_match(desc: np.ndarray, pattern: str | None) -> np.ndarray:
    if not pattern:
        return np.zeros(len(desc), bool)
    rx = re.compile(pattern, re.I)
    return np.array([bool(d and rx.search(d)) for d in desc])


# ── inputs ───────────────────────────────────────────────────────────────────
def resolve_local_path(city: str | None, override: str | None) -> Path:
    """Same lookup as parquet_to_pmtiles.resolve_local_path, anchored at the repo root."""
    if override:
        return Path(override).expanduser()
    if city:
        meta = CITY_PARQUETS.get(city)
        if meta:
            for base in (ROOT, Path.cwd()):
                p = base / "data" / "jurisidictions" / "data" / city / meta.legacy_filename
                if p.exists():
                    return p
        return ROOT / "data" / "output" / "final" / f"{city}.parquet"
    raise ValueError("Either --city or --file must be provided")


def load_city_config(city: str | None) -> dict:
    """The frontend city JSON (viz/src/cities/<key>.json, or the CIVICMAPPER_EXTRA_CITIES overlay)."""
    if not city:
        return {}
    dirs = [ROOT / "viz" / "src" / "cities"]
    extra = os.environ.get("CIVICMAPPER_EXTRA_CITIES", "").strip()
    if extra:
        dirs.append(Path(extra))
    for d in dirs:
        p = d / f"{city}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return {}


# ── optional sources (ArcGIS REST, cached next to the parquet) ───────────────
UA = "civic-mapper build_review_feed.py (parcel review feed; cached; <= 1 request/s)"


def _get_json(url: str, params: dict, tries: int = 4) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    for k in range(tries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                js = json.loads(r.read().decode("utf-8"))
            if isinstance(js, dict) and "error" in js:
                raise RuntimeError(js["error"])
            return js
        except Exception:
            if k == tries - 1:
                raise
            time.sleep(5 * (k + 1))
    return {}


def arcgis_fetch(layer_url: str, where: str, fields: list[str], geometry: bool = False,
                 pause: float = 1.0) -> list[dict]:
    """Every feature of an ArcGIS REST layer matching `where`, paged, one request per `pause` s."""
    meta = _get_json(layer_url, {"f": "json"})
    oid = meta.get("objectIdField") or next(
        (f["name"] for f in meta.get("fields", []) if f.get("type") == "esriFieldTypeOID"), None)
    page = max(1, min(int(meta.get("maxRecordCount") or 1000), 2000))
    out: list[dict] = []
    off = 0
    while True:
        time.sleep(pause)
        params = {"where": where, "outFields": ",".join(fields), "f": "json",
                  "returnGeometry": "true" if geometry else "false",
                  "resultOffset": off, "resultRecordCount": page}
        if oid:
            params["orderByFields"] = oid
        if geometry:
            params["outSR"] = 4326
        js = _get_json(layer_url.rstrip("/") + "/query", params)
        feats = js.get("features") or []
        out += feats
        print(f"    {layer_url.rsplit('/', 3)[-3]}: {len(out):,} records", end="\r", flush=True)
        if not feats or (len(feats) < page and not js.get("exceededTransferLimit")):
            break
        off += len(feats)
    print()
    return out


def _cached(cache: Path, mode: str, fetch) -> pd.DataFrame | None:
    """mode: auto (cache, else fetch) / cache (cache only) / refresh (always fetch) / off."""
    if mode == "off":
        return None
    if cache.exists() and mode != "refresh":
        return pd.read_parquet(cache)
    if mode == "cache":
        print(f"  (no cache at {cache.name}; --sources cache: skipped)")
        return None
    try:
        df = fetch()
    except Exception as e:  # network / service trouble: the feed still builds without it
        print(f"  WARNING: could not fetch {cache.name} ({e}); continuing without it")
        return None
    df.to_parquet(cache, index=False)
    print(f"  cached {len(df):,} rows -> {cache}")
    return df


def load_prior_values(spec: dict | None, cache: Path, mode: str) -> pd.DataFrame | None:
    """The previous roll: id, class, improved, land, building, total, impr (= total - land)."""
    if not spec:
        return None
    f = spec["fields"]

    def fetch() -> pd.DataFrame:
        print(f"  fetching the {spec['label']} from {spec['url']}")
        want = [v for v in f.values() if v]
        rows = [x["attributes"] for x in arcgis_fetch(spec["url"], spec.get("where", "1=1"), want)]
        df = pd.DataFrame(rows)
        out = pd.DataFrame({k: df[v] if v in df.columns else None for k, v in f.items() if v})
        for c in ("land", "building", "total"):
            if c in out.columns:
                out[c] = pd.to_numeric(out[c], errors="coerce")
        out["id"] = out["id"].astype(str).str.strip()
        return out

    df = _cached(cache, mode, fetch)
    if df is None or df.empty:
        return None
    if "total" in df.columns and "land" in df.columns:
        df["impr"] = np.where(df["total"] > 0, df["total"] - df["land"].fillna(0), df.get("building"))
    else:
        df["impr"] = df.get("building")
    return df.drop_duplicates("id").set_index("id")


def load_damage_points(spec: dict | None, cache: Path, mode: str) -> pd.DataFrame | None:
    """Storm-damage assessment points: id (parcel id, may be blank), lng, lat."""
    if not spec:
        return None

    def fetch() -> pd.DataFrame:
        print(f"  fetching {spec['label']} damage points from {spec['url']}")
        feats = arcgis_fetch(spec["url"], spec.get("where", "1=1"), [spec["id_field"]], geometry=True)
        return pd.DataFrame({
            "id": [str((x.get("attributes") or {}).get(spec["id_field"]) or "").strip() for x in feats],
            "lng": [(x.get("geometry") or {}).get("x") for x in feats],
            "lat": [(x.get("geometry") or {}).get("y") for x in feats],
        })

    df = _cached(cache, mode, fetch)
    return None if df is None or df.empty else df


# ── formatting (reason text) ─────────────────────────────────────────────────
class Fmt:
    def __init__(self, currency: str = "$", metric: bool = False):
        self.cur, self.metric = currency, metric
        self.unit = "m²" if metric else "sqft"

    def money(self, v: float) -> str:
        v = float(v)
        a = abs(v)
        if a >= 1e9:
            s = f"{a / 1e9:.1f}B"
        elif a >= 1e6:
            s = f"{a / 1e6:.1f}M"
        else:
            s = f"{a:,.0f}"
        return ("-" if v < 0 else "") + self.cur + s

    def rate(self, psf: float) -> str:
        v = psf * SQFT_PER_M2 if self.metric else psf
        if v >= 100:
            s = f"{v:,.0f}"
        elif v >= 0.1:
            s = f"{v:,.2f}"
        else:
            s = f"{v:.3f}"
        return f"{self.cur}{s}/{self.unit}"

    def area(self, sqft: float) -> str:
        if self.metric:
            m2 = sqft / SQFT_PER_M2
            return f"{m2 / 10000:,.2f} ha" if m2 >= 10000 else f"{m2:,.0f} m²"
        return f"{sqft / SQFT_PER_ACRE:,.1f} acres" if sqft >= SQFT_PER_ACRE else f"{sqft:,.0f} sqft"

    @staticmethod
    def times(x: float) -> str:
        return f"{x:,.0f}×" if x >= 10 else f"{x:.1f}×"


# ── neighbour baseline ───────────────────────────────────────────────────────
def knn(xy: np.ndarray, donors: np.ndarray, targets: np.ndarray, k: int):
    """k nearest donors of each target, excluding the target itself. Returns (idx, dist); -1/inf pads."""
    n = len(xy)
    idx = np.full((n, k), -1, dtype=np.int64)
    dist = np.full((n, k), np.inf)
    d = np.flatnonzero(donors)
    t = np.flatnonzero(targets)
    if not len(d) or not len(t):
        return idx, dist
    kk = min(k + 1, len(d))
    dd, ii = cKDTree(xy[d]).query(xy[t], k=kk)
    dd, ii = dd.reshape(len(t), -1), d[np.asarray(ii).reshape(len(t), -1)]
    is_self = ii == t[:, None]
    # Drop self (at most once per row), keep the first k of the rest.
    order = np.argsort(is_self, axis=1, kind="stable")
    ii = np.take_along_axis(ii, order, axis=1)[:, :k]
    dd = np.take_along_axis(dd, order, axis=1)[:, :k]
    self_left = np.take_along_axis(is_self, order, axis=1)[:, :k]
    ii[self_left], dd[self_left] = -1, np.inf
    idx[t, : ii.shape[1]], dist[t, : dd.shape[1]] = ii, dd
    return idx, dist


def _nanmedian_rows(v: np.ndarray) -> np.ndarray:
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return np.nanmedian(v, axis=1)


def masked_median(values: np.ndarray, idx: np.ndarray, ok: np.ndarray | None = None) -> np.ndarray:
    v = np.where(idx >= 0, values[np.clip(idx, 0, None)], np.nan)
    if ok is not None:
        v = np.where(ok, v, np.nan)
    return _nanmedian_rows(v)


def similar_size_median(xy: np.ndarray, la: np.ndarray, vals: np.ndarray, donors: np.ndarray,
                        targets: np.ndarray) -> np.ndarray:
    """Median of vals over the K nearest donors within SIM_RADIUS_M whose lot is within SIM_BAND x
    the target's (>= SIM_MIN of them, else NaN). The target never counts itself."""
    out = np.full(len(xy), np.nan)
    d = np.flatnonzero(donors)
    t = np.flatnonzero(targets)
    if not len(d) or not len(t):
        return out
    kk = min(SIM_POOL, len(d))
    dd, ii = cKDTree(xy[d]).query(xy[t], k=kk)
    dd, ii = dd.reshape(len(t), -1), d[np.asarray(ii).reshape(len(t), -1)]
    ok = (dd <= SIM_RADIUS_M) & (ii != t[:, None]) & (np.abs(la[ii] - la[t][:, None]) <= math.log(SIM_BAND))
    ok &= np.cumsum(ok, axis=1) <= K
    med = _nanmedian_rows(np.where(ok, vals[ii], np.nan))
    enough = ok.sum(axis=1) >= SIM_MIN
    out[t[enough]] = med[enough]
    return out


def trimmed_slope(x: np.ndarray, y: np.ndarray) -> float:
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 200:
        return -0.5
    b = np.polyfit(x, y, 1)
    r = y - np.polyval(b, x)
    mad = np.median(np.abs(r - np.median(r))) * 1.4826
    keep = np.abs(r - np.median(r)) <= 3 * mad
    b = np.polyfit(x[keep], y[keep], 1)
    return float(np.clip(b[0], -0.9, -0.1))


def _med_sigma(r: np.ndarray) -> tuple[float, float]:
    med = float(np.median(r))
    return med, float(1.4826 * np.median(np.abs(r - med))) or 1e-9


def banded_z(v: np.ndarray, ref: np.ndarray, band: np.ndarray) -> tuple[np.ndarray, float, list]:
    """Robust z of v, with the median / MAD taken over reference parcels in the same lot-size band
    (the citywide figures where a band has too few). Returns z, the citywide sigma, band sigmas."""
    ok = ref & np.isfinite(v)
    _, sig_all = _med_sigma(v[ok]) if ok.any() else (0.0, 1.0)
    med_all = float(np.median(v[ok])) if ok.any() else 0.0
    z = np.full(len(v), np.nan)
    sig_b = []
    for b in range(len(SIZE_BANDS_ACRES) + 1):
        sel = band == b
        r = ok & sel
        med, sig = _med_sigma(v[r]) if r.sum() >= BAND_MIN_DONORS else (med_all, sig_all)
        z[sel] = (v[sel] - med) / sig
        sig_b.append(round(sig, 4) if r.sum() >= BAND_MIN_DONORS else None)
    return z, sig_all, sig_b


def enclosed_share(gm: gpd.GeoSeries, ix: list[int]) -> dict[int, float]:
    """Share of each parcel's boundary within ENCLOSED_TOL_M of another parcel. ~1.0 means other parcels
    surround it: no street frontage (streets are gaps between parcels), i.e. landlocked or backland.
    Parcels missing from the file (exempt, $0 common areas) count as frontage, so it errs towards 'not
    enclosed'."""
    out: dict[int, float] = {}
    sidx = gm.sindex
    for i in ix:
        g = gm.iloc[i]
        if g is None or g.is_empty:
            continue
        cand = [int(c) for c in sidx.query(g.buffer(ENCLOSED_TOL_M), predicate="intersects") if int(c) != i]
        b = g.boundary
        if not cand or b.length <= 0:
            out[i] = 0.0
            continue
        nb = unary_union([gm.iloc[c].buffer(ENCLOSED_TOL_M) for c in cand])
        out[i] = float(b.intersection(nb).length / b.length)
    return out


# ── outline ──────────────────────────────────────────────────────────────────
def outline_rings(geom, cx: float, cy: float, max_vertices: int = 40) -> list[list[float]]:
    """Simplified outline in metres east/north of (cx, cy): a list of flat rings [x0, y0, x1, y1, ...]
    (closing vertex dropped). Keeps the largest parts (and big holes) within max_vertices total."""
    if geom is None or geom.is_empty:
        return []
    polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
    polys = sorted(polys, key=lambda p: p.area, reverse=True)
    total = sum(p.area for p in polys) or 1.0
    polys = [p for p in polys if p.area >= 0.02 * total][:4] or polys[:1]
    minx, miny, maxx, maxy = geom.bounds
    span = max(maxx - minx, maxy - miny, 1e-6)
    prec = 1 if span < 40 else 0  # 0.1 m on small lots, whole metres otherwise

    def rings_of(tol: float):
        out = []
        for p in polys:
            s = p.simplify(tol, preserve_topology=True) if tol > 0 else p
            if s.is_empty:
                continue
            parts = list(s.geoms) if s.geom_type == "MultiPolygon" else [s]
            for q in parts:
                out.append(list(q.exterior.coords)[:-1])
                for h in q.interiors:
                    if _ring_area(list(h.coords)) >= 0.05 * q.area:
                        out.append(list(h.coords)[:-1])
        return out

    tol = span * 0.003  # drops near-collinear vertices that are invisible in a thumbnail
    rings = rings_of(tol)
    while sum(len(r) for r in rings) > max_vertices and tol < span:
        tol *= 1.6
        rings = rings_of(tol)
    res = []
    for r in rings:
        flat: list = []
        for x, y in r:
            px, py = round(x - cx, prec), round(y - cy, prec)
            if prec == 0:
                px, py = int(px), int(py)
            if len(flat) >= 2 and flat[-2] == px and flat[-1] == py:
                continue
            flat += [px, py]
        if len(flat) >= 6:
            res.append(flat)
    return res


def _ring_area(coords) -> float:
    a = 0.0
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


# ── main ─────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", help="City key (e.g. asheville); resolves the parquet, reads the city's viz "
                                   "config (hideRemnants, currency, units) and picks its CITY_RULES.")
    ap.add_argument("--file", help="Override the local parquet path.")
    ap.add_argument("--out", help="Output JSON path (default: next to the parquet, <prefix>-review.json).")
    ap.add_argument("--top", type=int, default=300, help="Items per tab (default 300; Opportunities also "
                                                        "lists every token-building / storm parcel).")
    ap.add_argument("--hide-remnants", action=argparse.BooleanOptionalAction, default=None,
                    help="Leave likely_remnant parcels out (default: the city's hideRemnants).")
    ap.add_argument("--sources", choices=("auto", "cache", "refresh", "off"), default="auto",
                    help="Optional per-city sources (previous roll, storm damage): auto = use the cache next "
                         "to the parquet, fetching it if missing; cache = never fetch; refresh = re-fetch; "
                         "off = ignore them.")
    ap.add_argument("--explain", nargs="+", metavar="ID",
                    help="Print every baseline, z-score, signal and state for these parcel ids (why is X "
                         "(not) flagged?).")
    ap.add_argument("--csv", help="Also write EVERY flagged parcel (not just the top N) with its per-signal "
                                  "severity and stake to this CSV, for auditing the scoring.")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    city = args.city.strip().lower() if args.city else None
    path = resolve_local_path(city, args.file)
    if not path.exists():
        raise SystemExit(f"Parquet not found: {path}")
    cfg = load_city_config(city)
    hide_remnants = cfg.get("hideRemnants") is True if args.hide_remnants is None else args.hide_remnants
    fmt = Fmt(cfg.get("currencySymbol", "$"), cfg.get("unitSystem") == "metric")
    combined_only = cfg.get("combinedValueOnly") is True

    meta = None
    if city:
        try:
            meta = resolve_city(city)
        except ValueError:
            if not args.file:
                raise
    prefix = meta.slug if meta else re.sub(r"-parcels$", "", path.stem)
    out = Path(args.out) if args.out else path.with_name(f"{prefix}-review.json")
    rules, rules_key = resolve_rules(city, prefix)

    print(f"Loading {path}")
    gdf = gpd.read_parquet(path)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].reset_index(drop=True)
    n = len(gdf)
    print(f"  {n:,} parcels; rules: {rules_key or 'default'}")

    # Columns (canonical names first, then the aliases other cities ship).
    c_id = pick(gdf, "parcel_id", "PARCELID", "parcelid", "pin", "PIN", "parcelpin", "parcel_number",
                "PROPID", "gpin", "account_number", "OBJECTID")
    c_land = pick(gdf, "current_full_land_value", "land_value", "REALLANDVA")
    c_impr = pick(gdf, "improvement_value", "REALIMPROV")
    c_total = pick(gdf, "full_market_value", "TLLDIMPROV", "total_value")
    c_cat = pick(gdf, "property_land_use_category", "PROPERTY_CATEGORY", "property_category")
    c_ref = pick(gdf, "property_land_use_refined", "property_category_refined")
    c_use = pick(gdf, "use_desc", "use_description", "use_code_desc", "land_use_desc")
    c_code = pick(gdf, "use_code", "USE_CODE", "class_code", "property_class")
    c_link = pick(gdf, "link", "parcel_link")
    if c_land is None:
        raise SystemExit("No land value column (current_full_land_value / land_value / REALLANDVA)")
    print(f"  columns: id={c_id} land={c_land} impr={c_impr} total={c_total} category={c_cat} "
          f"refined={c_ref} use={c_use} code={c_code} link={c_link}")

    pid = text(gdf, c_id) if c_id else np.array([f"row-{i}" for i in range(n)], dtype=object)
    pid = np.array([p if p is not None else f"row-{i}" for i, p in enumerate(pid)], dtype=object)
    land = np.nan_to_num(num(gdf, c_land), nan=0.0)
    impr = np.nan_to_num(num(gdf, c_impr), nan=0.0) if c_impr else np.zeros(n)
    total = num(gdf, c_total) if c_total else land + impr
    total = np.where(np.isfinite(total) & (total > 0), total, land + impr)
    cat = text(gdf, c_cat)
    refined = text(gdf, c_ref)
    use_desc = text(gdf, c_use)
    code = text(gdf, c_code)
    link = text(gdf, c_link)
    note = text(gdf, "record_note" if "record_note" in gdf.columns else None)
    imputed = np.nan_to_num(num(gdf, pick(gdf, "condo_land_imputed"), 0), nan=0) == 1
    remnant = np.nan_to_num(num(gdf, pick(gdf, "likely_remnant"), 0), nan=0) == 1
    n_acc = np.nan_to_num(num(gdf, pick(gdf, "n_accounts"), 1), nan=1)

    metric_crs = gdf.estimate_utm_crs()
    gm = gdf.geometry.to_crs(metric_crs)
    c_acres, c_sqft, c_m2 = pick(gdf, "land_area_acres"), pick(gdf, "land_area_sqft", "area_sqft"), \
        pick(gdf, "land_area_sqm")
    if c_acres:
        area = num(gdf, c_acres) * SQFT_PER_ACRE
    elif c_sqft:
        area = num(gdf, c_sqft)
    elif c_m2:
        area = num(gdf, c_m2) * SQFT_PER_M2
    else:
        area = np.full(n, np.nan)
    geo_area = gm.area.to_numpy() * SQFT_PER_M2
    area = np.where(np.isfinite(area) & (area > 0), area, geo_area)
    print(f"  area from {c_acres or c_sqft or c_m2 or 'geometry'}; metric CRS {metric_crs}")

    rp = gm.representative_point()
    xy = np.column_stack([rp.x.to_numpy(), rp.y.to_numpy()])
    rp_ll = gpd.GeoSeries(rp, crs=metric_crs).to_crs(4326)
    lng, lat = rp_ll.x.to_numpy(), rp_ll.y.to_numpy()

    # ── optional sources: the previous roll and storm-damage points ──────────
    src_dir = path.parent
    prior = load_prior_values(rules.get("prior_values"), src_dir / f"{prefix}-prior-values.parquet",
                              args.sources)
    prior_label = (rules.get("prior_values") or {}).get("label", "previous roll")
    has_prior = np.zeros(n, bool)
    p_land = np.full(n, np.nan)
    p_impr = np.full(n, np.nan)
    p_total = np.full(n, np.nan)
    p_cls = np.full(n, None, dtype=object)
    p_improved = np.full(n, None, dtype=object)
    if prior is not None:
        pr = prior.reindex(pd.Index(pid.astype(str)))
        has_prior = pr["land"].notna().to_numpy() | pr["impr"].notna().to_numpy()
        p_land = pr["land"].to_numpy(float)
        p_impr = pd.to_numeric(pr["impr"], errors="coerce").to_numpy(float)
        p_total = pr["total"].to_numpy(float) if "total" in pr.columns else p_land + p_impr
        if "class" in pr.columns:
            p_cls = pr["class"].astype(object).where(pr["class"].notna(), None).to_numpy()
        if "improved" in pr.columns:
            p_improved = pr["improved"].astype(object).where(pr["improved"].notna(), None).to_numpy()
        print(f"  {prior_label}: {len(prior):,} records; {int(has_prior.sum()):,} of {n:,} parcels matched by id")

    dmg_spec = rules.get("damage_points") or {}
    storm_label = dmg_spec.get("label", "storm")
    storm = np.zeros(n, bool)
    dmg = load_damage_points(rules.get("damage_points"), src_dir / f"{prefix}-damage-points.parquet",
                             args.sources)
    if dmg is not None:
        storm |= np.isin(pid.astype(str), dmg["id"][dmg["id"] != ""].unique())
        pts = dmg.dropna(subset=["lng", "lat"])
        if len(pts):
            pg = gpd.GeoDataFrame(geometry=gpd.points_from_xy(pts["lng"], pts["lat"]), crs=4326).to_crs(metric_crs)
            # A parcel is tagged when a point lies in it or within DAMAGE_SNAP_M of it (assessment
            # points often sit on the street frontage or the building next door). The tag only says
            # which storm explains a building write-down; it never raises a score.
            j = gpd.sjoin_nearest(gpd.GeoDataFrame(geometry=gm.reset_index(drop=True), crs=metric_crs), pg,
                                  how="inner", max_distance=DAMAGE_SNAP_M)
            storm[np.unique(j.index.to_numpy())] = True
        print(f"  {storm_label} damage points: {len(dmg):,}; {int(storm.sum()):,} parcels tagged")

    # ── the land $/sqft baseline ─────────────────────────────────────────────
    with np.errstate(divide="ignore", invalid="ignore"):
        psf = np.where(area > 0, land / area, np.nan)
        lpsf = np.where(psf > 0, np.log(psf), np.nan)
        la = np.where(area > 0, np.log(area), np.nan)
        impr_share = np.where(total > 0, impr / total, np.nan)
    fam = use_family(cat)
    is_vac = fam == "vacant"
    fam_peer = peer_family(fam, code, use_desc, rules)
    no_low = code_in(code, rules.get("no_low_psf_codes")) | desc_match(use_desc, rules.get("no_low_psf_desc"))
    no_psf = code_in(code, rules.get("no_psf_codes"))
    house = (np.array([bool(c and re.search(rules["house_codes"], c)) for c in code])
             if rules.get("house_codes") and c_code else np.isin(cat, list(rules.get("house_categories") or ())))
    pad = (((code_in(code, rules.get("pad_codes")) | np.isin(cat, list(rules.get("pad_categories") or ())))
            & (area < float(rules.get("pad_max_sqft") or 0)))
           | (house & (area < float(rules.get("pad_house_max_sqft") or 0))))
    donor = np.isfinite(lpsf) & np.isfinite(la) & ~remnant & ~imputed & ~pad & ~no_low & ~no_psf
    # Footprint pads are only compared with other pads: next to detached lots every pad is a
    # "sliver" worth 5x its neighbours' rate, which says nothing about the pad's record.
    pad_donor = np.isfinite(lpsf) & np.isfinite(la) & ~remnant & ~imputed & pad
    fam_peer[pad] = "pad"
    everyone = np.ones(n, bool)
    band = np.digitize(np.nan_to_num(area, nan=0) / SQFT_PER_ACRE, SIZE_BANDS_ACRES)

    # Plain neighbours.
    nb_idx, _ = knn(xy, donor, everyone, K)
    if pad_donor.sum() > K:
        nb_idx[pad] = knn(xy, pad_donor, pad, K)[0][pad]
    nb_lpsf = masked_median(lpsf, nb_idx)
    nb_psf = np.exp(nb_lpsf)
    nb_area = np.exp(masked_median(la, nb_idx))
    raw = lpsf - nb_lpsf
    # City size elasticity: neighbour-demeaned ln psf on neighbour-demeaned ln area (donors).
    beta = trimmed_slope((la - masked_median(la, nb_idx))[donor], raw[donor])
    adj = lpsf - beta * la
    # Same-use peers (residential vs non-residential; vacant land joins its use's family) within
    # PEER_RADIUS_M, else plain neighbours.
    peer_idx = nb_idx.copy()
    peer_ok = np.ones_like(nb_idx, dtype=bool)
    used_peer = np.zeros(n, bool)
    for f in ("res", "nonres", "pad"):
        t = fam_peer == f
        pi, pd_ = knn(xy, (pad_donor if f == "pad" else donor) & t, t, K)
        close = (pi >= 0) & (pd_ <= PEER_RADIUS_M)
        enough = close.sum(axis=1) >= PEER_MIN
        sel = t & enough
        peer_idx[sel], peer_ok[sel], used_peer[sel] = pi[sel], close[sel], True
    peer = lpsf - masked_median(lpsf, peer_idx, peer_ok)
    size = lpsf - (masked_median(adj, peer_idx, peer_ok) + beta * la)
    # Big lots: the same-family neighbours' size-adjusted rate over lots of SIMILAR size only.
    sim = np.full(n, np.nan)
    big = np.isfinite(lpsf) & (area >= BIG_LOT_SQFT)
    big_donor = donor & (area >= BIG_LOT_SQFT / SIM_BAND)
    for f in ("res", "nonres", None):
        in_f = (fam_peer == f) if f else ~np.isin(fam_peer, ["res", "nonres", "pad"])
        base = similar_size_median(xy, la, adj, big_donor & ((fam_peer == f) if f else everyone), big & in_f)
        sel = big & in_f & np.isfinite(base)
        sim[sel] = lpsf[sel] - (base[sel] + beta * la[sel])
    # Each baseline is z-scored against its OWN spread, per lot-size band; the least extreme z wins,
    # and only if every available baseline agrees in sign.
    zs, sigmas, sig_bands = [], [], []
    for v in (raw, peer, size, sim):
        zv, sg, sb = banded_z(v, donor, band)
        zs.append(zv)
        sigmas.append(sg)
        sig_bands.append(sb)
    zst = np.vstack(zs)
    avail = np.isfinite(zst)
    with np.errstate(invalid="ignore"):
        same_sign = (np.all(np.where(avail, zst > 0, True), axis=0)
                     | np.all(np.where(avail, zst < 0, True), axis=0))
    pick_ix = np.argmin(np.where(avail, np.abs(zst), np.inf), axis=0)
    z_min = np.take_along_axis(zst, pick_ix[None, :], axis=0)[0]
    valid = np.isfinite(lpsf) & np.isfinite(nb_lpsf) & np.isfinite(zst[:3]).all(axis=0)
    z = np.where(valid, np.where(same_sign, np.clip(z_min, -Z_CAP, Z_CAP), 0.0), np.nan)
    # The dollar gap uses the least extreme log-ratio (the smallest gap any baseline implies).
    lrs = np.vstack([raw, peer, size, sim])
    lr_small = np.take_along_axis(lrs, np.argmin(np.where(avail & np.isfinite(lrs), np.abs(lrs), np.inf),
                                                 axis=0)[None, :], axis=0)[0]
    lr = np.where(valid & same_sign, lr_small, 0.0)
    ratio = psf / nb_psf
    adj_ratio = np.exp(lr)
    x_flag = [math.exp(Z_FLAG * s) for s in sigmas[:3]]

    print(f"  size elasticity b = {beta:.3f}; sigma of ln-ratio: plain {sigmas[0]:.3f}, same-use "
          f"{sigmas[1]:.3f}, size-adjusted {sigmas[2]:.3f}, similar-size {sigmas[3]:.3f} "
          f"(|z|>={Z_FLAG:g} = {x_flag[0]:.1f}x / {x_flag[1]:.1f}x / {x_flag[2]:.1f}x); same-use peers for "
          f"{used_peer.mean():.0%} of parcels, similar-size for {np.isfinite(sim).sum():,} big lots")
    print(f"  size-adjusted sigma by lot size (<1/4, <1, <5, 5+ acres): {sig_bands[2]}")

    # ── signals ──────────────────────────────────────────────────────────────
    sev = {k: np.zeros(n) for k in SIGNALS}
    stake = {k: np.zeros(n) for k in SIGNALS}
    reason: dict[str, dict[int, str]] = {k: {} for k in SIGNALS}
    weight = {k: np.full(n, spec["weight"]) for k, spec in SIGNALS.items()}
    # Unbuildable, steep, landlocked or present-use-valued VACANT land is legitimately cheap far
    # more often than built land, so far-below weighs less there.
    weight["land_psf_low"][is_vac] = W_LOW_VACANT
    z_sev = np.clip((np.abs(np.nan_to_num(z)) - Z_FLAG) / (Z_CAP - Z_FLAG), 0, 1)

    def adj_note(i: int) -> str:
        a, r = adj_ratio[i], ratio[i]
        if not np.isfinite(a) or abs(math.log(max(a, 1e-9))) > 0.8 * abs(math.log(max(r, 1e-9))):
            return ""
        a_txt = Fmt.times(a) if a >= 1 else f"1/{Fmt.times(1 / a)[:-1]}"
        return f"; still ~{a_txt} after allowing for lot size and use"

    low_cand = np.flatnonzero((z_sev > 0) & (np.nan_to_num(z) < 0) & ~imputed & ~no_low & ~no_psf & ~pad)
    enclosed = enclosed_share(gm, [int(i) for i in low_cand])
    for i in np.flatnonzero(z_sev > 0):
        if imputed[i]:
            key = "estimate_off"
        else:
            key = "land_psf_high" if z[i] > 0 else "land_psf_low"
            if no_psf[i] or pad[i] or (key == "land_psf_low" and no_low[i]):
                # nominal by design, a method artefact, or a footprint pad whose land is a per-unit
                # share: its $/sqft is not a land rate
                continue
        sev[key][i] = z_sev[i]
        exp_land = land[i] / adj_ratio[i]
        stake[key][i] = abs(land[i] - exp_land)
        r = ratio[i]
        rtxt = f"{Fmt.times(r)} its" if r >= 1 else f"only 1/{Fmt.times(1 / r)[:-1]} of its"
        what = "Estimated land" if imputed[i] else "Land"
        txt = f"{what} {fmt.rate(psf[i])} is {rtxt} neighbours' median ({fmt.rate(nb_psf[i])}){adj_note(i)}"
        if key == "land_psf_low":
            # Never more than the parcel itself is worth: a $400 remnant can't put $50k at stake.
            stake[key][i] = min(stake[key][i], total[i])
            if has_prior[i] and np.isfinite(p_land[i]) and p_land[i] >= 2 * land[i] and p_land[i] > 0:
                txt += f"; the land was {fmt.money(p_land[i])} in the {prior_label}"
                if storm[i]:
                    txt += f" (written down after {storm_label})"
                    weight[key][i] *= STORM_LOW_WEIGHT
            if enclosed.get(i, 0.0) >= ENCLOSED_SHARE:
                # Other parcels surround it: backland or landlocked land is legitimately cheap.
                weight[key][i] *= ENCLOSED_WEIGHT
                txt += "; other parcels surround it (no street frontage), which often explains cheap land"
        reason[key][i] = txt

    be_state = np.full(n, None, dtype=object)
    token_opp = np.zeros(n, bool)
    storm_opp = np.zeros(n, bool)
    stale_vacant = np.zeros(n, bool)   # mapped Vacant, but the class still names a building
    est_bldg = np.full(n, np.nan)
    if not combined_only and c_impr:
        # zero / nominal land under a valued building
        zero = (land <= 0) & (impr > 0) & ~remnant
        nominal = (land > 0) & (impr >= NOMINAL_MIN_IMPR) & (land < NOMINAL_LAND_SHARE * total) & ~imputed
        for i in np.flatnonzero(zero | nominal):
            # The record's whole land/building split is suspect, so its total value is at stake.
            # A nominal pad whose land $/sqft is in line is usually a PUD / office-park pad whose
            # land sits in a shared (unshipped) parcel: half the severity.
            sev["zero_land"][i] = 1.0 if zero[i] else (0.6 if abs(np.nan_to_num(z[i])) >= Z_FLAG else 0.3)
            stake["zero_land"][i] = total[i]
            nb = f" (land nearby runs ~{fmt.rate(nb_psf[i])})" if np.isfinite(nb_psf[i]) else ""
            if zero[i]:
                reason["zero_land"][i] = (f"Land is {fmt.money(0)} under {fmt.money(impr[i])} of improvements: "
                                          f"the land value looks missing{nb}")
            else:
                reason["zero_land"][i] = (f"Land is just {fmt.money(land[i])} ({land[i] / total[i]:.1%} of value) "
                                          f"under {fmt.money(impr[i])} of improvements{nb}")

        catl = np.array([(c or "").lower() for c in cat], dtype=object)
        refl = np.array([(r or "") for r in refined], dtype=object)
        share = np.nan_to_num(impr_share)
        # vacant label with a building
        vac_lbl = np.array(["vacant" in c for c in catl]) | (refl == "Vacant")
        vb = vac_lbl & (impr >= VACANT_MIN_IMPR) & (share >= 0.2)
        for i in np.flatnonzero(vb):
            sev["label_vacant_built"][i] = 0.5 + 0.5 * np.clip((share[i] - 0.2) / 0.6, 0, 1)
            stake["label_vacant_built"][i] = impr[i]
            what = f"Assessor class is {cat[i]}" if "vacant" in catl[i] else "Mapped as Vacant"
            ud = f" ({use_desc[i]})" if use_desc[i] and use_desc[i] != cat[i] else ""
            reason["label_vacant_built"][i] = (f"{what}{ud} but it carries {fmt.money(impr[i])} of improvements "
                                               f"({share[i]:.0%} of value)")
        # parking label with a big building (garages / decks are buildings: excluded)
        structure = np.array([bool(re.search(r"garage|deck|structure|ramp", c)) for c in catl])
        pk_lbl = (np.array(["parking" in c for c in catl]) & ~structure) | (refl == "Parking Lot")
        pb = pk_lbl & (impr >= PARKING_MIN_IMPR) & (share >= 0.5)
        for i in np.flatnonzero(pb):
            sev["label_parking_built"][i] = 0.5 + 0.5 * np.clip((share[i] - 0.2) / 0.6, 0, 1)
            stake["label_parking_built"][i] = impr[i]
            reason["label_parking_built"][i] = (f"Labelled a parking lot but improvements are {fmt.money(impr[i])} "
                                                f"({share[i]:.0%} of value): more like a building or a deck")

        # ── building class with ~no building value ──────────────────────────
        not_built = np.array([bool(re.search(r"vacant|parking|common|park|open space|minor|agric|rural|"
                                             r"utility|other|transport|right.of.way|water", c)) or not c
                              for c in catl])
        be = (~not_built & (share <= BUILT_EMPTY_MAX_SHARE) & (land >= BUILT_EMPTY_MIN_LAND) & ~remnant
              & ~code_in(code, rules.get("built_empty_skip_codes"))
              & ~desc_match(note, rules.get("building_elsewhere_note")))
        # The class's typical building: median improvements / land over its normally built parcels.
        grp = np.array([c or k or "" for c, k in zip(code, cat)], dtype=object)
        with np.errstate(divide="ignore", invalid="ignore"):
            il = np.where(land > 0, impr / land, np.nan)
        built_ok = (share >= 0.05) & np.isfinite(il) & ~imputed
        ratio_by = pd.Series(il[built_ok]).groupby(grp[built_ok]).agg(["median", "count"])
        ratio_by = ratio_by[ratio_by["count"] >= 10]["median"].clip(0.25, 10).to_dict()
        city_ratio = float(np.clip(np.nanmedian(il[built_ok]), 0.25, 10)) if built_ok.any() else 1.0
        cat_of_code = {}
        for c, k in zip(code, cat):
            if c and k and c not in cat_of_code:
                cat_of_code[c] = k

        def token(b: float, t: float) -> bool:
            return b <= max(TOKEN_MAX, BUILT_EMPTY_MAX_SHARE * t)

        for i in np.flatnonzero(be):
            ud = use_desc[i] or cat[i]
            pb_, pl_, pt_ = p_impr[i], p_land[i], p_total[i]
            if prior is None or n_acc[i] > 1:
                st = "unknown"      # no previous roll, or a merged condo group (not comparable)
            elif not has_prior[i]:
                st = "new_parcel"   # a split or recombination since the previous roll
            else:
                was_vacant = (str(p_improved[i] or "").upper() == "N"
                              or "vacant" in (cat_of_code.get(p_cls[i]) or "").lower())
                pb0 = np.nan_to_num(pb_)
                if was_vacant and token(pb0, np.nan_to_num(pt_)):
                    st = "was_unbuilt"
                elif not (np.nan_to_num(pt_) > 0):
                    st = "unknown"      # an unvalued prior record says nothing
                elif token(pb0, pt_):
                    st = "was_nominal"
                elif storm[i]:
                    st = "storm"
                elif land[i] >= LAND_MOVED_MIN * np.nan_to_num(pl_) and total[i] >= TOTAL_KEPT_MIN * pt_:
                    st = "moved_to_land"
                else:
                    st = "vanished"
            be_state[i] = st
            has = (f"improvements are only {fmt.money(impr[i])}" if impr[i] > 0 else
                   "it carries no improvement value")
            mapped = f", so it maps as {refined[i]}" if refined[i] else ""

            def flag(key: str, s: float, stk: float, txt: str) -> None:
                sev[key][i], stake[key][i], reason[key][i] = s, stk, txt

            if refined[i] == "Vacant":
                # The map already shows no building here; only the class label is out of date.
                stale_vacant[i] = True
                if st == "storm":
                    storm_opp[i] = True
                flag("label_built_empty", 0.2, land[i],
                     f"Class is {ud} but no building is on record, so the map already shows it as Vacant: "
                     f"the class looks out of date")
                continue
            if st == "storm":
                storm_opp[i] = True     # a storm write-down: real, and not a data error
                continue
            if st in ("was_nominal", "moved_to_land"):
                token_opp[i] = True     # the assessor's deliberate "worth its land" value
                if house[i] and st == "was_nominal":
                    flag("label_built_empty", 0.2, land[i],
                         f"Class is {ud} but the building has been valued at {fmt.money(impr[i])} since at "
                         f"least the {prior_label}: a lapsed permit, a stale class, or a missing house")
                continue
            if house[i] and st in ("was_unbuilt", "new_parcel"):
                continue                # a house under construction: valued once finished
            if st == "was_unbuilt":
                pc = cat_of_code.get(p_cls[i]) or p_cls[i] or "vacant"
                flag("label_built_empty", 0.25, land[i],
                     f"Reclassed from {pc} to {ud} since the {prior_label} but {has}: new construction not "
                     f"yet valued, or a class set ahead of a building")
            elif st == "new_parcel":
                r_ = ratio_by.get(grp[i], city_ratio)
                est_bldg[i] = land[i] * r_
                flag("label_built_empty", 0.8, est_bldg[i],
                     f"A new parcel since the {prior_label} (a split or recombination) with a {ud} class but "
                     f"{has}: {ud} parcels here carry ~{r_:.1f}× their land in buildings "
                     f"(~{fmt.money(float(f'{est_bldg[i]:.2g}'))} here)")
            elif st == "vanished":
                what = "house" if house[i] else "building"
                tail = (": demolished, or a missing value" if house[i] else
                        ", and the land did not absorb it")
                no_rec = ", with no storm-damage record" if dmg is not None else ""
                flag("building_dropped", 0.3 if house[i] else 0.8, pb_,
                     f"The {what} was valued at {fmt.money(pb_)} in the {prior_label} and is "
                     f"{fmt.money(impr[i])} now{no_rec}{tail}")
            else:  # unknown: no previous roll to tell a token value from a lost one
                if not house[i]:
                    token_opp[i] = True
                flag("label_built_empty", 0.2 if house[i] else 0.25, land[i],
                     f"Class is {ud} but {has} on {fmt.money(land[i])} of land{mapped}")

    # A storm write-down that moved part of the building's value onto the land makes the land look
    # dear next to its neighbours: real, explained, and listed under Opportunities.
    for i in np.flatnonzero(storm_opp & (sev["land_psf_high"] > 0)):
        weight["land_psf_high"][i] *= STORM_LOW_WEIGHT
        if np.isfinite(p_land[i]) and land[i] > p_land[i]:
            reason["land_psf_high"][i] += (f"; the county raised the land from {fmt.money(p_land[i])} when it wrote "
                                           f"the building off after {storm_label}")

    # small lot carrying a big land value
    with np.errstate(divide="ignore", invalid="ignore"):
        lots_bought = np.where(nb_psf > 0, land / nb_psf / area, np.nan)
    sl = ((area < SLIVER_MAX_SQFT) & (area <= SLIVER_MAX_REL * nb_area) & (land >= SLIVER_MIN_LAND)
          & (np.nan_to_num(lots_bought) >= SLIVER_MIN_X) & ~pad)
    for i in np.flatnonzero(sl):
        sev["sliver"][i] = float(np.clip((math.log10(lots_bought[i]) - 0.7) / 1.3, 0, 1))
        stake["sliver"][i] = land[i]
        reason["sliver"][i] = (f"A {fmt.area(area[i])} lot carries {fmt.money(land[i])} of land: what "
                               f"~{fmt.area(land[i] / nb_psf[i])} would be worth at its neighbours' "
                               f"{fmt.rate(nb_psf[i])}")

    # estimated land that is only a conservative floor
    for i in range(n):
        if note[i] and "conservative floor" in note[i].lower():
            sev["estimate_floor"][i] = 0.6
            stake["estimate_floor"][i] = land[i]
            reason["estimate_floor"][i] = (f"Land ({fmt.money(land[i])}, {land[i] / total[i]:.0%} of value) is a "
                                           f"conservative floor estimate: few similar-sized parcels nearby")

    # ── score ────────────────────────────────────────────────────────────────
    def V(x):
        return np.minimum(1.0, np.log10(1 + np.maximum(np.nan_to_num(x), 0) / STAKE_REF)
                          / math.log10(1 + STAKE_NORM / STAKE_REF))

    keep = ~remnant if hide_remnants else np.ones(n, bool)
    prod = np.ones(n)
    for k in SIGNALS:
        prod *= 1 - weight[k] * sev[k] * V(stake[k])
    score = 100 * (1 - prod)
    flagged = (score > 0) & keep
    counts = {k: int(((sev[k] > 0) & keep).sum()) for k in SIGNALS}
    order = np.argsort(-np.where(flagged, score, -1), kind="stable")
    issue_ix = [int(i) for i in order[: min(args.top, int(flagged.sum()))]]
    issue_rank = {i: r + 1 for r, i in enumerate(issue_ix)}

    # Opportunities: the top N mapped Vacant / Underdeveloped / Parking Lot by land value, plus every
    # token-building and storm write-down parcel (which may map unclassified), by land value.
    refl_all = np.array([(r or "") for r in refined], dtype=object)
    opp_base = np.isin(refl_all, OPPORTUNITY_LABELS) & keep
    extra = (token_opp | storm_opp | stale_vacant) & keep
    opp = opp_base | extra
    base_order = np.argsort(-np.where(opp_base, land, -1), kind="stable")
    top_base = set(int(i) for i in base_order[: min(args.top, int(opp_base.sum()))])
    opp_set = top_base | set(int(i) for i in np.flatnonzero(extra))
    opp_ix = sorted(opp_set, key=lambda i: (-land[i], i))

    # ── items ────────────────────────────────────────────────────────────────
    # When (nearly) every record link is <prefix><parcel_id>, ship the template once instead.
    link_tpl = None
    with_link = [i for i in range(n) if link[i]]
    if with_link:
        first = with_link[0]
        if link[first].endswith(pid[first]):
            prefix_url = link[first][: -len(pid[first])]
            share_ok = np.mean([link[i] == prefix_url + pid[i] for i in with_link])
            if share_ok >= 0.95 and len(with_link) == n:
                link_tpl = prefix_url + "{parcel_id}"

    def r2(v, nd=2):
        return None if v is None or not np.isfinite(v) else round(float(v), nd)

    def sig3(v):
        if v is None or not np.isfinite(v) or v == 0:
            return None if v is None or not np.isfinite(v) else 0
        return float(f"{v:.3g}")

    def item(i: int, rank: int, reasons: list[tuple[str, str]], with_score: bool) -> dict:
        cx, cy = xy[i]
        d = {"rank": rank}
        if with_score:
            d["score"] = round(float(score[i]), 1)
        d.update({
            "parcel_id": pid[i],
            "category": cat[i],
            "refined": refined[i],
            "use_desc": use_desc[i],
            "use_code": code[i],
            "land": int(round(land[i])),
            "impr": int(round(impr[i])),
            "total": int(round(total[i])),
            "land_psf": sig3(psf[i]),
            "nbr_psf": sig3(nb_psf[i]),
            "psf_ratio": sig3(ratio[i]),
            "z": r2(z[i], 1),
            "lot_sqft": int(round(area[i])) if np.isfinite(area[i]) else None,
            "lot_acres": r2(area[i] / SQFT_PER_ACRE, 3),
            "impr_share": r2(impr_share[i], 3),
            "signals": [k for k, _ in reasons],
            "reasons": [t for _, t in reasons],
            "note": note[i],
            "link": None if link_tpl and link[i] == link_tpl.replace("{parcel_id}", pid[i]) else link[i],
            "center": [round(float(lng[i]), 5), round(float(lat[i]), 5)],
            "outline": outline_rings(gm.iloc[i], cx, cy),
        })
        if imputed[i]:
            d["estimated_land"] = True
        if has_prior[i] and np.isfinite(p_total[i]) and p_total[i] > 0:
            d["prior_land"] = int(round(np.nan_to_num(p_land[i])))
            d["prior_impr"] = int(round(np.nan_to_num(p_impr[i])))
        if storm[i]:
            d["damage_event"] = storm_label
        return {k: v for k, v in d.items() if v is not None}

    def issue_reasons(i: int) -> list[tuple[str, str]]:
        ks = sorted((k for k in SIGNALS if sev[k][i] > 0),
                    key=lambda k: -weight[k][i] * sev[k][i] * float(V(stake[k][i])))
        return [(k, reason[k][i]) for k in ks]

    issues = [item(i, r + 1, issue_reasons(i), True) for r, i in enumerate(issue_ix)]

    def opp_reason(i: int) -> tuple[str, str, str]:
        """(reason key, text, opportunity_type). Token / storm reasons use the 'underdeveloped' chip."""
        lab = refl_all[i]
        if storm_opp[i]:
            return ("underdeveloped",
                    f"Building written off after {storm_label}: {fmt.money(p_impr[i])} in the {prior_label}, "
                    f"{fmt.money(impr[i])} now, so the land ({fmt.money(land[i])}) carries the value",
                    "storm_writedown")
        if token_opp[i]:
            what = "house" if house[i] else "building"
            st = be_state[i]
            if st == "moved_to_land":
                txt = (f"The county values the {what} at {fmt.money(impr[i])} and the land at {fmt.money(land[i])}: "
                       f"since the {prior_label} it cut the {what} from {fmt.money(p_impr[i])} and raised the land "
                       f"from {fmt.money(p_land[i])}")
            elif st == "was_nominal":
                txt = (f"The county values the {what} at {fmt.money(impr[i])} and puts the value on the land "
                       f"({fmt.money(land[i])}), as it did in the {prior_label}")
            else:
                txt = (f"The county values the {what} at {fmt.money(impr[i])} and puts the value on the land "
                       f"({fmt.money(land[i])})")
            return ("underdeveloped", txt, "token_building")
        if lab == "Vacant":
            return ("vacant", f"Vacant: {fmt.money(land[i])} of land"
                    + (f" with {fmt.money(impr[i])} of improvements" if impr[i] > 0 else " and no improvements")
                    + (f" (the class still says {use_desc[i] or cat[i]})" if stale_vacant[i] else ""),
                    "vacant")
        if lab == "Parking Lot":
            return ("parking", f"Surface parking on {fmt.area(area[i])} of {fmt.rate(psf[i])} land", "parking")
        share_txt = "under 1%" if impr_share[i] < 0.005 else f"only {impr_share[i]:.0%}"
        return ("underdeveloped", f"Improvements are {share_txt} of its value "
                                  f"({fmt.money(impr[i])} on {fmt.money(land[i])} of land)", "underdeveloped")

    opps = []
    for r, i in enumerate(opp_ix):
        key, txt, otype = opp_reason(i)
        rs: list[tuple[str, str]] = [(key, txt)]
        if flagged[i]:
            rk = issue_rank.get(i)
            where = f" (#{rk} on that list)" if rk else ""
            rs.append(("check_data", f"Also a likely data issue{where}: "
                                     + (issue_reasons(i)[0][1] if issue_reasons(i) else "")))
        d = item(i, r + 1, rs, False)
        d["opportunity_type"] = otype
        if flagged[i]:
            d["issue_score"] = round(float(score[i]), 1)
            d["issue_signals"] = [k for k, _ in issue_reasons(i)]
        opps.append(d)

    med_land = float(np.median(land[opp])) if opp.any() else 0.0
    state_counts = pd.Series([s for s in be_state[keep] if s]).value_counts().to_dict()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    doc = {
        "city": city or prefix,
        "city_label": (f"{cfg['displayName']}, {cfg.get('displayRegion') or str(cfg.get('state', '')).upper()}"
                       if cfg.get("displayName") else prefix),
        "generated": now.isoformat().replace("+00:00", "Z"),
        "source": path.name,
        "n_parcels": n,
        "units": {"currency": fmt.cur, "area": "m2" if fmt.metric else "sqft",
                  "note": "All numbers are per sqft / sqft; convert for metric display."},
        "remnants": {"hidden": bool(hide_remnants), "count": int(remnant.sum()),
                     "note": ("likely_remnant slivers (<500 sqft) are hidden on the map for this city and "
                              "left out of both lists." if hide_remnants else
                              "likely_remnant slivers are included.")},
        "method": {
            "issues": ("Each parcel gets plain-English signals, each with a severity (0-1) and the dollars at "
                       "stake. score = 100 x (1 - prod(1 - w x severity x V(stake))), where V(stake) = "
                       "log10(1 + stake/$10k) / log10(1 + $100M/$10k), capped at 1: extreme AND valuable "
                       "parcels rank first."),
            "land_psf": (f"Land $/sqft is compared with the median of the {K} nearest parcels (excluding "
                         "remnant slivers, estimated land, townhome/condo footprint pads and nominally valued "
                         f"classes), with same-use neighbours within {PEER_RADIUS_M / 1000:g} km (vacant land "
                         "joins its use), with those neighbours' rate adjusted for lot size (elasticity "
                         f"{beta:.2f}), and for lots over an acre with similar-sized lots within "
                         f"{SIM_RADIUS_M / 1000:g} km. Each log-ratio is z-scored with median/MAD within its "
                         "lot-size band; the least extreme counts. Flags start at "
                         f"|z| = {Z_FLAG:g} and saturate at {Z_CAP:g}."),
            "built_empty": (f"Buildings valued at a token amount (<= max($1k, 1% of value)) are compared with the "
                            f"{prior_label}: the same token value, or value moved to the land, is the assessor's "
                            "'worth its land' call (listed under Opportunities); a building written off after a "
                            "tagged storm is listed there too; a building that vanished otherwise, or a new "
                            "parcel that lost its building, is a likely issue; houses under construction are "
                            "not flagged." if prior is not None else
                            "No previous roll for this city: token buildings on non-house classes are listed "
                            "under Opportunities and keep a weak issue flag; houses keep a weak flag."),
            "opportunities": (f"Parcels mapped as Vacant, Underdeveloped or Parking Lot (the top {args.top} by land "
                              "value), plus every parcel whose building the county values at a token amount or "
                              "wrote off after a storm; largest land value first."),
            "k": K, "z_flag": Z_FLAG, "z_cap": Z_CAP, "size_elasticity": round(beta, 3),
            "ln_ratio_sigma": {"plain": round(sigmas[0], 4), "same_use": round(sigmas[1], 4),
                               "size_adjusted": round(sigmas[2], 4), "similar_size": round(sigmas[3], 4),
                               "size_bands_acres": list(SIZE_BANDS_ACRES),
                               "by_band": {"plain": sig_bands[0], "same_use": sig_bands[1],
                                           "size_adjusted": sig_bands[2], "similar_size": sig_bands[3]}},
            "stake_ref": STAKE_REF, "stake_norm": STAKE_NORM,
            "weights": {k: v["weight"] for k, v in SIGNALS.items()},
            "rules": rules_key or "default",
            "prior_values": ({"label": prior_label, "source": rules["prior_values"]["url"],
                              "matched": int(has_prior.sum())} if prior is not None else None),
            "damage_points": ({"label": storm_label, "source": dmg_spec.get("url"),
                               "parcels_tagged": int(storm.sum())} if dmg is not None else None),
            "built_empty_states": state_counts,
        },
        "signals": {k: {"label": v["label"], "description": v["description"], "count": counts[k]}
                    for k, v in SIGNALS.items()},
        "city_medians": {
            "land_psf": r2(float(np.nanmedian(psf[donor])), 3),
            "lot_sqft": int(np.nanmedian(area)),
            "land": int(np.median(land)),
            "total": int(np.median(total)),
            "impr_share": r2(float(np.nanmedian(impr_share)), 3),
        },
        "outline_units": "metres east/north of `center`, flat rings [x0, y0, x1, y1, ...]",
        "link_template": link_tpl,
        "issues": {"flagged": int(flagged.sum()), "items": issues},
        "opportunities": {"eligible": int(opp.sum()), "land_total": int(land[opp].sum()),
                          "land_median": int(med_land), "top_by_land": len(top_base),
                          "token_buildings": int((token_opp & keep).sum()),
                          "storm_writedowns": int((storm_opp & keep).sum()), "items": opps},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if args.csv:
        fl = np.flatnonzero(flagged | extra)
        audit = pd.DataFrame({
            "rank": [issue_rank.get(int(i)) for i in fl], "score": score[fl].round(2), "parcel_id": pid[fl],
            "use_code": code[fl], "category": cat[fl], "refined": refined[fl], "use_desc": use_desc[fl],
            "family": fam_peer[fl], "land": land[fl], "impr": impr[fl], "lot_sqft": area[fl].round(),
            "land_psf": psf[fl], "nbr_psf": nb_psf[fl], "z": z[fl], "z_plain": zst[0][fl],
            "z_same_use": zst[1][fl], "z_size": zst[2][fl], "z_similar_size": zst[3][fl],
            "built_empty_state": be_state[fl], "token_opp": token_opp[fl], "storm_opp": storm_opp[fl],
            "prior_land": p_land[fl], "prior_impr": p_impr[fl], "damage": storm[fl],
            **{f"sev_{k}": sev[k][fl].round(3) for k in SIGNALS},
            **{f"stake_{k}": stake[k][fl].round() for k in SIGNALS},
            "reasons": [" | ".join(t for _, t in issue_reasons(int(i))) for i in fl],
        }).sort_values("score", ascending=False)
        audit.to_csv(args.csv, index=False, encoding="utf-8")
        print(f"Audit CSV: {args.csv} ({len(audit):,} flagged or token/storm parcels)")

    # ── log ──────────────────────────────────────────────────────────────────
    if args.explain:
        at = {p: i for i, p in enumerate(pid)}
        for p in args.explain:
            i = at.get(p)
            if i is None:
                print(f"\n--explain {p}: not in the parquet")
                continue
            print(f"\n--explain {p}: {code[i]} {use_desc[i]} [{cat[i]} / {refined[i]}] family {fam_peer[i]}"
                  f"{' pad' if pad[i] else ''}{' no-low-psf' if no_low[i] else ''}{' house' if house[i] else ''}"
                  f"  land {land[i]:,.0f} impr {impr[i]:,.0f} lot {area[i]:,.0f} sqft")
            print(f"  ln-ratio raw {raw[i]:+.2f} peer {peer[i]:+.2f} size {size[i]:+.2f} sim {sim[i]:+.2f}; "
                  f"z {zst[0][i]:+.1f} / {zst[1][i]:+.1f} / {zst[2][i]:+.1f} / {zst[3][i]:+.1f} -> {z[i]:+.1f}")
            print(f"  prior: {'matched' if has_prior[i] else 'no match'} land {p_land[i]:,.0f} impr "
                  f"{p_impr[i]:,.0f} class {p_cls[i]} improved {p_improved[i]}; damage tag {storm[i]}; "
                  f"built-empty state {be_state[i]}; token_opp {token_opp[i]} storm_opp {storm_opp[i]}")
            print(f"  score {score[i]:.1f} rank {issue_rank.get(i)}; " + "; ".join(
                f"{k} sev {sev[k][i]:.2f} w {weight[k][i]:.2f} stake {stake[k][i]:,.0f}"
                for k in SIGNALS if sev[k][i] > 0))

    print(f"\nRemnants: {int(remnant.sum())} likely_remnant parcels "
          f"{'hidden (hideRemnants) and left out' if hide_remnants else 'kept'}")
    print("Signal counts (parcels flagged, before the top-N cut):")
    for k, c in counts.items():
        print(f"  {k:<22} {c:>6,}   {SIGNALS[k]['label']}")
    print(f"Building class with a token value, by what the {prior_label} says: {state_counts}")
    print(f"Flagged parcels: {int(flagged.sum()):,}; listed {len(issues)}")
    s = score[flagged]
    if len(s):
        qs = np.percentile(s, [50, 75, 90, 99])
        print(f"Score distribution: max {s.max():.1f}, p99 {qs[3]:.1f}, p90 {qs[2]:.1f}, p75 {qs[1]:.1f}, "
              f"p50 {qs[0]:.1f}")
        edges = [0, 5, 10, 20, 30, 40, 50, 60, 80, 101]
        hist = np.histogram(s, bins=edges)[0]
        print("  " + "  ".join(f"[{a}-{b}): {h}" for a, b, h in zip(edges, edges[1:], hist)))
        if issues:
            print(f"  cut-off score at #{len(issues)}: {issues[-1]['score']}")
    print("\nTop 20 issues:")
    for it in issues[:20]:
        print(f"  #{it['rank']:<3} {it['score']:>5.1f}  {it['parcel_id']}  {it.get('use_desc') or it.get('category')}"
              f"  land {fmt.money(it['land'])} impr {fmt.money(it['impr'])} lot {fmt.area(it.get('lot_sqft', 0))}")
        for t in it["reasons"]:
            print(f"         - {t}")
    print(f"\nOpportunities: {int(opp.sum()):,} eligible ({fmt.money(land[opp].sum())} land); listed {len(opps)} "
          f"(top {len(top_base)} mapped by land + {int((token_opp & keep).sum())} token-building / "
          f"{int((storm_opp & keep).sum())} storm parcels); top 5:")
    for it in opps[:5]:
        print(f"  #{it['rank']:<3} {it['parcel_id']}  {it.get('refined')}  {it.get('use_desc') or ''}  land "
              f"{fmt.money(it['land'])}  impr {fmt.money(it['impr'])}  {fmt.area(it.get('lot_sqft', 0))}")
    kb = out.stat().st_size / 1024
    print(f"\nWrote {out} ({kb:,.0f} KB; {len(issues)} issues, {len(opps)} opportunities)")


if __name__ == "__main__":
    main()
