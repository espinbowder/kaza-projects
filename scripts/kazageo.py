"""Small geometry toolkit for the KAZA projects pipeline (needs only numpy).

Areas are measured on a fixed 1 km equal-area grid that covers KAZA and its surroundings.
Every polygon is turned into a grid mask (scanline fill), so overlaps and shares are
simple counts of grid cells. That is accurate to well under 1% for areas larger than ~50 km2.
"""
import json, math, re
import numpy as np

R = 6371007.2
PHI0 = math.radians(-17.0)                      # standard parallel through the middle of KAZA
LON0, LON1, LAT0, LAT1 = 16.5, 31.5, -23.5, -11.0  # grid extent (KAZA plus a margin)


def to_ea(lonlat):
    """lon/lat (degrees) -> Lambert cylindrical equal-area (metres)."""
    a = np.asarray(lonlat, float)
    return np.c_[R * np.radians(a[:, 0]) * math.cos(PHI0), R * np.sin(np.radians(a[:, 1])) / math.cos(PHI0)]


class Grid:
    def __init__(self, step_km=1.0):
        self.step = step_km * 1000.0
        (self.x0, self.y0), (x1, y1) = to_ea([[LON0, LAT0], [LON1, LAT1]])
        self.nx = int((x1 - self.x0) // self.step) + 1
        self.ny = int((y1 - self.y0) // self.step) + 1
        self.cell_km2 = (self.step / 1000.0) ** 2

    def empty(self):
        return np.zeros((self.ny, self.nx), bool)

    def mask(self, rings):
        """Even-odd fill of a list of lon/lat rings (outer rings and holes together) -> boolean grid."""
        m = self.empty()
        rings = [to_ea(r) for r in rings if len(r) >= 4]
        if not rings: return m
        allp = np.vstack(rings)
        r0 = max(int((allp[:, 1].min() - self.y0) / self.step - 0.5), 0)
        r1 = min(int((allp[:, 1].max() - self.y0) / self.step + 0.5) + 1, self.ny)
        if r1 <= r0: return m
        ax = np.concatenate([r[:-1, 0] for r in rings]); ay = np.concatenate([r[:-1, 1] for r in rings])
        bx = np.concatenate([r[1:, 0] for r in rings]); by = np.concatenate([r[1:, 1] for r in rings])
        for row in range(r0, r1):
            y = self.y0 + (row + 0.5) * self.step
            hit = ((ay <= y) & (by > y)) | ((by <= y) & (ay > y))
            if not hit.any(): continue
            xs = ax[hit] + (y - ay[hit]) * (bx[hit] - ax[hit]) / (by[hit] - ay[hit])
            idx = np.clip(np.ceil((xs - self.x0) / self.step - 0.5).astype(int), 0, self.nx)
            toggles = np.bincount(idx, minlength=self.nx + 1)[:self.nx]
            m[row] = (np.cumsum(toggles) % 2).astype(bool)
        return m


# ---------- GeoJSON helpers ----------
def rings_of(geom):
    """GeoJSON Polygon/MultiPolygon -> flat list of rings (lists of [lon, lat])."""
    if not geom: return []
    if geom['type'] == 'Polygon': return [r for r in geom['coordinates']]
    if geom['type'] == 'MultiPolygon': return [r for p in geom['coordinates'] for r in p]
    if geom['type'] == 'GeometryCollection': return [r for g in geom['geometries'] for r in rings_of(g)]
    return []


def polygons_of(geom):
    if not geom: return []
    if geom['type'] == 'Polygon': return [geom['coordinates']]
    if geom['type'] == 'MultiPolygon': return list(geom['coordinates'])
    if geom['type'] == 'GeometryCollection': return [p for g in geom['geometries'] for p in polygons_of(g)]
    return []


def simplify_ring(pts, tol):
    pts = np.asarray(pts, float)
    if len(pts) < 5: return pts
    keep = np.zeros(len(pts), bool); keep[0] = keep[-1] = True; stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1: continue
        p, q = pts[a], pts[b]; seg = q - p; L = math.hypot(*seg); v = pts[a + 1:b] - p
        d = np.abs(seg[0] * v[:, 1] - seg[1] * v[:, 0]) / L if L > 0 else np.hypot(v[:, 0], v[:, 1])
        i = int(np.argmax(d))
        if d[i] > tol: k = a + 1 + i; keep[k] = True; stack += [(a, k), (k, b)]
    out = pts[keep]
    return out if len(out) >= 4 else pts


def simplify(geom, tol=0.005, digits=4):
    """Simplify a (Multi)Polygon for display; drops parts smaller than the tolerance."""
    polys = []
    for poly in polygons_of(geom):
        outer = simplify_ring(poly[0], tol)
        if len(outer) < 4: continue
        x, y = outer[:, 0], outer[:, 1]
        if abs(0.5 * (np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) < tol * tol and polys: continue
        holes = [np.round(simplify_ring(h, tol), digits).tolist() for h in poly[1:] if len(h) >= 4]
        polys.append([np.round(outer, digits).tolist()] + holes)
    return {'type': 'MultiPolygon', 'coordinates': polys} if polys else None


def merge(geoms):
    """Combine several geometries into one MultiPolygon (parts are kept, not dissolved)."""
    polys = [p for g in geoms for p in polygons_of(g)]
    return {'type': 'MultiPolygon', 'coordinates': polys} if polys else None


# ---------- reading shapes that people submit ----------
def parse_odk_geoshape(text):
    """ODK/Kobo geoshape 'lat lon alt acc;lat lon alt acc;...' -> GeoJSON Polygon."""
    pts = []
    for part in (text or '').split(';'):
        v = part.strip().split()
        if len(v) >= 2: pts.append([float(v[1]), float(v[0])])
    if len(pts) < 3: return None
    if pts[0] != pts[-1]: pts.append(pts[0])
    return {'type': 'Polygon', 'coordinates': [pts]}


def read_shape_file(name, data):
    """Uploaded GeoJSON or KML (bytes) -> (geometry, properties). Zipped shapefiles are not read here."""
    low = name.lower()
    if low.endswith(('.geojson', '.json')):
        g = json.loads(data.decode('utf-8-sig'))
        feats = g['features'] if g.get('type') == 'FeatureCollection' else ([g] if g.get('type') == 'Feature' else [{'geometry': g, 'properties': {}}])
        return merge([f.get('geometry') for f in feats]), (feats[0].get('properties') or {}) if feats else {}
    if low.endswith('.kml'):
        txt = data.decode('utf-8', 'ignore'); polys = []
        for block in re.findall(r'<outerBoundaryIs>.*?<coordinates>(.*?)</coordinates>', txt, re.S):
            pts = [[float(c.split(',')[0]), float(c.split(',')[1])] for c in block.split() if ',' in c]
            if len(pts) >= 4: polys.append([pts])
        return ({'type': 'MultiPolygon', 'coordinates': polys} if polys else None), {}
    return None, {}
