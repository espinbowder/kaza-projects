"""Merge (dissolve) all areas of a project into one clean outline, for the map.

  1. every part is repaired (make_valid) and all parts are merged: overlapping and touching areas become one shape;
  2. gaps between neighbouring areas narrower than GAP_M are closed (buffer out by GAP_M/2, then back in);
  3. separate pieces and holes smaller than MIN_KM2 are removed (a project that is only a small site keeps its largest piece).

Only the map outline changes; the list of areas a project works in (and the WDA and country counts) is not affected.
Works in metres on an equal-area projection centred on KAZA. Needs Shapely 2 (installed by the GitHub workflow);
without it the outlines are used as they are.
"""
import math
import numpy as np

try:
    import shapely
    from shapely.geometry import shape, mapping, Polygon, MultiPolygon
    from shapely.ops import transform
    HAVE_SHAPELY = int(shapely.__version__.split('.')[0]) >= 2
except ImportError:
    HAVE_SHAPELY = False

R = 6371007.2
C = math.cos(math.radians(-17.0))          # standard parallel through the middle of KAZA


def _to_m(x, y, z=None):                    # lon/lat -> Lambert cylindrical equal-area (metres)
    x, y = np.asarray(x, float), np.asarray(y, float)
    return R * np.radians(x) * C, R * np.sin(np.radians(y)) / C


def _to_ll(x, y, z=None):                   # and back
    x, y = np.asarray(x, float), np.asarray(y, float)
    return np.degrees(x / (R * C)), np.degrees(np.arcsin(np.clip(y * C / R, -1.0, 1.0)))


def _polys(g):
    if g is None or g.is_empty: return []
    if g.geom_type == 'Polygon': return [g]
    if g.geom_type == 'MultiPolygon': return list(g.geoms)
    if hasattr(g, 'geoms'): return [p for x in g.geoms for p in _polys(x)]
    return []


def clean_outline(geoms, gap_m=250.0, min_km2=2.0, stats=None):
    """geoms: GeoJSON geometries in lon/lat. Returns (GeoJSON MultiPolygon or None, area in km2)."""
    parts = []
    for g in geoms:
        if not g: continue
        parts += _polys(shapely.make_valid(shape(g)))
    if not parts: return None, 0.0
    merged = shapely.union_all([transform(_to_m, p) for p in parts])
    n_before = len(_polys(merged))
    if gap_m:
        h = gap_m / 2.0
        merged = merged.buffer(h, quad_segs=4, join_style='mitre', mitre_limit=2.0).buffer(-h, quad_segs=4, join_style='mitre', mitre_limit=2.0)
        merged = shapely.make_valid(merged)
    min_m2 = min_km2 * 1e6
    keep, holes_removed = [], 0
    for p in _polys(merged):
        holes = [r for r in p.interiors if Polygon(r).area >= min_m2]
        holes_removed += len(p.interiors) - len(holes)
        q = Polygon(p.exterior, holes)
        if q.area >= min_m2: keep.append(q)
    if not keep and _polys(merged):           # a small site: keep its largest piece rather than losing it
        keep = [max(_polys(merged), key=lambda p: p.area)]
    if stats is not None:
        stats['projects'] = stats.get('projects', 0) + 1
        stats['pieces_merged'] = stats.get('pieces_merged', 0) + max(len(parts) - n_before, 0)
        stats['pieces_removed'] = stats.get('pieces_removed', 0) + max(len(_polys(merged)) - len(keep), 0)
        stats['holes_removed'] = stats.get('holes_removed', 0) + holes_removed
    if not keep: return None, 0.0
    area_km2 = sum(p.area for p in keep) / 1e6
    out = MultiPolygon([transform(_to_ll, p) for p in keep])
    return mapping(out), round(area_km2, 1)
