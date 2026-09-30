#!/usr/bin/env python3
"""
Build the parcel review feed for one city: a small JSON the viz/review.html page lists as cards.

Two ranked lists (tabs), from any city's canonical parcel parquet (docs/parcel-parquet-format.md;
Asheville-only columns such as condo_land_imputed / record_note / likely_remnant are optional):

1. "Likely data issues": parcels most out of distribution, i.e. probable assessor or pipeline
   errors, or values that mislead on the map. Scored as below.
2. "Biggest opportunities": parcels the refined classifier calls Vacant / Underdeveloped /
   Parking Lot, ranked by land value (largest first).

Usage (from the repo root):
    python data/scripts/build_review_feed.py --city asheville
    python data/scripts/build_review_feed.py --file path/to/x-parcels.parquet --out viz/public/x-review.json
Default output: next to the parquet, as <prefix>-review.json (e.g. asheville-nc-review.json).
Upload it next to the parcel parquet and set reviewFilename / reviewVersion in viz/src/cities/<key>.json.

THE LAND $/SQFT BASELINE (signals land_psf_high / land_psf_low / estimate_off)
-----------------------------------------------------------------------------
Donors = parcels with land > 0 and a real lot area, excluding `likely_remnant` slivers and
parcels whose land is estimated (`condo_land_imputed` = 1: derived from neighbours already).
For each parcel i (representative points in a metric CRS; the parcel itself never counts):
  raw_i  = ln(psf_i) - median ln(psf) of the K=15 nearest donors               ("neighbours")
  peer_i = ln(psf_i) - median ln(psf) of the K nearest donors of the same broad use
           (residential / non-residential) within 1.5 km, when at least 8 exist; else raw_i.
           Commercial land is assessed at a different rate than the houses behind it, so a
           corridor lot is judged against corridor lots.
  size_i = ln(psf_i) - [median over those peers of (ln psf_j - b ln area_j) + b ln area_i]
           i.e. the peers' rate, adjusted for lot size with the city's own size elasticity b
           (trimmed OLS of the neighbour-demeaned ln psf on ln area; Asheville b ~ -0.6:
           land $/sqft falls steeply with lot size).
  z_b,i  = (b_i - median b) / (1.4826 * MAD b) for each baseline b in (raw, peer, size), with
           median/MAD over donors citywide. Each baseline gets its OWN spread: the size-adjusted
           one is ~3x tighter (Asheville sigma 0.10 vs 0.31: land schedules are mostly a lot-size
           curve), so pooling them would flag 1.3x gaps.
  z_i    = the least extreme of the three z's, or 0 if they disagree in sign; capped at +/-12.
           A parcel is out of line only if it is out of line against ALL of: its plain
           neighbours, its same-use neighbours, and its neighbours' rate at its lot size.
  lr_i   = the least extreme of the three log-ratios (the smallest gap any baseline implies).
Reason text quotes the plain neighbours' median, which is always at least as extreme; when a
fairer baseline shrinks the gap a lot, it adds "still ~Nx after allowing for lot size and use".

SIGNALS (each gives a severity sev in [0,1] and a dollar stake: the value that is at issue)
------------------------------------------------------------------------------------------
land_psf_high     z >= Z_FLAG (4, ~3.5x the plain neighbours).  sev = (|z| - 4) / (12 - 4),
                  clipped to [0,1].  stake = land - land / e^lr.
land_psf_low      z <= -4.  Same sev.  stake = land / e^lr - land (the land it "should" carry).
zero_land         land <= 0 under improvements > 0 (sev 1), or land < 1% of total under
                  improvements >= $25k (sev 0.6).  stake = total value (the whole land/building
                  split of the record is suspect).
sliver            lot < 5,000 sqft AND <= 1/4 of the neighbours' median lot, land >= $25k, and the
                  land would buy >= 10 such lots at the neighbours' $/sqft (Hartford's 0 OLIVE ST:
                  305 sqft carrying $360,400).  sev = (log10(x) - 0.7) / 1.3.  stake = land.
label_vacant_built   vacant category / refined Vacant, improvements >= $25k and >= 20% of total.
label_parking_built  surface-parking category / refined Parking Lot (not a garage / deck),
                  improvements >= $250k and >= 50% of total.
                  Both: sev = 0.5 + 0.5 * (share - 0.2) / 0.6, clipped.  stake = improvements.
label_built_empty a building use class (not vacant / parking / common area / open space / other)
                  whose improvements are <= 1% of total, with land >= $50k (a $4M "BANK W/ OFFICE"
                  with $100 of improvements maps as Underdeveloped).  sev = 0.5 (demolition or a
                  building on another account can explain it).  stake = land.
estimate_off      estimated land (condo_land_imputed = 1) with |z| >= 4.  sev as land_psf_*.
estimate_floor    record_note says the estimate is a conservative floor.  sev 0.6, stake = land.

SCORE
-----
  V(stake) = min(1, log10(1 + stake / $10k) / log10(1 + $100M / $10k))    (value at stake, 0..1)
  p_s      = w_s * sev_s * V(stake_s)
             w: land_psf_high 1.0; land_psf_low 0.7 (0.5 on vacant-category parcels); zero_land
                1.0; sliver 1.0; label_vacant_built / label_parking_built 0.8; label_built_empty
                0.6; estimate_off 0.8; estimate_floor 0.6
  score    = 100 * (1 - prod_s (1 - p_s))  (noisy-OR: more signals raise it, never past 100)
So importance is extremeness x log(value at stake): a $300k sliver scores ~8x a $5k oddity, and
far-below flags weigh less than far-above ones (steep, landlocked, easement-bound or
present-use-valued land is legitimately cheap more often than land is legitimately dear;
vacant land most of all).

`likely_remnant` parcels are left out of both lists when the city's config has hideRemnants
(they are hidden on the map too); the output metadata records how many. --csv writes every
flagged parcel with its per-signal severity / stake / z-scores, for auditing the scoring.

JSON: top-level metadata (city, generated, method, per-signal counts, city medians,
link_template) plus issues.items / opportunities.items. Per item: rank, score (issues),
parcel_id, category, refined, use_desc, land / impr / total, land_psf, nbr_psf, psf_ratio, z,
lot_sqft, lot_acres, impr_share, signals + reasons (aligned lists), note (record_note), link
(omitted when link_template covers it), center [lng, lat] (a point inside the parcel), and
outline (<= ~40 vertices, metres east/north of center, flat rings [x0, y0, x1, y1, ...]).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from data.parquet_registry import CITY_PARQUETS, resolve_city  # noqa: E402

SQFT_PER_ACRE = 43560.0
SQFT_PER_M2 = 10.763910417

# ── tuning ────────────────────────────────────────────────────────────────────
K = 15                     # nearest donors for the neighbour median
PEER_RADIUS_M = 1500.0     # same-use peers must be this close ...
PEER_MIN = 8               # ... and at least this many, else fall back to plain neighbours
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
W_LOW_VACANT = 0.5         # land_psf_low weight on vacant-category parcels (0.7 elsewhere)

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
    "label_built_empty": {"weight": 0.6, "label": "Building class, no building value",
                          "description": "A building use class whose improvements are ~$0, so it maps as "
                                         "vacant / underused land."},
    "estimate_off": {"weight": 0.8, "label": "Estimated land off-pattern",
                     "description": "Land is our estimate (the assessor gave $0) and sits far from its "
                                    "neighbours' rate."},
    "estimate_floor": {"weight": 0.6, "label": "Land estimate is a floor",
                       "description": "Land is a conservative floor estimate: few similar parcels nearby."},
}

OPPORTUNITY_LABELS = ("Vacant", "Underdeveloped", "Parking Lot")


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


def masked_median(values: np.ndarray, idx: np.ndarray, ok: np.ndarray | None = None) -> np.ndarray:
    v = np.where(idx >= 0, values[np.clip(idx, 0, None)], np.nan)
    if ok is not None:
        v = np.where(ok, v, np.nan)
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            return np.nanmedian(v, axis=1)


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


def robust_z(v: np.ndarray, ref: np.ndarray) -> tuple[np.ndarray, float, float]:
    r = v[ref & np.isfinite(v)]
    med = float(np.median(r))
    sigma = float(1.4826 * np.median(np.abs(r - med))) or 1e-9
    return (v - med) / sigma, med, sigma


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
    ap.add_argument("--city", help="City key (e.g. asheville); resolves the parquet and reads the "
                                   "city's viz config (hideRemnants, currency, units).")
    ap.add_argument("--file", help="Override the local parquet path.")
    ap.add_argument("--out", help="Output JSON path (default: next to the parquet, <prefix>-review.json).")
    ap.add_argument("--top", type=int, default=300, help="Items per tab (default 300).")
    ap.add_argument("--hide-remnants", action=argparse.BooleanOptionalAction, default=None,
                    help="Leave likely_remnant parcels out (default: the city's hideRemnants).")
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

    print(f"Loading {path}")
    gdf = gpd.read_parquet(path)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].reset_index(drop=True)
    n = len(gdf)
    print(f"  {n:,} parcels")

    # Columns (canonical names first, then the aliases other cities ship).
    c_id = pick(gdf, "parcel_id", "PARCELID", "parcelid", "pin", "PIN", "parcelpin", "parcel_number",
                "PROPID", "gpin", "account_number", "OBJECTID")
    c_land = pick(gdf, "current_full_land_value", "land_value", "REALLANDVA")
    c_impr = pick(gdf, "improvement_value", "REALIMPROV")
    c_total = pick(gdf, "full_market_value", "TLLDIMPROV", "total_value")
    c_cat = pick(gdf, "property_land_use_category", "PROPERTY_CATEGORY", "property_category")
    c_ref = pick(gdf, "property_land_use_refined", "property_category_refined")
    c_use = pick(gdf, "use_desc", "use_description", "use_code_desc", "land_use_desc")
    c_link = pick(gdf, "link", "parcel_link")
    if c_land is None:
        raise SystemExit("No land value column (current_full_land_value / land_value / REALLANDVA)")
    print(f"  columns: id={c_id} land={c_land} impr={c_impr} total={c_total} category={c_cat} "
          f"refined={c_ref} use={c_use} link={c_link}")

    pid = text(gdf, c_id) if c_id else np.array([f"row-{i}" for i in range(n)], dtype=object)
    pid = np.array([p if p is not None else f"row-{i}" for i, p in enumerate(pid)], dtype=object)
    land = np.nan_to_num(num(gdf, c_land), nan=0.0)
    impr = np.nan_to_num(num(gdf, c_impr), nan=0.0) if c_impr else np.zeros(n)
    total = num(gdf, c_total) if c_total else land + impr
    total = np.where(np.isfinite(total) & (total > 0), total, land + impr)
    cat = text(gdf, c_cat)
    refined = text(gdf, c_ref)
    use_desc = text(gdf, c_use)
    link = text(gdf, c_link)
    note = text(gdf, "record_note" if "record_note" in gdf.columns else None)
    imputed = np.nan_to_num(num(gdf, pick(gdf, "condo_land_imputed"), 0), nan=0) == 1
    remnant = np.nan_to_num(num(gdf, pick(gdf, "likely_remnant"), 0), nan=0) == 1

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

    with np.errstate(divide="ignore", invalid="ignore"):
        psf = np.where(area > 0, land / area, np.nan)
        lpsf = np.where(psf > 0, np.log(psf), np.nan)
        la = np.where(area > 0, np.log(area), np.nan)
        impr_share = np.where(total > 0, impr / total, np.nan)
    fam = use_family(cat)
    donor = np.isfinite(lpsf) & np.isfinite(la) & ~remnant & ~imputed
    everyone = np.ones(n, bool)

    # Plain neighbours.
    nb_idx, _ = knn(xy, donor, everyone, K)
    nb_lpsf = masked_median(lpsf, nb_idx)
    nb_psf = np.exp(nb_lpsf)
    nb_area = np.exp(masked_median(la, nb_idx))
    raw = lpsf - nb_lpsf
    # City size elasticity: neighbour-demeaned ln psf on neighbour-demeaned ln area (donors).
    beta = trimmed_slope((la - masked_median(la, nb_idx))[donor], raw[donor])
    # Same-use peers (residential vs non-residential) within PEER_RADIUS_M, else plain neighbours.
    peer_idx = nb_idx.copy()
    peer_ok = np.ones_like(nb_idx, dtype=bool)
    used_peer = np.zeros(n, bool)
    for f in ("res", "nonres"):
        t = fam == f
        pi, pd_ = knn(xy, donor & t, t, K)
        close = (pi >= 0) & (pd_ <= PEER_RADIUS_M)
        enough = close.sum(axis=1) >= PEER_MIN
        sel = t & enough
        peer_idx[sel], peer_ok[sel], used_peer[sel] = pi[sel], close[sel], True
    peer = lpsf - masked_median(lpsf, peer_idx, peer_ok)
    size_base = masked_median(lpsf - beta * la, peer_idx, peer_ok) + beta * la
    size = lpsf - size_base
    # Each baseline is z-scored against its OWN citywide spread (the size-adjusted one is far
    # tighter: assessors' land schedules are mostly a lot-size curve), then the least extreme z
    # wins, and only if all three agree in sign.
    zs, sigmas = [], []
    for v in (raw, peer, size):
        zv, _, sg = robust_z(v, donor)
        zs.append(zv)
        sigmas.append(sg)
    zst = np.vstack(zs)
    with np.errstate(invalid="ignore"):
        same_sign = np.all(zst > 0, axis=0) | np.all(zst < 0, axis=0)
    pick_ix = np.argmin(np.where(np.isfinite(zst), np.abs(zst), np.inf), axis=0)
    z_min = np.take_along_axis(zst, pick_ix[None, :], axis=0)[0]
    valid = np.isfinite(lpsf) & np.isfinite(nb_lpsf) & np.all(np.isfinite(zst), axis=0)
    z = np.where(valid, np.where(same_sign, np.clip(z_min, -Z_CAP, Z_CAP), 0.0), np.nan)
    # The dollar gap uses the least extreme log-ratio (the smallest gap any baseline implies).
    lrs = np.vstack([raw, peer, size])
    lr_small = np.take_along_axis(lrs, np.argmin(np.where(np.isfinite(lrs), np.abs(lrs), np.inf),
                                                 axis=0)[None, :], axis=0)[0]
    lr = np.where(valid & same_sign, lr_small, 0.0)
    ratio = psf / nb_psf
    adj_ratio = np.exp(lr)
    x_flag = [math.exp(Z_FLAG * s) for s in sigmas]

    print(f"  size elasticity b = {beta:.3f}; sigma of ln-ratio: plain {sigmas[0]:.3f}, same-use "
          f"{sigmas[1]:.3f}, size-adjusted {sigmas[2]:.3f} (|z|>={Z_FLAG:g} = {x_flag[0]:.1f}x / "
          f"{x_flag[1]:.1f}x / {x_flag[2]:.1f}x); same-use peers for {used_peer.mean():.0%} of parcels")

    # ── signals ──────────────────────────────────────────────────────────────
    sev = {k: np.zeros(n) for k in SIGNALS}
    stake = {k: np.zeros(n) for k in SIGNALS}
    reason: dict[str, dict[int, str]] = {k: {} for k in SIGNALS}
    z_sev = np.clip((np.abs(np.nan_to_num(z)) - Z_FLAG) / (Z_CAP - Z_FLAG), 0, 1)

    def adj_note(i: int) -> str:
        a, r = adj_ratio[i], ratio[i]
        if not np.isfinite(a) or abs(math.log(max(a, 1e-9))) > 0.8 * abs(math.log(max(r, 1e-9))):
            return ""
        a_txt = Fmt.times(a) if a >= 1 else f"1/{Fmt.times(1 / a)[:-1]}"
        return f"; still ~{a_txt} after allowing for lot size and use"

    for i in np.flatnonzero(z_sev > 0):
        if imputed[i]:
            key = "estimate_off"
        else:
            key = "land_psf_high" if z[i] > 0 else "land_psf_low"
        sev[key][i] = z_sev[i]
        exp_land = land[i] / adj_ratio[i]
        stake[key][i] = abs(land[i] - exp_land)
        r = ratio[i]
        rtxt = f"{Fmt.times(r)} its" if r >= 1 else f"only 1/{Fmt.times(1 / r)[:-1]} of its"
        what = "Estimated land" if imputed[i] else "Land"
        reason[key][i] = (f"{what} {fmt.rate(psf[i])} is {rtxt} neighbours' median "
                          f"({fmt.rate(nb_psf[i])}){adj_note(i)}")

    if not combined_only and c_impr:
        # zero / nominal land under a valued building
        zero = (land <= 0) & (impr > 0) & ~remnant
        nominal = (land > 0) & (impr >= NOMINAL_MIN_IMPR) & (land < NOMINAL_LAND_SHARE * total) & ~imputed
        for i in np.flatnonzero(zero | nominal):
            # The record's whole land/building split is suspect, so its total value is at stake.
            sev["zero_land"][i] = 1.0 if zero[i] else 0.6
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
        # building class with ~no building value
        not_built = np.array([bool(re.search(r"vacant|parking|common|park|open space|minor|agric|rural|"
                                             r"utility|other|transport|right.of.way|water", c)) or not c
                              for c in catl])
        be = ~not_built & (share <= BUILT_EMPTY_MAX_SHARE) & (land >= BUILT_EMPTY_MIN_LAND) & ~remnant
        for i in np.flatnonzero(be):
            sev["label_built_empty"][i] = 0.5
            stake["label_built_empty"][i] = land[i]
            ud = use_desc[i] or cat[i]
            mapped = f", so it maps as {refined[i]}" if refined[i] else ""
            has = (f"improvements are only {fmt.money(impr[i])}" if impr[i] > 0 else
                   "it carries no improvement value")
            reason["label_built_empty"][i] = f"Class is {ud} but {has} on {fmt.money(land[i])} of land{mapped}"

    # small lot carrying a big land value
    with np.errstate(divide="ignore", invalid="ignore"):
        lots_bought = np.where(nb_psf > 0, land / nb_psf / area, np.nan)
    sl = ((area < SLIVER_MAX_SQFT) & (area <= SLIVER_MAX_REL * nb_area) & (land >= SLIVER_MIN_LAND)
          & (np.nan_to_num(lots_bought) >= SLIVER_MIN_X))
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
        return np.minimum(1.0, np.log10(1 + np.maximum(x, 0) / STAKE_REF) / math.log10(1 + STAKE_NORM / STAKE_REF))

    keep = ~remnant if hide_remnants else np.ones(n, bool)
    weight = {k: np.full(n, spec["weight"]) for k, spec in SIGNALS.items()}
    # Unbuildable, steep, landlocked or present-use-valued VACANT land is legitimately cheap far
    # more often than built land, so far-below weighs less there.
    weight["land_psf_low"][fam == "vacant"] = W_LOW_VACANT
    prod = np.ones(n)
    for k in SIGNALS:
        prod *= 1 - weight[k] * sev[k] * V(stake[k])
    score = 100 * (1 - prod)
    flagged = (score > 0) & keep
    counts = {k: int(((sev[k] > 0) & keep).sum()) for k in SIGNALS}
    order = np.argsort(-np.where(flagged, score, -1), kind="stable")
    issue_ix = [int(i) for i in order[: min(args.top, int(flagged.sum()))]]
    issue_rank = {i: r + 1 for r, i in enumerate(issue_ix)}

    opp = np.isin(refl if (not combined_only and c_impr) else np.array([(r or "") for r in refined]),
                  OPPORTUNITY_LABELS) & keep
    opp_order = np.argsort(-np.where(opp, land, -1), kind="stable")
    opp_ix = [int(i) for i in opp_order[: min(args.top, int(opp.sum()))]]

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
        return {k: v for k, v in d.items() if v is not None}

    def issue_reasons(i: int) -> list[tuple[str, str]]:
        ks = sorted((k for k in SIGNALS if sev[k][i] > 0),
                    key=lambda k: -weight[k][i] * sev[k][i] * float(V(stake[k][i])))
        return [(k, reason[k][i]) for k in ks]

    issues = [item(i, r + 1, issue_reasons(i), True) for r, i in enumerate(issue_ix)]

    med_land = float(np.median(land[opp])) if opp.any() else 0.0
    opps = []
    for r, i in enumerate(opp_ix):
        rs: list[tuple[str, str]] = []
        lab = refl[i] if len(refl) else refined[i]
        if lab == "Vacant":
            rs.append(("vacant", f"Vacant: {fmt.money(land[i])} of land"
                                 + (f" with {fmt.money(impr[i])} of improvements" if impr[i] > 0 else
                                    " and no improvements")))
        elif lab == "Parking Lot":
            rs.append(("parking", f"Surface parking on {fmt.area(area[i])} of {fmt.rate(psf[i])} land"))
        else:
            share_txt = "under 1%" if impr_share[i] < 0.005 else f"only {impr_share[i]:.0%}"
            rs.append(("underdeveloped", f"Improvements are {share_txt} of its value "
                                         f"({fmt.money(impr[i])} on {fmt.money(land[i])} of land)"))
        if flagged[i]:
            rk = issue_rank.get(i)
            where = f" (#{rk} on that list)" if rk else ""
            rs.append(("check_data", f"Also a likely data issue{where}: "
                                     + (issue_reasons(i)[0][1] if issue_reasons(i) else "")))
        d = item(i, r + 1, rs, False)
        if flagged[i]:
            d["issue_score"] = round(float(score[i]), 1)
            d["issue_signals"] = [k for k, _ in issue_reasons(i)]
        opps.append(d)

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
                         "remnant slivers and estimated land), with same-use neighbours within "
                         f"{PEER_RADIUS_M / 1000:g} km, and with those neighbours' rate adjusted for lot size "
                         f"(elasticity {beta:.2f}). Each log-ratio is z-scored citywide with median/MAD; the "
                         f"least extreme of the three counts. Flags start at |z| = {Z_FLAG:g} (about "
                         f"{x_flag[0]:.1f}x off the plain neighbours) and saturate at {Z_CAP:g}."),
            "opportunities": "Parcels mapped as Vacant, Underdeveloped or Parking Lot, largest land value first.",
            "k": K, "z_flag": Z_FLAG, "z_cap": Z_CAP, "size_elasticity": round(beta, 3),
            "ln_ratio_sigma": {"plain": round(sigmas[0], 4), "same_use": round(sigmas[1], 4),
                               "size_adjusted": round(sigmas[2], 4)},
            "stake_ref": STAKE_REF, "stake_norm": STAKE_NORM,
            "weights": {k: v["weight"] for k, v in SIGNALS.items()},
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
                          "land_median": int(med_land), "items": opps},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if args.csv:
        fl = np.flatnonzero(flagged)
        audit = pd.DataFrame({
            "rank": [issue_rank.get(int(i)) for i in fl], "score": score[fl].round(2), "parcel_id": pid[fl],
            "category": cat[fl], "refined": refined[fl], "use_desc": use_desc[fl], "land": land[fl],
            "impr": impr[fl], "lot_sqft": area[fl].round(), "land_psf": psf[fl], "nbr_psf": nb_psf[fl],
            "z": z[fl], "z_plain": zst[0][fl], "z_same_use": zst[1][fl], "z_size": zst[2][fl],
            **{f"sev_{k}": sev[k][fl].round(3) for k in SIGNALS},
            **{f"stake_{k}": stake[k][fl].round() for k in SIGNALS},
            "reasons": [" | ".join(t for _, t in issue_reasons(int(i))) for i in fl],
        }).sort_values("score", ascending=False)
        audit.to_csv(args.csv, index=False, encoding="utf-8")
        print(f"Audit CSV: {args.csv} ({len(audit):,} flagged parcels)")

    # ── log ──────────────────────────────────────────────────────────────────
    print(f"\nRemnants: {int(remnant.sum())} likely_remnant parcels "
          f"{'hidden (hideRemnants) and left out' if hide_remnants else 'kept'}")
    print("Signal counts (parcels flagged, before the top-N cut):")
    for k, c in counts.items():
        print(f"  {k:<22} {c:>6,}   {SIGNALS[k]['label']}")
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
    print(f"\nOpportunities: {int(opp.sum()):,} eligible ({fmt.money(land[opp].sum())} land); top 5:")
    for it in opps[:5]:
        print(f"  #{it['rank']:<3} {it['parcel_id']}  {it.get('refined')}  {it.get('use_desc') or ''}  land "
              f"{fmt.money(it['land'])}  impr {fmt.money(it['impr'])}  {fmt.area(it.get('lot_sqft', 0))}")
    kb = out.stat().st_size / 1024
    print(f"\nWrote {out} ({kb:,.0f} KB; {len(issues)} issues, {len(opps)} opportunities)")


if __name__ == "__main__":
    main()
